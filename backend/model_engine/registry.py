from __future__ import annotations

import os
from collections.abc import Sequence

from backend.core.config import ModelSettings
from backend.core.errors import ConfigError
from backend.core.ports import EmbeddingAdapter, ModelAdapter
from backend.model_engine.embedding import FakeEmbeddingAdapter, LlamaCppEmbeddingAdapter
from backend.model_engine.fake import FakeModelAdapter
from backend.model_engine.llama_cpp import LlamaCppAdapter


def create_model_adapter(
    settings: ModelSettings,
    *,
    responses: Sequence[str] | None = None,
) -> ModelAdapter:
    """Build the model adapter named in config (ADR-0003)."""
    if settings.adapter == "fake":
        return FakeModelAdapter(responses or ("SELECT 1",))
    if settings.adapter == "llama_cpp":
        path = os.environ.get(settings.model_path_env, "").strip()
        if not path:
            raise ConfigError(f"model path env var {settings.model_path_env} is not set")
        expected_sha = os.environ.get(f"{settings.model_path_env}_SHA256", "").strip() or None
        return LlamaCppAdapter(
            path,
            settings.context_length,
            vram_budget_mb=settings.vram_budget_mb,
            kv_cache_type=settings.kv_cache_type,
            flash_attn=settings.flash_attn,
            n_gpu_layers=settings.n_gpu_layers,
            seed=settings.seed,
            expected_sha256=expected_sha,
        )
    raise ConfigError(f"unknown model adapter: {settings.adapter!r}")


def create_embedding_adapter(
    settings: ModelSettings,
    *,
    dimension: int = 64,
) -> EmbeddingAdapter:
    """Build the embedding adapter named in config (CPU-only for llama_cpp)."""
    if settings.adapter == "fake":
        return FakeEmbeddingAdapter(dimension=dimension)
    if settings.adapter == "llama_cpp":
        path = os.environ.get(settings.embedding_model_path_env, "").strip()
        if not path:
            raise ConfigError(f"embedding model path env var {settings.embedding_model_path_env} is not set")
        return LlamaCppEmbeddingAdapter(path, settings.context_length)
    raise ConfigError(f"unknown embedding adapter: {settings.adapter!r}")
