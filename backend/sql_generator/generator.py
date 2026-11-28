from __future__ import annotations

import re
import time

from backend.core.contracts import Dialect, GenerationParams, PromptBundle, SQLCandidate
from backend.core.ports import ModelAdapter

_THINK_BLOCK = re.compile(r"<think>(.*?)</think>", re.DOTALL | re.IGNORECASE)
_THINK_OPEN = re.compile(r"<think>", re.IGNORECASE)
_THINK_CLOSE = re.compile(r"</think>", re.IGNORECASE)
_SQL_FENCE = re.compile(r"```sql\s*(.*?)```", re.DOTALL | re.IGNORECASE)
_ANY_FENCE = re.compile(r"```(?:\w+)?\s*(.*?)```", re.DOTALL)
_SELECT_OR_WITH = re.compile(r"\b(WITH|SELECT)\b", re.IGNORECASE)
_UNSAFE_LEAD = re.compile(
    r"^\s*(?:DROP|DELETE|INSERT|UPDATE|ALTER|CREATE|TRUNCATE|PRAGMA|ATTACH|DETACH|MERGE|GRANT|COPY)\b",
    re.IGNORECASE,
)


def _strip_thinking(text: str) -> tuple[str | None, str]:
    blocks = [m.group(1).strip() for m in _THINK_BLOCK.finditer(text) if m.group(1).strip()]
    if _THINK_BLOCK.search(text):
        remainder = _THINK_BLOCK.sub("", text).strip()
        return ("\n\n".join(blocks) if blocks else None), remainder

    close_match = _THINK_CLOSE.search(text)
    if close_match is not None:
        reasoning = _THINK_OPEN.sub("", text[: close_match.start()]).strip()
        return (reasoning or None), text[close_match.end() :].strip()

    open_match = _THINK_OPEN.search(text)
    if open_match is not None:
        before = text[: open_match.start()].strip()
        after = text[open_match.end() :].strip()
        return (after or None), before

    return None, text.strip()


def _trim_after_first_semicolon(sql_text: str) -> str:
    """Keep up to the first semicolon outside quoted strings if non-SQL prose follows."""
    in_single = False
    in_double = False
    i = 0
    length = len(sql_text)
    while i < length:
        ch = sql_text[i]
        if ch == "'" and not in_double:
            if in_single and i + 1 < length and sql_text[i + 1] == "'":
                i += 2
                continue
            in_single = not in_single
        elif ch == '"' and not in_single:
            if in_double and i + 1 < length and sql_text[i + 1] == '"':
                i += 2
                continue
            in_double = not in_double
        elif ch == ";" and not in_single and not in_double:
            trailing = sql_text[i + 1 :].strip()
            # If another SQL statement follows, preserve whole string so L6 detects stacked injection.
            if trailing and (_SELECT_OR_WITH.match(trailing) or _UNSAFE_LEAD.match(trailing)):
                return sql_text.strip()
            return sql_text[: i + 1].strip()
        i += 1
    return sql_text.strip()


def extract_sql_and_reasoning(text: str) -> tuple[str, str | None]:
    """Strip ``<think>...</think>`` reasoning and extract SQL from fenced or bare output."""
    reasoning, body = _strip_thinking(text)
    if not body:
        return "", reasoning

    sql_fence = _SQL_FENCE.search(body)
    if sql_fence is not None:
        return sql_fence.group(1).strip(), reasoning

    any_fence = _ANY_FENCE.search(body)
    if any_fence is not None:
        return any_fence.group(1).strip(), reasoning

    if _UNSAFE_LEAD.match(body):
        return body.strip(), reasoning

    stmt_match = _SELECT_OR_WITH.search(body)
    if stmt_match is not None:
        candidate = body[stmt_match.start() :]
        return _trim_after_first_semicolon(candidate), reasoning

    return body.strip(), reasoning


def extract_sql(text: str) -> str:
    """Strip ``<think>`` blocks and extract the SQL statement from model output."""
    sql, _ = extract_sql_and_reasoning(text)
    return sql


class SQLGenerator:
    """Calls a ``ModelAdapter`` and converts its text output into ``SQLCandidate`` objects."""

    def __init__(self, model: ModelAdapter, params: GenerationParams | None = None) -> None:
        self._model = model
        self._params = params or GenerationParams()

    def _generate_with_params(
        self,
        prompt: PromptBundle,
        dialect: Dialect,
        attempt: int,
        params: GenerationParams,
    ) -> SQLCandidate:
        started = time.perf_counter()
        raw = self._model.generate(prompt, params)
        elapsed = (time.perf_counter() - started) * 1000
        sql, reasoning = extract_sql_and_reasoning(raw)
        return SQLCandidate(
            sql=sql,
            dialect=dialect,
            model_id=self._model.info.model_id,
            attempt=attempt,
            latency_ms=elapsed,
            reasoning=reasoning,
        )

    def generate(self, prompt: PromptBundle, dialect: Dialect, attempt: int) -> SQLCandidate:
        return self._generate_with_params(prompt, dialect, attempt, self._params)

    def generate_candidates(
        self,
        prompt: PromptBundle,
        dialect: Dialect,
        attempt: int,
        n: int = 1,
    ) -> list[SQLCandidate]:
        """Generate ``n`` SQL candidates for D6 self-consistency voting.

        When ``n == 1``, uses ``self._params`` verbatim (typically deterministic
        ``temperature=0.0``). When ``n > 1``, candidate 0 keeps ``self._params``
        and subsequent candidates slightly vary ``temperature`` within ``[0.0, 2.0]``.
        """
        if n < 1:
            raise ValueError(f"n must be >= 1, got {n}")
        if n == 1:
            return [self.generate(prompt, dialect, attempt)]

        base_temp = self._params.temperature
        candidates: list[SQLCandidate] = []
        for idx in range(n):
            if idx == 0:
                params = self._params
            elif base_temp >= 1.9:
                temp = round(max(0.0, base_temp - 0.05 * idx), 4)
                params = self._params.model_copy(update={"temperature": temp})
            else:
                anchor = base_temp if base_temp > 0.0 else 0.15
                temp = round(min(2.0, anchor + 0.05 * idx), 4)
                params = self._params.model_copy(update={"temperature": temp})
            candidates.append(self._generate_with_params(prompt, dialect, attempt, params))
        return candidates
