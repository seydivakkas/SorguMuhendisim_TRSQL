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
from backend.turkish_nlp.ambiguity import AmbiguityDetector
from backend.turkish_nlp.morphology import TurkishMorphologyAnalyzer
from backend.turkish_nlp.normalize import normalize_question, strip_suffix, synonym_candidates
from backend.turkish_nlp.temporal import resolve_temporal

_NUMBER_WORDS: dict[str, int] = {
    "bir": 1, "iki": 2, "üç": 3, "dört": 4, "beş": 5, "altı": 6, "yedi": 7,
    "sekiz": 8, "dokuz": 9, "on": 10, "yirmi": 20, "elli": 50, "yüz": 100,
}  # fmt: skip

_DESC_MARKERS = ("en çok", "en fazla", "en yüksek", "en büyük", "en iyi")
_ASC_MARKERS = ("en az", "en düşük", "en küçük", "en kötü")
_COUNT_MARKERS = ("kaç", "kaç tane", "sayısı")
_TREND_MARKERS = ("trend", "değişim", "aylık", "yıllık", "zamanla", "gidişat", "seyir")
_AGG_MARKERS = ("toplam", "ortalama", "ortalaması", "toplamı")
_COMPARE_MARKERS = ("karşılaştır", "kıyasla", "göre fark")


class RuleBasedTurkishParser:
    """Deterministic Turkish question parser with morphology, temporal, and ambiguity analysis.

    ``lexicon`` maps Turkish lemmas to a :class:`MentionKind` (e.g. ``"bayi"``
    -> ENTITY, ``"satış"`` -> METRIC). Known locations are passed separately.
    """

    def __init__(
        self,
        lexicon: Mapping[str, MentionKind] | None = None,
        locations: frozenset[str] = frozenset(),
        today: Callable[[], date] = date.today,
        *,
        use_zemberek: bool = False,
        ambiguity_detector: AmbiguityDetector | None = None,
    ) -> None:
        self._lexicon = {normalize_question(k): v for k, v in (lexicon or {}).items()}
        self._locations = frozenset(normalize_question(x) for x in locations)
        self._today = today
        known_stems = set(self._lexicon.keys()) | set(self._locations)
        self._morphology = TurkishMorphologyAnalyzer(known_stems, use_zemberek=use_zemberek)
        self._ambiguity = ambiguity_detector or AmbiguityDetector()

    def parse(self, question: str) -> ParsedQuestion:
        text = normalize_question(question)
        raw_tokens = text.split()
        tokens = [strip_suffix(t) for t in raw_tokens]

        sort = self._sort(text)
        temporal = resolve_temporal(text, self._today())
        non_temporal_text = text
        for expr in temporal:
            non_temporal_text = non_temporal_text.replace(expr.text, " ", 1)
        limit = self._limit(
            [strip_suffix(t) for t in non_temporal_text.split()],
            sort,
        )
        mentions = self._mentions(raw_tokens, tokens)
        intent = self._intent(text, sort)

        ambiguities = self._ambiguity.detect(
            normalized_text=text,
            intent=intent,
            mentions=tuple(mentions),
            temporal=tuple(temporal),
            sort=sort,
        )

        return ParsedQuestion(
            original_text=question,
            normalized_text=text,
            intent=intent,
            mentions=tuple(mentions),
            temporal=tuple(temporal),
            sort=sort,
            limit=limit,
            ambiguities=ambiguities,
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

    def _mentions(self, raw_tokens: list[str], stripped_tokens: list[str]) -> list[Mention]:
        found: list[Mention] = []
        # Check bigram phrases first for multi-word synonyms (e.g. "satış tutarı")
        skip_indices: set[int] = set()
        for idx in range(len(stripped_tokens) - 1):
            bigram = f"{stripped_tokens[idx]} {stripped_tokens[idx + 1]}"
            if bigram in self._lexicon:
                found.append(Mention(text=bigram, kind=self._lexicon[bigram], lemma=bigram))
                skip_indices.update({idx, idx + 1})

        for idx, (raw_tok, tok) in enumerate(zip(raw_tokens, stripped_tokens, strict=True)):
            if idx in skip_indices:
                continue
            morph_lemma = self._morphology.lemmatize(raw_tok)
            if tok in self._locations:
                found.append(Mention(text=tok, kind=MentionKind.LOCATION, lemma=tok))
                continue
            if morph_lemma in self._locations:
                found.append(Mention(text=tok, kind=MentionKind.LOCATION, lemma=morph_lemma))
                continue
            lemma = self._lemma(tok, morph_lemma)
            if lemma is not None:
                found.append(Mention(text=tok, kind=self._lexicon[lemma], lemma=lemma))
        return found

    def _lemma(self, token: str, morph_lemma: str) -> str | None:
        """Resolve token or its morphological lemma (and synonyms) against ``_lexicon``."""
        for candidate in (morph_lemma, token):
            if candidate in self._lexicon:
                return candidate
        for candidate in (morph_lemma, token):
            for syn in synonym_candidates(candidate):
                if syn in self._lexicon:
                    return syn
        # Fallback longest prefix match for unmodeled agglutinated forms
        best: str | None = None
        for lemma in self._lexicon:
            if (token.startswith(lemma) or morph_lemma.startswith(lemma)) and (
                best is None or len(lemma) > len(best)
            ):
                best = lemma
        return best
