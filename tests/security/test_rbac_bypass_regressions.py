"""Regression tests for RBAC / resource bypasses found in the feature0 security review.

Security gate: never skip or weaken (AGENTS.md §1.8).
"""

from collections.abc import Callable

import pytest

from backend.core.contracts import (
    ApprovedQuery,
    AuthContext,
    CheckName,
    CheckResult,
    Dialect,
    SchemaSnapshot,
    SQLCandidate,
    ValidationReport,
    Verdict,
)
from backend.core.errors import ExecutionError
from backend.database_adapters import SQLiteAdapter
from backend.policy_engine import PolicyEngine
from backend.sql_validator import SQLValidator

pytestmark = pytest.mark.security

V = SQLValidator()

MUST_REJECT = [
    # A CTE named like a real-table alias must not hide the alias' denied column.
    "WITH x AS (SELECT 1 AS one) SELECT x.tax_number FROM dealers x",
    "WITH d AS (SELECT 1 AS one) SELECT d.tax_number FROM dealers AS d",
    # Same trick with a table-valued function alias.
    "SELECT u.tax_number FROM json_each('[1]') u JOIN dealers u ON 1 = 1",
    # Memory exhaustion in a single VM step.
    "SELECT randomblob(1000000000)",
    "SELECT zeroblob(1000000000)",
]

MUST_REJECT_PG = [
    # Whole-row references expose every column, including denied ones.
    "SELECT d FROM dealers d",
    "SELECT row_to_json(d) FROM dealers d",
    "SELECT (d).tax_number FROM dealers d",
    "WITH c AS (SELECT 1 AS one) SELECT d FROM dealers d JOIN c ON c.one = d.dealer_id",
    "WITH c AS (SELECT 1 AS one) SELECT to_jsonb(d) FROM dealers d JOIN c ON c.one = d.dealer_id",
    # Functions that run arbitrary SQL, dump schemas, sleep, lock or have side effects.
    "SELECT ts_stat('SELECT amount FROM salaries')",
    "SELECT database_to_xml(true, true, '')",
    "SELECT schema_to_xml('public', true, true, '')",
    "SELECT cursor_to_xml('c', 1, true, true, '')",
    "SELECT pg_sleep_for('1 hour')",
    "SELECT pg_sleep_until(now() + interval '1 hour')",
    "SELECT pg_advisory_lock(1)",
    "SELECT pg_try_advisory_lock(1)",
    "SELECT nextval('s')",
    "SELECT setval('s', 1)",
    "SELECT pg_notify('c', 'x')",
]

REPAIRABLE = [
    # A schema qualifier must not be silently dropped: hr.dealers is not dealers.
    "SELECT name FROM hr.dealers",
    "SELECT name FROM other_db.main.dealers",
    # A dummy CTE must not make arbitrary unqualified names acceptable.
    "WITH c AS (SELECT 1 AS one) SELECT bogus FROM c",
]

APPROVED = [
    # COUNT(*) on a table with a denied column exposes nothing.
    "SELECT COUNT(*) FROM dealers",
    "SELECT city, COUNT(*) AS n FROM dealers GROUP BY city",
    "SELECT COUNT(*) FROM sales s JOIN dealers d ON d.dealer_id = s.dealer_id",
    "SELECT name FROM main.dealers",
    "SELECT x.n FROM (SELECT COUNT(*) AS n FROM dealers) x",
    "WITH c(a, b) AS (SELECT 1, 2) SELECT a FROM c",
]


@pytest.mark.parametrize("sql", MUST_REJECT)
def test_rejects_sqlite(
    sql: str, schema: SchemaSnapshot, analyst: AuthContext, candidate: Callable[[str], SQLCandidate]
) -> None:
    assert V.validate(candidate(sql), schema, analyst).verdict is Verdict.REJECTED, sql


@pytest.mark.parametrize("sql", MUST_REJECT_PG)
def test_rejects_postgres(
    sql: str, schema: SchemaSnapshot, analyst: AuthContext, candidate: Callable[..., SQLCandidate]
) -> None:
    assert V.validate(candidate(sql, Dialect.POSTGRES), schema, analyst).verdict is Verdict.REJECTED, sql


@pytest.mark.parametrize("sql", REPAIRABLE)
def test_repairable(
    sql: str, schema: SchemaSnapshot, analyst: AuthContext, candidate: Callable[[str], SQLCandidate]
) -> None:
    assert V.validate(candidate(sql), schema, analyst).verdict is Verdict.REPAIRABLE, sql


@pytest.mark.parametrize("sql", APPROVED)
def test_approved(
    sql: str, schema: SchemaSnapshot, analyst: AuthContext, candidate: Callable[[str], SQLCandidate]
) -> None:
    report = V.validate(candidate(sql), schema, analyst)
    assert report.verdict is Verdict.APPROVED, report.failures


# --- Database-level defense in depth (validator assumed broken) --------------


def _forged(sql: str, auth: AuthContext) -> ApprovedQuery:
    cand = SQLCandidate(sql=sql, dialect=Dialect.SQLITE, model_id="x", attempt=1)
    report = ValidationReport(candidate=cand, checks=(CheckResult(check=CheckName.SYNTAX, passed=True),))
    return ApprovedQuery(
        sql=sql, dialect=Dialect.SQLITE, report=report, max_rows=10, timeout_ms=2000, auth=auth
    )


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT amount FROM salaries",
        "SELECT tax_number FROM dealers",
        "SELECT * FROM dealers",
        "SELECT d.name FROM dealers d WHERE d.tax_number LIKE '1%'",
    ],
)
def test_sqlite_authorizer_enforces_rbac(sql: str, adapter: SQLiteAdapter, analyst: AuthContext) -> None:
    with pytest.raises(ExecutionError):
        adapter.execute(_forged(sql, analyst))


def test_sqlite_authorizer_allows_permitted_reads(adapter: SQLiteAdapter, analyst: AuthContext) -> None:
    result = adapter.execute(_forged("SELECT name, city FROM dealers", analyst))
    assert result.row_count > 0
    assert adapter.execute(_forged("SELECT COUNT(*) FROM dealers", analyst)).rows[0][0] > 0


def test_sqlite_value_size_is_capped(adapter: SQLiteAdapter, analyst: AuthContext) -> None:
    with pytest.raises(ExecutionError):
        adapter.execute(_forged("SELECT length(zeroblob(200000000))", analyst))


def test_policy_binds_identity_to_approved_query(
    schema: SchemaSnapshot, analyst: AuthContext, candidate: Callable[[str], SQLCandidate]
) -> None:
    report = V.validate(candidate("SELECT name FROM dealers"), schema, analyst)
    approved = PolicyEngine().approve(report, analyst)
    assert approved.auth == analyst
