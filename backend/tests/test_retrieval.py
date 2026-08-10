from app.services.evaluation import evaluate_retrieval
from app.support.demo_benchmark import demo_cases, demo_documents


def test_hybrid_rerank_reaches_expected_demo_quality():
    metrics = evaluate_retrieval(
        demo_documents(), demo_cases(), variant="hybrid_rerank", top_k=5
    )
    assert metrics["hit_rate@5"] >= 0.95
    assert metrics["mrr"] >= 0.75


def test_hybrid_does_not_regress_hit_rate_against_bm25():
    documents = demo_documents()
    cases = demo_cases()
    baseline = evaluate_retrieval(documents, cases, variant="bm25", top_k=5)
    hybrid = evaluate_retrieval(documents, cases, variant="hybrid", top_k=5)
    assert hybrid["hit_rate@5"] >= baseline["hit_rate@5"]
