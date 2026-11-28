from __future__ import annotations

import math
import sqlite3
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from backend.core.contracts import (
    ColumnInfo,
    Dialect,
    LinkedSchema,
    OutcomeStatus,
    SchemaLink,
    SchemaSnapshot,
    TableInfo,
)
from benchmarks.metrics import (
    AbstentionMetrics,
    AbstentionRecord,
    ExecutionComparison,
    SafetyMetrics,
    SafetyRecord,
    SchemaLinkingMetrics,
    SchemaLinkingSample,
    TestSuiteCase,
    compute_validity_metrics,
    evaluate_test_suite,
    execution_accuracy,
    extract_gold_tables_and_columns,
    has_schema_hallucination,
    has_top_level_order_by,
    is_parseable_sql,
    results_match,
    results_match_sql,
    test_suite_accuracy_from_results,
    ves,
)
from benchmarks.report import (
    ExperimentRecord,
    format_comparison_markdown,
    mcnemar_test,
    paired_bootstrap_ci,
)


def test_execution_row_order_ignored_without_order_by() -> None:
    gold_sql = "SELECT name, city FROM dealers WHERE city = 'Trabzon'"
    assert not has_top_level_order_by(gold_sql, dialect="sqlite")
    gold_rows = [("Bayi A", "Trabzon"), ("Bayi B", "Trabzon")]
    pred_rows = [("Bayi B", "Trabzon"), ("Bayi A", "Trabzon")]
    assert results_match_sql(gold_sql, gold_rows, pred_rows, dialect="sqlite")


def test_execution_row_order_enforced_with_top_level_order_by() -> None:
    gold_sql = (
        "SELECT name, total_amount FROM dealers d "
        "JOIN sales s ON s.dealer_id = d.dealer_id ORDER BY total_amount DESC"
    )
    assert has_top_level_order_by(gold_sql, dialect="sqlite")
    gold_rows = [("Bayi A", 1000), ("Bayi B", 980)]
    pred_rows_wrong_order = [("Bayi B", 980), ("Bayi A", 1000)]
    assert not results_match_sql(gold_sql, gold_rows, pred_rows_wrong_order, dialect="sqlite")
    assert results_match_sql(gold_sql, gold_rows, list(gold_rows), dialect="sqlite")


def test_subquery_order_by_is_not_top_level() -> None:
    sql = (
        "WITH top_sales AS (SELECT dealer_id FROM sales ORDER BY total_amount DESC) "
        "SELECT dealer_id FROM top_sales"
    )
    assert not has_top_level_order_by(sql, dialect="sqlite")
    union_sql = "SELECT name FROM dealers UNION SELECT status FROM sales ORDER BY 1"
    assert has_top_level_order_by(union_sql, dialect="sqlite")


def test_execution_ignores_column_order_and_rejects_cross_row_mismatch() -> None:
    gold = [("Bayi A", 100), ("Bayi B", 200)]
    pred_swapped_cols = [(200, "Bayi B"), (100, "Bayi A")]
    assert results_match(gold, pred_swapped_cols, order_matters=False)

    # Same individual column multisets {1, 2}, different row pairings -> MUST NOT match
    assert not results_match([(1, 2), (2, 1)], [(1, 1), (2, 2)], order_matters=False)
    # Ordered rows with swapped columns still match if row order is preserved
    assert results_match(gold, [(100, "Bayi A"), (200, "Bayi B")], order_matters=True)
    assert not results_match(gold, [(200, "Bayi B"), (100, "Bayi A")], order_matters=True)


def test_execution_float_tolerance_and_duplicate_multiset() -> None:
    assert results_match([(1.23451,)], [(1.23454,)], decimals=4)
    assert not results_match([(1.2345,)], [(1.2351,)], decimals=4)
    assert results_match([(Decimal("10.0"),), (None,)], [(10,), (None,)], decimals=4)
    assert results_match([(date(2026, 10, 5),)], [("2026-10-05",)])

    # Multiset duplicate counts: {1, 1, 2} != {1, 2, 2}
    assert not results_match([(1,), (1,), (2,)], [(1,), (2,), (2,)], order_matters=False)
    assert results_match([(1,), (1,), (2,)], [(2,), (1,), (1,)], order_matters=False)


def test_execution_accuracy_and_ves() -> None:
    comps = [
        ExecutionComparison(
            gold_sql="SELECT COUNT(*) FROM dealers",
            gold_rows=((5,),),
            pred_rows=((5,),),
            gold_ms=16.0,
            pred_ms=4.0,
        ),
        ExecutionComparison(
            gold_sql="SELECT name FROM dealers ORDER BY name",
            gold_rows=(("Bayi A",), ("Bayi B",)),
            pred_rows=(("Bayi B",), ("Bayi A",)),
            gold_ms=10.0,
            pred_ms=2.0,
        ),
    ]
    assert execution_accuracy(comps) == pytest.approx(0.5)
    # First matches with sqrt(16/4) = 2.0, second fails -> 0.0 => mean 1.0
    assert ves(comps) == pytest.approx(1.0)
    assert ves([True, False], [9.0, 9.0], [1.0, 1.0]) == pytest.approx(1.5)


def _create_mutated_db(path: Path, rows: list[tuple[int, str, str]]) -> Path:
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE dealers (dealer_id INTEGER PRIMARY KEY, name TEXT, city TEXT)")
    conn.executemany("INSERT INTO dealers VALUES (?, ?, ?)", rows)
    conn.commit()
    conn.close()
    return path


def test_test_suite_accuracy_across_mutated_snapshots(tmp_path: Path) -> None:
    db1 = _create_mutated_db(tmp_path / "s1.sqlite", [(1, "A", "Trabzon"), (2, "B", "Trabzon")])
    db2 = _create_mutated_db(tmp_path / "s2.sqlite", [(1, "A", "Trabzon"), (2, "B", "Ankara")])
    db3 = _create_mutated_db(tmp_path / "s3.sqlite", [(1, "A", "Rize"), (2, "B", "Trabzon")])

    cases = [
        # Buggy query drops WHERE city='Trabzon': passes on db1 by coincidence, fails on db2 & db3!
        TestSuiteCase(
            gold_sql="SELECT name FROM dealers WHERE city = 'Trabzon'",
            pred_sql="SELECT name FROM dealers",
        ),
        # Equivalent query passes on all 3 mutated DBs
        TestSuiteCase(
            gold_sql="SELECT COUNT(*) FROM dealers WHERE city = 'Trabzon'",
            pred_sql="SELECT COUNT(dealer_id) FROM dealers WHERE city = 'Trabzon'",
        ),
    ]
    summary = evaluate_test_suite(cases, [db1, db2, db3])
    assert summary.total == 2
    assert summary.passed_count == 1
    assert summary.accuracy == pytest.approx(0.5)
    assert summary.results[0].snapshots_passed == 1
    assert summary.results[1].snapshots_passed == 3

    assert test_suite_accuracy_from_results(
        [
            [([(1,)], [(1,)], False), ([(2,)], [(3,)], False)],
            [([(1,)], [(1,)], False), ([(2,)], [(2,)], False)],
        ]
    ) == pytest.approx(0.5)


def test_validity_splits_parseable_and_executable(db_path: Path, schema: SchemaSnapshot) -> None:
    sqls = [
        "SELECT name FROM dealers",  # parseable + executable + valid schema
        "SELECT missing_col FROM dealers",  # parseable, NOT executable, hallucinated
        "SELECT FROM WHERE",  # NOT parseable, NOT executable
        "DROP TABLE dealers",  # parseable SQLGlot, NOT executable in read-only mode
    ]
    report = compute_validity_metrics(sqls, dialect="sqlite", db_path=db_path, schema=schema)
    assert report.total == 4
    assert report.parseable_count == 3
    assert report.executable_count == 1
    assert report.parseable_rate == pytest.approx(0.75)
    assert report.executable_rate == pytest.approx(0.25)
    assert report.hallucination_rate == pytest.approx(0.75)
    assert not is_parseable_sql("")
    assert has_schema_hallucination("SELECT x FROM unknown_tbl", schema)
    assert not has_schema_hallucination("SELECT d.name FROM dealers d", schema)


def test_schema_linking_metrics_sqlglot_extraction(schema: SchemaSnapshot) -> None:
    gold_sql = (
        "SELECT d.name, SUM(s.total_amount - s.return_amount) AS net_sales "
        "FROM dealers d JOIN sales s ON s.dealer_id = d.dealer_id "
        "WHERE d.city = 'Trabzon' GROUP BY d.name ORDER BY net_sales DESC"
    )
    extracted = extract_gold_tables_and_columns(gold_sql, dialect="sqlite", schema=schema)
    assert extracted.tables == frozenset({"dealers", "sales"})
    assert extracted.columns == frozenset(
        {
            "dealers.name",
            "dealers.city",
            "dealers.dealer_id",
            "sales.dealer_id",
            "sales.total_amount",
            "sales.return_amount",
        }
    )

    linked = LinkedSchema(
        tables=("dealers", "sales"),
        links=(
            SchemaLink(mention="bayi", table="dealers", column="name", score=1.0),
            SchemaLink(mention="trabzon", table="dealers", column="city", score=1.0),
            SchemaLink(mention="satış", table="sales", column="total_amount", score=1.0),
        ),
    )
    metrics = SchemaLinkingMetrics.from_linked([gold_sql], [linked], schema=schema)
    assert metrics.table_precision == pytest.approx(1.0)
    assert metrics.table_recall == pytest.approx(1.0)
    assert metrics.table_f1 == pytest.approx(1.0)
    assert metrics.column_precision == pytest.approx(1.0)
    assert metrics.column_recall == pytest.approx(0.5)

    # Unqualified single-table column resolution without explicit SchemaSnapshot
    single = extract_gold_tables_and_columns("SELECT COUNT(*) FROM dealers WHERE city = 'Rize'")
    assert single.tables == frozenset({"dealers"})
    assert single.columns == frozenset({"dealers.city"})

    # Test missing-table penalty
    partial = SchemaLinkingMetrics.evaluate(
        [SchemaLinkingSample(gold_sql=gold_sql, pred_tables=("dealers",))]
    )
    assert partial.table_recall == pytest.approx(0.5)
    assert partial.full_table_recall_rate == pytest.approx(0.0)


def test_safety_and_abstention_metrics() -> None:
    records = [
        SafetyRecord(
            is_attack=True,
            generated_sqls=("DROP TABLE sales",),
            was_rejected=True,
            db_executed=False,
            answerable=False,
        ),
        SafetyRecord(
            is_attack=True,
            generated_sqls=("SELECT amount FROM salaries",),
            was_rejected=True,
            db_executed=False,
            answerable=False,
        ),
        SafetyRecord(
            is_attack=False,
            generated_sqls=("SELECT name FROM dealers",),
            was_rejected=False,
            db_executed=True,
            answerable=True,
        ),
        SafetyRecord(
            is_attack=False,
            generated_sqls=("SELECT name FROM dealers",),
            was_rejected=True,
            db_executed=False,
            answerable=True,
        ),
    ]
    safety = SafetyMetrics.compute(
        records,
        allowed_tables=frozenset({"dealers", "sales"}),
        denied_columns=frozenset({"dealers.tax_number"}),
    )
    assert safety.generated_unsafe_count == 3  # 2 attacks + 1 rejected benign with generated SQL
    assert safety.db_reached_unsafe_count == 0
    assert safety.db_reached_unsafe_rate == pytest.approx(0.0)
    assert safety.attack_capture_rate == pytest.approx(1.0)
    assert safety.false_rejection_rate == pytest.approx(0.5)

    # If an attack reaches DB execution, db_reached_unsafe_rate > 0
    breach = SafetyMetrics.compute(
        [
            SafetyRecord(
                is_attack=True,
                generated_sqls=("SELECT * FROM salaries",),
                was_rejected=False,
                db_executed=True,
                answerable=False,
            )
        ],
        allowed_tables=frozenset({"dealers", "sales"}),
    )
    assert breach.db_reached_unsafe_rate == pytest.approx(1.0)
    assert breach.attack_capture_rate == pytest.approx(0.0)

    abst = AbstentionMetrics.compute(
        [
            AbstentionRecord("ambiguous", OutcomeStatus.NEEDS_CLARIFICATION),
            AbstentionRecord("ambiguous", OutcomeStatus.ANSWERED),
            AbstentionRecord("unanswerable", OutcomeStatus.REJECTED),
            AbstentionRecord("normal", OutcomeStatus.ANSWERED),
        ]
    )
    assert abst.clarification_precision == pytest.approx(1.0)
    assert abst.clarification_recall == pytest.approx(0.5)
    assert abst.clarification_f1 == pytest.approx(2 / 3)
    assert abst.unanswerable_f1 == pytest.approx(1.0)
    assert abst.silent_wrong_sql_rate == pytest.approx(1 / 3)


def test_statistical_tests_and_markdown_report(tmp_path: Path) -> None:
    # Exact McNemar (discordant = 1 + 9 = 10 < 25)
    base = [True] * 10 + [False] * 10 + [True]
    cand = [True] * 10 + [True] * 9 + [False] + [False]
    mcn = mcnemar_test(base, cand)
    assert mcn.exact
    assert mcn.n10 == 1 and mcn.n01 == 9
    assert mcn.p_value < 0.05
    assert mcn.significant

    # Large discordant count uses chi-square
    base_lg = [True] * 5 + [False] * 30
    cand_lg = [False] * 5 + [True] * 30
    mcn_lg = mcnemar_test(base_lg, cand_lg)
    assert not mcn_lg.exact
    assert mcn_lg.p_value < 1e-4

    # Equal predictions -> p=1.0
    mcn_eq = mcnemar_test([True, False], [True, False])
    assert math.isclose(mcn_eq.p_value, 1.0)

    boot = paired_bootstrap_ci(base, cand, n_resamples=2000, seed=42)
    assert boot.ci_low > 0.0
    assert boot.significant
    assert boot.ci_low <= boot.observed_delta <= boot.ci_high

    records = [
        ExperimentRecord(
            model="Qwen3-4B",
            stage="D0",
            dataset="turspider",
            ex=0.50,
            parseable_rate=0.90,
            executable_rate=0.80,
            p95_latency_ms=1200.0,
            peak_vram_mb=4100,
            generated_unsafe_rate=0.10,
            db_reached_unsafe_rate=0.0,
            attack_capture_rate=1.0,
            per_example_correct=tuple(base),
        ),
        ExperimentRecord(
            model="Qwen3-4B",
            stage="D1",
            dataset="turspider",
            ex=0.75,
            parseable_rate=0.95,
            executable_rate=0.90,
            p95_latency_ms=1350.0,
            peak_vram_mb=4200,
            generated_unsafe_rate=0.05,
            db_reached_unsafe_rate=0.0,
            attack_capture_rate=1.0,
            per_example_correct=tuple(cand),
        ),
    ]
    md = format_comparison_markdown(records, bootstrap_resamples=1000)
    assert "Qwen3-4B" in md
    assert "D0" in md and "D1" in md
    assert "+25.0 pp" in md
    assert "McNemar" in md
    assert "Güvenlik Özeti" in md


def test_schema_snapshot_smoke(schema: SchemaSnapshot) -> None:
    # Ensure fixture schema matches expected dialect
    assert schema.dialect is Dialect.SQLITE
    assert isinstance(schema.table("dealers"), TableInfo)
    assert isinstance(schema.table("dealers").column("name"), ColumnInfo)  # type: ignore[union-attr]
