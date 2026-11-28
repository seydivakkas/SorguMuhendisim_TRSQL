from __future__ import annotations

from backend.core.contracts import AuthContext, SchemaSnapshot, TableInfo


def scope_schema(schema: SchemaSnapshot, auth: AuthContext) -> SchemaSnapshot:
    """Remove every table and column the user is not allowed to see.

    Foreign keys pointing at hidden tables or columns are removed too, so
    that join-path discovery cannot route through forbidden data.
    """
    allowed = {t.lower() for t in auth.allowed_tables}
    denied = {c.lower() for c in auth.denied_columns}

    visible: list[TableInfo] = []
    for table in schema.tables:
        tname = table.name.lower()
        if tname not in allowed:
            continue
        columns = tuple(c for c in table.columns if f"{tname}.{c.name.lower()}" not in denied)
        if not columns:
            continue
        visible.append(table.model_copy(update={"columns": columns}))

    visible_cols = {(t.name.lower(), c.name.lower()) for t in visible for c in t.columns}
    result: list[TableInfo] = []
    for table in visible:
        fks = tuple(
            fk
            for fk in table.foreign_keys
            if (table.name.lower(), fk.column.lower()) in visible_cols
            and (fk.ref_table.lower(), fk.ref_column.lower()) in visible_cols
        )
        result.append(table.model_copy(update={"foreign_keys": fks}))
    return SchemaSnapshot(dialect=schema.dialect, tables=tuple(result))
