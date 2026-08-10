from __future__ import annotations

import re
import uuid
from typing import TypedDict

from app.core.config import Settings
from app.models.domain import EvidenceOut, InvestigationOut, SearchHit
from app.services.llm import OpenAICompatibleLLM
from app.services.retrieval import EvidenceReranker, HybridRetriever
from app.services.tracing import LangfuseExporter, LocalTrace
from app.storage.sqlite import SQLiteStore


class InvestigationState(TypedDict, total=False):
    repository: str
    question: str
    hits: list[SearchHit]
    answer: str
    used_llm: bool
    confidence: str
    warning: str | None


class InvestigationService:
    def __init__(self, store: SQLiteStore, settings: Settings):
        self.store = store
        self.settings = settings
        self.reranker = EvidenceReranker()
        self.llm = OpenAICompatibleLLM(settings)
        self.langfuse = LangfuseExporter(settings.langfuse_enabled)

    def run(self, repository: str, question: str) -> InvestigationOut:
        documents = self.store.list_documents(repository)
        if not documents:
            raise ValueError("仓库还没有导入，请先建立索引")

        local_trace = LocalTrace()
        state: InvestigationState = {"repository": repository, "question": question}

        with self.langfuse.trace(
            "repotrace-investigation",
            {"repository": repository, "question": question},
        ) as external_trace:
            graph = self._build_graph(local_trace, documents)
            state = graph.invoke(state)
            if external_trace is not None:
                try:
                    external_trace.update(output={"confidence": state.get("confidence")})
                except Exception:
                    pass

        hits = state.get("hits", [])
        evidence = [
            EvidenceOut(
                id=hit.document.id,
                kind=hit.document.kind,
                title=hit.document.title,
                url=hit.document.url,
                number=hit.document.number,
                score=round(hit.score, 4),
                reasons=hit.reasons,
                excerpt=" ".join(hit.document.body.split())[:360],
            )
            for hit in hits
        ]
        result = InvestigationOut(
            id=str(uuid.uuid4()),
            repository=repository,
            question=question,
            answer=state.get("answer", ""),
            confidence=state.get("confidence", "low"),
            evidence=evidence,
            trace=local_trace.steps,
            used_llm=state.get("used_llm", False),
        )
        self.store.save_investigation(result.model_dump(mode="json"))
        return result

    def _build_graph(self, trace: LocalTrace, documents):
        service = self

        def retrieve(state: InvestigationState) -> dict:
            with trace.step("hybrid_retrieval", {"documents": len(documents)}) as record:
                retriever = HybridRetriever(documents)
                hits = retriever.search(
                    state["question"], top_k=service.settings.retrieval_top_k, variant="hybrid"
                )
                record["output"] = {"hits": len(hits)}
                return {"hits": hits}

        def rerank(state: InvestigationState) -> dict:
            with trace.step("evidence_rerank", {"hits": len(state.get("hits", []))}) as record:
                hits = service.reranker.rerank(
                    state["question"], state.get("hits", []), service.settings.rerank_top_k
                )
                record["output"] = {"hits": len(hits)}
                return {"hits": hits}

        def synthesize(state: InvestigationState) -> dict:
            with trace.step("answer_synthesis", {"evidence": len(state.get("hits", []))}) as record:
                result = service.llm.answer(state["question"], state.get("hits", []))
                record["output"] = {
                    "used_llm": result.used_llm,
                    "usage": result.usage,
                    "warning": result.warning,
                }
                return {
                    "answer": result.answer,
                    "used_llm": result.used_llm,
                    "warning": result.warning,
                }

        def verify(state: InvestigationState) -> dict:
            with trace.step("evidence_check") as record:
                hits = state.get("hits", [])
                answer = state.get("answer", "")
                citation_count = len(set(re.findall(r"\[E\d+\]", answer)))
                if not hits:
                    confidence = "low"
                elif state.get("used_llm") and citation_count >= 2:
                    confidence = "high"
                elif hits[0].score >= 0.45:
                    confidence = "medium"
                else:
                    confidence = "low"
                record["output"] = {"citations": citation_count, "confidence": confidence}
                return {"confidence": confidence}

        return _compile_graph(retrieve, rerank, synthesize, verify)


class _SequentialGraph:
    def __init__(self, nodes):
        self.nodes = nodes

    def invoke(self, state: InvestigationState) -> InvestigationState:
        current = dict(state)
        for node in self.nodes:
            current.update(node(current))
        return current


def _compile_graph(*nodes):
    """Use LangGraph when installed; keep a tiny fallback for constrained environments/tests."""
    try:
        from langgraph.graph import END, START, StateGraph
    except ImportError:
        return _SequentialGraph(nodes)

    builder = StateGraph(InvestigationState)
    names = ["retrieve", "rerank", "synthesize", "verify"]
    for name, node in zip(names, nodes, strict=True):
        builder.add_node(name, node)
    builder.add_edge(START, "retrieve")
    builder.add_edge("retrieve", "rerank")
    builder.add_edge("rerank", "synthesize")
    builder.add_edge("synthesize", "verify")
    builder.add_edge("verify", END)
    return builder.compile()
