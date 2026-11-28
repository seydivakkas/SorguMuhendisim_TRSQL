from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.core.config import (
    AuthSettings,
    ModelSettings,
    RagSettings,
    RoutingSettings,
    Settings,
    ValidationSettings,
    load_settings,
)
from backend.knowledge_base import load_knowledge_base
from models.download import (
    CANDIDATE_MODELS,
    check_license_compliance,
    compute_sha256,
    validate_download_url,
    validate_weight_filename,
    verify_sha256,
)

ROOT = Path(__file__).resolve().parents[2]


def test_default_settings_load() -> None:
    s = load_settings(ROOT / "configs" / "default.toml")
    assert s.offline is True
    assert 1 <= s.retry.max_attempts <= 5


def test_default_settings_sections_and_fields() -> None:
    s = load_settings(ROOT / "configs" / "default.toml")
    assert s.validation.max_joins == 6
    assert s.validation.max_explain_cost == 1_000_000.0
    assert s.validation.max_explain_rows == 10_000_000

    assert s.model.adapter == "llama_cpp"
    assert s.model.kv_cache_type == "q8_0"
    assert s.model.flash_attn is True
    assert s.model.n_gpu_layers == -1
    assert s.model.embedding_model_path_env == "TRSQL_EMBEDDING_MODEL_PATH"
    assert s.model.seed == 42

    assert s.rag == RagSettings()
    assert s.rag.bm25_weight == 0.5
    assert s.rag.dense_weight == 0.5
    assert s.rag.rrf_k == 60
    assert s.rag.top_k_rules == 5
    assert s.rag.top_k_examples == 3
    assert s.rag.enable_schema_rag is True
    assert s.rag.enable_example_rag is True
    assert s.rag.enable_rule_rag is True
    assert s.rag.enable_value_linking is True

    assert s.routing == RoutingSettings()
    assert s.routing.enabled is True
    assert s.routing.thinking_threshold == 0.5
    assert s.routing.vote_candidates == 4
    assert s.routing.vote_threshold == 0.7

    assert s.auth == AuthSettings()
    assert s.auth.rate_limit_per_minute == 60


def test_settings_defaults_and_validation_bounds() -> None:
    defaults = Settings()
    assert defaults.model.adapter == "fake"
    assert defaults.rag.rrf_k == 60
    assert defaults.routing.vote_candidates == 4
    assert defaults.auth.rate_limit_per_minute == 60

    with pytest.raises(ValidationError):
        RagSettings(rrf_k=0)
    with pytest.raises(ValidationError):
        RoutingSettings(thinking_threshold=1.5)
    with pytest.raises(ValidationError):
        AuthSettings(rate_limit_per_minute=0)
    with pytest.raises(ValidationError):
        ValidationSettings(max_explain_cost=-1.0)
    with pytest.raises(ValidationError):
        ModelSettings(n_gpu_layers=-2)


def test_example_rules_are_not_approved() -> None:
    kb = load_knowledge_base(ROOT / "configs" / "knowledge.example.toml")
    assert kb.rules and kb.approved_rules() == ()


def test_model_manifest_and_sha256_verification(tmp_path: Path) -> None:
    expected_keys = {
        "hati-glint-sql-9b",
        "xiyansql-qwencoder-7b",
        "arctic-text2sql-r1-7b",
        "qwen3-4b-instruct",
        "bge-m3-gguf",
    }
    assert expected_keys.issubset(CANDIDATE_MODELS.keys())
    for spec in CANDIDATE_MODELS.values():
        assert spec.commercial_allowed is True
        validate_weight_filename(spec.filename)
        validate_download_url(spec.url)
        check_license_compliance(spec.license, model_key=spec.key)
        assert (ROOT / spec.card_path).is_file()

    weights_file = tmp_path / "test-model.Q4_K_M.gguf"
    weights_file.write_bytes(b"gguf-mock-payload")
    digest = compute_sha256(weights_file)
    assert len(digest) == 64
    assert verify_sha256(weights_file, digest.upper()) is True
    assert verify_sha256(weights_file, "0" * 64) is False

    with pytest.raises(ValueError):
        verify_sha256(weights_file, "not-a-sha256")


def test_model_downloader_refuses_pickle_and_restricted_licenses() -> None:
    validate_weight_filename("model.Q5_K_M.gguf")
    validate_weight_filename("model.safetensors")

    for bad_name in ("pytorch_model.bin", "weights.pt", "model.ckpt", "adapter.pkl", "data.bin.gz"):
        with pytest.raises(ValueError):
            validate_weight_filename(bad_name)

    with pytest.raises(ValueError):
        validate_download_url("http://huggingface.co/model.gguf")

    with pytest.raises(ValueError):
        check_license_compliance("qwen-research")
    with pytest.raises(ValueError):
        check_license_compliance("apache-2.0", model_key="xiyansql-qwencoder-3b-2504")
    check_license_compliance("qwen-research", allow_non_commercial=True)
