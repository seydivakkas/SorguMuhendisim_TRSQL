from datetime import date

from backend.core.contracts import Intent, MentionKind, SortDirection
from backend.turkish_nlp import RuleBasedTurkishParser, tr_casefold


def test_turkish_casefold() -> None:
    assert tr_casefold("İSTANBUL") == "istanbul"
    assert tr_casefold("IĞDIR") == "ığdır"
    assert tr_casefold("ŞİŞLİ") == "şişli"


def test_reference_question(parser: RuleBasedTurkishParser) -> None:
    p = parser.parse("Geçen ay Trabzon'daki en çok satış yapan beş bayimiz hangileri?")
    assert p.intent is Intent.RANKING
    assert p.sort is SortDirection.DESC
    assert p.limit == 5
    kinds = {(m.lemma, m.kind) for m in p.mentions}
    assert ("trabzon", MentionKind.LOCATION) in kinds
    assert ("bayi", MentionKind.ENTITY) in kinds
    assert ("satış", MentionKind.METRIC) in kinds
    (t,) = p.temporal
    assert (t.text, t.start, t.end) == ("geçen ay", date(2026, 10, 1), date(2026, 11, 1))
    assert not p.is_ambiguous


def test_vague_question_is_ambiguous(parser: RuleBasedTurkishParser) -> None:
    assert parser.parse("İyi bayiler hangileri?").is_ambiguous


def test_ranking_without_metric_is_ambiguous(parser: RuleBasedTurkishParser) -> None:
    assert parser.parse("En çok olan 3 bayi").is_ambiguous


def test_count_intent(parser: RuleBasedTurkishParser) -> None:
    assert parser.parse("Rize'de kaç bayi var?").intent is Intent.COUNT


def test_january_rollover() -> None:
    p = RuleBasedTurkishParser(today=lambda: date(2027, 1, 15)).parse("geçen ay satış")
    assert (p.temporal[0].start, p.temporal[0].end) == (date(2026, 12, 1), date(2027, 1, 1))
