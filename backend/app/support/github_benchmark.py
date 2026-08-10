from __future__ import annotations

import json
import math
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import Normalizer

from app.models.domain import DocumentType, EvidenceDocument, SearchHit
from app.services.retrieval import EvidenceReranker, HybridRetriever, reciprocal_rank_fusion

DATASET_PATH = Path(__file__).resolve().parents[2] / "benchmarks" / "github_issue_pr_v1.jsonl"


@dataclass(slots=True)
class GitHubBenchmarkCase:
    id: str
    repo: str
    query: str
    expected_document_id: str
    issue_url: str
    pr_url: str


class DenseLSAIndex:
    """Offline dense baseline built from TF-IDF followed by truncated SVD.

    This is deliberately named LSA rather than "embedding": it is dense and semantic-ish,
    but it is not a neural sentence embedding model.
    """

    def __init__(self, documents: list[EvidenceDocument], max_components: int = 64):
        self.documents = documents
        self.vectorizer = TfidfVectorizer(
            analyzer="word",
            ngram_range=(1, 2),
            min_df=1,
            sublinear_tf=True,
            max_features=30_000,
            strip_accents="unicode",
        )
        corpus = [document.searchable_text for document in documents]
        if not corpus:
            self.matrix = None
            self.svd = None
            self.normalizer = None
            return

        sparse_matrix = self.vectorizer.fit_transform(corpus)
        components = min(
            max_components,
            max(1, sparse_matrix.shape[0] - 1),
            max(1, sparse_matrix.shape[1] - 1),
        )
        self.svd = TruncatedSVD(n_components=components, random_state=42)
        self.normalizer = Normalizer(copy=False)
        self.matrix = self.normalizer.fit_transform(self.svd.fit_transform(sparse_matrix))

    def score(self, query: str) -> list[float]:
        if self.matrix is None or self.svd is None or self.normalizer is None:
            return []
        sparse_query = self.vectorizer.transform([query])
        dense_query = self.normalizer.transform(self.svd.transform(sparse_query))[0]
        return (self.matrix @ dense_query).astype(float).tolist()


def _load_rows(dataset_path: Path = DATASET_PATH) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in dataset_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _document_id(repo: str, pr_number: int) -> str:
    return f"{repo}:pr:{pr_number}"


def load_github_benchmark(
    dataset_path: Path = DATASET_PATH,
) -> tuple[list[EvidenceDocument], list[GitHubBenchmarkCase]]:
    rows = _load_rows(dataset_path)
    documents: list[EvidenceDocument] = []
    cases: list[GitHubBenchmarkCase] = []

    for row in rows:
        document_id = _document_id(row["repo"], row["pr_number"])
        documents.append(
            EvidenceDocument(
                id=document_id,
                repo=row["repo"],
                kind=DocumentType.PULL_REQUEST,
                title=row["pr_title"],
                body=row.get("pr_body", ""),
                url=row["pr_url"],
                number=row["pr_number"],
                state="closed",
                metadata={"merged_at": True},
            )
        )
        cases.append(
            GitHubBenchmarkCase(
                id=row["id"],
                repo=row["repo"],
                query="\n".join(
                    part for part in (row["issue_title"], row.get("issue_body", "")) if part
                ),
                expected_document_id=document_id,
                issue_url=row["issue_url"],
                pr_url=row["pr_url"],
            )
        )

    return documents, cases


def _rank_for_document(hits: list[SearchHit], expected_document_id: str) -> int | None:
    for rank, hit in enumerate(hits, start=1):
        if hit.document.id == expected_document_id:
            return rank
    return None


def _hits_from_scores(
    documents: list[EvidenceDocument],
    scores: list[float],
    *,
    bm25_scores: list[float] | None = None,
    vector_scores: list[float] | None = None,
) -> list[SearchHit]:
    order = sorted(range(len(documents)), key=lambda index: scores[index], reverse=True)
    return [
        SearchHit(
            document=documents[index],
            score=float(scores[index]),
            bm25_score=float(bm25_scores[index]) if bm25_scores is not None else 0.0,
            vector_score=float(vector_scores[index]) if vector_scores is not None else 0.0,
        )
        for index in order
    ]


def _metrics(ranks: list[int | None], candidate_counts: list[int]) -> dict[str, float]:
    count = max(len(ranks), 1)

    def recall_at(k: int) -> float:
        return sum(rank is not None and rank <= k for rank in ranks) / count

    reciprocal_rank = sum(1 / rank if rank is not None else 0.0 for rank in ranks) / count
    ndcg_at_5 = sum(
        1 / math.log2(rank + 1) if rank is not None and rank <= 5 else 0.0 for rank in ranks
    ) / count
    mean_rank = sum(
        rank if rank is not None else candidates + 1
        for rank, candidates in zip(ranks, candidate_counts, strict=True)
    ) / count

    return {
        "recall@1": round(recall_at(1), 4),
        "recall@3": round(recall_at(3), 4),
        "recall@5": round(recall_at(5), 4),
        "mrr": round(reciprocal_rank, 4),
        "ndcg@5": round(ndcg_at_5, 4),
        "mean_rank": round(mean_rank, 4),
    }


def _evaluate_group(
    documents: list[EvidenceDocument],
    cases: list[GitHubBenchmarkCase],
) -> dict[str, list[int | None]]:
    retriever = HybridRetriever(documents)
    dense_lsa = DenseLSAIndex(documents)
    reranker = EvidenceReranker()
    ranks: dict[str, list[int | None]] = defaultdict(list)

    for case in cases:
        top_k = len(documents)
        bm25_hits = retriever.search(case.query, top_k=top_k, variant="bm25")
        hybrid_hits = retriever.search(case.query, top_k=top_k, variant="hybrid")

        lsa_scores = dense_lsa.score(case.query)
        lsa_hits = _hits_from_scores(documents, lsa_scores)

        bm25_scores = retriever.bm25.score(case.query)
        vector_scores = retriever.vector.score(case.query)
        bm25_lsa_scores = reciprocal_rank_fusion(bm25_scores, lsa_scores)
        bm25_lsa_hits = _hits_from_scores(
            documents,
            bm25_lsa_scores,
            bm25_scores=bm25_scores,
            vector_scores=lsa_scores,
        )

        reranked_hits = reranker.rerank(case.query, hybrid_hits, top_k=top_k)

        variants = {
            "bm25": bm25_hits,
            "hybrid_char": hybrid_hits,
            "dense_lsa": lsa_hits,
            "hybrid_bm25_lsa": bm25_lsa_hits,
            "hybrid_char_rerank": reranked_hits,
        }
        for variant, hits in variants.items():
            ranks[variant].append(_rank_for_document(hits, case.expected_document_id))

    return ranks


def run_github_benchmark(
    *,
    scope: Literal["repo", "global"] = "repo",
    dataset_path: Path = DATASET_PATH,
) -> dict[str, Any]:
    documents, cases = load_github_benchmark(dataset_path)
    by_repo_documents: dict[str, list[EvidenceDocument]] = defaultdict(list)
    by_repo_cases: dict[str, list[GitHubBenchmarkCase]] = defaultdict(list)

    if scope == "repo":
        for document in documents:
            by_repo_documents[document.repo].append(document)
        for case in cases:
            by_repo_cases[case.repo].append(case)
        groups = [
            (by_repo_documents[repo], by_repo_cases[repo])
            for repo in sorted(by_repo_documents)
        ]
    else:
        groups = [(documents, cases)]

    all_ranks: dict[str, list[int | None]] = defaultdict(list)
    candidate_counts: list[int] = []
    for group_documents, group_cases in groups:
        group_ranks = _evaluate_group(group_documents, group_cases)
        candidate_counts.extend([len(group_documents)] * len(group_cases))
        for variant, ranks in group_ranks.items():
            all_ranks[variant].extend(ranks)

    labels = {
        "bm25": "BM25",
        "hybrid_char": "BM25 + char TF-IDF RRF",
        "dense_lsa": "Dense LSA baseline",
        "hybrid_bm25_lsa": "BM25 + Dense LSA RRF",
        "hybrid_char_rerank": "Hybrid + evidence reranker",
    }
    variants = [
        {"id": variant, "label": labels[variant], **_metrics(ranks, candidate_counts)}
        for variant, ranks in all_ranks.items()
    ]

    return {
        "dataset": "github_issue_pr_v1",
        "scope": scope,
        "cases": len(cases),
        "repositories": sorted({case.repo for case in cases}),
        "ground_truth": "merged PR with explicit Fixes/Closes/Resolves relation",
        "variants": variants,
    }
