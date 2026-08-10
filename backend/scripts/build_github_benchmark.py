from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any

import httpx

DEFAULT_REPOS = ("langchain-ai/langchain", "pydantic/pydantic")
RELATION_RE = re.compile(
    r"(?im)\b(?P<verb>fix(?:e[sd])?|close[sd]?|resolve[sd]?)\s+"
    r"(?:(?:https://github\.com/(?P<owner>[\w.-]+)/(?P<repo>[\w.-]+)/issues/)?#?)(?P<number>\d+)"
)
HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
MARKDOWN_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
HTML_IMAGE_RE = re.compile(r"<img\b[^>]*>", re.I)
SYSTEM_INFO_RE = re.compile(r"(?ims)^#{1,4}\s*(?:System Info|Python, Pydantic & OS Version).*\Z")


def extract_issue_numbers(body: str, repo_full_name: str) -> list[tuple[int, str]]:
    owner, repo = repo_full_name.split("/", 1)
    found: list[tuple[int, str]] = []
    for match in RELATION_RE.finditer(body or ""):
        linked_owner = match.group("owner")
        linked_repo = match.group("repo")
        if linked_owner and (linked_owner.lower(), linked_repo.lower()) != (owner.lower(), repo.lower()):
            continue
        evidence = match.group(0).strip()
        found.append((int(match.group("number")), evidence))
    return found


def clean_markdown(text: str, *, remove_relations: bool = False) -> str:
    value = HTML_COMMENT_RE.sub(" ", text or "")
    value = MARKDOWN_IMAGE_RE.sub(" ", value)
    value = HTML_IMAGE_RE.sub(" ", value)
    value = SYSTEM_INFO_RE.sub(" ", value)
    if remove_relations:
        value = RELATION_RE.sub(" ", value)
    value = re.sub(r"(?m)^\s*[-*]\s*\[[ xX]\].*$", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


class GitHubClient:
    def __init__(self, token: str | None):
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self.client = httpx.Client(base_url="https://api.github.com", headers=headers, timeout=30)

    def get(self, path: str, **params: Any) -> Any:
        response = self.client.get(path, params=params)
        response.raise_for_status()
        return response.json()


def collect_repo(client: GitHubClient, repo: str, limit: int) -> list[dict[str, Any]]:
    candidates: dict[int, dict[str, Any]] = {}
    for keyword in ("fixes", "closes", "resolves"):
        result = client.get(
            "/search/issues",
            q=f'repo:{repo} is:pr is:merged {keyword}',
            per_page=min(100, max(limit * 2, 30)),
            sort="updated",
            order="desc",
        )
        for item in result.get("items", []):
            candidates[item["number"]] = item

    rows: list[dict[str, Any]] = []
    for pr_number in sorted(candidates, reverse=True):
        if len(rows) >= limit:
            break
        pr = client.get(f"/repos/{repo}/pulls/{pr_number}")
        if not pr.get("merged_at"):
            continue
        author = (pr.get("user") or {}).get("login", "")
        if author.endswith("[bot]") or "dependabot" in author.lower() or "renovate" in author.lower():
            continue
        if re.search(r"\b(?:deps?|dependencies|bump)\b", pr.get("title", ""), re.I):
            continue

        relations = extract_issue_numbers(pr.get("body") or "", repo)
        for issue_number, evidence in relations:
            issue = client.get(f"/repos/{repo}/issues/{issue_number}")
            if "pull_request" in issue:
                continue
            rows.append(
                {
                    "id": f"{repo.split('/')[-1]}-{issue_number}",
                    "repo": repo,
                    "issue_number": issue_number,
                    "issue_url": issue["html_url"],
                    "issue_title": issue["title"],
                    "issue_body": clean_markdown(issue.get("body") or "")[:4000],
                    "pr_number": pr_number,
                    "pr_url": pr["html_url"],
                    "pr_title": pr["title"],
                    "pr_body": clean_markdown(pr.get("body") or "", remove_relations=True)[:3000],
                    "relation": "explicit_closure",
                    "relation_evidence": evidence,
                }
            )
            if len(rows) >= limit:
                break
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a real GitHub Issue -> merged PR benchmark snapshot")
    parser.add_argument("--repo", action="append", dest="repos", help="owner/repo; repeatable")
    parser.add_argument("--limit-per-repo", type=int, default=50)
    parser.add_argument("--output", type=Path, default=Path("benchmarks/github_issue_pr_v1.jsonl"))
    args = parser.parse_args()

    token = os.getenv("REPO_TRACE_GITHUB_TOKEN") or os.getenv("GITHUB_TOKEN")
    client = GitHubClient(token)
    rows: list[dict[str, Any]] = []
    for repo in args.repos or DEFAULT_REPOS:
        rows.extend(collect_repo(client, repo, args.limit_per_repo))

    deduped = {(row["repo"], row["issue_number"], row["pr_number"]): row for row in rows}
    by_issue: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for row in deduped.values():
        by_issue.setdefault((row["repo"], row["issue_number"]), []).append(row)

    # The evaluator currently assumes one definitive PR per Issue. Skip ambiguous issues
    # that have multiple merged PRs explicitly claiming the same closure relation.
    unambiguous = [group[0] for group in by_issue.values() if len(group) == 1]
    ordered = sorted(unambiguous, key=lambda row: (row["repo"], row["issue_number"]))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in ordered) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {len(ordered)} verified pairs to {args.output}")


if __name__ == "__main__":
    main()
