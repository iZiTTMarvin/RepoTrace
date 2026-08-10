from __future__ import annotations

from dataclasses import dataclass

from app.models.domain import EvidenceDocument
from app.services.retrieval import EvidenceReranker, HybridRetriever


@dataclass(slots=True)
class EvalCase:
    id: str
    query: str
    expected_document_ids: set[str]


def evaluate_retrieval(
    documents: list[EvidenceDocument],
    cases: list[EvalCase],
    variant: str,
    top_k: int = 5,
) -> dict[str, float]:
    retriever = HybridRetriever(documents)
    reranker = EvidenceReranker()
    hits_at_k = 0
    reciprocal_ranks: list[float] = []

    for case in cases:
        candidates = retriever.search(case.query, top_k=max(12, top_k), variant=variant)
        if variant == "hybrid_rerank":
            candidates = reranker.rerank(case.query, candidates, top_k=top_k)
        else:
            candidates = candidates[:top_k]

        found_rank = None
        for rank, hit in enumerate(candidates, start=1):
            if hit.document.id in case.expected_document_ids:
                found_rank = rank
                break
        if found_rank is not None:
            hits_at_k += 1
            reciprocal_ranks.append(1 / found_rank)
        else:
            reciprocal_ranks.append(0.0)

    n = max(len(cases), 1)
    return {
        f"hit_rate@{top_k}": round(hits_at_k / n, 4),
        "mrr": round(sum(reciprocal_ranks) / n, 4),
    }
