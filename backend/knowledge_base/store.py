"""In-memory enterprise knowledge store and TOML loader."""

from __future__ import annotations

import tomllib
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from backend.core.contracts import BusinessRule, FewShotExample, MetricDefinition

_TR_UPPER_MAP = str.maketrans({"I": "ı", "İ": "i"})
_TR_DIACRITIC_FOLD_MAP = str.maketrans(
    {
        "ç": "c",
        "ğ": "g",
        "ı": "i",
        "ö": "o",
        "ş": "s",
        "ü": "u",
        "â": "a",
        "î": "i",
        "û": "u",
    }
)


def tr_casefold(text: str) -> str:
    """Turkish-aware lowercase (`I` -> `ı`, `İ` -> `i`) with NFC normalization."""
    return unicodedata.normalize("NFC", text).translate(_TR_UPPER_MAP).lower().replace("\u0307", "")


def fold_turkish_diacritics(text: str) -> str:
    """Casefold Turkish text and map Turkish diacritics to ASCII equivalents."""
    return tr_casefold(text).translate(_TR_DIACRITIC_FOLD_MAP)


def _normalize_code_values(
    raw: Mapping[str, object] | Sequence[tuple[str, str]] | Sequence[Sequence[str]],
) -> tuple[tuple[str, str], ...]:
    if isinstance(raw, Mapping):
        return tuple((str(k), str(v)) for k, v in raw.items())
    out: list[tuple[str, str]] = []
    for pair in raw:
        if len(pair) != 2:
            raise ValueError(f"code mapping entry must have 2 elements, got {len(pair)}")
        out.append((str(pair[0]), str(pair[1])))
    return tuple(out)


@dataclass(frozen=True)
class MetadataEntry:
    """Institutional metadata / code-lookup entry for a schema column."""

    entry_id: str
    table: str
    column: str
    description: str
    code_values: tuple[tuple[str, str], ...] = ()
    unit: str | None = None
    synonyms: tuple[str, ...] = ()
    approved: bool = True

    @property
    def qualified_column(self) -> str:
        return f"{self.table.lower()}.{self.column.lower()}"

    @property
    def code_map(self) -> dict[str, str]:
        return dict(self.code_values)

    @classmethod
    def from_mapping(cls, data: Mapping[str, object]) -> MetadataEntry:
        raw_codes = data.get("code_values", data.get("code_mappings", ()))
        code_pairs: tuple[tuple[str, str], ...] = ()
        if isinstance(raw_codes, Mapping | list | tuple):
            code_pairs = _normalize_code_values(raw_codes)
        raw_synonyms = data.get("synonyms", ())
        synonyms = tuple(str(s) for s in raw_synonyms) if isinstance(raw_synonyms, list | tuple) else ()
        raw_unit = data.get("unit")
        return cls(
            entry_id=str(data["entry_id"]),
            table=str(data["table"]),
            column=str(data["column"]),
            description=str(data["description"]),
            code_values=code_pairs,
            unit=str(raw_unit) if raw_unit is not None else None,
            synonyms=synonyms,
            approved=bool(data.get("approved", True)),
        )


@dataclass(frozen=True)
class InMemoryKnowledgeBase:
    """Immutable institutional knowledge store loaded from config or tests."""

    rules: tuple[BusinessRule, ...] = ()
    metrics: tuple[MetricDefinition, ...] = ()
    examples: tuple[FewShotExample, ...] = field(default=())
    metadata: tuple[MetadataEntry, ...] = ()

    def approved_rules(self) -> tuple[BusinessRule, ...]:
        """Return only rules explicitly approved by the institution."""
        return tuple(r for r in self.rules if r.approved)

    def approved_metadata(self, allowed_tables: frozenset[str] | None = None) -> tuple[MetadataEntry, ...]:
        """Return approved metadata entries, optionally scoped to ``allowed_tables``."""
        if allowed_tables is None:
            return tuple(m for m in self.metadata if m.approved)
        allowed = {t.lower() for t in allowed_tables}
        return tuple(m for m in self.metadata if m.approved and m.table.lower() in allowed)


def load_knowledge_base(path: str | Path) -> InMemoryKnowledgeBase:
    """Load rules, metrics, examples, and optional metadata entries from TOML."""
    data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    return InMemoryKnowledgeBase(
        rules=tuple(BusinessRule.model_validate(r) for r in data.get("rules", [])),
        metrics=tuple(MetricDefinition.model_validate(m) for m in data.get("metrics", [])),
        examples=tuple(FewShotExample.model_validate(e) for e in data.get("examples", [])),
        metadata=tuple(MetadataEntry.from_mapping(m) for m in data.get("metadata", [])),
    )
