from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

from backend.core.contracts import (
    ColumnInfo,
    ForeignKey,
    LinkedSchema,
    SchemaSnapshot,
    TableInfo,
)

_CONTEXTUAL_COL_NAMES = frozenset(
    {
        "name",
        "ad",
        "adi",
        "title",
        "baslik",
        "city",
        "sehir",
        "status",
        "durum",
        "date",
        "tarih",
        "sale_date",
        "order_date",
        "amount",
        "tutar",
        "total_amount",
        "return_amount",
        "price",
        "fiyat",
        "quantity",
        "miktar",
    }
)


def default_token_counter(text: str) -> int:
    """Fast deterministic token estimator (~4 chars per token)."""
    if not text:
        return 0
    return max(1, math.ceil(len(text) / 4))


def _format_column_line(col: ColumnInfo) -> str:
    pk = ", PK" if col.is_primary_key else ""
    desc = f", {col.description}" if col.description else ""
    return f"  ({col.name}: {col.data_type}{pk}{desc})"


def _format_fk_line(table_name: str, fk: ForeignKey) -> str:
    return f"  FK {table_name}.{fk.column} -> {fk.ref_table}.{fk.ref_column}"


def estimate_table_tokens(
    table: TableInfo,
    *,
    token_counter: Callable[[str], int] | None = None,
) -> int:
    """Estimate prompt tokens for a single :class:`TableInfo`."""
    counter = token_counter or default_token_counter
    head = f"# Table: {table.name}" + (f"  -- {table.description}" if table.description else "")
    total = counter(head)
    for col in table.columns:
        total += counter(_format_column_line(col))
    for fk in table.foreign_keys:
        total += counter(_format_fk_line(table.name, fk))
    return total


def estimate_schema_tokens(
    schema: SchemaSnapshot,
    *,
    token_counter: Callable[[str], int] | None = None,
) -> int:
    """Estimate total prompt tokens for ``schema``."""
    counter = token_counter or default_token_counter
    total = counter(f"【DB_DIALECT】{schema.dialect.value}")
    for table in schema.tables:
        total += estimate_table_tokens(table, token_counter=counter)
    return total


@dataclass(frozen=True)
class _ColumnCandidate:
    table_lower: str
    col: ColumnInfo
    value: float
    cost: int


def _knapsack_select(items: list[_ColumnCandidate], capacity: int) -> set[tuple[str, str]]:
    """KaSLA-style 0/1 knapsack selector (exact DP for moderate capacity, greedy fallback)."""
    if capacity <= 0 or not items:
        return set()

    if capacity <= 2000 and len(items) <= 250:
        dp = [0] * (capacity + 1)
        keep: list[list[bool]] = [[False] * (capacity + 1) for _ in range(len(items))]
        for idx, item in enumerate(items):
            w = item.cost
            v = max(1, round(item.value * 1000))
            if w > capacity:
                continue
            for cap in range(capacity, w - 1, -1):
                cand = dp[cap - w] + v
                if cand > dp[cap]:
                    dp[cap] = cand
                    keep[idx][cap] = True
        chosen: set[tuple[str, str]] = set()
        rem = capacity
        for idx in range(len(items) - 1, -1, -1):
            if keep[idx][rem]:
                item = items[idx]
                chosen.add((item.table_lower, item.col.name.lower()))
                rem -= item.cost
        return chosen

    # High-budget greedy value-density fallback
    ranked = sorted(items, key=lambda x: x.value / max(1, x.cost), reverse=True)
    chosen = set()
    used = 0
    for item in ranked:
        if used + item.cost <= capacity:
            chosen.add((item.table_lower, item.col.name.lower()))
            used += item.cost
    return chosen


def select_schema_within_budget(
    schema: SchemaSnapshot,
    linked: LinkedSchema,
    max_tokens: int,
    *,
    token_counter: Callable[[str], int] | None = None,
    include_unlinked_tables: bool = False,
) -> SchemaSnapshot:
    """KaSLA-inspired token-budget schema selector.

    Ranks tables and columns by link score, preserves PKs and FK columns needed
    for ``linked.join_path``, and uses 0/1 knapsack selection to pack optional
    columns without exceeding ``max_tokens``.
    """
    if max_tokens < 0:
        raise ValueError("max_tokens must be non-negative")
    counter = token_counter or default_token_counter
    dialect_cost = counter(f"【DB_DIALECT】{schema.dialect.value}")
    if max_tokens <= dialect_cost or not schema.tables:
        return SchemaSnapshot(dialect=schema.dialect, tables=())

    # 1. Compute table & column scores and mandatory key sets
    table_scores: dict[str, float] = {}
    col_scores: dict[tuple[str, str], float] = {}
    for lnk in linked.links:
        t_low = lnk.table.lower()
        table_scores[t_low] = max(table_scores.get(t_low, 0.0), lnk.score)
        if lnk.column:
            c_key = (t_low, lnk.column.lower())
            col_scores[c_key] = max(col_scores.get(c_key, 0.0), lnk.score)

    priority_tables: dict[str, None] = {}
    for idx, t_name in enumerate(linked.tables):
        t_low = t_name.lower()
        priority_tables[t_low] = None
        table_scores[t_low] = max(table_scores.get(t_low, 0.5), 0.5 - idx * 0.01)

    join_cols: dict[str, set[str]] = {}
    for step in linked.join_path:
        l_low = step.left_table.lower()
        r_low = step.right_table.lower()
        priority_tables[l_low] = None
        priority_tables[r_low] = None
        table_scores.setdefault(l_low, 0.6)
        table_scores.setdefault(r_low, 0.6)
        join_cols.setdefault(l_low, set()).add(step.left_column.lower())
        join_cols.setdefault(r_low, set()).add(step.right_column.lower())

    table_by_low = {t.name.lower(): t for t in schema.tables}
    if not priority_tables:
        for t in schema.tables:
            priority_tables[t.name.lower()] = None
            table_scores[t.name.lower()] = 0.2
    elif include_unlinked_tables:
        for t in schema.tables:
            t_low = t.name.lower()
            if t_low not in priority_tables:
                priority_tables[t_low] = None
                table_scores[t_low] = 0.05

    ordered_candidates = sorted(
        (t for t in priority_tables if t in table_by_low),
        key=lambda t: table_scores.get(t, 0.0),
        reverse=True,
    )

    # 2. Identify mandatory PK + join FK columns per candidate table
    def _mandatory_cols_for(table: TableInfo, allowed_targets: set[str]) -> set[str]:
        t_low = table.name.lower()
        req = set(join_cols.get(t_low, set()))
        for c in table.columns:
            if c.is_primary_key:
                req.add(c.name.lower())
        for fk in table.foreign_keys:
            if fk.ref_table.lower() in allowed_targets:
                req.add(fk.column.lower())
        return req

    def _table_skeleton_cost(table: TableInfo, mandatory: set[str], allowed_targets: set[str]) -> int:
        head = f"# Table: {table.name}" + (f"  -- {table.description}" if table.description else "")
        cost = counter(head)
        for col in table.columns:
            if col.name.lower() in mandatory:
                cost += counter(_format_column_line(col))
        for fk in table.foreign_keys:
            if fk.column.lower() in mandatory and fk.ref_table.lower() in allowed_targets:
                cost += counter(_format_fk_line(table.name, fk))
        return cost

    # Fit as many highest-ranked tables + mandatory keys as fit in max_tokens
    kept_table_set: set[str] = set()
    used_tokens = dialect_cost
    # Try keeping all candidate tables first; drop lowest-ranked if over budget
    candidate_set = set(ordered_candidates)
    total_skeleton = dialect_cost + sum(
        _table_skeleton_cost(
            table_by_low[t], _mandatory_cols_for(table_by_low[t], candidate_set), candidate_set
        )
        for t in ordered_candidates
    )
    if total_skeleton <= max_tokens:
        kept_table_set = candidate_set
        used_tokens = total_skeleton
    else:
        for cand_name in ordered_candidates:
            tentative = kept_table_set | {cand_name}
            cost_tentative = dialect_cost + sum(
                _table_skeleton_cost(
                    table_by_low[kt], _mandatory_cols_for(table_by_low[kt], tentative), tentative
                )
                for kt in tentative
            )
            if cost_tentative <= max_tokens:
                kept_table_set = tentative
                used_tokens = cost_tentative

    if not kept_table_set:
        return SchemaSnapshot(dialect=schema.dialect, tables=())

    mandatory_by_table = {t: _mandatory_cols_for(table_by_low[t], kept_table_set) for t in kept_table_set}

    # 3. Allocate remaining budget across optional columns via 0/1 knapsack
    remaining = max_tokens - used_tokens
    optional_items: list[_ColumnCandidate] = []
    for t_low in kept_table_set:
        table = table_by_low[t_low]
        mand = mandatory_by_table[t_low]
        t_bonus = table_scores.get(t_low, 0.0) * 0.2
        for col in table.columns:
            c_low = col.name.lower()
            if c_low in mand:
                continue
            base = col_scores.get((t_low, c_low), 0.0)
            prior = 0.15 if c_low in _CONTEXTUAL_COL_NAMES else 0.05
            val = base + prior + t_bonus
            col_cost = counter(_format_column_line(col))
            # If this column is an FK pointing to a kept table, include FK line cost
            fk_extra = sum(
                counter(_format_fk_line(table.name, fk))
                for fk in table.foreign_keys
                if fk.column.lower() == c_low and fk.ref_table.lower() in kept_table_set
            )
            optional_items.append(
                _ColumnCandidate(table_lower=t_low, col=col, value=val, cost=col_cost + fk_extra)
            )

    chosen_optional = _knapsack_select(optional_items, remaining)

    # 4. Reconstruct pruned SchemaSnapshot preserving original table & column order
    pruned_tables: list[TableInfo] = []
    for table in schema.tables:
        t_low = table.name.lower()
        if t_low not in kept_table_set:
            continue
        kept_cols_low = mandatory_by_table[t_low] | {c_low for tbl, c_low in chosen_optional if tbl == t_low}
        cols = tuple(c for c in table.columns if c.name.lower() in kept_cols_low)
        fks = tuple(
            fk
            for fk in table.foreign_keys
            if fk.column.lower() in kept_cols_low and fk.ref_table.lower() in kept_table_set
        )
        pruned_tables.append(
            TableInfo(
                name=table.name,
                columns=cols,
                foreign_keys=fks,
                description=table.description,
            )
        )

    return SchemaSnapshot(dialect=schema.dialect, tables=tuple(pruned_tables))
