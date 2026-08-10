from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import quote

import httpx

from app.core.config import Settings
from app.models.domain import DocumentType, EvidenceDocument


_REPO_PATTERN = re.compile(r"^(?:https?://github\.com/)?([\w.-]+)/([\w.-]+?)(?:\.git)?/?$")


@dataclass(slots=True)
class GitHubImportResult:
    repository: str
    metadata: dict
    documents: list[EvidenceDocument]


class GitHubClient:
    def __init__(self, settings: Settings):
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "RepoTrace/0.1",
        }
        if settings.github_token:
            headers["Authorization"] = f"Bearer {settings.github_token}"
        self.settings = settings
        self.client = httpx.Client(
            base_url="https://api.github.com",
            headers=headers,
            timeout=30.0,
            follow_redirects=True,
        )

    @staticmethod
    def normalize_repository(value: str) -> str:
        match = _REPO_PATTERN.match(value.strip())
        if not match:
            raise ValueError("仓库格式应为 owner/repo 或完整 GitHub URL")
        return f"{match.group(1)}/{match.group(2)}"

    def import_repository(self, value: str) -> GitHubImportResult:
        repo = self.normalize_repository(value)
        metadata = self._get(f"/repos/{repo}")
        documents: list[EvidenceDocument] = []
        documents.extend(self._fetch_issues(repo))
        documents.extend(self._fetch_pulls(repo))
        documents.extend(self._fetch_commits(repo))
        documents.extend(self._fetch_docs(repo, metadata.get("default_branch", "main")))
        return GitHubImportResult(repository=repo, metadata=metadata, documents=documents)

    def _fetch_issues(self, repo: str) -> list[EvidenceDocument]:
        items = self._paged(
            f"/repos/{repo}/issues",
            limit=self.settings.github_max_issues,
            params={"state": "all", "sort": "updated", "direction": "desc"},
        )
        documents = []
        for item in items:
            if "pull_request" in item:
                continue
            labels = [label.get("name", "") for label in item.get("labels", [])]
            documents.append(
                EvidenceDocument(
                    id=f"issue:{repo}:{item['number']}",
                    repo=repo,
                    kind=DocumentType.ISSUE,
                    title=item.get("title") or "",
                    body=item.get("body") or "",
                    url=item.get("html_url") or "",
                    number=item.get("number"),
                    state=item.get("state"),
                    metadata={
                        "labels": " ".join(labels),
                        "comments": item.get("comments", 0),
                        "created_at": item.get("created_at"),
                        "updated_at": item.get("updated_at"),
                    },
                )
            )
        return documents

    def _fetch_pulls(self, repo: str) -> list[EvidenceDocument]:
        items = self._paged(
            f"/repos/{repo}/pulls",
            limit=self.settings.github_max_pulls,
            params={"state": "all", "sort": "updated", "direction": "desc"},
        )
        return [
            EvidenceDocument(
                id=f"pr:{repo}:{item['number']}",
                repo=repo,
                kind=DocumentType.PULL_REQUEST,
                title=item.get("title") or "",
                body=item.get("body") or "",
                url=item.get("html_url") or "",
                number=item.get("number"),
                state=item.get("state"),
                metadata={
                    "merged_at": item.get("merged_at"),
                    "head": item.get("head", {}).get("ref"),
                    "base": item.get("base", {}).get("ref"),
                    "created_at": item.get("created_at"),
                    "updated_at": item.get("updated_at"),
                },
            )
            for item in items
        ]

    def _fetch_commits(self, repo: str) -> list[EvidenceDocument]:
        items = self._paged(
            f"/repos/{repo}/commits",
            limit=self.settings.github_max_commits,
            params={},
        )
        documents = []
        for item in items:
            commit = item.get("commit", {})
            message = commit.get("message") or ""
            title = message.splitlines()[0] if message else item.get("sha", "")[:12]
            documents.append(
                EvidenceDocument(
                    id=f"commit:{repo}:{item.get('sha')}",
                    repo=repo,
                    kind=DocumentType.COMMIT,
                    title=title,
                    body=message,
                    url=item.get("html_url") or "",
                    metadata={
                        "sha": item.get("sha"),
                        "author": commit.get("author", {}).get("name"),
                        "date": commit.get("author", {}).get("date"),
                    },
                )
            )
        return documents

    def _fetch_docs(self, repo: str, branch: str) -> list[EvidenceDocument]:
        docs: list[EvidenceDocument] = []
        for path in ["README.md", "README.zh-CN.md", "README_CN.md"]:
            content = self._try_content(repo, path, branch)
            if content:
                docs.append(self._doc_from_content(repo, path, content, branch))
                break

        try:
            tree = self._get(f"/repos/{repo}/git/trees/{quote(branch, safe='')}", params={"recursive": "1"})
        except httpx.HTTPStatusError:
            return docs

        candidates = [
            item["path"]
            for item in tree.get("tree", [])
            if item.get("type") == "blob"
            and item.get("path", "").lower().startswith(("docs/", "doc/"))
            and item.get("path", "").lower().endswith((".md", ".mdx", ".txt"))
        ][: self.settings.github_max_docs]
        for path in candidates:
            content = self._try_content(repo, path, branch)
            if content:
                docs.append(self._doc_from_content(repo, path, content, branch))
        return docs

    def _doc_from_content(self, repo: str, path: str, content: str, branch: str) -> EvidenceDocument:
        return EvidenceDocument(
            id=f"doc:{repo}:{path}",
            repo=repo,
            kind=DocumentType.DOC,
            title=path,
            body=content,
            url=f"https://github.com/{repo}/blob/{branch}/{path}",
            metadata={"path": path},
        )

    def _try_content(self, repo: str, path: str, branch: str) -> str | None:
        try:
            response = self.client.get(
                f"/repos/{repo}/contents/{quote(path, safe='/')}",
                params={"ref": branch},
                headers={"Accept": "application/vnd.github.raw+json"},
            )
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return response.text[:200_000]
        except httpx.HTTPError:
            return None

    def _get(self, path: str, params: dict | None = None) -> dict:
        response = self.client.get(path, params=params)
        response.raise_for_status()
        return response.json()

    def _paged(self, path: str, limit: int, params: dict) -> list[dict]:
        results: list[dict] = []
        page = 1
        while len(results) < limit:
            requested = min(100, limit - len(results))
            response = self.client.get(
                path,
                params={**params, "per_page": requested, "page": page},
            )
            response.raise_for_status()
            batch = response.json()
            if not batch:
                break
            results.extend(batch)
            if len(batch) < requested:
                break
            page += 1
        return results[:limit]
