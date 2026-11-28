"""Typed settings loaded from ``configs/*.toml``.

No secrets live in TOML files. Connection strings and keys come from
environment variables named in the config (``*_env`` fields).
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from pydantic import Field

from backend.core.contracts import Contract
from backend.core.errors import ConfigError


class RetrySettings(Contract):
    max_attempts: int = Field(default=3, ge=1, le=5)
    """Total generation attempts, including the first (ADR-0006)."""


class ExecutionSettings(Contract):
    timeout_ms: int = Field(default=5000, gt=0, le=60_000)
    max_rows: int = Field(default=1000, gt=0, le=100_000)


class ValidationSettings(Contract):
    max_joins: int = Field(default=6, ge=0)
    forbidden_functions: tuple[str, ...] = (
        "pg_sleep",
        "pg_read_file",
        "pg_ls_dir",
        "lo_import",
        "lo_export",
        "dblink",
        "load_extension",
        "readfile",
        "writefile",
    )


class ModelSettings(Contract):
    adapter: str = "fake"
    model_path_env: str = "TRSQL_MODEL_PATH"
    context_length: int = Field(default=4096, gt=0)
    vram_budget_mb: int = Field(default=6800, gt=0)
    """Net VRAM budget on the reference machine (RTX 4070 Laptop, 8 GB)."""


class Settings(Contract):
    offline: bool = True
    """When True, no component may open outbound network connections (ADR-0002)."""
    retry: RetrySettings = RetrySettings()
    execution: ExecutionSettings = ExecutionSettings()
    validation: ValidationSettings = ValidationSettings()
    model: ModelSettings = ModelSettings()


def load_settings(path: str | Path) -> Settings:
    p = Path(path)
    try:
        data = tomllib.loads(p.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f"config could not be read: {p}") from exc
    return Settings.model_validate(data)
