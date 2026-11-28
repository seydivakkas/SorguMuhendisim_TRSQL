from __future__ import annotations

import hashlib
import importlib
import inspect
import math
import re
import shutil
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Protocol, cast

from backend.core.contracts import GenerationParams, ModelInfo, PromptBundle, ReasoningMode
from backend.core.errors import ConfigError, ExecutionError

_FORBIDDEN_WEIGHT_SUFFIXES = frozenset({".bin", ".pt", ".pth", ".ckpt", ".pkl", ".pickle", ".joblib"})
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_QUANT_RE = re.compile(r"(IQ\d_[A-Z0-9]+|Q\d_[A-Z0-9_]+|F16|F32|BF16)", re.IGNORECASE)
_THINK_BLOCK_RE = re.compile(r"<think>(.*?)</think>", re.DOTALL | re.IGNORECASE)
_THINK_OPEN_RE = re.compile(r"<think>", re.IGNORECASE)
_THINK_CLOSE_RE = re.compile(r"</think>", re.IGNORECASE)

# Standard ggml_type numeric identifiers expected by llama-cpp-python type_k/type_v.
_KV_CACHE_GGML_TYPES: dict[str, tuple[str, int, float]] = {
    "f32": ("GGML_TYPE_F32", 0, 4.0),
    "f16": ("GGML_TYPE_F16", 1, 2.0),
    "fp16": ("GGML_TYPE_F16", 1, 2.0),
    "q4_0": ("GGML_TYPE_Q4_0", 2, 0.5),
    "q4_1": ("GGML_TYPE_Q4_1", 3, 0.5625),
    "q5_0": ("GGML_TYPE_Q5_0", 6, 0.6875),
    "q5_1": ("GGML_TYPE_Q5_1", 7, 0.75),
    "q8_0": ("GGML_TYPE_Q8_0", 8, 1.0),
}

# Reference 7B-9B GQA KV elements per token: 2 * 32 layers * 8 kv_heads * 128 head_dim.
_KV_ELEMENTS_PER_TOKEN = 2 * 32 * 8 * 128
_CUDA_SCRATCH_OVERHEAD_MB = 256


class _LlamaInstance(Protocol):
    def create_chat_completion(self, **kwargs: object) -> object: ...

    def __call__(self, prompt: str, **kwargs: object) -> object: ...


class _LlamaGrammarFactory(Protocol):
    @staticmethod
    def from_string(grammar: str, verbose: bool = False) -> object: ...


def _infer_quantization(model_path: str | Path) -> str:
    match = _QUANT_RE.search(Path(model_path).name)
    return match.group(1).upper() if match else "gguf"


def _normalize_sha256(digest: str) -> str:
    cleaned = digest.strip().lower()
    if not _SHA256_RE.fullmatch(cleaned):
        raise ConfigError(f"Geçersiz SHA-256 özeti (64 hex karakter beklenir): {digest!r}")
    return cleaned


def _compute_file_sha256(path: Path, chunk_size: int = 1024 * 1024) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            hasher.update(chunk)
    return hasher.hexdigest()


def estimate_vram_mb(
    file_size_bytes: int,
    context_length: int,
    kv_cache_type: str = "q8_0",
    n_gpu_layers: int = -1,
) -> int:
    """Estimate GPU VRAM footprint in MiB from GGUF weights and KV cache size."""
    kv_key = kv_cache_type.strip().lower()
    if kv_key not in _KV_CACHE_GGML_TYPES:
        raise ConfigError(f"Desteklenmeyen KV cache tipi: {kv_cache_type!r}")
    if context_length <= 0:
        raise ConfigError(f"context_length pozitif olmalıdır: {context_length}")
    if n_gpu_layers == 0:
        return 0
    _, _, bytes_per_element = _KV_CACHE_GGML_TYPES[kv_key]
    weights_mb = math.ceil(max(0, file_size_bytes) / (1024 * 1024))
    kv_bytes = context_length * _KV_ELEMENTS_PER_TOKEN * bytes_per_element
    kv_mb = math.ceil(kv_bytes / (1024 * 1024))
    return weights_mb + kv_mb + _CUDA_SCRATCH_OVERHEAD_MB


def query_nvidia_smi_vram_mb() -> tuple[int, int, int] | None:
    """Return ``(total_mb, used_mb, free_mb)`` for GPU 0 via ``nvidia-smi``, or ``None``."""
    exe = shutil.which("nvidia-smi")
    if not exe:
        return None
    try:
        proc = subprocess.run(  # noqa: S603
            [exe, "--query-gpu=memory.total,memory.used,memory.free", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    first_line = next((line.strip() for line in proc.stdout.splitlines() if line.strip()), "")
    if not first_line:
        return None
    parts = [p.strip() for p in first_line.split(",")]
    if len(parts) < 3:
        return None
    try:
        return int(float(parts[0])), int(float(parts[1])), int(float(parts[2]))
    except ValueError:
        return None


def extract_thinking_and_response(text: str) -> tuple[str | None, str]:
    """Split ``<think>...</think>`` reasoning from the final response body.

    Handles well-formed ``<think>...</think>`` blocks, orphan closing
    ``</think>`` (when chat templates pre-fill ``<think>``), and truncated
    outputs that open ``<think>`` without closing it.
    """
    blocks = [m.group(1).strip() for m in _THINK_BLOCK_RE.finditer(text) if m.group(1).strip()]
    if _THINK_BLOCK_RE.search(text):
        remainder = _THINK_BLOCK_RE.sub("", text).strip()
        reasoning = "\n\n".join(blocks) if blocks else None
        return reasoning, remainder

    close_match = _THINK_CLOSE_RE.search(text)
    if close_match is not None:
        reasoning_part = _THINK_OPEN_RE.sub("", text[: close_match.start()]).strip()
        response_part = text[close_match.end() :].strip()
        return (reasoning_part or None), response_part

    open_match = _THINK_OPEN_RE.search(text)
    if open_match is not None:
        before = text[: open_match.start()].strip()
        after = text[open_match.end() :].strip()
        return (after or None), before

    return None, text.strip()


def _import_llama_cpp() -> object:
    try:
        return importlib.import_module("llama_cpp")
    except ImportError as exc:
        raise ConfigError(
            "llama-cpp-python kurulu değil; yerel GGUF çıkarımı için 'pip install -e .[llm]' kurun."
        ) from exc


def _resolve_kv_cache_type(llama_mod: object, kv_cache_type: str) -> int:
    key = kv_cache_type.strip().lower()
    if key not in _KV_CACHE_GGML_TYPES:
        raise ConfigError(f"Desteklenmeyen KV cache tipi: {kv_cache_type!r}")
    attr_name, fallback_code, _ = _KV_CACHE_GGML_TYPES[key]
    raw_val = getattr(llama_mod, attr_name, fallback_code)
    return int(raw_val) if isinstance(raw_val, int) else fallback_code


def _filter_supported_kwargs(callable_obj: object, kwargs: dict[str, object]) -> dict[str, object]:
    if not callable(callable_obj):
        return kwargs
    try:
        sig = inspect.signature(callable_obj)
    except (TypeError, ValueError):
        return kwargs
    params = sig.parameters
    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()):
        return kwargs
    return {k: v for k, v in kwargs.items() if k in params}


def _extract_completion_text(response: object) -> str | None:
    if isinstance(response, str):
        return response
    if not isinstance(response, Mapping):
        return None
    choices = response.get("choices")
    if not isinstance(choices, Sequence) or not choices:
        return None
    first = choices[0]
    if not isinstance(first, Mapping):
        return None
    message = first.get("message")
    if isinstance(message, Mapping):
        content = message.get("content")
        if isinstance(content, str):
            return content
    text = first.get("text")
    if isinstance(text, str):
        return text
    return None


class LlamaCppAdapter:
    """Offline-first local GGUF backend powered by ``llama-cpp-python``.

    Loads the model lazily on first inference (or explicit :meth:`load`),
    verifies file existence and optional SHA-256 digest, enforces the configured
    VRAM budget before and after loading, and uses deterministic defaults
    (``temperature=0.0``, ``seed``) with optional GBNF grammar constraints.
    """

    def __init__(
        self,
        model_path: str | Path,
        context_length: int = 4096,
        *,
        vram_budget_mb: int = 6800,
        kv_cache_type: str = "q8_0",
        flash_attn: bool = True,
        n_gpu_layers: int = -1,
        seed: int = 42,
        expected_sha256: str | None = None,
        quantization: str | None = None,
        model_id: str | None = None,
        grammar: str | None = None,
        reasoning_mode: ReasoningMode = ReasoningMode.DIRECT,
        strip_thinking: bool = False,
    ) -> None:
        if context_length <= 0:
            raise ConfigError(f"context_length pozitif olmalıdır: {context_length}")
        if vram_budget_mb <= 0:
            raise ConfigError(f"vram_budget_mb pozitif olmalıdır: {vram_budget_mb}")
        if kv_cache_type.strip().lower() not in _KV_CACHE_GGML_TYPES:
            raise ConfigError(f"Desteklenmeyen KV cache tipi: {kv_cache_type!r}")
        normalized_sha = _normalize_sha256(expected_sha256) if expected_sha256 is not None else None

        self._model_path = Path(model_path)
        self._context_length = context_length
        self._vram_budget_mb = vram_budget_mb
        self._kv_cache_type = kv_cache_type.strip().lower()
        self._flash_attn = flash_attn
        self._n_gpu_layers = n_gpu_layers
        self._seed = seed
        self._expected_sha256 = normalized_sha
        self._default_grammar = grammar
        self._reasoning_mode = reasoning_mode
        self._strip_thinking = strip_thinking

        self._llm: _LlamaInstance | None = None
        self._llama_mod: object | None = None
        self.last_reasoning: str | None = None

        self._info = ModelInfo(
            model_id=model_id if model_id is not None else str(model_path),
            quantization=quantization or _infer_quantization(model_path),
            context_length=context_length,
            sha256=normalized_sha,
        )

    @property
    def info(self) -> ModelInfo:
        return self._info

    @property
    def is_loaded(self) -> bool:
        return self._llm is not None

    @property
    def reasoning_mode(self) -> ReasoningMode:
        return self._reasoning_mode

    def _validate_model_file(self) -> Path:
        path = self._model_path
        if not path.is_file():
            raise ConfigError(f"Model dosyası bulunamadı: {path}")
        suffixes = [s.lower() for s in path.suffixes]
        for suffix in suffixes:
            if suffix in _FORBIDDEN_WEIGHT_SUFFIXES:
                raise ConfigError(
                    f"Güvenlik gereği pickle/ikili model dosyası reddedildi ({suffix}): {path.name}"
                )
        if not suffixes or suffixes[-1] != ".gguf":
            raise ConfigError(f"Yalnızca .gguf model dosyaları desteklenir: {path.name}")
        if self._expected_sha256 is not None:
            actual_sha = _compute_file_sha256(path)
            if actual_sha != self._expected_sha256:
                raise ConfigError(
                    f"Model SHA-256 doğrulaması başarısız ({path.name}): "
                    f"beklenen={self._expected_sha256}, bulunan={actual_sha}"
                )
        return path

    def load(self) -> None:
        """Validate the local GGUF file, verify VRAM budget, and load into memory."""
        self._ensure_loaded()

    def _ensure_loaded(self) -> _LlamaInstance:
        if self._llm is not None:
            return self._llm

        path = self._validate_model_file()
        estimated_mb = estimate_vram_mb(
            file_size_bytes=path.stat().st_size,
            context_length=self._context_length,
            kv_cache_type=self._kv_cache_type,
            n_gpu_layers=self._n_gpu_layers,
        )
        if estimated_mb > self._vram_budget_mb:
            raise ConfigError(
                f"Tahmini VRAM kullanımı ({estimated_mb} MB) belirlenen bütçeyi "
                f"({self._vram_budget_mb} MB) aşıyor: {path.name}"
            )

        vram_before = query_nvidia_smi_vram_mb() if self._n_gpu_layers != 0 else None
        if vram_before is not None:
            _, _, free_mb = vram_before
            if estimated_mb > free_mb:
                raise ExecutionError(f"Yetersiz boş GPU VRAM: gerekli≈{estimated_mb} MB, boş={free_mb} MB")

        llama_mod = _import_llama_cpp()
        llama_cls = getattr(llama_mod, "Llama", None)
        if llama_cls is None or not callable(llama_cls):
            raise ConfigError("llama_cpp.Llama sınıfı bulunamadı.")

        kv_type_id = _resolve_kv_cache_type(llama_mod, self._kv_cache_type)
        init_kwargs: dict[str, object] = {
            "model_path": str(path),
            "n_ctx": self._context_length,
            "n_gpu_layers": self._n_gpu_layers,
            "flash_attn": self._flash_attn,
            "seed": self._seed,
            "type_k": kv_type_id,
            "type_v": kv_type_id,
            "verbose": False,
        }
        filtered_kwargs = _filter_supported_kwargs(llama_cls, init_kwargs)
        try:
            instance = llama_cls(**filtered_kwargs)
        except Exception as exc:
            raise ExecutionError(f"Model yüklenirken hata oluştu ({path.name}): {exc}") from exc

        if self._n_gpu_layers != 0:
            vram_after = query_nvidia_smi_vram_mb()
            if vram_before is not None and vram_after is not None:
                delta_mb = max(0, vram_after[1] - vram_before[1])
                if delta_mb > self._vram_budget_mb:
                    self._close_instance(instance)
                    raise ExecutionError(
                        f"Yükleme sonrası GPU VRAM artışı ({delta_mb} MB) bütçeyi "
                        f"({self._vram_budget_mb} MB) aştı."
                    )

        self._llama_mod = llama_mod
        self._llm = cast(_LlamaInstance, instance)
        self._info = self._info.model_copy(update={"vram_mb_estimate": estimated_mb})
        return self._llm

    @staticmethod
    def _close_instance(instance: object) -> None:
        close_fn = getattr(instance, "close", None)
        if callable(close_fn):
            close_fn()

    def unload(self) -> None:
        """Release the loaded model instance from memory."""
        if self._llm is not None:
            self._close_instance(self._llm)
            self._llm = None
            self._llama_mod = None

    def _compile_grammar(self, grammar_text: str | None) -> object:
        if not grammar_text:
            return None
        if self._llama_mod is None:
            raise ExecutionError("Model henüz yüklenmediği için dilbilgisi derlenemedi.")
        factory = getattr(self._llama_mod, "LlamaGrammar", None)
        if factory is None:
            raise ConfigError("llama_cpp.LlamaGrammar bu kurulumda kullanılamıyor.")
        from_string = getattr(cast(_LlamaGrammarFactory, factory), "from_string", None)
        if not callable(from_string):
            raise ConfigError("llama_cpp.LlamaGrammar.from_string bulunamadı.")
        return from_string(grammar_text)

    def _invoke_model(
        self,
        prompt: PromptBundle,
        params: GenerationParams,
        *,
        grammar: str | None,
    ) -> str:
        llm = self._ensure_loaded()
        compiled_grammar = self._compile_grammar(grammar)
        stop_list = list(params.stop) if params.stop else None

        chat_fn = getattr(llm, "create_chat_completion", None)
        if callable(chat_fn):
            chat_kwargs: dict[str, object] = {
                "messages": [
                    {"role": "system", "content": prompt.system},
                    {"role": "user", "content": prompt.user},
                ],
                "max_tokens": params.max_tokens,
                "temperature": params.temperature,
                "seed": self._seed,
                "stop": stop_list,
            }
            if compiled_grammar is not None:
                chat_kwargs["grammar"] = compiled_grammar
            raw_resp = chat_fn(**_filter_supported_kwargs(chat_fn, chat_kwargs))
            extracted = _extract_completion_text(raw_resp)
            if extracted is not None:
                return extracted

        if callable(llm):
            combined_prompt = f"{prompt.system}\n\n{prompt.user}"
            call_kwargs: dict[str, object] = {
                "max_tokens": params.max_tokens,
                "temperature": params.temperature,
                "seed": self._seed,
                "stop": stop_list,
            }
            if compiled_grammar is not None:
                call_kwargs["grammar"] = compiled_grammar
            raw_resp = llm(combined_prompt, **_filter_supported_kwargs(llm, call_kwargs))
            extracted = _extract_completion_text(raw_resp)
            if extracted is not None:
                return extracted

        raise ExecutionError("Model beklenen metin çıktısını üretmedi.")

    def generate(
        self,
        prompt: PromptBundle,
        params: GenerationParams,
        *,
        grammar: str | None = None,
    ) -> str:
        """Generate a raw SQL (or ``<think>`` + SQL) completion for ``prompt``."""
        active_grammar = grammar if grammar is not None else self._default_grammar
        raw = self._invoke_model(prompt, params, grammar=active_grammar)
        reasoning, response = extract_thinking_and_response(raw)
        self.last_reasoning = reasoning
        if self._strip_thinking:
            return response
        return raw

    def generate_with_thinking(
        self,
        prompt: PromptBundle,
        params: GenerationParams,
        *,
        grammar: str | None = None,
    ) -> tuple[str | None, str]:
        """Generate output and explicitly return ``(reasoning, final_response)``."""
        active_grammar = grammar if grammar is not None else self._default_grammar
        raw = self._invoke_model(prompt, params, grammar=active_grammar)
        reasoning, response = extract_thinking_and_response(raw)
        self.last_reasoning = reasoning
        return reasoning, response
