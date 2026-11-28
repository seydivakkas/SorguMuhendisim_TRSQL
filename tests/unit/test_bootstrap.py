from __future__ import annotations

import logging
from pathlib import Path

import pytest

from backend.core.config import ModelSettings, Settings
from backend.core.contracts import AuthContext, QueryRequest
from backend.core.errors import ConfigError
from backend.model_engine import FakeModelAdapter
from backend.orchestration import build_embedder_from_env, build_pipeline_from_env
from backend.rag import DeterministicHashEmbedder


def _write_fake_config(path: Path) -> Path:
    path.write_text(
        """
offline = true

[model]
adapter = "fake"
embedding_model_path_env = "TRSQL_EMBEDDING_MODEL_PATH"
""",
        encoding="utf-8",
    )
    return path


def test_build_pipeline_from_env_sqlite_succeeds(db_path: Path, tmp_path: Path) -> None:
    cfg = _write_fake_config(tmp_path / "cfg.toml")
    pipeline = build_pipeline_from_env(
        environ={
            "TRSQL_CONFIG": str(cfg),
            "TRSQL_DB_DIALECT": "sqlite",
            "TRSQL_SQLITE_PATH": str(db_path),
            "TRSQL_PIPELINE": "hybrid",
        },
        model=FakeModelAdapter(["SELECT COUNT(*) FROM dealers"]),
    )
    assert pipeline is not None
    preview = pipeline.preview_plan(
        QueryRequest(question="kaç bayi var", connection_id="demo"),
        AuthContext(user_id="u1", tenant_id="t1", allowed_tables=frozenset({"dealers"})),
    )
    assert preview.tables == ("dealers",)


def test_build_pipeline_from_env_missing_db_fails_closed(tmp_path: Path) -> None:
    cfg = _write_fake_config(tmp_path / "cfg.toml")
    with pytest.raises(ConfigError):
        build_pipeline_from_env(environ={"TRSQL_CONFIG": str(cfg)})

    with pytest.raises(ConfigError):
        build_pipeline_from_env(
            environ={
                "TRSQL_CONFIG": str(cfg),
                "TRSQL_DB_DIALECT": "sqlite",
                "TRSQL_SQLITE_PATH": str(tmp_path / "missing.sqlite"),
            }
        )


def test_build_pipeline_from_env_never_leaks_dsn_or_password(tmp_path: Path) -> None:
    cfg = _write_fake_config(tmp_path / "cfg.toml")
    dsn_sample = "postgresql://nl2sql_reader:SuperSecretPass99@db.internal:5432/trsql"
    bad_dsn = "not-a-valid-dsn-with-SecretPass42"

    # Missing PG env var -> ConfigError without secret value
    with pytest.raises(ConfigError) as exc_missing:
        build_pipeline_from_env(
            environ={
                "TRSQL_CONFIG": str(cfg),
                "TRSQL_DB_DIALECT": "postgres",
            }
        )
    assert "SuperSecretPass99" not in str(exc_missing.value)

    # Invalid DSN format -> ConfigError must NOT echo the malformed DSN
    with pytest.raises(ConfigError) as exc_bad:
        build_pipeline_from_env(
            environ={
                "TRSQL_CONFIG": str(cfg),
                "TRSQL_DB_DIALECT": "postgres",
                "TRSQL_PG_DSN": bad_dsn,
            }
        )
    assert "SecretPass42" not in str(exc_bad.value)
    assert bad_dsn not in str(exc_bad.value)

    # Valid-looking DSN without live server -> ConfigError sanitized (no password)
    with pytest.raises(ConfigError) as exc_conn:
        build_pipeline_from_env(
            environ={
                "TRSQL_CONFIG": str(cfg),
                "TRSQL_DB_DIALECT": "postgres",
                "TRSQL_PG_DSN": dsn_sample,
            },
            model=FakeModelAdapter(["SELECT 1"]),
        )
    assert "SuperSecretPass99" not in str(exc_conn.value)
    assert "db.internal" not in str(exc_conn.value)


def test_build_embedder_from_env_logs_warning_on_hash_fallback(
    caplog: pytest.LogCaptureFixture,
) -> None:
    settings = Settings(model=ModelSettings(adapter="llama_cpp"))
    with caplog.at_level(logging.WARNING):
        embedder, is_fallback = build_embedder_from_env(settings, environ={})
    assert is_fallback is True
    assert isinstance(embedder, DeterministicHashEmbedder)
    assert any("DeterministicHashEmbedder" in rec.message for rec in caplog.records)
