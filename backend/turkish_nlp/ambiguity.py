from __future__ import annotations

import re
from collections.abc import Collection

from backend.core.contracts import (
    Intent,
    Mention,
    MentionKind,
    SchemaSnapshot,
    SortDirection,
    TemporalExpression,
)
from backend.turkish_nlp.morphology import lemmatize_text
from backend.turkish_nlp.normalize import normalize_question

_VAGUE_WORD_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(rf"\b{re.escape(term)}\b")
    for term in (
        "iyi",
        "kötü",
        "önemli",
        "büyük müşteri",
        "başarılı",
        "verimli",
        "popüler",
        "kaliteli",
        "kârlı",
        "riskli",
    )
)

_COMPARISON_HINTS: tuple[str, ...] = (
    "karşılaştır",
    "kıyasla",
    "göre",
    "fark",
    "ile",
)


def _has_disjoint_dates(temporal: tuple[TemporalExpression, ...]) -> bool:
    concrete = [t for t in temporal if t.start is not None and t.end is not None]
    if len(concrete) < 2:
        return False
    for idx, first in enumerate(concrete):
        if first.start is None or first.end is None:
            continue
        for second in concrete[idx + 1 :]:
            if second.start is None or second.end is None:
                continue
            if first.end <= second.start or second.end <= first.start:
                return True
    return False


class AmbiguityDetector:
    """Rule-based detector for ambiguous or underspecified Turkish questions.

    Produces human-readable Turkish clarification prompts when SQL generation
    should be paused for ``OutcomeStatus.NEEDS_CLARIFICATION``.
    """

    def detect(
        self,
        *,
        normalized_text: str,
        intent: Intent,
        mentions: tuple[Mention, ...],
        temporal: tuple[TemporalExpression, ...],
        sort: SortDirection | None,
    ) -> tuple[str, ...]:
        """Detect ambiguity signals in a parsed Turkish question."""
        issues: list[str] = []

        if not normalized_text or not any(ch.isalnum() for ch in normalized_text):
            issues.append("Soru anlaşılamadı; lütfen sorgulamak istediğiniz bilgiyi belirtin.")
            return tuple(issues)

        has_metric = any(m.kind is MentionKind.METRIC for m in mentions)

        if (
            any(pat.search(normalized_text) for pat in _VAGUE_WORD_PATTERNS)
            and sort is None
            and not has_metric
        ):
            issues.append("Belirsiz nitelik: hangi ölçüte göre değerlendirilsin?")

        if intent is Intent.RANKING and not has_metric:
            issues.append("Sıralama için ölçüt (ör. satış tutarı) belirtilmedi.")

        if intent in (Intent.TREND, Intent.COMPARISON) and not temporal:
            if intent is Intent.TREND:
                issues.append("Trend analizi için zaman aralığı belirtilmedi (ör. son 6 ay, bu yıl).")
            else:
                issues.append("Karşılaştırma için zaman aralığı belirtilmedi (ör. geçen ay ile bu ay).")

        if (
            intent is not Intent.COMPARISON
            and _has_disjoint_dates(temporal)
            and not any(re.search(rf"\b{h}\b", normalized_text) for h in _COMPARISON_HINTS[:-1])
        ):
            issues.append(
                "Çelişkili tarih filtreleri bulundu; lütfen tek bir geçerli zaman aralığı belirtin."
            )

        return tuple(issues)

    def detect_unanswerable(
        self,
        question: str,
        schema: SchemaSnapshot,
        extra_terms: Collection[str] = (),
    ) -> str | None:
        """Return a Turkish reason if a question has zero overlap with the scoped schema."""
        tokens = set(lemmatize_text(normalize_question(question)))
        if not tokens:
            return "Soru boş veya anlamsız; veritabanında sorgulanacak kavram bulunamadı."
        schema_vocab: set[str] = {normalize_question(t) for t in extra_terms}
        for table in schema.tables:
            schema_vocab.update(normalize_question(table.name).replace("_", " ").split())
            if table.description:
                schema_vocab.update(lemmatize_text(table.description))
            for col in table.columns:
                schema_vocab.update(normalize_question(col.name).replace("_", " ").split())
                if col.description:
                    schema_vocab.update(lemmatize_text(col.description))
        if tokens & schema_vocab:
            return None
        return "Sorudaki kavramlar erişilebilir veritabanı şemasında bulunamadı."
