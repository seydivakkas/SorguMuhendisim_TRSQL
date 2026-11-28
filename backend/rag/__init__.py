"""L4 — Enterprise RAG: retrieves business rules, schema elements, masked
SQL examples, metadata, and cell values relevant to a Turkish question.
"""

from __future__ import annotations

from backend.rag.bm25 import (
    BM25Retriever,
    OkapiBM25,
    SchemaElement,
    infer_question_skeleton,
    mask_sql_literals_and_identifiers,
    schema_elements_from_snapshot,
    skeleton_similarity,
    tokenize_turkish,
)
from backend.rag.dense import DenseRetriever, DeterministicHashEmbedder
from backend.rag.fusion import (
    HybridKnowledgeRetriever,
    HybridRetrievalResult,
    reciprocal_rank_fusion,
)
from backend.rag.retriever import KeywordRetriever
from backend.rag.values import (
    DEFAULT_PII_COLUMN_TOKENS,
    MinHashLSHIndex,
    ValueLinker,
    ValueMatch,
    lemmatize_turkish_token,
    levenshtein_distance,
    turkish_lemma_candidates,
)

__all__ = [
    "DEFAULT_PII_COLUMN_TOKENS",
    "BM25Retriever",
    "DenseRetriever",
    "DeterministicHashEmbedder",
    "HybridKnowledgeRetriever",
    "HybridRetrievalResult",
    "KeywordRetriever",
    "MinHashLSHIndex",
    "OkapiBM25",
    "SchemaElement",
    "ValueLinker",
    "ValueMatch",
    "infer_question_skeleton",
    "lemmatize_turkish_token",
    "levenshtein_distance",
    "mask_sql_literals_and_identifiers",
    "reciprocal_rank_fusion",
    "schema_elements_from_snapshot",
    "skeleton_similarity",
    "tokenize_turkish",
    "turkish_lemma_candidates",
]
