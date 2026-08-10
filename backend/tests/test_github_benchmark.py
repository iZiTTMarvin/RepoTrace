from __future__ import annotations

from app.support.github_benchmark import load_github_benchmark, run_github_benchmark
from scripts.build_github_benchmark import clean_markdown, extract_issue_numbers


def test_frozen_github_dataset_is_real_and_nontrivial() -> None:
    documents, cases = load_github_benchmark()
    assert len(cases) >= 30
    assert len(documents) == len(cases)
    assert len({case.id for case in cases}) == len(cases)
    assert len({(case.repo, case.issue_url) for case in cases}) == len(cases)
    assert len({(case.repo, case.pr_url) for case in cases}) == len(cases)
    assert all(case.issue_url.startswith("https://github.com/") for case in cases)
    assert all(case.pr_url.startswith("https://github.com/") for case in cases)


def test_real_benchmark_has_reproducible_metrics() -> None:
    result = run_github_benchmark(scope="repo")
    variants = {row["id"]: row for row in result["variants"]}
    assert result["cases"] >= 30
    assert variants["bm25"]["recall@5"] >= 0.6
    assert variants["hybrid_char_rerank"]["mrr"] >= variants["hybrid_char"]["mrr"]


def test_extract_issue_numbers_only_keeps_same_repo_closures() -> None:
    body = "Fixes #12\nCloses https://github.com/acme/demo/issues/13\nResolves other/repo#14"
    assert extract_issue_numbers(body, "acme/demo") == [
        (12, "Fixes #12"),
        (13, "Closes https://github.com/acme/demo/issues/13"),
    ]


def test_clean_markdown_removes_relation_leakage() -> None:
    text = "Fixes #42\n\n## Change\nHandle the parser crash.\n<!-- template -->"
    cleaned = clean_markdown(text, remove_relations=True)
    assert "#42" not in cleaned
    assert "parser crash" in cleaned
