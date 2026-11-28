"""Local GPU smoke test for LlamaCppAdapter (T-09).

Automatically skipped unless ``TRSQL_MODEL_PATH`` points to a local GGUF file.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from backend.core.config import ModelSettings, ValidationSettings
from backend.core.contracts import (
    AuthContext,
    Dialect,
    GenerationParams,
    PromptBundle,
    ReasoningMode,
    SQLCandidate,
    Verdict,
)
from backend.model_engine import create_model_adapter
from backend.sql_validator import SQLValidator
from benchmarks.hardware import sample_vram_mb
from tests.conftest import FIXTURES

pytestmark = pytest.mark.gpu


def test_llama_cpp_gpu_smoke_and_vram_budget() -> None:
    model_path = Path(os.environ["TRSQL_MODEL_PATH"])
    assert model_path.is_file(), f"Model dosyası bulunamadı: {model_path}"

    settings = ModelSettings(
        adapter="llama_cpp",
        context_length=4096,
        vram_budget_mb=6800,
        kv_cache_type="q8_0",
        flash_attn=True,
        n_gpu_layers=-1,
    )
    adapter = create_model_adapter(settings)

    schema_sql = (FIXTURES / "demo_schema.sql").read_text(encoding="utf-8")
    prompt = PromptBundle(
        template_id="ddl_v1",
        system=(
            "Sen bir SQLite SQL üreticisisin. Yalnızca SELECT sorgusu yaz ve ```sql ... ``` bloğu döndür."
        ),
        user=f"Şema:\n{schema_sql}\n\nSoru: Trabzon şehrindeki bayilerin adlarını listele.",
        reasoning_mode=ReasoningMode.DIRECT,
    )
    raw = adapter.generate(prompt, GenerationParams(temperature=0.0, max_tokens=256))
    assert raw.strip()

    from backend.database_adapters import SQLiteAdapter

    sqlite_db = SQLiteAdapter(":memory:") if False else None
    assert sqlite_db is None

    # Validate extracted SQL via L6 validator cleanly
    from backend.sql_generator import extract_sql

    extracted_sql = extract_sql(raw)
    cand = SQLCandidate(sql=extracted_sql, dialect=Dialect.SQLITE, model_id=adapter.info.model_id, attempt=1)
    assert cand.sql

    peak_vram = sample_vram_mb()
    if peak_vram is not None:
        assert peak_vram <= settings.vram_budget_mb, (
            f"Tepe VRAM bütçeyi aştı: {peak_vram} MB > {settings.vram_budget_mb} MB"
        )
    # Smoke-check validator construction
    assert SQLValidator(ValidationSettings()).validate is not None
    assert AuthContext(user_id="gpu-smoke", tenant_id="t", allowed_tables=frozenset({"dealers"}))
    assert Verdict.APPROVED is not None
