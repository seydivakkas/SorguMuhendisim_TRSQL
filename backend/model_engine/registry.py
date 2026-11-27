from __future__ import annotations

import os

from backend.core.config import ModelSettings
from backend.core.errors import ConfigError
from backend.core.ports import ModelAdapter
from backend.model_engine.llama_cpp import LlamaCppAdapter


def create_model_adapter(settings: ModelSettings) -> ModelAdapter:
    """Build the adapter named in config. Adding a model = adding a branch
    here plus one adapter class; no other module changes (ADR-0003)."""
    if settings.adapter == "llama_cpp":
        path = os.environ.get(settings.model_path_env)
        if not path:
            raise ConfigError(f"model path env var {settings.model_path_env} is not set")
        return LlamaCppAdapter(path, settings.context_length)
    raise ConfigError(f"unknown model adapter: {settings.adapter!r}")
