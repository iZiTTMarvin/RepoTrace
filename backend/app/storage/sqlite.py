from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from app.models.domain import DocumentType, EvidenceDocument


SCHEMA = """
CREATE TABLE IF NOT EXISTS repositories (
    full_name TEXT PRIMARY KEY,
    imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    document_count INTEGER NOT NULL DEFAULT 0,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    repo TEXT NOT NULL,
    kind TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    url TEXT NOT NULL,
    number INTEGER,
    state TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_documents_repo ON documents(repo);
CREATE INDEX IF NOT EXISTS idx_documents_repo_kind ON documents(repo, kind);

CREATE TABLE IF NOT EXISTS investigations (
    id TEXT PRIMARY KEY,
    repo TEXT NOT NULL,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    confidence TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    trace_json TEXT NOT NULL,
    used_llm INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


class SQLiteStore:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def upsert_repository(self, full_name: str, metadata: dict, document_count: int) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO repositories(full_name, document_count, metadata_json)
                VALUES (?, ?, ?)
                ON CONFLICT(full_name) DO UPDATE SET
                    imported_at = CURRENT_TIMESTAMP,
                    document_count = excluded.document_count,
                    metadata_json = excluded.metadata_json
                """,
                (full_name, document_count, json.dumps(metadata, ensure_ascii=False)),
            )

    def replace_documents(self, repo: str, documents: list[EvidenceDocument]) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM documents WHERE repo = ?", (repo,))
            conn.executemany(
                """
                INSERT INTO documents(id, repo, kind, title, body, url, number, state, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        doc.id,
                        doc.repo,
                        doc.kind.value,
                        doc.title,
                        doc.body,
                        doc.url,
                        doc.number,
                        doc.state,
                        json.dumps(doc.metadata, ensure_ascii=False),
                    )
                    for doc in documents
                ],
            )

    def list_documents(self, repo: str) -> list[EvidenceDocument]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM documents WHERE repo = ? ORDER BY kind, id", (repo,)
            ).fetchall()
        return [self._row_to_document(row) for row in rows]

    def list_repositories(self) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT full_name, imported_at, document_count, metadata_json FROM repositories "
                "ORDER BY imported_at DESC"
            ).fetchall()
        return [
            {
                "full_name": row["full_name"],
                "imported_at": row["imported_at"],
                "document_count": row["document_count"],
                "metadata": json.loads(row["metadata_json"]),
            }
            for row in rows
        ]

    def save_investigation(self, payload: dict) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO investigations(
                    id, repo, question, answer, confidence, evidence_json, trace_json, used_llm
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["id"],
                    payload["repository"],
                    payload["question"],
                    payload["answer"],
                    payload["confidence"],
                    json.dumps(payload["evidence"], ensure_ascii=False),
                    json.dumps(payload["trace"], ensure_ascii=False),
                    int(payload["used_llm"]),
                ),
            )

    @staticmethod
    def _row_to_document(row: sqlite3.Row) -> EvidenceDocument:
        return EvidenceDocument(
            id=row["id"],
            repo=row["repo"],
            kind=DocumentType(row["kind"]),
            title=row["title"],
            body=row["body"],
            url=row["url"],
            number=row["number"],
            state=row["state"],
            metadata=json.loads(row["metadata_json"]),
        )
