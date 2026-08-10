from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class LocalTrace:
    steps: list[dict[str, Any]] = field(default_factory=list)

    @contextmanager
    def step(self, name: str, input_summary: dict | None = None) -> Iterator[dict]:
        started = time.perf_counter()
        record: dict[str, Any] = {
            "name": name,
            "status": "running",
            "input": input_summary or {},
        }
        try:
            yield record
            record["status"] = "ok"
        except Exception as exc:
            record["status"] = "error"
            record["error"] = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            record["duration_ms"] = round((time.perf_counter() - started) * 1000, 2)
            self.steps.append(record)


class LangfuseExporter:
    """Optional exporter. Local traces remain the source of truth for the UI."""

    def __init__(self, enabled: bool):
        self.enabled = enabled

    @contextmanager
    def trace(self, name: str, input_payload: dict) -> Iterator[object | None]:
        if not self.enabled:
            yield None
            return
        try:
            from langfuse import get_client

            client = get_client()
            with client.start_as_current_observation(
                as_type="agent",
                name=name,
                input=input_payload,
            ) as observation:
                yield observation
        except Exception:
            # Observability should never make the investigation endpoint unavailable.
            yield None
