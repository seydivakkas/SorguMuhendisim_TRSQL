from __future__ import annotations

import re
import time

from backend.core.contracts import Dialect, GenerationParams, PromptBundle, SQLCandidate
from backend.core.ports import ModelAdapter

_FENCE = re.compile(r"```(?:sql)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def extract_sql(text: str) -> str:
    """Take the first fenced block if present, otherwise the whole text."""
    match = _FENCE.search(text)
    sql = match.group(1) if match else text
    return sql.strip()


class SQLGenerator:
    def __init__(self, model: ModelAdapter, params: GenerationParams | None = None) -> None:
        self._model = model
        self._params = params or GenerationParams()

    def generate(self, prompt: PromptBundle, dialect: Dialect, attempt: int) -> SQLCandidate:
        started = time.perf_counter()
        raw = self._model.generate(prompt, self._params)
        elapsed = (time.perf_counter() - started) * 1000
        return SQLCandidate(
            sql=extract_sql(raw),
            dialect=dialect,
            model_id=self._model.info.model_id,
            attempt=attempt,
            latency_ms=elapsed,
        )
