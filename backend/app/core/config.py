from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file="../.env",
        env_prefix="REPO_TRACE_",
        extra="ignore",
    )

    env: str = "development"
    db_path: Path = Path("./var/repotrace.db")
    cors_origins: str = "http://localhost:5173"

    github_token: str | None = None
    github_max_issues: int = 120
    github_max_pulls: int = 80
    github_max_commits: int = 120
    github_max_docs: int = 40

    llm_enabled: bool = False
    llm_base_url: str = "https://opencode.ai/zen/go/v1"
    llm_api_key: str | None = None
    llm_model: str = "deepseek-v4-flash"
    llm_reasoning_effort: str | None = "max"
    llm_timeout_seconds: float = 90.0

    retrieval_top_k: int = Field(default=12, ge=3, le=50)
    rerank_top_k: int = Field(default=6, ge=2, le=20)

    langfuse_enabled: bool = False

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
