from __future__ import annotations

from datetime import date

import pytest

from backend.core.contracts import (
    ColumnInfo,
    Dialect,
    Intent,
    MentionKind,
    SchemaSnapshot,
    SortDirection,
    TableInfo,
)
from backend.turkish_nlp import (
    AmbiguityDetector,
    RuleBasedTurkishParser,
    TurkishMorphologyAnalyzer,
    is_zemberek_available,
    lemmatize_token,
    normalize_ascii_turkish,
    normalize_question,
    resolve_synonym,
    resolve_temporal,
    tr_casefold,
)

REF_TODAY = date(2026, 11, 27)


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


@pytest.mark.parametrize(
    ("phrase", "expected_start", "expected_end"),
    [
        ("bugün satışlar", date(2026, 11, 27), date(2026, 11, 28)),
        ("dün satışlar", date(2026, 11, 26), date(2026, 11, 27)),
        ("evvelsi gün satışlar", date(2026, 11, 25), date(2026, 11, 26)),
        ("yarın teslimatlar", date(2026, 11, 28), date(2026, 11, 29)),
        ("bu hafta satışlar", date(2026, 11, 23), date(2026, 11, 30)),
        ("geçen hafta satışlar", date(2026, 11, 16), date(2026, 11, 23)),
        ("gelecek hafta teslimat", date(2026, 11, 30), date(2026, 12, 7)),
        ("önümüzdeki hafta siparişler", date(2026, 11, 30), date(2026, 12, 7)),
        ("bu ay satışlar", date(2026, 11, 1), date(2026, 12, 1)),
        ("geçen ay satışlar", date(2026, 10, 1), date(2026, 11, 1)),
        ("gelecek ay hedefler", date(2026, 12, 1), date(2027, 1, 1)),
        ("önümüzdeki ay planı", date(2026, 12, 1), date(2027, 1, 1)),
        ("bu yıl ciro", date(2026, 1, 1), date(2027, 1, 1)),
        ("geçen yıl ciro", date(2025, 1, 1), date(2026, 1, 1)),
        ("önümüzdeki yıl hedefler", date(2027, 1, 1), date(2028, 1, 1)),
        ("geçen yılın aynı dönemi", date(2025, 11, 1), date(2025, 12, 1)),
        ("son 7 gün ciro", date(2026, 11, 20), date(2026, 11, 28)),
        ("son 30 gün satış", date(2026, 10, 28), date(2026, 11, 28)),
        ("son 90 gün iadeler", date(2026, 8, 29), date(2026, 11, 28)),
        ("son yedi gün satışlar", date(2026, 11, 20), date(2026, 11, 28)),
        ("son 2 hafta siparişler", date(2026, 11, 13), date(2026, 11, 28)),
        ("son 3 ay satışlar", date(2026, 8, 27), date(2026, 11, 28)),
        ("son 1 yıl ciro", date(2025, 11, 27), date(2026, 11, 28)),
        ("bu çeyrek satışlar", date(2026, 10, 1), date(2027, 1, 1)),
        ("geçen çeyrek satışlar", date(2026, 7, 1), date(2026, 10, 1)),
        ("önümüzdeki çeyrek hedef", date(2027, 1, 1), date(2027, 4, 1)),
        ("1. çeyrek satışları", date(2026, 1, 1), date(2026, 4, 1)),
        ("2. çeyrek satışları", date(2026, 4, 1), date(2026, 7, 1)),
        ("3. çeyrek satışları", date(2026, 7, 1), date(2026, 10, 1)),
        ("4. çeyrek satışları", date(2026, 10, 1), date(2027, 1, 1)),
        ("2025 yılı 2. çeyrek", date(2025, 4, 1), date(2025, 7, 1)),
        ("yılbaşından bugüne satışlar", date(2026, 1, 1), date(2026, 11, 28)),
        ("aybaşından bugüne satışlar", date(2026, 11, 1), date(2026, 11, 28)),
        ("1. yarıyıl ciro", date(2026, 1, 1), date(2026, 7, 1)),
        ("ocak 2025 satışları", date(2025, 1, 1), date(2025, 2, 1)),
        ("şubatta ödemeler", date(2026, 2, 1), date(2026, 3, 1)),
        ("mart ayı siparişleri", date(2026, 3, 1), date(2026, 4, 1)),
        ("nisan satışları", date(2026, 4, 1), date(2026, 5, 1)),
        ("mayıs'ta ciro", date(2026, 5, 1), date(2026, 6, 1)),
        ("haziran faturaları", date(2026, 6, 1), date(2026, 7, 1)),
        ("temmuz iadeleri", date(2026, 7, 1), date(2026, 8, 1)),
        ("ağustos'ta sevkiyat", date(2026, 8, 1), date(2026, 9, 1)),
        ("eylül 2025 satış", date(2025, 9, 1), date(2025, 10, 1)),
        ("ekim'de satış", date(2026, 10, 1), date(2026, 11, 1)),
        ("kasım satışları", date(2026, 11, 1), date(2026, 12, 1)),
        ("aralıkta satışlar", date(2026, 12, 1), date(2027, 1, 1)),
        ("2024 yılında satışlar", date(2024, 1, 1), date(2025, 1, 1)),
        ("2026-05-10 tarihli satış", date(2026, 5, 10), date(2026, 5, 11)),
        ("01.03.2026 - 15.03.2026 arası", date(2026, 3, 1), date(2026, 3, 16)),
    ],
)
def test_temporal_expressions(phrase: str, expected_start: date, expected_end: date) -> None:
    exprs = resolve_temporal(phrase, REF_TODAY)
    assert len(exprs) == 1
    assert exprs[0].start == expected_start
    assert exprs[0].end == expected_end


def test_same_period_last_year_paired_with_quarter() -> None:
    exprs = resolve_temporal("Bu çeyrek ile geçen yılın aynı dönemini karşılaştır", REF_TODAY)
    assert len(exprs) == 2
    assert (exprs[0].start, exprs[0].end) == (date(2026, 10, 1), date(2027, 1, 1))
    assert (exprs[1].start, exprs[1].end) == (date(2025, 10, 1), date(2026, 1, 1))


def test_zaman_araligi_is_not_december() -> None:
    assert resolve_temporal("zaman aralığı belirtilmedi", REF_TODAY) == []


def test_ascii_to_turkish_normalization() -> None:
    assert normalize_ascii_turkish("musteri satis sube sehir odeme") == "müşteri satış şube şehir ödeme"
    assert normalize_ascii_turkish("urun hasilat magaza calisan") == "ürün hasılat mağaza çalışan"
    assert normalize_ascii_turkish("gecen ay musteri satislari") == "geçen ay müşteri satışları"
    assert normalize_ascii_turkish("cust_id v1") == "cust_id v1"
    assert normalize_question("Gecen ay subedeki satis hasilati nedir?") == (
        "geçen ay şubedeki satış hasılatı nedir"
    )


def test_synonym_mapping_and_parser_integration(parser: RuleBasedTurkishParser) -> None:
    assert resolve_synonym("ciro") == "ciro"
    assert resolve_synonym("hasılat") == "ciro"
    assert resolve_synonym("satış tutarı") == "ciro"
    assert resolve_synonym("hasilat") == "ciro"

    p = parser.parse("Gecen ay en yuksek hasilat yapan 3 bayi hangileri?")
    assert p.intent is Intent.RANKING
    assert p.limit == 3
    assert any(m.kind is MentionKind.METRIC for m in p.mentions)
    assert not p.is_ambiguous


@pytest.mark.parametrize(
    ("word", "expected"),
    [
        ("müşterilerimizin", "müşteri"),
        ("siparişlerinden", "sipariş"),
        ("istanbul'daki", "istanbul"),
        ("bayimiz", "bayi"),
        ("bayilerimizdeki", "bayi"),
        ("şubelerimizden", "şube"),
        ("ödemelerini", "ödeme"),
        ("çalışanların", "çalışan"),
        ("ürünlerimiz", "ürün"),
        ("satışlarımız", "satış"),
        ("mağazalarımızda", "mağaza"),
        ("şehri", "şehir"),
        ("borcu", "borç"),
        ("dolar", "dolar"),
    ],
)
def test_turkish_morphology_lemmatizer(word: str, expected: str) -> None:
    assert lemmatize_token(word) == expected


def test_optional_zemberek_hook_and_fallback() -> None:
    assert isinstance(is_zemberek_available(), bool)
    analyzer = TurkishMorphologyAnalyzer(use_zemberek=True)
    # Works purely in Python even when zemberek-python / JVM is absent
    assert analyzer.lemmatize("müşterilerimizin") == "müşteri"

    class _FakeZemberekItem:
        root = "sipariş"

    class _FakeAnalysisEntry:
        item = _FakeZemberekItem()

    class _FakeAnalysisResult:
        def __init__(self) -> None:
            self.analysis_results = [_FakeAnalysisEntry()]

    class _FakeZemberek:
        def analyze(self, word: str) -> object:
            return _FakeAnalysisResult()

    hooked = TurkishMorphologyAnalyzer(use_zemberek=True, zemberek_analyzer=_FakeZemberek())
    assert hooked.using_zemberek
    assert hooked.lemmatize("siparişlerinden") == "sipariş"


def test_ambiguity_detection_cases(parser: RuleBasedTurkishParser) -> None:
    # Vague adjectives
    assert parser.parse("Önemli bayiler kimler?").is_ambiguous
    assert parser.parse("Başarılı şubeler hangileri?").is_ambiguous

    # Ranking without metric
    assert parser.parse("En iyi 5 bayi hangileri?").is_ambiguous

    # Missing time window on trend or comparison
    trend_missing = parser.parse("Satış trendi nasıl?")
    assert trend_missing.intent is Intent.TREND
    assert trend_missing.is_ambiguous
    assert any("zaman aralığı" in msg.lower() for msg in trend_missing.ambiguities)

    comp_missing = parser.parse("Bayi satışlarını karşılaştır")
    assert comp_missing.intent is Intent.COMPARISON
    assert comp_missing.is_ambiguous

    # Trend / comparison WITH time window should be clear
    assert not parser.parse("Son 6 ay satış trendi nasıl?").is_ambiguous
    assert not parser.parse("Geçen ay ile bu ay satışlarını karşılaştır").is_ambiguous

    # Conflicting disjoint date filters
    conflict = parser.parse("Dün geçen ayki satışlar ne kadardı?")
    assert conflict.is_ambiguous
    assert any("çelişkili" in msg.lower() for msg in conflict.ambiguities)


def test_temporal_number_not_treated_as_limit(parser: RuleBasedTurkishParser) -> None:
    p = parser.parse("Son 30 günün en çok satış yapan 5 bayisi")
    assert p.limit == 5
    p_no_limit = parser.parse("Son 30 günün satışları")
    assert p_no_limit.limit is None


def test_unanswerable_detection() -> None:
    mini_schema = SchemaSnapshot(
        dialect=Dialect.SQLITE,
        tables=(
            TableInfo(
                name="dealers",
                columns=(ColumnInfo(name="dealer_id", data_type="INTEGER", is_primary_key=True),),
                description="bayiler",
            ),
        ),
    )
    detector = AmbiguityDetector()
    assert detector.detect_unanswerable("Bugün hava durumu nasıl?", mini_schema) is not None
    assert detector.detect_unanswerable("Bayilerin listesi nedir?", mini_schema) is None
