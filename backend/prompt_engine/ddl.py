from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence

from backend.core.contracts import SchemaSnapshot
from backend.prompt_engine.mschema import lookup_sample_values

TEMPLATE_ID = "ddl_v1"


def render_ddl(
    schema: SchemaSnapshot,
    tables: tuple[str, ...] = (),
    *,
    denied_columns: Collection[str] = (),
    pii_columns: Collection[str] = (),
    sample_values: Mapping[str, Sequence[object]] | None = None,
    include_dialect_header: bool = True,
) -> str:
    """Render ``schema`` as classic SQL ``CREATE TABLE`` DDL statements (D0).

    PII and ``denied_columns`` sample values are strictly omitted even if a
    ``sample_values`` mapping is passed.
    """
    wanted = {t.lower() for t in tables}
    blocks: list[str] = []
    if include_dialect_header:
        blocks.append(f"-- Dialect: {schema.dialect.value}")

    for table in schema.tables:
        if wanted and table.name.lower() not in wanted:
            continue
        table_lines: list[str] = []
        if table.description:
            table_lines.append(f"-- {table.description}")
        table_lines.append(f"CREATE TABLE {table.name} (")

        items: list[tuple[str, str]] = []
        for col in table.columns:
            defn = f"  {col.name} {col.data_type}"
            if col.is_primary_key:
                defn += " PRIMARY KEY"
            elif not col.nullable:
                defn += " NOT NULL"

            comment_parts: list[str] = []
            if col.description:
                comment_parts.append(col.description)
            samples = lookup_sample_values(
                table.name,
                col,
                sample_values=sample_values,
                denied_columns=denied_columns,
                pii_columns=pii_columns,
            )
            if samples:
                comment_parts.append(f"örnek: {', '.join(samples)}")
            comment = f" -- {'; '.join(comment_parts)}" if comment_parts else ""
            items.append((defn, comment))

        for fk in table.foreign_keys:
            if wanted and fk.ref_table.lower() not in wanted:
                continue
            items.append((f"  FOREIGN KEY ({fk.column}) REFERENCES {fk.ref_table}({fk.ref_column})", ""))

        for idx, (defn, comment) in enumerate(items):
            comma = "," if idx < len(items) - 1 else ""
            table_lines.append(f"{defn}{comma}{comment}")
        table_lines.append(");")
        blocks.append("\n".join(table_lines))

    return "\n\n".join(blocks)
