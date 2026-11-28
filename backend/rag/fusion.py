"""Hybrid BM25 + Dense + Reciprocal Rank Fusion (RRF) knowledge retriever."""

from __future__ import annotations

from collections.abc import Callable, Hashable, Sequence
from dataclasses import dataclass
from typing import TypeVar

from backend.core.config import RagSettings
from backend.core.contracts import (
    BusinessRule,
    Dialect,
    FewShotExample,
    KnowledgeContext,
    MetricDefinition,
    ParsedQuestion,
    SchemaSnapshot,
)
from backend.core.ports import EmbeddingAdapter
from backend.knowledge_base import InMemoryKnowledgeBase, MetadataEntry
from backend.rag.bm25 import BM25Retriever, SchemaElement
from backend.rag.dense import DenseRetriever
from backend.rag.values import ValueLinker, ValueMatch

T = TypeVar("T")


def reciprocal_rank_fusion(
    ranked_lists: Sequence[Sequence[T]],
    *,
    weights: Sequence[float] | None = None,
    k: int = 60,
    key_fn: Callable[[T], Hashable] | None = None,
) -> list[tuple[T, float]]:
    """Fuse multiple ranked item lists via weighted Reciprocal Rank Fusion.

    ``RRF(d) = sum_i w_i / (k + rank_i(d))`` with 1-based ranks.
    """
    if k <= 0:
        raise ValueError("k must be positive")
    if weights is None:
        used_weights = [1.0] * len(ranked_lists)
    else:
        if len(weights) != len(ranked_lists):
            raise ValueError("weights length must match ranked_lists length")
        used_weights = list(weights)

    scores: dict[Hashable, float] = {}
    items: dict[Hashable, T] = {}
    first_order: dict[Hashable, int] = {}
    counter = 0

    for ranked, weight in zip(ranked_lists, used_weights, strict=True):
        if weight <= 0.0:
            continue
        seen_in_list: set[Hashable] = set()
        for rank, item in enumerate(ranked, start=1):
            key: Hashable = key_fn(item) if key_fn is not None else item
            if key in seen_in_list:
                continue
            seen_in_list.add(key)
            if key not in items:
                items[key] = item
                first_order[key] = counter
                counter += 1
            scores[key] = scores.get(key, 0.0) + (weight / (k + rank))

    ordered_keys = sorted(scores.keys(), key=lambda key: (-scores[key], first_order[key]))
    return [(items[key], round(scores[key], 8)) for key in ordered_keys]


@dataclass(frozen=True)
class HybridRetrievalResult:
    """Combined output of all enabled D3 RAG channels."""

    rules: tuple[BusinessRule, ...] = ()
    examples: tuple[FewShotExample, ...] = ()
    schema_elements: tuple[SchemaElement, ...] = ()
    metadata: tuple[MetadataEntry, ...] = ()
    value_matches: tuple[ValueMatch, ...] = ()


class HybridKnowledgeRetriever:
    """Fuses BM25 and Dense retrieval with RRF and supports D3 ablation flags."""

    def __init__(
        self,
        kb: InMemoryKnowledgeBase,
        *,
        embedder: EmbeddingAdapter | None = None,
        value_linker: ValueLinker | None = None,
        settings: RagSettings | None = None,
        schema: SchemaSnapshot | None = None,
        bm25: BM25Retriever | None = None,
        dense: DenseRetriever | None = None,
    ) -> None:
        self._settings = settings or RagSettings()
        self._schema = schema
        self._value_linker = value_linker
        self._bm25 = bm25 or BM25Retriever(
            kb,
            schema=schema,
            k_rules=self._settings.top_k_rules,
            k_examples=self._settings.top_k_examples,
        )
        self._dense: DenseRetriever | None = dense
        if self._dense is None and embedder is not None:
            self._dense = DenseRetriever(
                kb,
                embedder,
                schema=schema,
                k_rules=self._settings.top_k_rules,
                k_examples=self._settings.top_k_examples,
            )

    def _fuse(
        self,
        bm25_items: Sequence[T],
        dense_items: Sequence[T],
        *,
        limit: int,
        key_fn: Callable[[T], Hashable] | None = None,
    ) -> tuple[T, ...]:
        if limit <= 0:
            return ()
        lists: list[Sequence[T]] = []
        weights: list[float] = []
        if self._settings.bm25_weight > 0.0 and bm25_items:
            lists.append(bm25_items)
            weights.append(self._settings.bm25_weight)
        if self._dense is not None and self._settings.dense_weight > 0.0 and dense_items:
            lists.append(dense_items)
            weights.append(self._settings.dense_weight)
        if not lists:
            return ()
        fused = reciprocal_rank_fusion(
            lists,
            weights=weights,
            k=self._settings.rrf_k,
            key_fn=key_fn,
        )
        return tuple(item for item, _ in fused[:limit])

    def rules(self, question: ParsedQuestion, *, top_k: int | None = None) -> tuple[BusinessRule, ...]:
        if not self._settings.enable_rule_rag:
            return ()
        limit = self._settings.top_k_rules if top_k is None else top_k
        bm25_items = [r for r, _ in self._bm25.score_rules(question)]
        dense_items = [r for r, _ in self._dense.score_rules(question)] if self._dense else []
        return self._fuse(bm25_items, dense_items, limit=limit, key_fn=lambda r: r.rule_id)

    def examples(
        self,
        question: ParsedQuestion,
        *,
        candidate_sql: str | None = None,
        dialect: Dialect | None = None,
        top_k: int | None = None,
    ) -> tuple[FewShotExample, ...]:
        if not self._settings.enable_example_rag:
            return ()
        limit = self._settings.top_k_examples if top_k is None else top_k
        bm25_items = [
            e for e, _ in self._bm25.score_examples(question, candidate_sql=candidate_sql, dialect=dialect)
        ]
        dense_items = (
            [e for e, _ in self._dense.score_examples(question, dialect=dialect)] if self._dense else []
        )
        return self._fuse(
            bm25_items,
            dense_items,
            limit=limit,
            key_fn=lambda ex: (ex.question, ex.sql, ex.dialect),
        )

    def schema_elements(
        self,
        question: ParsedQuestion,
        *,
        schema: SchemaSnapshot | None = None,
        top_k: int = 8,
    ) -> tuple[SchemaElement, ...]:
        if not self._settings.enable_schema_rag:
            return ()
        target_schema = schema if schema is not None else self._schema
        bm25_items = [e for e, _ in self._bm25.score_schema_elements(question, schema=target_schema)]
        dense_items = (
            [e for e, _ in self._dense.score_schema_elements(question, schema=target_schema)]
            if self._dense
            else []
        )
        return self._fuse(
            bm25_items,
            dense_items,
            limit=top_k,
            key_fn=lambda elem: elem.qualified_name.lower(),
        )

    def metadata(
        self,
        question: ParsedQuestion,
        *,
        allowed_tables: frozenset[str] | None = None,
        top_k: int = 5,
    ) -> tuple[MetadataEntry, ...]:
        bm25_items = [m for m, _ in self._bm25.score_metadata(question, allowed_tables=allowed_tables)]
        dense_items = (
            [m for m, _ in self._dense.score_metadata(question, allowed_tables=allowed_tables)]
            if self._dense
            else []
        )
        return self._fuse(bm25_items, dense_items, limit=top_k, key_fn=lambda m: m.entry_id)

    def link_values(
        self,
        question: ParsedQuestion,
        *,
        allowed_tables: frozenset[str] | None = None,
        denied_columns: frozenset[str] = frozenset(),
        top_k: int = 5,
    ) -> tuple[ValueMatch, ...]:
        if not self._settings.enable_value_linking or self._value_linker is None:
            return ()
        return self._value_linker.link(
            question,
            allowed_tables=allowed_tables,
            denied_columns=denied_columns,
            top_k=top_k,
        )

    def retrieve(
        self,
        question: ParsedQuestion,
        *,
        schema: SchemaSnapshot | None = None,
        candidate_sql: str | None = None,
        dialect: Dialect | None = None,
        denied_columns: frozenset[str] = frozenset(),
    ) -> HybridRetrievalResult:
        """Run all enabled D3 retrieval stages respecting RBAC and ablation flags."""
        target_schema = schema if schema is not None else self._schema
        allowed_tables = target_schema.table_names if target_schema is not None else None
        used_dialect = (
            dialect if dialect is not None else (target_schema.dialect if target_schema is not None else None)
        )
        return HybridRetrievalResult(
            rules=self.rules(question),
            examples=self.examples(question, candidate_sql=candidate_sql, dialect=used_dialect),
            schema_elements=self.schema_elements(question, schema=target_schema),
            metadata=self.metadata(question, allowed_tables=allowed_tables),
            value_matches=self.link_values(
                question,
                allowed_tables=allowed_tables,
                denied_columns=denied_columns,
            ),
        )

    def to_knowledge_context(
        self,
        question: ParsedQuestion,
        *,
        metrics: tuple[MetricDefinition, ...] = (),
        candidate_sql: str | None = None,
        dialect: Dialect | None = None,
    ) -> KnowledgeContext:
        """Assemble a ``KnowledgeContext`` contract for L5 prompt generation."""
        return KnowledgeContext(
            rules=self.rules(question),
            metrics=metrics,
            examples=self.examples(question, candidate_sql=candidate_sql, dialect=dialect),
        )
