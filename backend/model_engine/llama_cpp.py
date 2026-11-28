from __future__ import annotations

from backend.core.contracts import GenerationParams, ModelInfo, PromptBundle


class LlamaCppAdapter:
    """llama.cpp (GGUF) backend — placeholder until AR-05 picks the runtime.

    Implementation notes:
    - Load the model lazily from a local path (env ``TRSQL_MODEL_PATH``);
      never download at runtime (offline-first, ADR-0002).
    - Respect ``Settings.model.vram_budget_mb``; refuse to load if the
      estimated footprint (weights + KV cache) exceeds it.
    - Use greedy decoding (temperature 0) for evaluation runs.
    """

    def __init__(self, model_path: str, context_length: int = 4096) -> None:
        self._info = ModelInfo(model_id=model_path, quantization="gguf", context_length=context_length)

    @property
    def info(self) -> ModelInfo:
        return self._info

    def generate(self, prompt: PromptBundle, params: GenerationParams) -> str:
        raise NotImplementedError("LlamaCppAdapter is implemented in AR-05")
