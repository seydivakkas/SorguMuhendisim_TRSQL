from __future__ import annotations

import hashlib
import math
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from backend.core.config import ModelSettings
from backend.core.contracts import GenerationParams, PromptBundle, ReasoningMode
from backend.core.errors import ConfigError, ExecutionError
from backend.core.ports import EmbeddingAdapter, ModelAdapter
from backend.model_engine import (
    FakeEmbeddingAdapter,
    FakeModelAdapter,
    LlamaCppAdapter,
    LlamaCppEmbeddingAdapter,
    create_embedding_adapter,
    create_model_adapter,
    estimate_vram_mb,
    extract_thinking_and_response,
)

PROMPT = PromptBundle(
    template_id="mschema_v1",
    system="Sen bir SQL üretim bileşenisin.",
    user="Bayi sayısını getir.",
)


def _make_dummy_gguf(
    tmp_path: Path, name: str = "Hati-Glint-SQL-9B.Q4_K_M.gguf", payload: bytes = b"GGUF"
) -> Path:
    path = tmp_path / name
    path.write_bytes(payload)
    return path


def _install_fake_llama_cpp(
    monkeypatch: pytest.MonkeyPatch,
    *,
    chat_content: str = "```sql\nSELECT 1\n```",
    embeddings: list[list[float]] | None = None,
) -> dict[str, Any]:
    recorded: dict[str, Any] = {"init_calls": [], "chat_calls": [], "grammar_calls": [], "embed_calls": []}

    class FakeGrammar:
        def __init__(self, text: str) -> None:
            self.text = text

        @staticmethod
        def from_string(grammar: str, verbose: bool = False) -> FakeGrammar:
            recorded["grammar_calls"].append(grammar)
            return FakeGrammar(grammar)

    class FakeLlama:
        def __init__(self, **kwargs: Any) -> None:
            recorded["init_calls"].append(kwargs)
            self.closed = False

        def create_chat_completion(self, **kwargs: Any) -> dict[str, Any]:
            recorded["chat_calls"].append(kwargs)
            return {"choices": [{"message": {"content": chat_content}}]}

        def create_embedding(self, texts: list[str]) -> dict[str, Any]:
            recorded["embed_calls"].append(texts)
            vecs = embeddings if embeddings is not None else [[1.0, 0.0, 0.0] for _ in texts]
            return {"data": [{"index": i, "embedding": vec} for i, vec in enumerate(vecs)]}

        def close(self) -> None:
            self.closed = True

    mod = ModuleType("llama_cpp")
    mod.Llama = FakeLlama  # type: ignore[attr-defined]
    mod.LlamaGrammar = FakeGrammar  # type: ignore[attr-defined]
    mod.GGML_TYPE_Q8_0 = 8  # type: ignore[attr-defined]
    mod.GGML_TYPE_F16 = 1  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "llama_cpp", mod)
    return recorded


def test_llama_cpp_adapter_is_lazy_and_conforms_to_port(tmp_path: Path) -> None:
    missing = tmp_path / "does_not_exist.gguf"
    adapter = LlamaCppAdapter(missing, context_length=4096)
    assert isinstance(adapter, ModelAdapter)
    assert adapter.is_loaded is False
    assert adapter.info.model_id == str(missing)
    assert adapter.info.context_length == 4096

    with pytest.raises(ConfigError, match="bulunamadı"):
        adapter.generate(PROMPT, GenerationParams())


def test_llama_cpp_rejects_pickle_and_sha256_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bad_bin = tmp_path / "weights.bin"
    bad_bin.write_bytes(b"pickle-risk")
    with pytest.raises(ConfigError, match="pickle"):
        LlamaCppAdapter(bad_bin).load()

    gguf = _make_dummy_gguf(tmp_path, payload=b"valid-gguf-bytes")
    wrong_sha = "0" * 64
    with pytest.raises(ConfigError, match="SHA-256"):
        LlamaCppAdapter(gguf, expected_sha256=wrong_sha).load()

    good_sha = hashlib.sha256(b"valid-gguf-bytes").hexdigest()
    recorded = _install_fake_llama_cpp(monkeypatch)
    monkeypatch.setattr("backend.model_engine.llama_cpp.query_nvidia_smi_vram_mb", lambda: None)
    adapter = LlamaCppAdapter(gguf, expected_sha256=good_sha)
    adapter.load()
    assert adapter.is_loaded is True
    assert adapter.info.sha256 == good_sha
    assert adapter.info.quantization == "Q4_K_M"
    assert len(recorded["init_calls"]) == 1


def test_vram_budget_guard_static_and_nvidia_smi(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert estimate_vram_mb(4 * 1024**3, 4096, "q8_0", n_gpu_layers=0) == 0
    q8_est = estimate_vram_mb(4 * 1024**3, 4096, "q8_0", n_gpu_layers=-1)
    f16_est = estimate_vram_mb(4 * 1024**3, 4096, "f16", n_gpu_layers=-1)
    assert f16_est > q8_est

    gguf = _make_dummy_gguf(tmp_path)
    # Static KV + scratch estimate (~513 MB at 4096 ctx) exceeds 200 MB budget.
    tight_adapter = LlamaCppAdapter(gguf, context_length=4096, vram_budget_mb=200)
    with pytest.raises(ConfigError, match="bütçeyi"):
        tight_adapter.load()

    # Insufficient free GPU VRAM reported by nvidia-smi before load.
    _install_fake_llama_cpp(monkeypatch)
    monkeypatch.setattr(
        "backend.model_engine.llama_cpp.query_nvidia_smi_vram_mb",
        lambda: (8192, 8000, 192),
    )
    with pytest.raises(ExecutionError, match="boş GPU VRAM"):
        LlamaCppAdapter(gguf, context_length=4096, vram_budget_mb=6800).load()

    # Post-load VRAM spike exceeding budget.
    readings = iter([(8192, 500, 7692), (8192, 7600, 592)])
    monkeypatch.setattr(
        "backend.model_engine.llama_cpp.query_nvidia_smi_vram_mb",
        lambda: next(readings),
    )
    with pytest.raises(ExecutionError, match="VRAM artışı"):
        LlamaCppAdapter(gguf, context_length=4096, vram_budget_mb=6800).load()


def test_mocked_llama_cpp_inference_settings_thinking_and_gbnf(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gguf = _make_dummy_gguf(tmp_path, name="Arctic-Text2SQL-R1-7B.Q5_K_M.gguf")
    think_payload = (
        "<think>Bayi tablosunu saymam gerekiyor.</think>\n```sql\nSELECT COUNT(*) FROM dealers\n```"
    )
    recorded = _install_fake_llama_cpp(monkeypatch, chat_content=think_payload)
    monkeypatch.setattr("backend.model_engine.llama_cpp.query_nvidia_smi_vram_mb", lambda: None)

    adapter = LlamaCppAdapter(
        gguf,
        context_length=8192,
        vram_budget_mb=6800,
        kv_cache_type="q8_0",
        flash_attn=True,
        n_gpu_layers=-1,
        seed=123,
        reasoning_mode=ReasoningMode.THINKING,
    )
    raw = adapter.generate(
        PROMPT, GenerationParams(max_tokens=256, temperature=0.0), grammar='root ::= "SELECT 1"'
    )
    assert raw == think_payload
    assert adapter.last_reasoning == "Bayi tablosunu saymam gerekiyor."

    init_kw = recorded["init_calls"][0]
    assert init_kw["n_gpu_layers"] == -1
    assert init_kw["flash_attn"] is True
    assert init_kw["n_ctx"] == 8192
    assert init_kw["type_k"] == 8
    assert init_kw["type_v"] == 8
    assert init_kw["seed"] == 123

    chat_kw = recorded["chat_calls"][0]
    assert chat_kw["temperature"] == 0.0
    assert chat_kw["seed"] == 123
    assert recorded["grammar_calls"] == ['root ::= "SELECT 1"']

    reasoning, clean_sql = adapter.generate_with_thinking(PROMPT, GenerationParams())
    assert reasoning == "Bayi tablosunu saymam gerekiyor."
    assert clean_sql == "```sql\nSELECT COUNT(*) FROM dealers\n```"

    stripped_adapter = LlamaCppAdapter(gguf, strip_thinking=True)
    assert (
        stripped_adapter.generate(PROMPT, GenerationParams()) == "```sql\nSELECT COUNT(*) FROM dealers\n```"
    )


def test_extract_thinking_and_response_variants() -> None:
    r1, body1 = extract_thinking_and_response("<think>adım 1</think>\nSELECT 1")
    assert r1 == "adım 1" and body1 == "SELECT 1"

    r2, body2 = extract_thinking_and_response("ön doldurulmuş düşünce</think>\nSELECT 2")
    assert r2 == "ön doldurulmuş düşünce" and body2 == "SELECT 2"

    r3, body3 = extract_thinking_and_response("<think>kesilmiş düşünce")
    assert r3 == "kesilmiş düşünce" and body3 == ""

    r4, body4 = extract_thinking_and_response("SELECT 3")
    assert r4 is None and body4 == "SELECT 3"


def test_fake_and_llama_cpp_embedding_adapters(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeEmbeddingAdapter(dimension=32)
    assert isinstance(fake, EmbeddingAdapter)
    vecs = fake.embed(["İstanbul bayileri", "İstanbuldaki bayi satışları", "veritabanı sunucusu"])
    assert len(vecs) == 3
    assert all(len(v) == 32 for v in vecs)
    assert fake.embed(["İstanbul bayileri"])[0] == vecs[0]
    assert math.isclose(sum(x * x for x in vecs[0]), 1.0, rel_tol=1e-6)

    def cos(a: list[float], b: list[float]) -> float:
        return sum(x * y for x, y in zip(a, b, strict=True))

    assert cos(vecs[0], vecs[1]) > cos(vecs[0], vecs[2])

    missing_emb = LlamaCppEmbeddingAdapter(tmp_path / "missing_bge.gguf")
    assert isinstance(missing_emb, EmbeddingAdapter)
    assert missing_emb.is_loaded is False
    with pytest.raises(ConfigError, match="bulunamadı"):
        missing_emb.embed(["test"])

    bge_gguf = _make_dummy_gguf(tmp_path, name="bge-m3-f16.gguf")
    recorded = _install_fake_llama_cpp(monkeypatch, embeddings=[[3.0, 4.0]])
    emb_adapter = LlamaCppEmbeddingAdapter(bge_gguf, context_length=8192)
    assert emb_adapter.embed([]) == []
    assert emb_adapter.is_loaded is False

    out = emb_adapter.embed(["net satış cirosu"])
    assert emb_adapter.is_loaded is True
    assert recorded["init_calls"][0]["n_gpu_layers"] == 0
    assert recorded["init_calls"][0]["embedding"] is True
    assert len(out) == 1
    assert math.isclose(out[0][0], 0.6, rel_tol=1e-6)
    assert math.isclose(out[0][1], 0.8, rel_tol=1e-6)


def test_registry_model_and_embedding_factories(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_model = create_model_adapter(ModelSettings(adapter="fake"))
    assert isinstance(fake_model, FakeModelAdapter)
    fake_emb = create_embedding_adapter(ModelSettings(adapter="fake"), dimension=16)
    assert isinstance(fake_emb, FakeEmbeddingAdapter)

    monkeypatch.delenv("TRSQL_MODEL_PATH", raising=False)
    monkeypatch.delenv("TRSQL_EMBEDDING_MODEL_PATH", raising=False)
    with pytest.raises(ConfigError, match="TRSQL_MODEL_PATH"):
        create_model_adapter(ModelSettings(adapter="llama_cpp"))
    with pytest.raises(ConfigError, match="TRSQL_EMBEDDING_MODEL_PATH"):
        create_embedding_adapter(ModelSettings(adapter="llama_cpp"))

    gguf = _make_dummy_gguf(tmp_path)
    bge = _make_dummy_gguf(tmp_path, name="bge-m3.gguf")
    monkeypatch.setenv("TRSQL_MODEL_PATH", str(gguf))
    monkeypatch.setenv("TRSQL_EMBEDDING_MODEL_PATH", str(bge))

    model_adapter = create_model_adapter(ModelSettings(adapter="llama_cpp", context_length=4096, seed=99))
    emb_adapter = create_embedding_adapter(ModelSettings(adapter="llama_cpp", context_length=4096))
    assert isinstance(model_adapter, LlamaCppAdapter)
    assert isinstance(emb_adapter, LlamaCppEmbeddingAdapter)
    assert model_adapter.info.context_length == 4096

    with pytest.raises(ConfigError, match="unknown model adapter"):
        create_model_adapter(ModelSettings(adapter="nonexistent"))
    with pytest.raises(ConfigError, match="unknown embedding adapter"):
        create_embedding_adapter(ModelSettings(adapter="nonexistent"))
