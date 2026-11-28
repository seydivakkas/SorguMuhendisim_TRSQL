from __future__ import annotations

from backend.core.contracts import (
    LinkedSchema,
    MentionKind,
    MetricDefinition,
    ParsedQuestion,
)
from backend.knowledge_base import InMemoryKnowledgeBase


class SemanticLayer:
    def __init__(self, kb: InMemoryKnowledgeBase) -> None:
        self._kb = kb

    def resolve(self, question: ParsedQuestion, linked: LinkedSchema) -> tuple[MetricDefinition, ...]:
        """Return metrics named in the question whose base table is visible
        to the user (i.e. present in the linked, scoped schema)."""
        words = {m.lemma or m.text for m in question.mentions if m.kind is MentionKind.METRIC}
        text = question.normalized_text
        visible = {t.lower() for t in linked.tables}
        out: list[MetricDefinition] = []
        for metric in self._kb.metrics:
            names = {metric.name.lower(), *(s.lower() for s in metric.synonyms)}
            if (names & words or any(n in text for n in names)) and metric.base_table.lower() in visible:
                out.append(metric)
        return tuple(out)
