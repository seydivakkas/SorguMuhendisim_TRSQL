from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from backend.core.contracts import (
    ApprovedQuery,
    ColumnInfo,
    Dialect,
    ExecutionResult,
    ForeignKey,
    SchemaSnapshot,
    TableInfo,
)
from backend.core.errors import ExecutionError

# Actions the SQLite authorizer lets through; everything else is denied.
_ALLOWED_ACTIONS = frozenset({
    sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION, sqlite3.SQLITE_RECURSIVE,
})  # fmt: skip


def _authorizer(action: int, arg1: str | None, arg2: str | None, db: str | None, src: str | None) -> int:
    if action in _ALLOWED_ACTIONS:
        if action == sqlite3.SQLITE_READ and arg1 and arg1.lower().startswith("sqlite_"):
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK
    return sqlite3.SQLITE_DENY


class SQLiteAdapter:
    """Read-only SQLite access with layered protection:

    1. file opened with ``mode=ro`` (URI),
    2. ``PRAGMA query_only = ON``,
    3. an authorizer that allows only SELECT/READ/FUNCTION,
    4. a progress-handler timeout and a hard row cap.
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        if not self._path.exists():
            raise ExecutionError(f"veritabanı bulunamadı: {self._path.name}")

    @property
    def dialect(self) -> Dialect:
        return Dialect.SQLITE

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(f"{self._path.resolve().as_uri()}?mode=ro", uri=True)
        conn.execute("PRAGMA query_only = ON")
        return conn

    def introspect(self) -> SchemaSnapshot:
        conn = self._connect()
        try:
            names = [r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )]  # fmt: skip
            tables: list[TableInfo] = []
            for name in names:
                quoted = '"' + name.replace('"', '""') + '"'
                cols = tuple(
                    ColumnInfo(name=r[1], data_type=r[2] or "", nullable=not r[3], is_primary_key=bool(r[5]))
                    for r in conn.execute(f"PRAGMA table_info({quoted})")
                )
                fks = tuple(
                    ForeignKey(column=r[3], ref_table=r[2], ref_column=r[4])
                    for r in conn.execute(f"PRAGMA foreign_key_list({quoted})")
                )
                tables.append(TableInfo(name=name, columns=cols, foreign_keys=fks))
            return SchemaSnapshot(dialect=Dialect.SQLITE, tables=tuple(tables))
        finally:
            conn.close()

    def execute(self, query: ApprovedQuery) -> ExecutionResult:
        conn = self._connect()
        conn.set_authorizer(_authorizer)
        deadline = time.monotonic() + query.timeout_ms / 1000
        conn.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 1000)
        started = time.perf_counter()
        try:
            cur = conn.execute(query.sql)
            rows = cur.fetchmany(query.max_rows + 1)
            columns = tuple(d[0] for d in cur.description or ())
        except sqlite3.Error as exc:
            raise ExecutionError("sorgu yürütülemedi") from exc
        finally:
            conn.close()
        truncated = len(rows) > query.max_rows
        return ExecutionResult(
            columns=columns,
            rows=tuple(tuple(r) for r in rows[: query.max_rows]),
            truncated=truncated,
            elapsed_ms=(time.perf_counter() - started) * 1000,
        )
