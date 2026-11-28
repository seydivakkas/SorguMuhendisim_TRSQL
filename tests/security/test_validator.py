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


# --- AR-07: semantic, business-rule, cost, EXPLAIN JSON & policy checks -----

SEMANTIC_REPAIRABLE = [
    "SELECT city, COUNT(dealer_id) FROM dealers",
    "SELECT dealer_id, COUNT(*) FROM sales",
    "SELECT city, name, COUNT(dealer_id) FROM dealers GROUP BY city",
    "SELECT dealer_id, status, COUNT(*) FROM sales GROUP BY dealer_id",
    "SELECT name FROM dealers HAVING city = 'Trabzon'",
    "SELECT SUM(MAX(total_amount)) FROM sales",
    "SELECT name AS x, city AS x FROM dealers",
    "SELECT name, city AS name FROM dealers",
    "SELECT total_amount FROM sales WHERE SUM(total_amount) > 100",
]

SEMANTIC_APPROVED = [
    "SELECT d.name, SUM(s.total_amount) OVER (PARTITION BY d.city) AS city_total "
    "FROM dealers d JOIN sales s ON s.dealer_id = d.dealer_id",
    "SELECT COUNT(*) FROM sales HAVING COUNT(*) > 1",
    "SELECT d.city, SUM(s.total_amount) AS total "
    "FROM dealers d JOIN sales s ON s.dealer_id = d.dealer_id GROUP BY 1",
    "SELECT d.city AS sehir, SUM(s.total_amount) AS total "
    "FROM dealers d JOIN sales s ON s.dealer_id = d.dealer_id GROUP BY sehir",
]


@pytest.mark.parametrize("sql", SEMANTIC_REPAIRABLE)
def test_semantic_rejects_invalid_queries(
    sql: str, schema: SchemaSnapshot, analyst: AuthContext, candidate: Callable[[str], SQLCandidate]
) -> None:
    from backend.core.contracts import CheckName

    report = V.validate(candidate(sql), schema, analyst)
    assert report.verdict is Verdict.REPAIRABLE, sql
    assert any(f.check is CheckName.SEMANTIC for f in report.failures)


@pytest.mark.parametrize("sql", SEMANTIC_APPROVED)
def test_semantic_allows_valid_queries(
    sql: str, schema: SchemaSnapshot, analyst: AuthContext, candidate: Callable[[str], SQLCandidate]
) -> None:
    report = V.validate(candidate(sql), schema, analyst)
    assert report.verdict is Verdict.APPROVED, report.failures


def test_business_rule_net_revenue_requires_return_and_status_filter(
    schema: SchemaSnapshot,
    analyst: AuthContext,
    knowledge: object,
    candidate: Callable[[str], SQLCandidate],
) -> None:
    from backend.core.contracts import CheckName, KnowledgeContext
    from backend.knowledge_base import InMemoryKnowledgeBase

    assert isinstance(knowledge, InMemoryKnowledgeBase)
    ctx = KnowledgeContext(
        rules=knowledge.rules,
        metrics=knowledge.metrics,
    )
    q = "Geçen ay net ciro ne kadardı?"

    bad_no_return = V.validate(
        candidate("SELECT SUM(total_amount) FROM sales WHERE status <> 'cancelled'"),
        schema,
        analyst,
        knowledge=ctx,
        question=q,
    )
    assert bad_no_return.verdict is Verdict.REPAIRABLE
    assert any(f.check is CheckName.BUSINESS_RULE for f in bad_no_return.failures)

    bad_no_status = V.validate(
        candidate("SELECT SUM(total_amount - return_amount) FROM sales"),
        schema,
        analyst,
        knowledge=ctx,
        question=q,
    )
    assert bad_no_status.verdict is Verdict.REPAIRABLE
    assert any(f.check is CheckName.BUSINESS_RULE for f in bad_no_status.failures)

    good = V.validate(
        candidate("SELECT SUM(total_amount - return_amount) FROM sales WHERE status <> 'cancelled'"),
        schema,
        analyst,
        knowledge=ctx,
        question=q,
    )
    assert good.verdict is Verdict.APPROVED, good.failures


def test_cost_checks_recursive_series_and_subqueries(
    schema: SchemaSnapshot, analyst: AuthContext, candidate: Callable[..., SQLCandidate]
) -> None:
    from backend.core.contracts import CheckName

    unbounded_rec = V.validate(
        candidate("WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM c) SELECT COUNT(*) FROM c"),
        schema,
        analyst,
    )
    assert unbounded_rec.verdict is Verdict.REPAIRABLE
    assert any(f.check is CheckName.COST for f in unbounded_rec.failures)

    bounded_rec = V.validate(
        candidate(
            "WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM c WHERE x < 10) "
            "SELECT COUNT(*) FROM c"
        ),
        schema,
        analyst,
    )
    assert bounded_rec.verdict is Verdict.APPROVED, bounded_rec.failures

    huge_series = V.validate(
        candidate("SELECT * FROM generate_series(1, 10000000)", Dialect.POSTGRES),
        schema,
        analyst,
    )
    assert huge_series.verdict is Verdict.REPAIRABLE
    assert any(f.check is CheckName.COST for f in huge_series.failures)

    small_series = V.validate(
        candidate("SELECT * FROM generate_series(1, 10)", Dialect.POSTGRES),
        schema,
        analyst,
    )
    assert small_series.verdict is Verdict.APPROVED, small_series.failures

    deep_subquery = V.validate(
        candidate(
            "SELECT * FROM (SELECT * FROM (SELECT * FROM (SELECT * FROM (SELECT * FROM "
            "(SELECT sale_id FROM sales) a) b) c) d) e"
        ),
        schema,
        analyst,
    )
    assert deep_subquery.verdict is Verdict.REPAIRABLE
    assert any(f.check is CheckName.COST for f in deep_subquery.failures)


def test_evaluate_explain_plan_rejects_risky_and_accepts_safe() -> None:
    from backend.sql_validator import evaluate_explain_plan

    safe_plan = [{"Plan": {"Node Type": "Index Scan", "Total Cost": 12.5, "Plan Rows": 15}}]
    assert evaluate_explain_plan(safe_plan).passed

    limit_seq = [
        {
            "Plan": {
                "Node Type": "Limit",
                "Total Cost": 0.45,
                "Plan Rows": 10,
                "Plans": [{"Node Type": "Seq Scan", "Total Cost": 50000.0, "Plan Rows": 1000000}],
            }
        }
    ]
    assert evaluate_explain_plan(limit_seq).passed

    full_scan = [{"Plan": {"Node Type": "Seq Scan", "Total Cost": 2500.0, "Plan Rows": 500000}}]
    assert not evaluate_explain_plan(full_scan).passed

    over_cost = [
        {
            "Plan": {
                "Node Type": "Hash Join",
                "Hash Cond": "(a = b)",
                "Total Cost": 2_000_000.0,
                "Plan Rows": 100,
            }
        }
    ]
    assert not evaluate_explain_plan(over_cost, max_cost=1_000_000.0).passed

    cartesian = [
        {
            "Plan": {
                "Node Type": "Nested Loop",
                "Join Type": "Inner",
                "Total Cost": 500.0,
                "Plan Rows": 10000,
                "Plans": [
                    {"Node Type": "Seq Scan", "Total Cost": 10.0, "Plan Rows": 100},
                    {"Node Type": "Seq Scan", "Total Cost": 10.0, "Plan Rows": 100},
                ],
            }
        }
    ]
    assert not evaluate_explain_plan(cartesian).passed


def test_policy_engine_caps_union_cte_and_rejects_forged(
    schema: SchemaSnapshot, analyst: AuthContext, candidate: Callable[..., SQLCandidate]
) -> None:
    from backend.core.config import ExecutionSettings
    from backend.core.contracts import CheckName, CheckResult, ValidationReport
    from backend.core.errors import SecurityViolation
    from backend.policy_engine import PolicyEngine

    pe = PolicyEngine(ExecutionSettings(max_rows=1000))

    union_cand = candidate("SELECT name FROM dealers UNION SELECT city FROM dealers")
    union_report = V.validate(union_cand, schema, analyst)
    assert union_report.verdict is Verdict.APPROVED
    assert pe.approve(union_report, analyst).sql.endswith("LIMIT 100")

    cte_cand = candidate("WITH d AS (SELECT name FROM dealers) SELECT name FROM d LIMIT 5000")
    cte_report = V.validate(cte_cand, schema, analyst)
    assert cte_report.verdict is Verdict.APPROVED
    assert pe.approve(cte_report, analyst).sql.endswith("LIMIT 100")

    forged_cand = candidate("DROP TABLE sales")
    forged_report = ValidationReport(
        candidate=forged_cand,
        checks=(CheckResult(check=CheckName.SYNTAX, passed=True),),
    )
    with pytest.raises(SecurityViolation):
        pe.approve(forged_report, analyst)
