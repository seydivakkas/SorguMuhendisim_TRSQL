from __future__ import annotations

import re
from collections.abc import Collection, Mapping, Sequence

from backend.core.contracts import ColumnInfo, SchemaSnapshot

TEMPLATE_ID = "mschema_v1"

_PII_KEYWORDS: frozenset[str] = frozenset(
    {
        "tckn",
        "tc_kimlik",
        "tc_kimlik_no",
        "kimlik_no",
        "kimlik_numarasi",
        "tax_number",
        "vergi_no",
        "vergi_numarasi",
        "vkn",
        "iban",
        "kredi_karti",
        "credit_card",
        "card_number",
        "kart_no",
        "telefon",
        "phone",
        "gsm",
        "cep_tel",
        "eposta",
        "e_posta",
        "email",
        "adres",
        "address",
        "maas",
        "salary",
        "ucret",
        "parola",
        "password",
        "sifre",
        "pasaport",
        "passport",
        "ssn",
    }
)

_PII_DESC_RE = re.compile(
    r"(?:^|\b)(?:pii|kisisel veri|kişisel veri|gizli|sensitive|maskeli|denied)(?:\b|$)",
    re.IGNORECASE,
)


def _tr_ascii_fold(text: str) -> str:
    lowered = text.replace("İ", "i").replace("I", "ı").lower()
    return (
        lowered.replace("ı", "i")
        .replace("ş", "s")
        .replace("ğ", "g")
        .replace("ü", "u")
        .replace("ö", "o")
        .replace("ç", "c")
    )


def is_pii_column(
    table_name: str,
    column: ColumnInfo,
    *,
    denied_columns: Collection[str] = (),
    pii_columns: Collection[str] = (),
) -> bool:
    """Return True if a column is denied or holds sensitive/PII data."""
    denied_norm = {_tr_ascii_fold(item.strip()) for item in denied_columns}
    pii_norm = {_tr_ascii_fold(item.strip()) for item in pii_columns}
    qualified = _tr_ascii_fold(f"{table_name}.{column.name}")
    col_only = _tr_ascii_fold(column.name)

    if qualified in denied_norm or col_only in denied_norm:
        return True
    if qualified in pii_norm or col_only in pii_norm:
        return True
    if col_only in _PII_KEYWORDS:
        return True
    pii_substrings = ("tckn", "tc_kimlik", "iban", "password", "parola", "sifre", "credit_card")
    if any(kw in col_only for kw in pii_substrings):
        return True
    return bool(column.description and _PII_DESC_RE.search(_tr_ascii_fold(column.description)))


def _sanitize_sample_value(value: object) -> str:
    text = str(value).replace("\r", " ").replace("\n", " ").strip()
    text = text.replace("[", "(").replace("]", ")")
    if len(text) > 48:
        return text[:45] + "..."
    return text


def lookup_sample_values(
    table_name: str,
    column: ColumnInfo,
    *,
    sample_values: Mapping[str, Sequence[object]] | None = None,
    denied_columns: Collection[str] = (),
    pii_columns: Collection[str] = (),
    max_samples: int = 3,
) -> tuple[str, ...]:
    """Return up to ``max_samples`` (capped at 3) non-PII sample values for a column.

    Returns an empty tuple if the column is PII or in ``denied_columns``.
    """
    if not sample_values or max_samples <= 0:
        return ()
    if is_pii_column(table_name, column, denied_columns=denied_columns, pii_columns=pii_columns):
        return ()

    limit = min(max_samples, 3)
    lowered_map = {k.lower(): v for k, v in sample_values.items()}
    raw_seq = lowered_map.get(f"{table_name}.{column.name}".lower())
    if raw_seq is None:
        raw_seq = lowered_map.get(column.name.lower())
    if not raw_seq:
        return ()

    seen: set[str] = set()
    cleaned: list[str] = []
    for item in raw_seq:
        if item is None:
            continue
        rendered = _sanitize_sample_value(item)
        if not rendered or rendered in seen:
            continue
        seen.add(rendered)
        cleaned.append(rendered)
        if len(cleaned) >= limit:
            break
    return tuple(cleaned)


def render_mschema(
    schema: SchemaSnapshot,
    tables: tuple[str, ...] = (),
    *,
    sample_values: Mapping[str, Sequence[object]] | None = None,
    denied_columns: Collection[str] = (),
    pii_columns: Collection[str] = (),
    max_samples: int = 3,
) -> str:
    """Render ``schema`` in XiYan-style M-Schema format (D1).

    Includes column types, primary-key markers, descriptions, 2-3 non-PII sample
    values (when provided via ``sample_values``), and foreign keys. Sample
    values for PII or ``denied_columns`` are strictly suppressed.
    """
    wanted = {t.lower() for t in tables}
    lines: list[str] = [f"【DB_DIALECT】{schema.dialect.value}", "【Schema】"]
    foreign_keys: list[str] = []

    for table in schema.tables:
        if wanted and table.name.lower() not in wanted:
            continue
        header = f"# Table: {table.name}"
        if table.description:
            header += f", {table.description}"
        lines.append(header)
        lines.append("[")

        col_lines: list[str] = []
        for col in table.columns:
            parts: list[str] = [f"{col.name}: {col.data_type}"]
            if col.is_primary_key:
                parts.append("Primary Key")
            if col.description:
                parts.append(col.description)
            samples = lookup_sample_values(
                table.name,
                col,
                sample_values=sample_values,
                denied_columns=denied_columns,
                pii_columns=pii_columns,
                max_samples=max_samples,
            )
            if samples:
                parts.append(f"Examples: [{', '.join(samples)}]")
            col_lines.append(f"({', '.join(parts)})")

        for idx, line in enumerate(col_lines):
            suffix = "," if idx < len(col_lines) - 1 else ""
            lines.append(f"{line}{suffix}")
        lines.append("]")

        for fk in table.foreign_keys:
            if wanted and fk.ref_table.lower() not in wanted:
                continue
            foreign_keys.append(f"{table.name}.{fk.column} = {fk.ref_table}.{fk.ref_column}")

    if foreign_keys:
        lines.append("【Foreign keys】")
        lines.extend(foreign_keys)

    return "\n".join(lines)
