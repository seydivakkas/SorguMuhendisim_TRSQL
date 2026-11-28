"""L4 — Semantic Layer resolver integrating synonyms and deterministic KPI templates."""

from __future__ import annotations

import re
from datetime import date

from backend.core.contracts import (
    Dialect,
    LinkedSchema,
    MentionKind,
    MetricDefinition,
    ParsedQuestion,
    SchemaSnapshot,
)
from backend.knowledge_base import (
    InMemoryKnowledgeBase,
    fold_turkish_diacritics,
    tr_casefold,
)
from backend.semantic_layer.templates import MetricTemplateRegistry, TemplateMatch

_METRIC_SYNONYM_GROUPS: tuple[tuple[str, ...], ...] = (
    ("ciro", "hasılat", "satış tutarı", "net satış", "net ciro", "satış geliri"),
    ("iade oranı", "iade yüzdesi", "geri dönüş oranı"),
    ("aktif müşteri", "aktif müşteriler", "etkin müşteri"),
    ("vadesi geçmiş borç", "gecikmiş borç", "vadesi dolmuş borç", "gecikmiş cari borç"),
)


def _expand_synonyms(names: set[str]) -> set[str]:
    expanded = set(names)
    for group in _METRIC_SYNONYM_GROUPS:
        group_folded = {tr_casefold(g) for g in group}
        group_ascii = {fold_turkish_diacritics(g) for g in group_folded}
        if expanded & group_folded or expanded & group_ascii:
            expanded |= group_folded | group_ascii
    return expanded


def _contains_term(term: str, text: str) -> bool:
    if len(term) <= 3:
        pattern = rf"(?<![0-9a-zçğıöşü_]){re.escape(term)}(?![0-9a-zçğıöşü_])"
        return re.search(pattern, text) is not None
    return term in text


class SemanticLayer:
    """Resolves Turkish metric phrases to approved ``MetricDefinition``s and templates."""

    def __init__(
        self,
        kb: InMemoryKnowledgeBase,
        registry: MetricTemplateRegistry | None = None,
    ) -> None:
        self._kb = kb
        self._registry = registry or MetricTemplateRegistry()

    @property
    def registry(self) -> MetricTemplateRegistry:
        return self._registry

    def resolve(self, question: ParsedQuestion, linked: LinkedSchema) -> tuple[MetricDefinition, ...]:
        """Return metrics named in the question whose base table is visible
        to the user (i.e. present in the linked, scoped schema)."""
        words = {tr_casefold(m.lemma or m.text) for m in question.mentions if m.kind is MentionKind.METRIC}
        words |= {fold_turkish_diacritics(w) for w in words}

        text_tr = tr_casefold(question.normalized_text or question.original_text)
        text_ascii = fold_turkish_diacritics(text_tr)
        visible = {t.lower() for t in linked.tables}
        out: list[MetricDefinition] = []

        for metric in self._kb.metrics:
            if metric.base_table.lower() not in visible:
                continue
            direct_names = {tr_casefold(metric.name), *(tr_casefold(s) for s in metric.synonyms)}
            direct_names |= {fold_turkish_diacritics(n) for n in direct_names}
            expanded_names = _expand_synonyms(direct_names)
            if (expanded_names & words) or any(
                _contains_term(n, text_tr) or _contains_term(n, text_ascii) for n in expanded_names
            ):
                out.append(metric)
        return tuple(out)

    def resolve_template(
        self,
        question: ParsedQuestion,
        linked: LinkedSchema,
        *,
        dialect: Dialect = Dialect.SQLITE,
        schema: SchemaSnapshot | None = None,
        denied_columns: frozenset[str] = frozenset(),
        today: date | None = None,
    ) -> TemplateMatch | None:
        """Resolve an approved deterministic KPI SQL template if safe and allowed."""
        return self._registry.match(
            question,
            linked,
            dialect=dialect,
            schema=schema,
            denied_columns=denied_columns,
            today=today,
        )
