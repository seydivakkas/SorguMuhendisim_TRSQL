from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from backend.core.contracts import (
    ApprovedQuery,
    ChartSpec,
    ExecutionResult,
    Intent,
    ParsedQuestion,
    QueryPlan,
    ResultReport,
)


def format_tr_number(value: int | float | Decimal, decimals: int = 2) -> str:
    """Turkish number format: ``1250000.5`` → ``1.250.000,50``; ints keep no decimals."""
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return f"{value:,}".replace(",", ".")
    q = Decimal(str(value)).quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP)
    whole, _, frac = f"{q:,.{decimals}f}".partition(".")
    return whole.replace(",", ".") + ("," + frac if frac else "")


def _is_number(v: Any) -> bool:
    return isinstance(v, (int, float, Decimal)) and not isinstance(v, bool)


class ResultBuilder:
    def build(
        self, question: ParsedQuestion, plan: QueryPlan, query: ApprovedQuery, result: ExecutionResult
    ) -> ResultReport:
        return ResultReport(
            title=question.original_text.strip(),
            summary=self._summary(plan, result),
            columns=result.columns,
            rows=result.rows,
            chart=self._chart(plan, result),
            sql=query.sql,
            metrics_used=tuple(f"{m.metric_id}@v{m.version}" for m in plan.metrics),
            truncated=result.truncated,
        )

    @staticmethod
    def _chart(plan: QueryPlan, result: ExecutionResult) -> ChartSpec:
        if len(result.columns) != 2 or not result.rows:
            return ChartSpec(kind="table")
        x, y = result.columns
        if not all(_is_number(r[1]) for r in result.rows):
            return ChartSpec(kind="table")
        kind = "line" if plan.intent is Intent.TREND else "bar"
        return ChartSpec(kind=kind, x=x, y=y)

    @staticmethod
    def _summary(plan: QueryPlan, result: ExecutionResult) -> str:
        if not result.rows:
            return "Sorgu sonuç döndürmedi."
        parts = [f"Sorgu {format_tr_number(result.row_count)} satır döndürdü."]
        first = result.rows[0]
        if plan.intent is Intent.RANKING and len(first) >= 2 and _is_number(first[-1]):
            parts.append(f"{first[0]}, {format_tr_number(first[-1])} değeriyle ilk sırada yer almaktadır.")
        if result.truncated:
            parts.append("Sonuçlar satır sınırı nedeniyle kısaltıldı.")
        return " ".join(parts)
