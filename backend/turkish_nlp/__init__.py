"""L2 — Turkish NLP Intelligence.

Turns a Turkish question into a :class:`ParsedQuestion` (intent, mentions,
temporal expressions, sort, limit, ambiguities) so that the small model
does not have to solve the linguistic problems alone.

Includes Turkish casefolding, ASCII-to-Turkish normalization, synonym mapping,
rule-based agglutinative morphology (with optional lazy ``zemberek-python``
hook), temporal resolution, and ambiguity detection (AR-03).
"""

from backend.turkish_nlp.ambiguity import AmbiguityDetector
from backend.turkish_nlp.morphology import (
    TurkishMorphologyAnalyzer,
    is_zemberek_available,
    lemmatize_text,
    lemmatize_token,
    strip_turkish_suffixes,
)
from backend.turkish_nlp.normalize import (
    ASCII_TURKISH_MAP,
    SYNONYM_GROUPS,
    SYNONYM_MAP,
    normalize_ascii_turkish,
    normalize_question,
    resolve_synonym,
    strip_suffix,
    synonym_candidates,
    tr_casefold,
)
from backend.turkish_nlp.parser import RuleBasedTurkishParser
from backend.turkish_nlp.temporal import resolve_temporal

__all__ = [
    "ASCII_TURKISH_MAP",
    "SYNONYM_GROUPS",
    "SYNONYM_MAP",
    "AmbiguityDetector",
    "RuleBasedTurkishParser",
    "TurkishMorphologyAnalyzer",
    "is_zemberek_available",
    "lemmatize_text",
    "lemmatize_token",
    "normalize_ascii_turkish",
    "normalize_question",
    "resolve_synonym",
    "resolve_temporal",
    "strip_suffix",
    "strip_turkish_suffixes",
    "synonym_candidates",
    "tr_casefold",
]
