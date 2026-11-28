from __future__ import annotations

from backend.core.contracts import KnowledgeContext, LinkedSchema, ParsedQuestion
from backend.knowledge_base import InMemoryKnowledgeBase
from backend.rag import KeywordRetriever
from backend.semantic_layer import SemanticLayer


class KnowledgeAssembler:
    """Combines RAG (rules, examples) and the semantic layer (metrics) into
    one :class:`KnowledgeContext` — the L4 output."""

    def __init__(self, kb: InMemoryKnowledgeBase) -> None:
        self._retriever = KeywordRetriever(kb)
        self._semantic = SemanticLayer(kb)

    def context_for(self, question: ParsedQuestion, linked: LinkedSchema) -> KnowledgeContext:
        return KnowledgeContext(
            rules=self._retriever.rules(question),
            metrics=self._semantic.resolve(question, linked),
            examples=self._retriever.examples(question),
        )
