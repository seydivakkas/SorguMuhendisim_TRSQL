"""L5 — Model Engine: local LLM backends behind the ``ModelAdapter`` port.

Rules (enforced by ``backend/boundaries.toml``):
- This module may import only ``backend.core``.
- It must never import database drivers, ``execution_engine`` or
  ``database_adapters``. A model has no path to the database (ADR-0004).
- Heavy inference libraries (``llama_cpp``, ``onnxruntime``, ``torch``...)
  may only be imported here.

Candidate models (AR-02): Hati-Glint-SQL-9B, Arctic-Text2SQL-R1-7B,
XiYanSQL-QwenCoder-7B as 4-bit GGUF within a ~6.8 GB VRAM budget.
"""

from backend.model_engine.fake import FakeModelAdapter
from backend.model_engine.llama_cpp import LlamaCppAdapter
from backend.model_engine.registry import create_model_adapter

__all__ = ["FakeModelAdapter", "LlamaCppAdapter", "create_model_adapter"]
