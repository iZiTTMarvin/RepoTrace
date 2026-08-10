from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.core.config import get_settings
from app.services.github_client import GitHubClient
from app.services.investigation import InvestigationService
from app.storage.sqlite import SQLiteStore
from app.support.demo_benchmark import run_demo_benchmark


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="RepoTrace API",
        version="0.1.0",
        description="GitHub 历史故障调查与证据检索 API",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    store = SQLiteStore(settings.db_path)
    app.state.store = store
    app.state.github = GitHubClient(settings)
    app.state.investigation = InvestigationService(store, settings)
    app.state.demo_evaluation = run_demo_benchmark()
    app.include_router(router)
    return app


app = create_app()
