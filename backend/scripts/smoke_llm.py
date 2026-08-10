from __future__ import annotations

from app.core.config import get_settings
from app.models.domain import DocumentType, EvidenceDocument, SearchHit
from app.services.llm import OpenAICompatibleLLM


if __name__ == "__main__":
    settings = get_settings()
    llm = OpenAICompatibleLLM(settings)
    if not llm.available:
        raise SystemExit("请先设置 REPO_TRACE_LLM_ENABLED=true 和 REPO_TRACE_LLM_API_KEY")
    hit = SearchHit(
        document=EvidenceDocument(
            id="smoke",
            repo="demo/repo",
            kind=DocumentType.ISSUE,
            title="Intermittent 401 after token refresh",
            body="Concurrent refresh requests can reuse the old access token.",
            url="https://example.invalid/issue/1",
        ),
        score=1.0,
    )
    result = llm.answer("为什么会偶发 401？", [hit])
    print(result.answer)
