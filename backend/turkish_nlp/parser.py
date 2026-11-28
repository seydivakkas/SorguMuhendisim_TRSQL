from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from datetime import date

from backend.core.contracts import (
    Intent,
    Mention,
    MentionKind,
    ParsedQuestion,
    SortDirection,
)
from backend.turkish_nlp.normalize import normalize_question, strip_suffix
from backend.turkish_nlp.temporal import resolve_temporal

_NUMBER_WORDS: dict[str, int] = {
    "bir": 1, "iki": 2, "üç": 3, "dört": 4, "beş": 5, "altı": 6, "yedi": 7,
    "sekiz": 8, "dokuz": 9, "on": 10, "yirmi": 20, "elli": 50, "yüz": 100,
}  # fmt: skip

_DESC_MARKERS = ("en çok", "en fazla", "en yüksek", "en büyük", "en iyi")
_ASC_MARKERS = ("en az", "en düşük", "en küçük", "en kötü")
_COUNT_MARKERS = ("kaç", "kaç tane", "sayısı")
_TREND_MARKERS = ("trend", "değişim", "aylık", "yıllık", "zamanla")
_AGG_MARKERS = ("toplam", "ortalama", "ortalaması", "toplamı")
_COMPARE_MARKERS = ("karşılaştır", "kıyasla", "göre fark")
_VAGUE_MARKERS = ("iyi", "kötü", "önemli", "büyük müşteri")


class RuleBasedTurkishParser:
    """Deterministic baseline parser.

    ``lexicon`` maps Turkish lemmas to a :class:`MentionKind` (e.g. ``"bayi"``
    → ENTITY, ``"satış"`` → METRIC). Known locations are passed separately.
    """

    def __init__(
        self,
        lexicon: Mapping[str, MentionKind] | None = None,
        locations: frozenset[str] = frozenset(),
        today: Callable[[], date] = date.today,
    ) -> None:
        self._lexicon = dict(lexicon or {})
        self._locations = frozenset(normalize_question(x) for x in locations)
        self._today = today

    def parse(self, question: str) -> ParsedQuestion:
        text = normalize_question(question)
        tokens = [strip_suffix(t) for t in text.split()]

        sort = self._sort(text)
        limit = self._limit(tokens, sort)
        temporal = resolve_temporal(text, self._today())
        mentions = self._mentions(tokens)
        intent = self._intent(text, sort)

        ambiguities: list[str] = []
        if any(m in text for m in _VAGUE_MARKERS) and sort is None:
            ambiguities.append("Belirsiz nitelik: hangi ölçüte göre değerlendirilsin?")
        if intent is Intent.RANKING and not any(m.kind is MentionKind.METRIC for m in mentions):
            ambiguities.append("Sıralama için ölçüt (ör. satış tutarı) belirtilmedi.")

        return ParsedQuestion(
            original_text=question,
            normalized_text=text,
            intent=intent,
            mentions=tuple(mentions),
            temporal=tuple(temporal),
            sort=sort,
            limit=limit,
            ambiguities=tuple(ambiguities),
        )

    @staticmethod
    def _sort(text: str) -> SortDirection | None:
        if any(m in text for m in _DESC_MARKERS):
            return SortDirection.DESC
        if any(m in text for m in _ASC_MARKERS):
            return SortDirection.ASC
        return None

    @staticmethod
    def _limit(tokens: list[str], sort: SortDirection | None) -> int | None:
        for tok in tokens:
            if tok.isdigit() and 0 < int(tok) <= 10_000:
                return int(tok)
        if sort is not None:
            for tok in tokens:
                if tok in _NUMBER_WORDS and tok != "bir":
                    return _NUMBER_WORDS[tok]
        return None

    @staticmethod
    def _intent(text: str, sort: SortDirection | None) -> Intent:
        if sort is not None:
            return Intent.RANKING
        if any(re.search(rf"\b{m}\b", text) for m in _COUNT_MARKERS):
            return Intent.COUNT
        if any(m in text for m in _TREND_MARKERS):
            return Intent.TREND
        if any(m in text for m in _COMPARE_MARKERS):
            return Intent.COMPARISON
        if any(m in text for m in _AGG_MARKERS):
            return Intent.AGGREGATE
        return Intent.LOOKUP

    def _mentions(self, tokens: list[str]) -> list[Mention]:
        found: list[Mention] = []
        for tok in tokens:
            if tok in self._locations:
                found.append(Mention(text=tok, kind=MentionKind.LOCATION, lemma=tok))
                continue
            lemma = self._lemma(tok)
            if lemma is not None:
                found.append(Mention(text=tok, kind=self._lexicon[lemma], lemma=lemma))
        return found

    def _lemma(self, token: str) -> str | None:
        """Longest lexicon entry that prefixes the token (``bayimiz`` → ``bayi``).

        Crude stand-in for morphological analysis; replaced in AR-03.
        """
        best: str | None = None
        for lemma in self._lexicon:
            if token.startswith(lemma) and (best is None or len(lemma) > len(best)):
                best = lemma
        return best
