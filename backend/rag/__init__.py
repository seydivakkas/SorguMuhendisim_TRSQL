"""L4 — Enterprise RAG: finds the business rules and few-shot examples
relevant to a question.

Baseline: token-overlap scoring. BM25 + FAISS (BGE-M3 on CPU) fused with
RRF is the AR-04 candidate (ablation tier D3).
"""

from backend.rag.retriever import KeywordRetriever

__all__ = ["KeywordRetriever"]
