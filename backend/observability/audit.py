from __future__ import annotations

import json
import threading
from pathlib import Path
from uuid import UUID

from backend.core.contracts import AuditEvent, AuthContext
from backend.core.ports import AuditSink
from backend.observability.masking import mask_sensitive


class InMemoryAuditSink:
    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    def emit(self, event: AuditEvent) -> None:
        self.events.append(event)


class JsonlAuditSink:
    """Append-only JSON Lines file. Rotation/retention is a deployment concern."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._lock = threading.Lock()

    def emit(self, event: AuditEvent) -> None:
        line = json.dumps(event.model_dump(mode="json"), ensure_ascii=False)
        with self._lock, self._path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")


class AuditLogger:
    """Records one event per pipeline stage. All detail values are masked."""

    def __init__(self, sink: AuditSink) -> None:
        self._sink = sink

    def record(self, request_id: UUID, auth: AuthContext, stage: str, status: str, **details: object) -> None:
        self._sink.emit(AuditEvent(
            request_id=request_id,
            stage=stage,
            status=status,
            user_id=auth.user_id,
            tenant_id=auth.tenant_id,
            details={k: mask_sensitive(str(v)) for k, v in details.items()},
        ))  # fmt: skip
