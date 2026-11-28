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


def test_policy_loader_denies_tables_absent_from_policy_file(
    schema: SchemaSnapshot, candidate: Callable[[str], SQLCandidate]
) -> None:
    from pathlib import Path

    from backend.auth import load_role_policies, scope_schema

    policies = load_role_policies(Path("security_policies"), include_examples=True)
    ctx = policies["analyst"].to_auth_context(user_id="u-policy", tenant_id="t-demo")
    scoped = scope_schema(schema, ctx)
    assert {t.name for t in scoped.tables} == {"dealers", "sales"}

    # Tables absent from analyst policy (`salaries`) must not be visible and must fail closed.
    report = V.validate(candidate("SELECT amount FROM salaries"), schema, ctx)
    assert report.verdict is Verdict.REJECTED

    # Default PII columns must always be blocked even if omitted from the TOML file.
    for pii_col in ("tc_kimlik_no", "telefon", "eposta", "iban"):
        assert f"dealers.{pii_col}" in ctx.denied_columns


def _multi_schema_snapshot() -> SchemaSnapshot:
    from backend.core.contracts import ColumnInfo, ForeignKey, TableInfo

    return SchemaSnapshot(
        dialect=Dialect.POSTGRES,
        tables=(
            TableInfo(
                name="musteri",
                schema_name="public",
                columns=(
                    ColumnInfo(name="id", data_type="integer", is_primary_key=True),
                    ColumnInfo(name="ad", data_type="text"),
                    ColumnInfo(name="maas", data_type="numeric"),
                    ColumnInfo(name="tc_kimlik_no", data_type="text"),
                ),
            ),
            TableInfo(
                name="hr.musteri",
                schema_name="hr",
                columns=(
                    ColumnInfo(name="id", data_type="integer", is_primary_key=True),
                    ColumnInfo(name="ad", data_type="text"),
                    ColumnInfo(name="maas", data_type="numeric"),
                    ColumnInfo(name="sicil_no", data_type="text"),
                ),
                foreign_keys=(ForeignKey(column="id", ref_table="musteri", ref_column="id"),),
            ),
        ),
    )


def test_multischema_unqualified_allowlist_fails_closed() -> None:
    from backend.auth import scope_schema

    snap = _multi_schema_snapshot()
    auth = AuthContext(
        user_id="u-pg",
        tenant_id="t-demo",
        allowed_tables=frozenset({"musteri"}),
        denied_columns=frozenset({"public.musteri.maas"}),
    )
    scoped = scope_schema(snap, auth)
    assert scoped.tables == ()

    for sql in (
        "SELECT ad FROM musteri",
        "SELECT ad FROM public.musteri",
        "SELECT ad FROM hr.musteri",
        'SELECT ad FROM "Public"."Musteri"',
    ):
        cand = SQLCandidate(sql=sql, dialect=Dialect.POSTGRES, model_id="x", attempt=1)
        assert V.validate(cand, snap, auth).verdict is Verdict.REJECTED, sql


def test_multischema_quoted_case_and_search_path_and_column_levels() -> None:
    from backend.auth import scope_schema

    snap = _multi_schema_snapshot()
    auth = AuthContext(
        user_id="u-pg",
        tenant_id="t-demo",
        allowed_tables=frozenset({"public.musteri", "hr.musteri"}),
        denied_columns=frozenset({"public.musteri.maas", "tc_kimlik_no"}),
    )
    scoped = scope_schema(snap, auth)
    assert len(scoped.tables) == 2
    pub_tbl = next(t for t in scoped.tables if t.resolved_schema == "public")
    hr_tbl = next(t for t in scoped.tables if t.resolved_schema == "hr")
    assert {c.name for c in pub_tbl.columns} == {"id", "ad"}
    assert {c.name for c in hr_tbl.columns} == {"id", "ad", "maas", "sicil_no"}

    must_reject = [
        # Quoted mixed case schema/table/column must still obey RBAC
        'SELECT ad FROM "Public"."Musteri" m JOIN "Public"."Musteri" m2 ON m.id = m2.id WHERE m."Maas" > 0',
        'SELECT "Maas" FROM "Public"."Musteri"',
        'SELECT "TC_Kimlik_No" FROM "Public"."Musteri"',
        'SELECT m.* FROM "Public"."Musteri" m',
        # Unqualified access relies on search_path when two schemas share the table name
        "SELECT ad FROM musteri",
        # Qualified denied column on public.musteri
        "SELECT m.maas FROM public.musteri m",
        # Unqualified column joined across both schemas
        "SELECT maas FROM public.musteri m JOIN hr.musteri h ON m.id = h.id",
    ]
    for sql in must_reject:
        cand = SQLCandidate(sql=sql, dialect=Dialect.POSTGRES, model_id="x", attempt=1)
        assert V.validate(cand, snap, auth).verdict is Verdict.REJECTED, sql

    # Same-named column in hr.musteri is permitted when only public.musteri.maas is denied
    allowed_cand = SQLCandidate(
        sql="SELECT h.maas FROM hr.musteri h",
        dialect=Dialect.POSTGRES,
        model_id="x",
        attempt=1,
    )
    assert V.validate(allowed_cand, snap, auth).verdict is Verdict.APPROVED

    # Only public.musteri allowed -> hr.musteri must be REJECTED
    pub_only = AuthContext(
        user_id="u-pg-pub",
        tenant_id="t-demo",
        allowed_tables=frozenset({"public.musteri"}),
        denied_columns=frozenset({"public.musteri.maas"}),
    )
    assert len(scope_schema(snap, pub_only).tables) == 1
    assert (
        V.validate(
            SQLCandidate(
                sql="SELECT sicil_no FROM hr.musteri", dialect=Dialect.POSTGRES, model_id="x", attempt=1
            ),
            snap,
            pub_only,
        ).verdict
        is Verdict.REJECTED
    )
    assert (
        V.validate(
            SQLCandidate(sql="SELECT ad FROM musteri", dialect=Dialect.POSTGRES, model_id="x", attempt=1),
            snap,
            pub_only,
        ).verdict
        is Verdict.REJECTED
    )
