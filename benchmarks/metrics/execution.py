"""BIRD/Spider-compliant Execution Accuracy (EX) and Valid Efficiency Score (VES)."""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, overload

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError


@dataclass(frozen=True)
class ExecutionComparison:
    """Single prediction vs. gold result comparison item."""

    gold_sql: str
    gold_rows: tuple[tuple[Any, ...], ...]
    pred_rows: tuple[tuple[Any, ...], ...]
    gold_ms: float = 0.0
    pred_ms: float = 0.0
    pred_valid: bool = True
    dialect: str | None = None


def has_top_level_order_by(sql: str, dialect: str | None = None) -> bool:
    """Return True iff ``sql`` has a top-level ``ORDER BY`` clause."""
    stripped = sql.strip()
    if not stripped:
        return False
    try:
        tree = sqlglot.parse_one(stripped, read=dialect)
    except ParseError:
        return False
    while isinstance(tree, exp.Subquery):
        tree = tree.this
    if not isinstance(tree, exp.Query):
        return False
    return tree.args.get("order") is not None


def normalize_value(value: Any, decimals: int = 4) -> tuple[int, Any]:
    """Convert a DB cell into a hashable, comparable canonical tuple."""
    if value is None:
        return (0, 0)
    if isinstance(value, bool):
        return (1, value)
    if isinstance(value, (int, float, Decimal)):
        num = float(value)
        if math.isnan(num):
            return (2, "nan")
        if math.isinf(num):
            return (2, "inf" if num > 0 else "-inf")
        rounded = round(num, decimals)
        if rounded == 0:
            return (2, 0)
        if rounded.is_integer():
            return (2, int(rounded))
        return (2, rounded)
    if isinstance(value, (datetime, date)):
        return (3, value.isoformat())
    if isinstance(value, str):
        return (3, value)
    if isinstance(value, bytes):
        return (4, value)
    return (5, str(value))


def normalize_rows(
    rows: Sequence[Sequence[Any]],
    decimals: int = 4,
) -> list[tuple[tuple[int, Any], ...]]:
    """Normalize every cell in a result table."""
    return [tuple(normalize_value(cell, decimals=decimals) for cell in row) for row in rows]


def _match_unordered_columns(
    norm_gold: list[tuple[tuple[int, Any], ...]],
    norm_pred: list[tuple[tuple[int, Any], ...]],
) -> bool:
    num_cols = len(norm_gold[0])
    gold_cols = [tuple(row[c] for row in norm_gold) for c in range(num_cols)]
    pred_cols = [tuple(row[c] for row in norm_pred) for c in range(num_cols)]

    gold_sigs = [tuple(sorted(col)) for col in gold_cols]
    pred_sigs = [tuple(sorted(col)) for col in pred_cols]
    if Counter(gold_sigs) != Counter(pred_sigs):
        return False

    pred_by_sig: dict[tuple[tuple[int, Any], ...], list[int]] = defaultdict(list)
    for idx, sig in enumerate(pred_sigs):
        pred_by_sig[sig].append(idx)

    # Order gold columns by fewest candidate matches first for fast pruning.
    gold_order = sorted(range(num_cols), key=lambda idx: len(pred_by_sig[gold_sigs[idx]]))

    gold_prefix_counters = [
        Counter(tuple(gold_cols[gold_order[k]][r] for k in range(depth + 1)) for r in range(len(norm_gold)))
        for depth in range(num_cols)
    ]

    used = [False] * num_cols
    perm = [0] * num_cols

    def backtrack(depth: int) -> bool:
        if depth == num_cols:
            return True
        g_idx = gold_order[depth]
        target_counter = gold_prefix_counters[depth]
        seen_vectors: set[tuple[tuple[int, Any], ...]] = set()
        for p_idx in pred_by_sig[gold_sigs[g_idx]]:
            if used[p_idx]:
                continue
            vec = pred_cols[p_idx]
            if vec in seen_vectors:
                continue
            seen_vectors.add(vec)
            perm[depth] = p_idx
            proj = Counter(
                tuple(pred_cols[perm[k]][r] for k in range(depth + 1)) for r in range(len(norm_pred))
            )
            if proj != target_counter:
                continue
            used[p_idx] = True
            if backtrack(depth + 1):
                return True
            used[p_idx] = False
        return False

    return backtrack(0)


def results_match(
    gold_rows: Sequence[Sequence[Any]],
    pred_rows: Sequence[Sequence[Any]],
    *,
    order_matters: bool = False,
    decimals: int = 4,
    ignore_column_order: bool = True,
) -> bool:
    """Compare execution result sets using BIRD/Spider semantics.

    * Empty tables match empty tables regardless of column metadata.
    * Row counts and column counts must match.
    * Column names are always ignored; column order is ignored when
      ``ignore_column_order=True``.
    * Duplicate row multiplicities are preserved via ``Counter``.
    * Row order is enforced iff ``order_matters=True``.
    """
    if len(gold_rows) != len(pred_rows):
        return False
    if not gold_rows:
        return True

    num_cols = len(gold_rows[0])
    if any(len(row) != num_cols for row in gold_rows) or any(len(row) != num_cols for row in pred_rows):
        return False
    if num_cols == 0:
        return True

    norm_gold = normalize_rows(gold_rows, decimals=decimals)
    norm_pred = normalize_rows(pred_rows, decimals=decimals)

    if order_matters:
        if norm_gold == norm_pred:
            return True
        if not ignore_column_order or num_cols == 1:
            return False
        gold_cols = [tuple(row[c] for row in norm_gold) for c in range(num_cols)]
        pred_cols = [tuple(row[c] for row in norm_pred) for c in range(num_cols)]
        return Counter(gold_cols) == Counter(pred_cols)

    if Counter(norm_gold) == Counter(norm_pred):
        return True
    if not ignore_column_order or num_cols == 1:
        return False
    return _match_unordered_columns(norm_gold, norm_pred)


def results_match_sql(
    gold_sql: str,
    gold_rows: Sequence[Sequence[Any]],
    pred_rows: Sequence[Sequence[Any]],
    *,
    dialect: str | None = None,
    decimals: int = 4,
    ignore_column_order: bool = True,
) -> bool:
    """Compare execution results using ``gold_sql`` to infer top-level ORDER BY."""
    order_matters = has_top_level_order_by(gold_sql, dialect=dialect)
    return results_match(
        gold_rows,
        pred_rows,
        order_matters=order_matters,
        decimals=decimals,
        ignore_column_order=ignore_column_order,
    )


def execution_accuracy(
    items: Sequence[bool | ExecutionComparison],
    *,
    decimals: int = 4,
    ignore_column_order: bool = True,
) -> float:
    """Compute Execution Accuracy (EX) across boolean outcomes or comparison objects."""
    if not items:
        return 0.0
    hits = 0
    for item in items:
        if isinstance(item, bool):
            hits += int(item)
        else:
            matched = item.pred_valid and results_match_sql(
                item.gold_sql,
                item.gold_rows,
                item.pred_rows,
                dialect=item.dialect,
                decimals=decimals,
                ignore_column_order=ignore_column_order,
            )
            hits += int(matched)
    return hits / len(items)


def _single_ves(matched: bool, gold_ms: float, pred_ms: float, cap_ratio: float | None) -> float:
    if not matched:
        return 0.0
    if gold_ms <= 0.0 and pred_ms <= 0.0:
        return 1.0
    if gold_ms <= 0.0:
        return 1.0
    denom = max(pred_ms, 1e-3)
    ratio = gold_ms / denom
    if cap_ratio is not None:
        ratio = min(ratio, cap_ratio)
    return math.sqrt(ratio)


@overload
def valid_efficiency_score(
    items: Sequence[ExecutionComparison | tuple[bool, float, float]],
    *,
    decimals: int = 4,
    cap_ratio: float | None = None,
) -> float: ...


@overload
def valid_efficiency_score(
    items: Sequence[bool],
    gold_times: Sequence[float],
    pred_times: Sequence[float],
    *,
    decimals: int = 4,
    cap_ratio: float | None = None,
) -> float: ...


def valid_efficiency_score(
    items: Sequence[ExecutionComparison | tuple[bool, float, float] | bool],
    gold_times: Sequence[float] | None = None,
    pred_times: Sequence[float] | None = None,
    *,
    decimals: int = 4,
    cap_ratio: float | None = None,
) -> float:
    """Compute BIRD Valid Efficiency Score (VES) = mean(1(match) * sqrt(gold_ms / pred_ms))."""
    if not items:
        return 0.0

    if gold_times is not None or pred_times is not None:
        if gold_times is None or pred_times is None:
            raise ValueError("gold_times ve pred_times birlikte verilmelidir.")
        if not (len(items) == len(gold_times) == len(pred_times)):
            raise ValueError("items, gold_times ve pred_times uzunlukları eşit olmalıdır.")
        scores = [
            _single_ves(bool(m), float(g), float(p), cap_ratio)
            for m, g, p in zip(items, gold_times, pred_times, strict=True)
        ]
        return sum(scores) / len(scores)

    total = 0.0
    for item in items:
        if isinstance(item, ExecutionComparison):
            matched = item.pred_valid and results_match_sql(
                item.gold_sql,
                item.gold_rows,
                item.pred_rows,
                dialect=item.dialect,
                decimals=decimals,
            )
            total += _single_ves(matched, item.gold_ms, item.pred_ms, cap_ratio)
        elif isinstance(item, tuple):
            matched, gold_ms, pred_ms = item
            total += _single_ves(bool(matched), float(gold_ms), float(pred_ms), cap_ratio)
        else:
            raise TypeError(
                "VES için ExecutionComparison, (matched, gold_ms, pred_ms) veya zaman listesi gerekir."
            )
    return total / len(items)


ves = valid_efficiency_score


def execute_postgres_readonly(
    adapter: object,
    sql: str,
    *,
    schema: object | None = None,
    timeout_ms: int = 5000,
    max_rows: int = 10_000,
) -> tuple[bool, tuple[tuple[Any, ...], ...], str | None]:
    """Execute gold SQL read-only via :class:`PostgresAdapter` (no direct psycopg import).

    The candidate query passes through :class:`SQLValidator` and
    :class:`PolicyEngine` so it enters the adapter solely as an
    :class:`ApprovedQuery` enforcing ``SET TRANSACTION READ ONLY``,
    ``statement_timeout``, and ``search_path``.
    """
    from backend.core.config import ExecutionSettings, ValidationSettings
    from backend.core.contracts import AuthContext, Dialect, SchemaSnapshot, SQLCandidate
    from backend.core.errors import TRSQLError
    from backend.core.ports import DatabaseAdapter
    from backend.policy_engine import PolicyEngine
    from backend.sql_validator import SQLValidator

    db: DatabaseAdapter = adapter  # type: ignore[assignment]
    snap = schema if isinstance(schema, SchemaSnapshot) else db.introspect()
    auth = AuthContext(
        user_id="gold-eval",
        tenant_id="benchmark",
        allowed_tables=snap.table_names,
        denied_columns=frozenset(),
        max_rows=max_rows,
    )
    candidate = SQLCandidate(sql=sql, dialect=Dialect.POSTGRES, model_id="gold", attempt=1)
    validator = SQLValidator(ValidationSettings(max_explain_rows=max_rows))
    report = validator.validate(candidate, snap, auth)
    try:
        approved = PolicyEngine(ExecutionSettings(timeout_ms=timeout_ms, max_rows=max_rows)).approve(
            report, auth
        )
        result = db.execute(approved)
        return True, result.rows, None
    except TRSQLError as exc:
        return False, (), str(exc)


__all__ = [
    "ExecutionComparison",
    "execute_postgres_readonly",
    "execution_accuracy",
    "has_top_level_order_by",
    "normalize_rows",
    "normalize_value",
    "results_match",
    "results_match_sql",
    "valid_efficiency_score",
    "ves",
]
