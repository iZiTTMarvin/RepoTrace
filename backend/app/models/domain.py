from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class DocumentType(StrEnum):
    ISSUE = "issue"
    PULL_REQUEST = "pull_request"
    COMMIT = "commit"
    DOC = "doc"


@dataclass(slots=True)
class EvidenceDocument:
    id: str
    repo: str
    kind: DocumentType
    title: str
    body: str
    url: str
    number: int | None = None
    state: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def searchable_text(self) -> str:
        parts = [self.title, self.body]
        if self.number is not None:
            parts.append(f"#{self.number}")
        if self.metadata:
            parts.extend(str(value) for value in self.metadata.values() if value)
        return "\n".join(parts)


@dataclass(slots=True)
class SearchHit:
    document: EvidenceDocument
    score: float
    bm25_score: float = 0.0
    vector_score: float = 0.0
    rerank_score: float = 0.0
    reasons: list[str] = field(default_factory=list)


class RepositoryImportRequest(BaseModel):
    repository: str = Field(examples=["fastapi/fastapi"])


class InvestigationRequest(BaseModel):
    repository: str
    question: str = Field(min_length=4, max_length=4000)


class EvidenceOut(BaseModel):
    id: str
    kind: DocumentType
    title: str
    url: str
    number: int | None = None
    score: float
    reasons: list[str]
    excerpt: str


class InvestigationOut(BaseModel):
    id: str
    repository: str
    question: str
    answer: str
    confidence: str
    evidence: list[EvidenceOut]
    trace: list[dict[str, Any]]
    used_llm: bool


class EvaluationSummary(BaseModel):
    dataset: str
    cases: int
    metrics: dict[str, float]
    variants: list[dict[str, Any]]
