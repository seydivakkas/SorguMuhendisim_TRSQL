"""L5 — Model Engine: local LLM backends behind the ``ModelAdapter`` port.

Rules (enforced by ``backend/boundaries.toml``):
- This module may import only ``backend.core``.
- It must never import database drivers, ``execution_engine`` or
  ``database_adapters``. A model has no path to the database (ADR-0004).
- Heavy inference libraries (``llama_cpp``, ``onnxruntime``, ``torch``...)
  may only be imported here.

Candidate models (AR-02): Hati-Glint-SQL-9B, Arctic-Text2SQL-R1-7B,
XiYanSQL-QwenCoder-7B as 4-bit/5-bit GGUF within a ~6.8 GB VRAM budget, plus
BGE-M3 GGUF on CPU behind ``EmbeddingAdapter`` (F4).
"""

from backend.model_engine.embedding import FakeEmbeddingAdapter, LlamaCppEmbeddingAdapter
from backend.model_engine.fake import FakeModelAdapter
from backend.model_engine.llama_cpp import (
    LlamaCppAdapter,
    estimate_vram_mb,
    extract_thinking_and_response,
    query_nvidia_smi_vram_mb,
)
from backend.model_engine.registry import create_embedding_adapter, create_model_adapter

__all__ = [
    "FakeEmbeddingAdapter",
    "FakeModelAdapter",
    "LlamaCppAdapter",
    "LlamaCppEmbeddingAdapter",
    "create_embedding_adapter",
    "create_model_adapter",
    "estimate_vram_mb",
    "extract_thinking_and_response",
    "query_nvidia_smi_vram_mb",
]
