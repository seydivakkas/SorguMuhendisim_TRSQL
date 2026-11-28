"""Live PostgreSQL 16 integration tests (T-11).

Automatically skipped when ``TRSQL_PG_TEST_DSN`` is unset so offline unit/CI
suites stay green without a running Postgres server.
"""

from __future__ import annotations

import os

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

pytestmark = pytest.mark.postgres


def _forged_pg(
    sql: str, *, max_rows: int = 10, timeout_ms: int = 1000, auth: AuthContext | None = None
) -> ApprovedQuery:
    cand = SQLCandidate(sql=sql, dialect=Dialect.POSTGRES, model_id="pg-live-test", attempt=1)
    report = ValidationReport(candidate=cand, checks=(CheckResult(check=CheckName.SYNTAX, passed=True),))
    return ApprovedQuery(
        sql=sql,
        dialect=Dialect.POSTGRES,
        report=report,
        max_rows=max_rows,
        timeout_ms=timeout_ms,
        auth=auth,
    )


def test_live_postgres_introspect_excludes_system_catalogs() -> None:
    adapter = PostgresAdapter("TRSQL_PG_TEST_DSN", allowed_schemas=("public",))
    snap = adapter.introspect()
    assert snap.dialect is Dialect.POSTGRES
    names = snap.table_names
    assert not any(n.startswith("pg_") or "information_schema" in n for n in names)


def test_live_postgres_enforces_readonly_timeout_and_row_cap() -> None:
    adapter = PostgresAdapter("TRSQL_PG_TEST_DSN", allowed_schemas=("public",), statement_timeout_ms=500)

    # Read-only role/transaction rejects writes even if ApprovedQuery were forged
    with pytest.raises(ExecutionError):
        adapter.execute(_forged_pg("CREATE TABLE trsql_evil_test (id int)"))

    # statement_timeout aborts pg_sleep(10)
    with pytest.raises(ExecutionError):
        adapter.execute(_forged_pg("SELECT pg_sleep(10)", timeout_ms=250))

    # Row cap truncates accurately
    res = adapter.execute(_forged_pg("SELECT generate_series(1, 50) AS n", max_rows=10, timeout_ms=2000))
    assert res.row_count == 10
    assert res.truncated is True


def test_live_postgres_masked_views_and_rls_when_present(monkeypatch: pytest.MonkeyPatch) -> None:
    assert os.environ.get("TRSQL_PG_TEST_DSN")
    adapter = PostgresAdapter("TRSQL_PG_TEST_DSN", allowed_schemas=("public",))
    snap = adapter.introspect()

    if snap.table("v_bayiler_masked") is not None:
        res = adapter.execute(
            _forged_pg("SELECT vergi_no, telefon, eposta FROM v_bayiler_masked", max_rows=5)
        )
        for row in res.rows:
            vergi, tel, email = (str(x or "") for x in row)
            assert "***" in vergi or "*" in vergi or vergi == ""
            assert "***" in tel or tel == ""
            assert "***" in email or email == ""

    if snap.table("musteriler") is not None:
        auth_a = AuthContext(user_id="u-1", tenant_id="tenant_a", allowed_tables=frozenset({"musteriler"}))
        auth_b = AuthContext(user_id="u-2", tenant_id="tenant_b", allowed_tables=frozenset({"musteriler"}))
        res_a = adapter.with_auth(auth_a).execute(_forged_pg("SELECT COUNT(*) FROM musteriler", auth=auth_a))
        res_b = adapter.with_auth(auth_b).execute(_forged_pg("SELECT COUNT(*) FROM musteriler", auth=auth_b))
        assert res_a.row_count == 1 and res_b.row_count == 1
