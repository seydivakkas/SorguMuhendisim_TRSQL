"""Dense vector retriever using ``EmbeddingAdapter`` with optional FAISS backend."""

from __future__ import annotations

import hashlib
import importlib
import importlib.util
import math
from collections.abc import Sequence
from typing import Protocol, cast

from backend.core.contracts import (
    BusinessRule,
    Dialect,
    FewShotExample,
    ParsedQuestion,
    SchemaSnapshot,
)
from backend.core.ports import EmbeddingAdapter
from backend.knowledge_base import InMemoryKnowledgeBase, MetadataEntry
from backend.rag.bm25 import SchemaElement, schema_elements_from_snapshot, tokenize_turkish


def _l2_normalize(vec: Sequence[float]) -> tuple[float, ...]:
    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0.0:
        return tuple(0.0 for _ in vec)
    return tuple(v / norm for v in vec)


class DeterministicHashEmbedder:
    """Offline zero-dependency ``EmbeddingAdapter`` using signed feature hashing.

    Hashes Turkish stems and character 3-grams into a fixed-dimensional vector
    and L2-normalizes it so related Turkish forms retain positive cosine
    similarity in unit tests and offline dev runs.
    """

    def __init__(self, dim: int = 256) -> None:
        if dim <= 0:
            raise ValueError("dim must be positive")
        self._dim = dim

    def _embed_one(self, text: str) -> list[float]:
        vec = [0.0] * self._dim
        tokens = tokenize_turkish(text)
        features: list[tuple[str, float]] = [(f"w:{tok}", 1.0) for tok in tokens]
        joined = " ".join(tokens)
        if len(joined) >= 3:
            for i in range(len(joined) - 2):
                features.append((f"c:{joined[i : i + 3]}", 0.35))
        for feat, weight in features:
            digest = hashlib.blake2b(feat.encode("utf-8"), digest_size=8).digest()
            idx = int.from_bytes(digest[:4], "little") % self._dim
            sign = 1.0 if (digest[4] & 1) == 0 else -1.0
            vec[idx] += sign * weight
        return list(_l2_normalize(vec))

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(t) for t in texts]


class _FaissIndexProtocol(Protocol):
    def add(self, x: object) -> None: ...

    def search(self, x: object, k: int) -> tuple[Sequence[Sequence[float]], Sequence[Sequence[int]]]: ...


class _ArrayFactory(Protocol):
    def __call__(self, data: object, *, dtype: str) -> object: ...


class _VectorIndex:
    """Flat inner-product index using ``faiss`` when available, pure Python otherwise."""

    def __init__(self, vectors: Sequence[Sequence[float]], *, use_faiss: bool = True) -> None:
        self._vectors = [_l2_normalize(v) for v in vectors]
        self._faiss_index: _FaissIndexProtocol | None = None
        self._np_asarray: _ArrayFactory | None = None

        if (
            use_faiss
            and self._vectors
            and importlib.util.find_spec("faiss") is not None
            and importlib.util.find_spec("numpy") is not None
        ):
            faiss_mod = importlib.import_module("faiss")
            np_mod = importlib.import_module("numpy")
            ctor = getattr(faiss_mod, "IndexFlatIP", None)
            asarray = getattr(np_mod, "asarray", None)
            dim = len(self._vectors[0])
            if callable(ctor) and callable(asarray) and dim > 0:
                idx = cast(_FaissIndexProtocol, ctor(dim))
                arr_fn = cast(_ArrayFactory, asarray)
                idx.add(arr_fn(self._vectors, dtype="float32"))
                self._faiss_index = idx
                self._np_asarray = arr_fn

    def search(self, query_vec: Sequence[float], top_k: int) -> list[tuple[int, float]]:
        if not self._vectors or top_k <= 0:
            return []
        q_norm = _l2_normalize(query_vec)
        if self._faiss_index is not None and self._np_asarray is not None:
            k = min(top_k, len(self._vectors))
            q_arr = self._np_asarray([q_norm], dtype="float32")
            distances, indices = self._faiss_index.search(q_arr, k)
            out: list[tuple[int, float]] = []
            for idx_val, score_val in zip(indices[0], distances[0], strict=True):
                idx_int = int(idx_val)
                if idx_int >= 0:
                    out.append((idx_int, float(score_val)))
            return out

        scored = [
            (idx, sum(a * b for a, b in zip(q_norm, doc_vec, strict=False)))
            for idx, doc_vec in enumerate(self._vectors)
        ]
        scored.sort(key=lambda item: (-item[1], item[0]))
        return scored[:top_k]


class DenseRetriever:
    """Dense semantic retriever powered by an injected ``EmbeddingAdapter``."""

    def __init__(
        self,
        kb: InMemoryKnowledgeBase,
        embedder: EmbeddingAdapter,
        *,
        schema: SchemaSnapshot | None = None,
        k_rules: int = 5,
        k_examples: int = 3,
        k_schema: int = 8,
        k_metadata: int = 5,
        min_score: float = 0.0,
        use_faiss: bool = True,
    ) -> None:
        self._kb = kb
        self._embedder = embedder
        self._schema = schema
        self._k_rules = k_rules
        self._k_examples = k_examples
        self._k_schema = k_schema
        self._k_metadata = k_metadata
        self._min_score = min_score
        self._use_faiss = use_faiss

        self._approved_rules = kb.approved_rules()
        self._rules_index: _VectorIndex | None = None

        self._examples = kb.examples
        self._examples_index: _VectorIndex | None = None

        self._metadata = kb.approved_metadata()
        self._metadata_index: _VectorIndex | None = None

        self._schema_cache: dict[
            tuple[tuple[str, str | None, str], ...],
            tuple[tuple[SchemaElement, ...], _VectorIndex],
        ] = {}

    def _build_index(self, texts: list[str]) -> _VectorIndex:
        if not texts:
            return _VectorIndex((), use_faiss=self._use_faiss)
        vectors = self._embedder.embed(texts)
        return _VectorIndex(vectors, use_faiss=self._use_faiss)

    def _embed_query(self, question: ParsedQuestion) -> list[float]:
        return self._embedder.embed([question.original_text])[0]

    def score_rules(self, question: ParsedQuestion) -> list[tuple[BusinessRule, float]]:
        """Score approved business rules by cosine similarity."""
        if not self._approved_rules:
            return []
        if self._rules_index is None:
            self._rules_index = self._build_index([f"{r.term}: {r.definition}" for r in self._approved_rules])
        hits = self._rules_index.search(self._embed_query(question), len(self._approved_rules))
        return [
            (self._approved_rules[idx], round(score, 6)) for idx, score in hits if score > self._min_score
        ]

    def rules(self, question: ParsedQuestion, *, top_k: int | None = None) -> tuple[BusinessRule, ...]:
        limit = self._k_rules if top_k is None else top_k
        if limit <= 0:
            return ()
        return tuple(rule for rule, _ in self.score_rules(question)[:limit])

    def score_examples(
        self,
        question: ParsedQuestion,
        *,
        dialect: Dialect | None = None,
    ) -> list[tuple[FewShotExample, float]]:
        """Score few-shot examples by question embedding similarity."""
        if not self._examples:
            return []
        if self._examples_index is None:
            self._examples_index = self._build_index([ex.question for ex in self._examples])
        hits = self._examples_index.search(self._embed_query(question), len(self._examples))
        out: list[tuple[FewShotExample, float]] = []
        for idx, score in hits:
            if score <= self._min_score:
                continue
            ex = self._examples[idx]
            if dialect is not None and ex.dialect is not dialect:
                continue
            out.append((ex, round(score, 6)))
        return out

    def examples(
        self,
        question: ParsedQuestion,
        *,
        dialect: Dialect | None = None,
        top_k: int | None = None,
    ) -> tuple[FewShotExample, ...]:
        limit = self._k_examples if top_k is None else top_k
        if limit <= 0:
            return ()
        return tuple(ex for ex, _ in self.score_examples(question, dialect=dialect)[:limit])

    def score_schema_elements(
        self,
        question: ParsedQuestion,
        *,
        schema: SchemaSnapshot | None = None,
    ) -> list[tuple[SchemaElement, float]]:
        """Score table and column elements of the scoped ``SchemaSnapshot``."""
        target_schema = schema if schema is not None else self._schema
        if target_schema is None:
            return []
        elements = schema_elements_from_snapshot(target_schema)
        if not elements:
            return []
        cache_key = tuple((e.table, e.column, e.description) for e in elements)
        cached = self._schema_cache.get(cache_key)
        if cached is None:
            index = self._build_index([e.to_search_text() for e in elements])
            self._schema_cache[cache_key] = (elements, index)
        else:
            elements, index = cached
        hits = index.search(self._embed_query(question), len(elements))
        return [(elements[idx], round(score, 6)) for idx, score in hits if score > self._min_score]

    def schema_elements(
        self,
        question: ParsedQuestion,
        *,
        schema: SchemaSnapshot | None = None,
        top_k: int | None = None,
    ) -> tuple[SchemaElement, ...]:
        limit = self._k_schema if top_k is None else top_k
        if limit <= 0:
            return ()
        return tuple(elem for elem, _ in self.score_schema_elements(question, schema=schema)[:limit])

    def score_metadata(
        self,
        question: ParsedQuestion,
        *,
        allowed_tables: frozenset[str] | None = None,
    ) -> list[tuple[MetadataEntry, float]]:
        """Score approved metadata entries by embedding similarity, honoring RBAC."""
        if not self._metadata:
            return []
        if self._metadata_index is None:
            self._metadata_index = self._build_index(
                [
                    " ".join(
                        [
                            m.table,
                            m.column,
                            m.description,
                            m.unit or "",
                            *m.synonyms,
                            *(f"{k} {v}" for k, v in m.code_values),
                        ]
                    )
                    for m in self._metadata
                ]
            )
        allowed = {t.lower() for t in allowed_tables} if allowed_tables is not None else None
        hits = self._metadata_index.search(self._embed_query(question), len(self._metadata))
        out: list[tuple[MetadataEntry, float]] = []
        for idx, score in hits:
            if score <= self._min_score:
                continue
            entry = self._metadata[idx]
            if allowed is not None and entry.table.lower() not in allowed:
                continue
            out.append((entry, round(score, 6)))
        return out

    def metadata(
        self,
        question: ParsedQuestion,
        *,
        allowed_tables: frozenset[str] | None = None,
        top_k: int | None = None,
    ) -> tuple[MetadataEntry, ...]:
        limit = self._k_metadata if top_k is None else top_k
        if limit <= 0:
            return ()
        return tuple(
            entry for entry, _ in self.score_metadata(question, allowed_tables=allowed_tables)[:limit]
        )
