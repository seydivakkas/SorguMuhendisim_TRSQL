"""L4 KnowledgeAssembler combining RAG (Keyword or Hybrid) and SemanticLayer."""

from __future__ import annotations

from backend.core.config import RagSettings
from backend.core.contracts import KnowledgeContext, LinkedSchema, ParsedQuestion, SchemaSnapshot
from backend.core.ports import EmbeddingAdapter
from backend.knowledge_base import InMemoryKnowledgeBase
from backend.rag import HybridKnowledgeRetriever, KeywordRetriever
from backend.semantic_layer import SemanticLayer


class KnowledgeAssembler:
    """Combines RAG (rules, examples) and the semantic layer (metrics) into
    one :class:`KnowledgeContext` — the L4 output.

    Backward-compatible with ``KnowledgeAssembler(kb)`` (keyword baseline),
    while supporting :class:`HybridKnowledgeRetriever` (BM25 + Dense + RRF)
    and an injected :class:`SemanticLayer`.
    """

    def __init__(
        self,
        kb: InMemoryKnowledgeBase,
        *,
        retriever: KeywordRetriever | HybridKnowledgeRetriever | None = None,
        semantic_layer: SemanticLayer | None = None,
        use_hybrid: bool = False,
        embedder: EmbeddingAdapter | None = None,
        rag_settings: RagSettings | None = None,
        schema: SchemaSnapshot | None = None,
    ) -> None:
        if retriever is not None:
            self._retriever: KeywordRetriever | HybridKnowledgeRetriever = retriever
        elif use_hybrid or embedder is not None or rag_settings is not None:
            self._retriever = HybridKnowledgeRetriever(
                kb,
                embedder=embedder,
                settings=rag_settings,
                schema=schema,
            )
        else:
            self._retriever = KeywordRetriever(kb)
        self._semantic = semantic_layer or SemanticLayer(kb)

    @property
    def retriever(self) -> KeywordRetriever | HybridKnowledgeRetriever:
        return self._retriever

    @property
    def semantic_layer(self) -> SemanticLayer:
        return self._semantic

    def context_for(self, question: ParsedQuestion, linked: LinkedSchema) -> KnowledgeContext:
        return KnowledgeContext(
            rules=self._retriever.rules(question),
            metrics=self._semantic.resolve(question, linked),
            examples=self._retriever.examples(question),
        )
