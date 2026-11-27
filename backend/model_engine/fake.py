from __future__ import annotations

from collections.abc import Sequence

from backend.core.contracts import GenerationParams, ModelInfo, PromptBundle


class FakeModelAdapter:
    """Deterministic adapter for tests: returns scripted responses in order.

    The last response repeats once the script is exhausted. ``prompts``
    records every prompt received so tests can assert on feedback.
    """

    def __init__(self, responses: Sequence[str], model_id: str = "fake-model") -> None:
        if not responses:
            raise ValueError("at least one scripted response is required")
        self._responses = list(responses)
        self._info = ModelInfo(model_id=model_id, context_length=4096)
        self.prompts: list[PromptBundle] = []

    @property
    def info(self) -> ModelInfo:
        return self._info

    def generate(self, prompt: PromptBundle, params: GenerationParams) -> str:
        idx = min(len(self.prompts), len(self._responses) - 1)
        self.prompts.append(prompt)
        return self._responses[idx]
