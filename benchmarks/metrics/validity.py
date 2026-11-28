"""Valid SQL Rate metrics split into SQLGlot parseability and DB executability."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

from backend.core.contracts import SchemaSnapshot
from benchmarks.metrics.test_suite import execute_sqlite_readonly


def is_parseable_sql(
    sql: str,
    *,
    dialect: str = "sqlite",
    require_single_statement: bool = True,
    read_only_only: bool = False,
) -> bool:
    """Return True iff ``sql`` parses cleanly with SQLGlot (not an empty or Command fallback)."""
    stripped = sql.strip()
    if not stripped:
        return False
    try:
        statements = [stmt for stmt in sqlglot.parse(stripped, read=dialect) if stmt is not None]
    except ParseError:
        return False
    if not statements:
        return False
    if require_single_statement and len(statements) != 1:
        return False
    for stmt in statements:
        if isinstance(stmt, exp.Command):
            return False
        if read_only_only and not isinstance(stmt, exp.Query):
            return False
    return True


def is_executable_sql(
    sql: str,
    db_path: str | Path | None = None,
    *,
    executor: Callable[[str], bool] | None = None,
    timeout_ms: int = 5000,
) -> bool:
    """Return True iff ``sql`` executes without database error in read-only mode."""
    stripped = sql.strip()
    if not stripped:
        return False
    if executor is not None:
        return executor(stripped)
    if db_path is None:
        raise ValueError("is_executable_sql için db_path veya executor sağlanmalıdır.")
    ok, _, _ = execute_sqlite_readonly(db_path, stripped, timeout_ms=timeout_ms, max_rows=100)
    return ok


def has_schema_hallucination(
    sql: str,
    schema: SchemaSnapshot,
    *,
    dialect: str | None = None,
) -> bool:
    """Return True if ``sql`` references a table or column absent from ``schema``."""
    stripped = sql.strip()
    if not stripped:
        return True
    try:
        tree = sqlglot.parse_one(stripped, read=dialect or schema.dialect.value)
    except ParseError:
        return True
    if not isinstance(tree, exp.Query):
        return True

    cte_names = {cte.alias_or_name.lower() for cte in tree.find_all(exp.CTE)}
    alias_to_table: dict[str, str] = {}
    real_tables: set[str] = set()

    for table in tree.find_all(exp.Table):
        tname = table.name.lower()
        if not tname or (tname in cte_names and not table.db):
            continue
        if schema.table(tname) is None:
            return True
        real_tables.add(tname)
        alias_to_table[table.alias_or_name.lower()] = tname

    select_aliases = {alias.alias.lower() for alias in tree.find_all(exp.Alias) if alias.alias}
    for col in tree.find_all(exp.Column):
        if isinstance(col.this, exp.Star):
            continue
        cname = col.name.lower()
        qualifier = col.table.lower() if col.table else ""
        if qualifier:
            if qualifier in cte_names:
                continue
            target = alias_to_table.get(qualifier)
            if target is None:
                return True
            tinfo = schema.table(target)
            if tinfo is None or tinfo.column(cname) is None:
                return True
        else:
            if cname in select_aliases or cte_names:
                continue
            if not any(
                (tinfo := schema.table(t)) is not None and tinfo.column(cname) is not None
                for t in real_tables
            ):
                return True
    return False


@dataclass(frozen=True)
class ValidityReport:
    """Valid SQL Rate breakdown separating SQLGlot parseability and DB executability."""

    total: int
    parseable_count: int
    executable_count: int
    parseable_rate: float
    executable_rate: float
    schema_valid_rate: float | None = None
    hallucination_rate: float | None = None


def compute_validity_metrics(
    sqls: Sequence[str],
    *,
    dialect: str = "sqlite",
    db_path: str | Path | None = None,
    execution_outcomes: Sequence[bool] | None = None,
    schema: SchemaSnapshot | None = None,
    executor: Callable[[str], bool] | None = None,
    timeout_ms: int = 5000,
) -> ValidityReport:
    """Compute ``parseable_rate`` (SQLGlot) and ``executable_rate`` (DB execution)."""
    total = len(sqls)
    if total == 0:
        return ValidityReport(
            total=0,
            parseable_count=0,
            executable_count=0,
            parseable_rate=0.0,
            executable_rate=0.0,
            schema_valid_rate=0.0 if schema is not None else None,
            hallucination_rate=0.0 if schema is not None else None,
        )

    if execution_outcomes is not None and len(execution_outcomes) != total:
        raise ValueError("execution_outcomes uzunluğu sqls uzunluğuna eşit olmalıdır.")

    parseable_count = sum(1 for sql in sqls if is_parseable_sql(sql, dialect=dialect))

    if execution_outcomes is not None:
        executable_count = sum(1 for ok in execution_outcomes if ok)
    elif db_path is not None or executor is not None:
        executable_count = sum(
            1 for sql in sqls if is_executable_sql(sql, db_path, executor=executor, timeout_ms=timeout_ms)
        )
    else:
        raise ValueError("execution_outcomes, db_path veya executor değerlerinden biri sağlanmalıdır.")

    schema_valid_rate: float | None = None
    hallucination_rate: float | None = None
    if schema is not None:
        hallucinated = sum(1 for sql in sqls if has_schema_hallucination(sql, schema, dialect=dialect))
        hallucination_rate = hallucinated / total
        schema_valid_rate = 1.0 - hallucination_rate

    return ValidityReport(
        total=total,
        parseable_count=parseable_count,
        executable_count=executable_count,
        parseable_rate=parseable_count / total,
        executable_rate=executable_count / total,
        schema_valid_rate=schema_valid_rate,
        hallucination_rate=hallucination_rate,
    )


__all__ = [
    "ValidityReport",
    "compute_validity_metrics",
    "has_schema_hallucination",
    "is_executable_sql",
    "is_parseable_sql",
]
