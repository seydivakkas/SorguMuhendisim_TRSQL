"""Baseline keyword retriever kept backward-compatible with L4 KnowledgeAssembler."""

from __future__ import annotations

from backend.core.contracts import BusinessRule, FewShotExample, ParsedQuestion
from backend.knowledge_base import InMemoryKnowledgeBase, tr_casefold


def _overlap(query: set[str], text: str) -> int:
    return len(query & set(tr_casefold(text).split()))


class KeywordRetriever:
    def __init__(self, kb: InMemoryKnowledgeBase, k_rules: int = 5, k_examples: int = 3) -> None:
        self._kb = kb
        self._k_rules = k_rules
        self._k_examples = k_examples

    def rules(self, question: ParsedQuestion) -> tuple[BusinessRule, ...]:
        """Only *approved* rules are ever retrieved."""
        q = set(tr_casefold(question.normalized_text).split())
        scored = [(r, _overlap(q, f"{r.term} {r.definition}")) for r in self._kb.approved_rules()]
        scored = [s for s in scored if s[1] > 0]
        scored.sort(key=lambda s: s[1], reverse=True)
        return tuple(r for r, _ in scored[: self._k_rules])

    def examples(self, question: ParsedQuestion) -> tuple[FewShotExample, ...]:
        q = set(tr_casefold(question.normalized_text).split())
        scored = [(e, _overlap(q, e.question)) for e in self._kb.examples]
        scored = [s for s in scored if s[1] > 0]
        scored.sort(key=lambda s: s[1], reverse=True)
        return tuple(e for e, _ in scored[: self._k_examples])
