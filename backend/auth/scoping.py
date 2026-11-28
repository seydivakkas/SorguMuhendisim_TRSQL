from __future__ import annotations

from collections import Counter

from backend.core.contracts import AuthContext, ColumnInfo, SchemaSnapshot, TableInfo


def _is_table_allowed(
    table: TableInfo,
    allowed: set[str],
    base_counts: Counter[str],
) -> bool:
    raw = table.name.lower()
    qualified = table.qualified_name
    base = table.unqualified_name
    if qualified in allowed:
        return True
    if "." in raw and raw in allowed:
        return True
    # Fail closed if the unqualified name exists in multiple schemas.
    return bool(base_counts[base] == 1 and base in allowed)


def _is_column_denied(table: TableInfo, column: ColumnInfo, denied: set[str]) -> bool:
    col = column.name.lower()
    raw = table.name.lower()
    base = table.unqualified_name
    qualified = table.qualified_name
    return (
        col in denied
        or f"{base}.{col}" in denied
        or f"{raw}.{col}" in denied
        or f"{qualified}.{col}" in denied
    )


def scope_schema(schema: SchemaSnapshot, auth: AuthContext) -> SchemaSnapshot:
    """Remove every table and column the user is not allowed to see.

    Foreign keys pointing at hidden or ambiguous tables/columns are removed too,
    so join-path discovery cannot route through forbidden data.
    Identifier comparison uses SQL identifier rules (lowercasing, not
    Turkish locale folding).
    """
    allowed = {t.lower() for t in auth.allowed_tables}
    denied = {c.lower() for c in auth.denied_columns}
    base_counts = Counter(t.unqualified_name for t in schema.tables)

    visible: list[TableInfo] = []
    for table in schema.tables:
        if not _is_table_allowed(table, allowed, base_counts):
            continue
        columns = tuple(c for c in table.columns if not _is_column_denied(table, c, denied))
        if not columns:
            continue
        visible.append(table.model_copy(update={"columns": columns}))

    visible_cols = {(t.qualified_name, c.name.lower()) for t in visible for c in t.columns}
    visible_base_counts = Counter(t.unqualified_name for t in visible)
    visible_by_key: dict[str, str] = {}
    for t in visible:
        visible_by_key[t.qualified_name] = t.qualified_name
        if "." in t.name:
            visible_by_key[t.name.lower()] = t.qualified_name
        elif visible_base_counts[t.unqualified_name] == 1 and base_counts[t.unqualified_name] == 1:
            visible_by_key[t.unqualified_name] = t.qualified_name

    result: list[TableInfo] = []
    for table in visible:
        src_key = table.qualified_name
        fks = tuple(
            fk
            for fk in table.foreign_keys
            if (src_key, fk.column.lower()) in visible_cols
            and (ref_key := visible_by_key.get(fk.ref_table.lower())) is not None
            and (ref_key, fk.ref_column.lower()) in visible_cols
        )
        result.append(table.model_copy(update={"foreign_keys": fks}))
    return SchemaSnapshot(dialect=schema.dialect, tables=tuple(result))
