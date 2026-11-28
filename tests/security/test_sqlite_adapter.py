"""Defense in depth: even if L6 were bypassed, the adapter must not write."""

import sqlite3
from pathlib import Path

import pytest

from backend.core.contracts import (
    ApprovedQuery,
    CheckName,
    CheckResult,
    Dialect,
    SQLCandidate,
    ValidationReport,
)
from backend.core.errors import ExecutionError
from backend.database_adapters import SQLiteAdapter

pytestmark = pytest.mark.security


def forged(sql: str, timeout_ms: int = 2000) -> ApprovedQuery:
    """Simulates a validator bug: a dangerous query with a fake 'all passed' report."""
    cand = SQLCandidate(sql=sql, dialect=Dialect.SQLITE, model_id="x", attempt=1)
    report = ValidationReport(candidate=cand, checks=(CheckResult(check=CheckName.SYNTAX, passed=True),))
    return ApprovedQuery(sql=sql, dialect=Dialect.SQLITE, report=report, max_rows=10, timeout_ms=timeout_ms)


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM sales",
        "UPDATE sales SET total_amount = 0",
        "DROP TABLE sales",
        "INSERT INTO salaries VALUES (2, 1)",
        "CREATE TABLE x (a INTEGER)",
        "ATTACH DATABASE ':memory:' AS x",
        "SELECT name FROM sqlite_master",
    ],
)
def test_adapter_refuses_non_select(sql: str, adapter: SQLiteAdapter, db_path: Path) -> None:
    with pytest.raises(ExecutionError):
        adapter.execute(forged(sql))
    conn = sqlite3.connect(db_path)
    assert conn.execute("SELECT COUNT(*) FROM sales").fetchone()[0] == 8
    conn.close()


def test_row_cap_and_truncation(adapter: SQLiteAdapter) -> None:
    result = adapter.execute(forged("SELECT * FROM sales"))
    assert result.row_count == 8 and not result.truncated
    q = forged("SELECT * FROM sales").model_copy(update={"max_rows": 3})
    capped = adapter.execute(q)
    assert capped.row_count == 3 and capped.truncated


def test_timeout(adapter: SQLiteAdapter) -> None:
    slow = "WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM c) SELECT COUNT(*) FROM c"
    with pytest.raises(ExecutionError):
        adapter.execute(forged(slow, timeout_ms=200))


def test_adapter_refuses_stacked_statements(adapter: SQLiteAdapter, db_path: Path) -> None:
    with pytest.raises(ExecutionError):
        adapter.execute(forged("SELECT 1; DROP TABLE sales"))
    conn = sqlite3.connect(db_path)
    assert conn.execute("SELECT COUNT(*) FROM sales").fetchone()[0] == 8
    conn.close()
