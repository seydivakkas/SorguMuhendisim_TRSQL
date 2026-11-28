"""Evaluation metrics for TRSQL (AR-08)."""

from __future__ import annotations

from benchmarks.metrics.execution import (
    ExecutionComparison,
    execute_postgres_readonly,
    execution_accuracy,
    has_top_level_order_by,
    normalize_rows,
    normalize_value,
    results_match,
    results_match_sql,
    valid_efficiency_score,
    ves,
)
from benchmarks.metrics.linking import (
    ExtractedSchema,
    SchemaLinkingMetrics,
    SchemaLinkingSample,
    extract_gold_tables_and_columns,
)
from benchmarks.metrics.safety import (
    AbstentionMetrics,
    AbstentionRecord,
    SafetyMetrics,
    SafetyRecord,
    is_sql_potentially_unsafe,
)
from benchmarks.metrics.test_suite import (
    SnapshotExecutor,
    TestSuiteCase,
    TestSuiteItemResult,
    TestSuiteSummary,
    evaluate_test_suite,
    evaluate_test_suite_case,
    execute_sqlite_readonly,
    test_suite_accuracy,
    test_suite_accuracy_from_results,
)
from benchmarks.metrics.validity import (
    ValidityReport,
    compute_validity_metrics,
    has_schema_hallucination,
    is_executable_sql,
    is_parseable_sql,
)

__all__ = [
    "AbstentionMetrics",
    "AbstentionRecord",
    "ExecutionComparison",
    "ExtractedSchema",
    "SafetyMetrics",
    "SafetyRecord",
    "SchemaLinkingMetrics",
    "SchemaLinkingSample",
    "SnapshotExecutor",
    "TestSuiteCase",
    "TestSuiteItemResult",
    "TestSuiteSummary",
    "ValidityReport",
    "compute_validity_metrics",
    "evaluate_test_suite",
    "evaluate_test_suite_case",
    "execute_postgres_readonly",
    "execute_sqlite_readonly",
    "execution_accuracy",
    "extract_gold_tables_and_columns",
    "has_schema_hallucination",
    "has_top_level_order_by",
    "is_executable_sql",
    "is_parseable_sql",
    "is_sql_potentially_unsafe",
    "normalize_rows",
    "normalize_value",
    "results_match",
    "results_match_sql",
    "test_suite_accuracy",
    "test_suite_accuracy_from_results",
    "valid_efficiency_score",
    "ves",
]
