from __future__ import annotations

import hashlib
import math
import re
import struct
from collections.abc import Mapping, Sequence
from pathlib import Path

from backend.core.errors import ConfigError, ExecutionError
from backend.model_engine.llama_cpp import _accepts_named_kwarg, _import_llama_cpp

_FORBIDDEN_WEIGHT_SUFFIXES = frozenset({".bin", ".pt", ".pth", ".ckpt", ".pkl", ".pickle", ".joblib"})
_TOKEN_RE = re.compile(r"[0-9a-zçğıöşü]+")


def _tr_lower(text: str) -> str:
    return text.replace("İ", "i").replace("I", "ı").lower()


def _l2_normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0.0:
        return vec
    return [v / norm for v in vec]


def _coerce_vector(raw: object, *, normalize: bool) -> list[float] | None:
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return None
    if not raw:
        return []
    first = raw[0]
    # Some llama.cpp builds return per-token vectors when pooling is disabled; mean-pool them.
    if isinstance(first, Sequence) and not isinstance(first, (str, bytes)):
        token_vecs: list[list[float]] = []
        for token_row in raw:
            if not isinstance(token_row, Sequence) or isinstance(token_row, (str, bytes)):
                return None
            token_vecs.append([float(x) for x in token_row])
        dim = len(token_vecs[0])
        if dim == 0:
            return []
        pooled = [sum(row[i] for row in token_vecs) / len(token_vecs) for i in range(dim)]
        return _l2_normalize(pooled) if normalize else pooled
    vec = [float(x) for x in raw]
    return _l2_normalize(vec) if normalize else vec


class FakeEmbeddingAdapter:
    """Deterministic character n-gram + word hash embedding adapter for tests.

    Produces unit-normalized vectors without requiring GGUF weights or
    ``llama-cpp-python`` installed. Identical texts always map to identical
    vectors; morphologically similar Turkish tokens share overlapping features.
    """

    def __init__(self, dimension: int = 64) -> None:
        if dimension <= 0:
            raise ConfigError(f"Gömme boyutu pozitif olmalıdır: {dimension}")
        self._dimension = dimension

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        vec = [0.0] * self._dimension
        normalized = _tr_lower(text).strip()
        if not normalized:
            return vec

        features: list[tuple[str, float]] = []
        for token in _TOKEN_RE.findall(normalized):
            features.append((f"w:{token}", 2.0))
            if len(token) >= 3:
                for i in range(len(token) - 2):
                    features.append((f"c:{token[i : i + 3]}", 1.0))
            else:
                features.append((f"c:{token}", 1.0))

        if not features:
            features.append((f"raw:{normalized}", 1.0))

        for feat, weight in features:
            digest = hashlib.blake2b(feat.encode("utf-8"), digest_size=8).digest()
            raw_int = struct.unpack("<Q", digest)[0]
            bucket = raw_int % self._dimension
            sign = 1.0 if ((raw_int >> 63) & 1) == 0 else -1.0
            vec[bucket] += sign * weight
        return _l2_normalize(vec)


class LlamaCppEmbeddingAdapter:
    """CPU-only local GGUF embedding adapter (e.g., BGE-M3) via ``llama-cpp-python``.

    Always initializes ``Llama`` with ``n_gpu_layers=0`` and ``embedding=True``
    so the 8 GB GPU VRAM stays reserved for the SQL generation LLM (F4).
    """

    def __init__(
        self,
        model_path: str | Path,
        context_length: int = 8192,
        *,
        normalize: bool = True,
        n_threads: int | None = None,
    ) -> None:
        if context_length <= 0:
            raise ConfigError(f"context_length pozitif olmalıdır: {context_length}")
        self._model_path = Path(model_path)
        self._context_length = context_length
        self._normalize = normalize
        self._n_threads = n_threads
        self._llm: object | None = None

    @property
    def is_loaded(self) -> bool:
        return self._llm is not None

    def _validate_path(self) -> Path:
        path = self._model_path
        if not path.is_file():
            raise ConfigError(f"Gömme modeli dosyası bulunamadı: {path}")
        suffixes = [s.lower() for s in path.suffixes]
        for suffix in suffixes:
            if suffix in _FORBIDDEN_WEIGHT_SUFFIXES:
                raise ConfigError(f"Pickle/ikili gömme dosyası reddedildi ({suffix}): {path.name}")
        if not suffixes or suffixes[-1] != ".gguf":
            raise ConfigError(f"Gömme modeli .gguf formatında olmalıdır: {path.name}")
        return path

    def load(self) -> None:
        """Validate the GGUF file and initialize ``llama_cpp.Llama`` in CPU embedding mode."""
        self._ensure_loaded()

    def _ensure_loaded(self) -> object:
        if self._llm is not None:
            return self._llm
        path = self._validate_path()
        llama_mod = _import_llama_cpp()
        llama_cls = getattr(llama_mod, "Llama", None)
        if llama_cls is None or not callable(llama_cls):
            raise ConfigError("llama_cpp.Llama sınıfı bulunamadı.")

        embed_param = "embeddings" if _accepts_named_kwarg(llama_cls, "embeddings") else "embedding"
        kwargs: dict[str, object] = {
            "model_path": str(path),
            embed_param: True,
            "n_gpu_layers": 0,
            "n_ctx": self._context_length,
            "verbose": False,
        }
        if self._n_threads is not None:
            kwargs["n_threads"] = self._n_threads
        try:
            self._llm = llama_cls(**kwargs)
        except Exception as exc:
            raise ExecutionError(f"Gömme modeli yüklenemedi ({path.name}): {exc}") from exc
        return self._llm

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Compute dense embeddings for ``texts`` on CPU."""
        if not texts:
            return []
        llm = self._ensure_loaded()

        create_fn = getattr(llm, "create_embedding", None)
        if callable(create_fn):
            raw_resp = create_fn(texts)
            if isinstance(raw_resp, Mapping):
                data = raw_resp.get("data")
                if isinstance(data, Sequence) and len(data) == len(texts):
                    vectors: list[list[float]] = []
                    valid = True
                    for item in data:
                        if not isinstance(item, Mapping):
                            valid = False
                            break
                        coerced = _coerce_vector(item.get("embedding"), normalize=self._normalize)
                        if coerced is None:
                            valid = False
                            break
                        vectors.append(coerced)
                    if valid:
                        return vectors

        embed_fn = getattr(llm, "embed", None)
        if callable(embed_fn):
            vectors = []
            for text in texts:
                coerced = _coerce_vector(embed_fn(text), normalize=self._normalize)
                if coerced is None:
                    raise ExecutionError("Gömme modeli geçersiz vektör döndürdü.")
                vectors.append(coerced)
            return vectors

        raise ExecutionError("Gömme modeli create_embedding veya embed yöntemi sağlamıyor.")
