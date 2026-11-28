"""Schema Linking Precision, Recall, and F1 using SQLGlot AST gold extraction."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

from backend.core.contracts import LinkedSchema, SchemaSnapshot


@dataclass(frozen=True)
class ExtractedSchema:
    """Tables and columns extracted from a SQL AST."""

    tables: frozenset[str]
    columns: frozenset[str]


def extract_gold_tables_and_columns(
    sql: str,
    *,
    dialect: str = "sqlite",
    schema: SchemaSnapshot | None = None,
) -> ExtractedSchema:
    """Extract lowercase gold table names and ``table.column`` names from SQL via SQLGlot."""
    stripped = sql.strip()
    if not stripped:
        return ExtractedSchema(tables=frozenset(), columns=frozenset())

    try:
        tree = sqlglot.parse_one(stripped, read=dialect)
    except ParseError:
        return ExtractedSchema(tables=frozenset(), columns=frozenset())

    cte_names = {cte.alias_or_name.lower() for cte in tree.find_all(exp.CTE)}
    alias_to_table: dict[str, str] = {}
    tables: set[str] = set()

    for table in tree.find_all(exp.Table):
        name = table.name.lower()
        if not name or (name in cte_names and not table.db):
            continue
        tables.add(name)
        alias_to_table[table.alias_or_name.lower()] = name

    select_aliases = {alias.alias.lower() for alias in tree.find_all(exp.Alias) if alias.alias}
    columns: set[str] = set()

    for col in tree.find_all(exp.Column):
        if isinstance(col.this, exp.Star):
            continue
        cname = col.name.lower()
        if not cname or cname == "*":
            continue
        qualifier = col.table.lower() if col.table else ""
        if qualifier:
            if qualifier in cte_names:
                continue
            target_table = alias_to_table.get(qualifier, qualifier)
            columns.add(f"{target_table}.{cname}")
            continue

        # Ignore ORDER BY / GROUP BY references to SELECT output aliases.
        if cname in select_aliases and not _is_inside_select_projection_or_filter(col, schema, tables):
            continue

        if schema is not None:
            matched_tables = [
                t for t in tables if (info := schema.table(t)) is not None and info.column(cname) is not None
            ]
            if matched_tables:
                for t in matched_tables:
                    columns.add(f"{t}.{cname}")
                continue
        if len(tables) == 1:
            only_table = next(iter(tables))
            columns.add(f"{only_table}.{cname}")
        else:
            columns.add(cname)

    return ExtractedSchema(tables=frozenset(tables), columns=frozenset(columns))


def _is_inside_select_projection_or_filter(
    col: exp.Column,
    schema: SchemaSnapshot | None,
    tables: set[str],
) -> bool:
    if schema is not None and any(
        (info := schema.table(t)) is not None and info.column(col.name.lower()) is not None for t in tables
    ):
        return True
    parent = col.parent
    while parent is not None:
        if isinstance(parent, (exp.Order, exp.Ordered, exp.Group, exp.Having)):
            return False
        if isinstance(parent, (exp.Select, exp.Where, exp.Join)):
            return True
        parent = parent.parent
    return True


def _prf(gold: frozenset[str], pred: frozenset[str]) -> tuple[float, float, float]:
    if not gold and not pred:
        return 1.0, 1.0, 1.0
    if not gold or not pred:
        return 0.0, 0.0, 0.0
    tp = len(gold & pred)
    precision = tp / len(pred)
    recall = tp / len(gold)
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0
    return precision, recall, f1


def _normalize_column_set(columns: Iterable[str]) -> frozenset[str]:
    return frozenset(c.strip().lower() for c in columns if c.strip())


def _normalize_table_set(tables: Iterable[str]) -> frozenset[str]:
    return frozenset(t.strip().lower() for t in tables if t.strip())


def _match_columns_with_unqualified_fallback(
    gold_cols: frozenset[str],
    pred_cols: frozenset[str],
) -> tuple[float, float, float]:
    if not gold_cols and not pred_cols:
        return 1.0, 1.0, 1.0
    if not gold_cols or not pred_cols:
        return 0.0, 0.0, 0.0

    # If a gold column is unqualified (no '.'), match any pred column ending with '.col'.
    matched_gold: set[str] = set()
    matched_pred: set[str] = set()
    for g in gold_cols:
        if g in pred_cols:
            matched_gold.add(g)
            matched_pred.add(g)
        elif "." not in g:
            for p in pred_cols:
                if p == g or p.endswith(f".{g}"):
                    matched_gold.add(g)
                    matched_pred.add(p)
        else:
            g_bare = g.split(".", 1)[1]
            if g_bare in pred_cols:
                matched_gold.add(g)
                matched_pred.add(g_bare)

    precision = len(matched_pred) / len(pred_cols)
    recall = len(matched_gold) / len(gold_cols)
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0
    return precision, recall, f1


@dataclass(frozen=True)
class SchemaLinkingSample:
    """Single schema-linking prediction paired with gold SQL."""

    gold_sql: str
    pred_tables: tuple[str, ...]
    pred_columns: tuple[str, ...] = ()


@dataclass(frozen=True)
class SchemaLinkingMetrics:
    """Macro-averaged Precision, Recall and F1 for schema linking."""

    sample_count: int
    table_precision: float
    table_recall: float
    table_f1: float
    column_precision: float
    column_recall: float
    column_f1: float
    full_table_recall_rate: float
    exact_table_match_rate: float

    @classmethod
    def evaluate(
        cls,
        samples: Sequence[SchemaLinkingSample],
        *,
        dialect: str = "sqlite",
        schema: SchemaSnapshot | None = None,
    ) -> SchemaLinkingMetrics:
        """Compute table and column Precision/Recall/F1 across ``samples``."""
        if not samples:
            return cls(
                sample_count=0,
                table_precision=0.0,
                table_recall=0.0,
                table_f1=0.0,
                column_precision=0.0,
                column_recall=0.0,
                column_f1=0.0,
                full_table_recall_rate=0.0,
                exact_table_match_rate=0.0,
            )

        tp_sum = tr_sum = tf_sum = 0.0
        cp_sum = cr_sum = cf_sum = 0.0
        full_recall_hits = 0
        exact_hits = 0

        for sample in samples:
            gold = extract_gold_tables_and_columns(sample.gold_sql, dialect=dialect, schema=schema)
            pred_tables = _normalize_table_set(sample.pred_tables)
            pred_cols = _normalize_column_set(sample.pred_columns)

            tp, tr, tf = _prf(gold.tables, pred_tables)
            cp, cr, cf = _match_columns_with_unqualified_fallback(gold.columns, pred_cols)

            tp_sum += tp
            tr_sum += tr
            tf_sum += tf
            cp_sum += cp
            cr_sum += cr
            cf_sum += cf
            if gold.tables <= pred_tables:
                full_recall_hits += 1
            if gold.tables == pred_tables:
                exact_hits += 1

        n = len(samples)
        return cls(
            sample_count=n,
            table_precision=tp_sum / n,
            table_recall=tr_sum / n,
            table_f1=tf_sum / n,
            column_precision=cp_sum / n,
            column_recall=cr_sum / n,
            column_f1=cf_sum / n,
            full_table_recall_rate=full_recall_hits / n,
            exact_table_match_rate=exact_hits / n,
        )

    @classmethod
    def from_linked(
        cls,
        gold_sqls: Sequence[str],
        linked_schemas: Sequence[LinkedSchema],
        *,
        dialect: str = "sqlite",
        schema: SchemaSnapshot | None = None,
    ) -> SchemaLinkingMetrics:
        """Compute schema-linking metrics directly from :class:`LinkedSchema` objects."""
        if len(gold_sqls) != len(linked_schemas):
            raise ValueError("gold_sqls ve linked_schemas uzunlukları eşit olmalıdır.")
        samples = [
            SchemaLinkingSample(
                gold_sql=sql,
                pred_tables=linked.tables,
                pred_columns=tuple(f"{link.table}.{link.column}" for link in linked.links if link.column),
            )
            for sql, linked in zip(gold_sqls, linked_schemas, strict=True)
        ]
        return cls.evaluate(samples, dialect=dialect, schema=schema)


__all__ = [
    "ExtractedSchema",
    "SchemaLinkingMetrics",
    "SchemaLinkingSample",
    "extract_gold_tables_and_columns",
]
