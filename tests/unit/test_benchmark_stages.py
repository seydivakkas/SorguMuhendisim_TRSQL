from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path

import pytest

from backend.core.config import ModelSettings, Settings
from backend.core.contracts import Dialect, MentionKind
from backend.core.errors import ConfigError
from backend.knowledge_base import InMemoryKnowledgeBase
from backend.model_engine import FakeModelAdapter
from benchmarks.runner import ExperimentConfig, run_benchmark
from benchmarks.stages import STAGE_PROFILES, resolve_stage_profile
from tests.conftest import FIXTURES, LOCATIONS, NLP_LEXICON, SCHEMA_LEXICON


def _write_demo_db(path: Path) -> Path:
    conn = sqlite3.connect(path)
    conn.executescript((FIXTURES / "demo_schema.sql").read_text(encoding="utf-8"))
    conn.commit()
    conn.close()
    return path


def _make_dataset(path: Path) -> Path:
    row = {
        "id": "q1",
        "question": "Trabzon'daki bayiler hangileri?",
        "gold_sql": "SELECT name FROM dealers WHERE city = 'Trabzon'",
        "db_id": "demo",
        "category": "normal",
        "difficulty": "easy",
    }
    path.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def test_unknown_stage_raises_config_error() -> None:
    with pytest.raises(ConfigError):
        resolve_stage_profile("D99")


def test_stage_profiles_d0_to_d8_cumulative() -> None:
    assert tuple(STAGE_PROFILES) == ("D0", "D1", "D2", "D3", "D4", "D5", "D6", "D7", "D8")
    assert STAGE_PROFILES["D0"].pipeline == "default"
    assert STAGE_PROFILES["D0"].prompt_template_id == "ddl_v1"
    assert STAGE_PROFILES["D0"].max_attempts == 1
    assert STAGE_PROFILES["D1"].prompt_template_id == "mschema_v1"
    assert STAGE_PROFILES["D2"].pipeline == "hybrid"
    assert STAGE_PROFILES["D2"].linker == "hybrid"
    assert STAGE_PROFILES["D2"].rag == "off"
    assert STAGE_PROFILES["D3"].rag == "full"
    assert STAGE_PROFILES["D4"].turkish_nlp == "morphology_ambiguity"
    assert STAGE_PROFILES["D5"].fail_closed_full is True
    assert STAGE_PROFILES["D6"].routing_enabled is True
    assert STAGE_PROFILES["D6"].vote_candidates == 4
    assert STAGE_PROFILES["D6"].max_attempts == 3
    assert STAGE_PROFILES["D7"].fine_tuned_adapter is True
    assert STAGE_PROFILES["D8"].use_kpi_templates is True


def test_stage_overrides_and_invalid_override_rejection() -> None:
    d6_gbnf = resolve_stage_profile("D6", {"grammar_constrained": True, "vote_candidates": 2})
    assert d6_gbnf.grammar_constrained is True
    assert d6_gbnf.vote_candidates == 2

    with pytest.raises(ConfigError):
        resolve_stage_profile("D0", {"max_attempts": 9})
    with pytest.raises(ConfigError):
        resolve_stage_profile("D0", {"nonexistent_flag": True})


def test_d0_and_d8_emit_different_prompts_and_write_resolved_profile(
    tmp_path: Path,
    knowledge: InMemoryKnowledgeBase,
    caplog: pytest.LogCaptureFixture,
) -> None:
    db_file = _write_demo_db(tmp_path / "demo.sqlite")
    ds_file = _make_dataset(tmp_path / "ds.jsonl")

    def _run_stage(stage: str, out_name: str, model: FakeModelAdapter) -> dict[str, object]:
        cfg = ExperimentConfig(
            name=f"test-{stage.lower()}",
            stage=stage,
            dataset="enterprise",
            dataset_path=str(ds_file),
            allow_dirty=True,
            dialect=Dialect.SQLITE,
            db_path=str(db_file),
            allowed_tables=("dealers", "sales"),
            denied_columns=("dealers.tax_number",),
            nlp_lexicon={k: MentionKind(v.value) for k, v in NLP_LEXICON.items()},
            schema_lexicon=dict(SCHEMA_LEXICON),
            locations=tuple(sorted(LOCATIONS)),
        )
        return run_benchmark(
            cfg,
            model=model,
            knowledge=knowledge,
            output_dir=tmp_path / out_name,
        )

    m_d0 = FakeModelAdapter(["SELECT name FROM dealers WHERE city = 'Trabzon'"], model_id="fake-d0")
    res_d0 = _run_stage("D0", "out_d0", m_d0)

    m_d8 = FakeModelAdapter(["SELECT name FROM dealers WHERE city = 'Trabzon'"], model_id="fake-d8")
    with caplog.at_level(logging.WARNING):
        res_d8 = _run_stage("D8", "out_d8", m_d8)

    assert len(m_d0.prompts) == 1
    assert len(m_d8.prompts) == 1
    assert "CREATE TABLE" in m_d0.prompts[0].user
    assert "【DB_DIALECT】" not in m_d0.prompts[0].user
    assert "【DB_DIALECT】" in m_d8.prompts[0].user
    assert "CREATE TABLE" not in m_d8.prompts[0].user

    assert res_d0["stage_profile"]["stage"] == "D0"  # type: ignore[index]
    assert res_d0["stage_profile"]["prompt_template_id"] == "ddl_v1"  # type: ignore[index]
    assert res_d8["stage_profile"]["stage"] == "D8"  # type: ignore[index]
    assert res_d8["stage_profile"]["use_kpi_templates"] is True  # type: ignore[index]
    assert res_d8["embedder"] == "hash-fallback"
    assert any(
        "hash-fallback" in rec.message or "DeterministicHashEmbedder" in rec.message for rec in caplog.records
    )


def test_configured_embedding_env_uses_create_embedding_adapter(
    tmp_path: Path,
    knowledge: InMemoryKnowledgeBase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_file = _write_demo_db(tmp_path / "demo.sqlite")
    ds_file = _make_dataset(tmp_path / "ds.jsonl")
    monkeypatch.setenv("TRSQL_EMBEDDING_MODEL_PATH", str(tmp_path / "fake-bge.gguf"))
    cfg = ExperimentConfig(
        name="test-d3-embedder",
        stage="D3",
        dataset="enterprise",
        dataset_path=str(ds_file),
        allow_dirty=True,
        dialect=Dialect.SQLITE,
        db_path=str(db_file),
        allowed_tables=("dealers", "sales"),
        denied_columns=("dealers.tax_number",),
        nlp_lexicon={k: MentionKind(v.value) for k, v in NLP_LEXICON.items()},
        schema_lexicon=dict(SCHEMA_LEXICON),
        locations=tuple(sorted(LOCATIONS)),
        settings=Settings(model=ModelSettings(adapter="fake")),
    )
    res = run_benchmark(
        cfg,
        model=FakeModelAdapter(["SELECT name FROM dealers WHERE city = 'Trabzon'"], model_id="fake-d3"),
        knowledge=knowledge,
        output_dir=tmp_path / "out_d3",
    )
    assert res["embedder"] == "adapter:fake"
    assert res["warnings"] == []
