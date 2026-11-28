"""EllieSQL / PRISM inspired adaptive reasoning-mode router (AR-05)."""

from __future__ import annotations

from backend.core.config import RoutingSettings
from backend.core.contracts import (
    Intent,
    LinkedSchema,
    ParsedQuestion,
    ReasoningMode,
    RoutingDecision,
)


class ComplexityRouter:
    """Computes a :class:`RoutingDecision` (``DIRECT`` vs ``THINKING``) from
    question linguistics, linked schema complexity, and prior ``REPAIRABLE`` failures.

    Simple queries remain on ``ReasoningMode.DIRECT`` with a single candidate to
    preserve low latency; queries whose complexity exceeds the configured
    threshold or that experienced a ``REPAIRABLE`` validation failure escalate
    to ``ReasoningMode.THINKING`` and multi-candidate consistency voting.
    """

    def __init__(self, settings: RoutingSettings | None = None) -> None:
        self._settings = settings or RoutingSettings()

    @property
    def settings(self) -> RoutingSettings:
        return self._settings

    def route(
        self,
        question: ParsedQuestion,
        linked: LinkedSchema,
        *,
        prior_failures: int = 0,
    ) -> RoutingDecision:
        """Compute complexity score, reasoning mode, and candidate count."""
        score = 0.0
        reasons: list[str] = []

        if question.intent in (Intent.COMPARISON, Intent.TREND):
            score += 0.30
            reasons.append(f"karmaşık niyet: {question.intent.value}")
        elif question.intent in (Intent.RANKING, Intent.AGGREGATE):
            score += 0.15
            reasons.append(f"analitik niyet: {question.intent.value}")

        temporal_count = len(question.temporal)
        if temporal_count >= 2:
            score += 0.20
            reasons.append(f"çoklu zaman ifadesi ({temporal_count})")
        elif temporal_count == 1:
            score += 0.10
            reasons.append("zaman filtresi")

        if question.ambiguities:
            score += 0.20
            reasons.append(f"belirsizlik sinyali ({len(question.ambiguities)})")

        table_count = len(linked.tables)
        if table_count >= 4:
            score += 0.30
            reasons.append(f"yüksek tablo sayısı ({table_count})")
        elif table_count == 3:
            score += 0.20
            reasons.append("çoklu tablo (3)")
        elif table_count == 2:
            score += 0.10
            reasons.append("iki tablo")

        join_depth = len(linked.join_path)
        if join_depth >= 3:
            score += 0.25
            reasons.append(f"derin join yolu ({join_depth})")
        elif join_depth == 2:
            score += 0.15
            reasons.append("çok adımlı join (2)")
        elif join_depth == 1:
            score += 0.05
            reasons.append("tekil join")

        if prior_failures > 0:
            penalty = min(0.50, 0.35 * prior_failures)
            score += penalty
            reasons.append(f"önceki düzeltilebilir hata ({prior_failures})")

        complexity = round(min(1.0, max(0.0, score)), 4)

        if not self._settings.enabled:
            return RoutingDecision(
                mode=ReasoningMode.DIRECT,
                num_candidates=1,
                complexity_score=complexity,
                reasons=tuple(reasons) or ("yönlendirici devre dışı",),
            )

        escalate_thinking = prior_failures > 0 or complexity >= self._settings.thinking_threshold
        escalate_voting = prior_failures > 0 or complexity >= self._settings.vote_threshold

        if escalate_thinking:
            num_candidates = self._settings.vote_candidates if escalate_voting else 1
            return RoutingDecision(
                mode=ReasoningMode.THINKING,
                num_candidates=num_candidates,
                complexity_score=complexity,
                reasons=tuple(reasons),
            )

        return RoutingDecision(
            mode=ReasoningMode.DIRECT,
            num_candidates=1,
            complexity_score=complexity,
            reasons=tuple(reasons) or ("düşük karmaşıklık",),
        )
