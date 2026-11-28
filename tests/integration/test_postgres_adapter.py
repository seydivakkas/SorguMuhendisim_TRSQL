"""Mocked psycopg integration tests for PostgresAdapter (no live DB required)."""

from __future__ import annotations

import json
import sys
from types import SimpleNamespace
from typing import Any

import pytest

from backend.core.contracts import (
    ApprovedQuery,
    AuthContext,
    CheckName,
    CheckResult,
    Dialect,
    SQLCandidate,
    ValidationReport,
)
from backend.core.errors import ExecutionError
from backend.database_adapters import PostgresAdapter


class _FakeCursor:
    def __init__(
        self,
        *,
        col_rows: list[tuple[Any, ...]] | None = None,
        fk_rows: list[tuple[Any, ...]] | None = None,
        query_rows: list[tuple[Any, ...]] | None = None,
        query_cols: tuple[str, ...] = ("id", "name"),
        explain_payload: Any = None,
    ) -> None:
        self.executed: list[tuple[str, Any]] = []
        self._col_rows = col_rows or []
        self._fk_rows = fk_rows or []
        self._query_rows = query_rows or []
        self._query_cols = query_cols
        self._explain_payload = explain_payload
        self._last_mode: str = ""
        self.description: list[tuple[str]] | None = None
        self.closed = False

    def execute(self, query: str, params: Any = None) -> None:
        self.executed.append((query, params))
        upper = query.strip().upper()
        if "FROM INFORMATION_SCHEMA.COLUMNS" in upper:
            self._last_mode = "cols"
            self.description = None
        elif "FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS" in upper:
            self._last_mode = "fks"
            self.description = None
        elif upper.startswith("EXPLAIN (FORMAT JSON)"):
            assert "ANALYZE" not in upper
            self._last_mode = "explain"
            self.description = [("QUERY PLAN",)]
        elif upper.startswith("SELECT SET_CONFIG") or upper.startswith("SET "):
            self._last_mode = "guc"
            self.description = None
        else:
            self._last_mode = "query"
            self.description = [(c,) for c in self._query_cols]

    def fetchall(self) -> list[tuple[Any, ...]]:
        if self._last_mode == "cols":
            return list(self._col_rows)
        if self._last_mode == "fks":
            return list(self._fk_rows)
        if self._last_mode == "explain":
            return [(self._explain_payload,)]
        return list(self._query_rows)

    def fetchmany(self, size: int = 100) -> list[tuple[Any, ...]]:
        return list(self._query_rows[:size])

    def close(self) -> None:
        self.closed = True


class _FakeConnection:
    def __init__(self, cursor: _FakeCursor) -> None:
        self._cursor = cursor
        self.rolled_back = False
        self.closed = False

    def cursor(self) -> _FakeCursor:
        return self._cursor

    def rollback(self) -> None:
        self.rolled_back = True

    def close(self) -> None:
        self.closed = True


def _approved_pg(sql: str, *, max_rows: int = 10, timeout_ms: int = 2500) -> ApprovedQuery:
    cand = SQLCandidate(sql=sql, dialect=Dialect.POSTGRES, model_id="test", attempt=1)
    report = ValidationReport(candidate=cand, checks=(CheckResult(check=CheckName.SYNTAX, passed=True),))
    return ApprovedQuery(
        sql=sql, dialect=Dialect.POSTGRES, report=report, max_rows=max_rows, timeout_ms=timeout_ms
    )


def test_missing_dsn_env_raises_execution_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TRSQL_PG_DSN", raising=False)
    adapter = PostgresAdapter("TRSQL_PG_DSN")
    with pytest.raises(ExecutionError, match="TRSQL_PG_DSN"):
        adapter.introspect()


def test_forbidden_schema_rejected() -> None:
    with pytest.raises(ExecutionError):
        PostgresAdapter(allowed_schemas=("pg_catalog",))
    with pytest.raises(ExecutionError):
        PostgresAdapter(allowed_schemas=("information_schema",))


def test_lazy_psycopg_import_and_introspect(monkeypatch: pytest.MonkeyPatch) -> None:
    test_dsn = "postgresql://nl2sql_reader@localhost:5432/trsql"
    monkeypatch.setenv("TRSQL_PG_DSN", test_dsn)

    cur = _FakeCursor(
        col_rows=[
            ("public", "dealers", "dealer_id", "integer", "NO", True),
            ("public", "dealers", "name", "text", "NO", False),
            ("pg_catalog", "pg_user", "usename", "name", "YES", False),
            ("public", "sales", "sale_id", "integer", "NO", True),
            ("public", "sales", "dealer_id", "integer", "NO", False),
        ],
        fk_rows=[
            ("public", "sales", "dealer_id", "public", "dealers", "dealer_id"),
        ],
    )
    conn = _FakeConnection(cur)
    connect_calls: list[tuple[str, dict[str, Any]]] = []

    def fake_connect(conninfo: str, **kwargs: Any) -> _FakeConnection:
        connect_calls.append((conninfo, kwargs))
        return conn

    monkeypatch.setitem(sys.modules, "psycopg", SimpleNamespace(connect=fake_connect))

    adapter = PostgresAdapter("TRSQL_PG_DSN", allowed_schemas=("public",))
    assert adapter.dialect is Dialect.POSTGRES
    snap = adapter.introspect()

    assert connect_calls == [(test_dsn, {"autocommit": False})]
    assert conn.rolled_back and conn.closed
    assert snap.dialect is Dialect.POSTGRES
    assert snap.table_names == frozenset({"dealers", "sales"})
    assert snap.table("pg_user") is None
    sales_tbl = snap.table("sales")
    assert sales_tbl is not None
    assert len(sales_tbl.foreign_keys) == 1
    assert sales_tbl.foreign_keys[0].ref_table == "dealers"
    executed_sqls = [q for q, _ in cur.executed]
    assert "SET TRANSACTION READ ONLY" in executed_sqls
    assert any("SET LOCAL statement_timeout" in q for q in executed_sqls)
    assert any("SET LOCAL lock_timeout" in q for q in executed_sqls)
    assert any("SET LOCAL idle_in_transaction_session_timeout" in q for q in executed_sqls)


def test_execute_enforces_session_gucs_rls_and_row_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRSQL_PG_DSN", "postgresql://reader@localhost/db")
    rows = [(1, "A"), (2, "B"), (3, "C"), (4, "D")]
    cur = _FakeCursor(query_rows=rows, query_cols=("dealer_id", "name"))
    conn = _FakeConnection(cur)

    auth = AuthContext(
        user_id="u-42",
        tenant_id="tenant-tr-01",
        allowed_tables=frozenset({"dealers"}),
        max_rows=3,
    )
    adapter = PostgresAdapter(connect_fn=lambda _dsn: conn).with_auth(auth)
    result = adapter.execute(
        _approved_pg("SELECT dealer_id, name FROM dealers LIMIT 10", max_rows=3, timeout_ms=4200)
    )

    assert result.columns == ("dealer_id", "name")
    assert result.row_count == 3
    assert result.truncated is True
    assert result.rows == ((1, "A"), (2, "B"), (3, "C"))
    assert conn.rolled_back and conn.closed

    executed = cur.executed
    assert executed[0][0] == "SET TRANSACTION READ ONLY"
    assert executed[1][0] == "SET LOCAL statement_timeout = 4200"
    assert executed[2][0] == "SET LOCAL lock_timeout = 2000"
    assert executed[3][0] == "SET LOCAL idle_in_transaction_session_timeout = 10000"
    assert ("SELECT set_config('app.user_id', %s, true)", ("u-42",)) in executed
    assert ("SELECT set_config('app.tenant_id', %s, true)", ("tenant-tr-01",)) in executed


def test_execute_explain_cost_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRSQL_PG_DSN", "postgresql://reader@localhost/db")

    # 1. Healthy indexed plan passes
    good_plan = [{"Plan": {"Node Type": "Index Scan", "Total Cost": 42.0, "Plan Rows": 5}}]
    good_cur = _FakeCursor(query_rows=[(1, "Trabzon")], query_cols=("id", "city"), explain_payload=good_plan)
    good_conn = _FakeConnection(good_cur)
    adapter_ok = PostgresAdapter(check_explain=True, connect_fn=lambda _dsn: good_conn)
    res = adapter_ok.execute(_approved_pg("SELECT id, city FROM dealers WHERE city = 'Trabzon'"))
    assert res.row_count == 1
    assert any(q.startswith("EXPLAIN (FORMAT JSON)") for q, _ in good_cur.executed)
    assert all("ANALYZE" not in q.upper() for q, _ in good_cur.executed)

    # 2. Full table scan plan blocked before query runs
    bad_plan = json.dumps([{"Plan": {"Node Type": "Seq Scan", "Total Cost": 5000.0, "Plan Rows": 250000}}])
    bad_cur = _FakeCursor(query_rows=[(1, "X")], explain_payload=bad_plan)
    bad_conn = _FakeConnection(bad_cur)
    adapter_bad = PostgresAdapter(
        check_explain=True, max_seq_scan_rows=10000, connect_fn=lambda _dsn: bad_conn
    )
    with pytest.raises(ExecutionError, match="Seq Scan"):
        adapter_bad.execute(_approved_pg("SELECT id, city FROM dealers"))
    assert bad_conn.rolled_back and bad_conn.closed
    assert all(not q.startswith("SELECT id, city") for q, _ in bad_cur.executed)

    # 3. Cartesian Nested Loop blocked
    cart_plan = [
        {
            "Plan": {
                "Node Type": "Nested Loop",
                "Join Type": "Inner",
                "Total Cost": 1200.0,
                "Plan Rows": 50000,
                "Plans": [
                    {"Node Type": "Seq Scan", "Total Cost": 10.0, "Plan Rows": 500},
                    {"Node Type": "Seq Scan", "Total Cost": 10.0, "Plan Rows": 100},
                ],
            }
        }
    ]
    cart_cur = _FakeCursor(explain_payload=cart_plan)
    cart_conn = _FakeConnection(cart_cur)
    adapter_cart = PostgresAdapter(check_explain=True, connect_fn=lambda _dsn: cart_conn)
    with pytest.raises(ExecutionError, match="kartezyen"):
        adapter_cart.execute(_approved_pg("SELECT * FROM dealers d JOIN sales s ON 1=1"))


def test_execute_uses_identity_bound_to_approved_query_for_rls(monkeypatch: pytest.MonkeyPatch) -> None:
    """The pipeline never calls ``with_auth``; RLS context must come from the ApprovedQuery."""
    monkeypatch.setenv("TRSQL_PG_DSN", "postgresql://reader@localhost/db")
    cur = _FakeCursor(query_rows=[(1, "A")], query_cols=("dealer_id", "name"))
    conn = _FakeConnection(cur)
    auth = AuthContext(user_id="u-7", tenant_id="tenant-7", allowed_tables=frozenset({"dealers"}))
    query = _approved_pg("SELECT dealer_id, name FROM dealers").model_copy(update={"auth": auth})

    PostgresAdapter(connect_fn=lambda _dsn: conn, allowed_schemas=("public", "sales")).execute(query)

    executed = cur.executed
    assert ("SELECT set_config('app.user_id', %s, true)", ("u-7",)) in executed
    assert ("SELECT set_config('app.tenant_id', %s, true)", ("tenant-7",)) in executed
    assert ("SELECT set_config('search_path', %s, true)", ('"public", "sales"',)) in executed
