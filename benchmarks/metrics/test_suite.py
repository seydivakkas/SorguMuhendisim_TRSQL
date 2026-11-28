"""Test Suite Accuracy across multiple mutated database snapshots."""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

from benchmarks.metrics.execution import has_top_level_order_by, results_match

_ALLOWED_ACTIONS = frozenset({
    sqlite3.SQLITE_SELECT,
    sqlite3.SQLITE_READ,
    sqlite3.SQLITE_FUNCTION,
    sqlite3.SQLITE_RECURSIVE,
})  # fmt: skip


def _ro_authorizer(
    action: int,
    arg1: str | None,
    arg2: str | None,
    db: str | None,
    src: str | None,
) -> int:
    if action in _ALLOWED_ACTIONS:
        if action == sqlite3.SQLITE_READ and arg1 and arg1.lower().startswith("sqlite_"):
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK
    return sqlite3.SQLITE_DENY


def execute_sqlite_readonly(
    db_path: str | Path,
    sql: str,
    *,
    timeout_ms: int = 5000,
    max_rows: int = 10_000,
) -> tuple[bool, tuple[tuple[Any, ...], ...], str | None]:
    """Execute SQL safely against a read-only SQLite database snapshot."""
    p = Path(db_path)
    if not p.exists():
        return False, (), f"veritabanı bulunamadı: {p}"
    conn = sqlite3.connect(f"{p.resolve().as_uri()}?mode=ro", uri=True)
    try:
        conn.execute("PRAGMA query_only = ON")
        conn.set_authorizer(_ro_authorizer)
        deadline = time.monotonic() + timeout_ms / 1000.0
        conn.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 1000)
        cur = conn.execute(sql)
        rows = tuple(tuple(r) for r in cur.fetchmany(max_rows))
        return True, rows, None
    except sqlite3.Error as exc:
        return False, (), str(exc)
    finally:
        conn.close()


SnapshotExecutor = Callable[[Path, str], tuple[bool, tuple[tuple[Any, ...], ...], str | None]]


@dataclass(frozen=True)
class TestSuiteCase:
    """Gold vs. predicted SQL pair to evaluate across multiple DB snapshots."""

    __test__: ClassVar[bool] = False
    gold_sql: str
    pred_sql: str
    dialect: str = "sqlite"


@dataclass(frozen=True)
class TestSuiteItemResult:
    """Per-question outcome across all snapshots in a test suite."""

    __test__: ClassVar[bool] = False
    passed: bool
    snapshots_passed: int
    snapshots_total: int
    error: str | None = None


@dataclass(frozen=True)
class TestSuiteSummary:
    """Aggregated Test Suite Accuracy report."""

    __test__: ClassVar[bool] = False
    accuracy: float
    passed_count: int
    total: int
    results: tuple[TestSuiteItemResult, ...]


def evaluate_test_suite_case(
    gold_sql: str,
    pred_sql: str,
    db_paths: Sequence[str | Path],
    *,
    dialect: str = "sqlite",
    decimals: int = 4,
    timeout_ms: int = 5000,
    max_rows: int = 10_000,
    executor: SnapshotExecutor | None = None,
) -> TestSuiteItemResult:
    """Evaluate one (gold_sql, pred_sql) pair across every snapshot in ``db_paths``."""
    paths = [Path(p) for p in db_paths]
    if not paths:
        raise ValueError("Test Suite değerlendirmesi için en az bir DB anlık görüntüsü gerekir.")

    if not pred_sql.strip():
        return TestSuiteItemResult(
            passed=False,
            snapshots_passed=0,
            snapshots_total=len(paths),
            error="empty predicted SQL",
        )

    run_sql = executor or (
        lambda p, s: execute_sqlite_readonly(p, s, timeout_ms=timeout_ms, max_rows=max_rows)
    )
    order_matters = has_top_level_order_by(gold_sql, dialect=dialect)

    snapshots_passed = 0
    first_error: str | None = None
    for db_path in paths:
        gold_ok, gold_rows, gold_err = run_sql(db_path, gold_sql)
        if not gold_ok:
            raise ValueError(f"Altın SQL {db_path.name} üzerinde çalıştırılamadı: {gold_err}")
        pred_ok, pred_rows, pred_err = run_sql(db_path, pred_sql)
        if not pred_ok:
            if first_error is None:
                first_error = pred_err or "execution failed"
            continue
        if results_match(gold_rows, pred_rows, order_matters=order_matters, decimals=decimals):
            snapshots_passed += 1
        elif first_error is None:
            first_error = f"result mismatch on {db_path.name}"

    return TestSuiteItemResult(
        passed=snapshots_passed == len(paths),
        snapshots_passed=snapshots_passed,
        snapshots_total=len(paths),
        error=first_error if snapshots_passed < len(paths) else None,
    )


def evaluate_test_suite(
    cases: Sequence[TestSuiteCase],
    db_paths: Sequence[str | Path],
    *,
    decimals: int = 4,
    timeout_ms: int = 5000,
    max_rows: int = 10_000,
    executor: SnapshotExecutor | None = None,
) -> TestSuiteSummary:
    """Compute Test Suite Accuracy across multiple mutated DB snapshots."""
    if not cases:
        return TestSuiteSummary(accuracy=0.0, passed_count=0, total=0, results=())

    results = tuple(
        evaluate_test_suite_case(
            case.gold_sql,
            case.pred_sql,
            db_paths,
            dialect=case.dialect,
            decimals=decimals,
            timeout_ms=timeout_ms,
            max_rows=max_rows,
            executor=executor,
        )
        for case in cases
    )
    passed = sum(1 for r in results if r.passed)
    return TestSuiteSummary(
        accuracy=passed / len(results),
        passed_count=passed,
        total=len(results),
        results=results,
    )


def test_suite_accuracy(
    cases: Sequence[TestSuiteCase],
    db_paths: Sequence[str | Path],
    *,
    decimals: int = 4,
    timeout_ms: int = 5000,
    max_rows: int = 10_000,
    executor: SnapshotExecutor | None = None,
) -> float:
    """Return Test Suite Accuracy (fraction of cases passing ALL DB snapshots)."""
    return evaluate_test_suite(
        cases,
        db_paths,
        decimals=decimals,
        timeout_ms=timeout_ms,
        max_rows=max_rows,
        executor=executor,
    ).accuracy


def test_suite_accuracy_from_results(
    case_snapshots: Sequence[Sequence[tuple[Sequence[Sequence[Any]], Sequence[Sequence[Any]], bool]]],
    *,
    decimals: int = 4,
) -> float:
    """Compute Test Suite Accuracy from pre-executed ``(gold_rows, pred_rows, order_matters)`` suites."""
    if not case_snapshots:
        return 0.0
    passed = 0
    for snapshots in case_snapshots:
        if snapshots and all(
            results_match(gold_rows, pred_rows, order_matters=order_matters, decimals=decimals)
            for gold_rows, pred_rows, order_matters in snapshots
        ):
            passed += 1
    return passed / len(case_snapshots)


for _fn in (test_suite_accuracy, test_suite_accuracy_from_results):
    object.__setattr__(_fn, "__test__", False)


__all__ = [
    "SnapshotExecutor",
    "TestSuiteCase",
    "TestSuiteItemResult",
    "TestSuiteSummary",
    "evaluate_test_suite",
    "evaluate_test_suite_case",
    "execute_sqlite_readonly",
    "test_suite_accuracy",
    "test_suite_accuracy_from_results",
]
