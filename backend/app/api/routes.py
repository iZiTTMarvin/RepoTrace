from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.models.domain import InvestigationRequest, RepositoryImportRequest


router = APIRouter(prefix="/api")


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "repotrace"}


@router.get("/repositories")
def list_repositories(request: Request) -> list[dict]:
    return request.app.state.store.list_repositories()


@router.post("/repositories/import")
def import_repository(payload: RepositoryImportRequest, request: Request) -> dict:
    try:
        result = request.app.state.github.import_repository(payload.repository)
        request.app.state.store.replace_documents(result.repository, result.documents)
        request.app.state.store.upsert_repository(
            result.repository,
            result.metadata,
            len(result.documents),
        )
        counts: dict[str, int] = {}
        for document in result.documents:
            counts[document.kind.value] = counts.get(document.kind.value, 0) + 1
        return {
            "repository": result.repository,
            "document_count": len(result.documents),
            "counts": counts,
        }
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"GitHub 导入失败：{exc}") from exc


@router.post("/investigations")
def investigate(payload: InvestigationRequest, request: Request):
    try:
        return request.app.state.investigation.run(payload.repository, payload.question)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/evaluation/demo")
def evaluation_demo(request: Request) -> dict:
    return request.app.state.demo_evaluation
