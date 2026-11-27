"""Security gate. These tests must never be skipped or weakened (AGENTS.md §6)."""

from collections.abc import Callable

import pytest

from backend.core.contracts import AuthContext, Dialect, SchemaSnapshot, SQLCandidate, Verdict
from backend.sql_validator import SQLValidator

pytestmark = pytest.mark.security

V = SQLValidator()

MUST_REJECT = [
    "DROP TABLE sales",
    "DELETE FROM sales",
    "UPDATE sales SET total_amount = 0",
    "INSERT INTO sales (dealer_id) VALUES (1)",
    "SELECT * FROM sales; DROP TABLE sales",
    "SELECT name FROM dealers; SELECT 1",
    "ATTACH DATABASE '/tmp/x.db' AS x",
    "PRAGMA table_info(sales)",
    "SELECT * FROM salaries",  # unauthorized table
    "SELECT s.amount FROM sales JOIN salaries s ON 1 = 1",  # unauthorized via join
    "SELECT tax_number FROM dealers",  # denied column
    "SELECT d.tax_number FROM dealers AS d",  # denied column via alias
    "SELECT * FROM dealers",  # star exposes denied column
    "SELECT name FROM sqlite_master",  # system catalog
    "SELECT load_extension('evil.so')",  # forbidden function
    "WITH x AS (SELECT * FROM salaries) SELECT * FROM x",  # unauthorized inside CTE
    "SELECT name FROM dealers WHERE dealer_id IN (SELECT employee_id FROM salaries)",
]

MUST_REJECT_PG = [
    "SELECT pg_sleep(10)",
    "SELECT * FROM pg_catalog.pg_user",
    "SELECT * FROM information_schema.tables",
    "SELECT name INTO new_table FROM dealers",
    "COPY sales TO '/tmp/out.csv'",
]

REPAIRABLE = [
    "SELEC name FROM dealers",
    "SELECT nme FROM dealers",
    "SELECT name FROM dealer",
    "SELECT d.name FROM dealers d, sales s",
    "SELECT name FROM dealers -- yorum",
    "",
]

APPROVED = [
    "SELECT name, city FROM dealers WHERE city = 'Trabzon'",
    "SELECT d.name, SUM(s.total_amount) AS total FROM dealers d JOIN sales s ON s.dealer_id = d.dealer_id "
    "GROUP BY d.name ORDER BY total DESC LIMIT 5",
    "WITH t AS (SELECT dealer_id, SUM(total_amount) AS amt FROM sales GROUP BY dealer_id) "
    "SELECT d.name, t.amt FROM t JOIN dealers d ON d.dealer_id = t.dealer_id",
    "SELECT COUNT(*) FROM sales",
    "SELECT sales.* FROM sales",
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


def test_rejection_message_does_not_name_hidden_table(
    schema: SchemaSnapshot, analyst: AuthContext, candidate: Callable[[str], SQLCandidate]
) -> None:
    report = V.validate(candidate("SELECT * FROM salaries"), schema, analyst)
    assert all("salaries" not in f.message for f in report.failures)
