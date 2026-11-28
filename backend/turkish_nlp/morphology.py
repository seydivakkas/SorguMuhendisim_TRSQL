from __future__ import annotations

import importlib
from collections.abc import Iterable
from typing import Protocol, runtime_checkable

from backend.turkish_nlp.normalize import normalize_ascii_turkish, strip_suffix, tr_casefold

_VOWELS = frozenset("aeıioöuü")
_BACK_VOWELS = frozenset("aıou")
_FRONT_VOWELS = frozenset("eiöü")

# Domain-safe stems that naturally end in a vowel or suffix-like letters so
# naive suffix peeling does not truncate them (e.g. ``bayi``, ``müşteri``).
_PROTECTED_STEMS: frozenset[str] = frozenset(
    {
        "müşteri",
        "bayi",
        "şube",
        "ödeme",
        "fatura",
        "mağaza",
        "bölge",
        "kategori",
        "iade",
        "kampanya",
        "depo",
        "sayı",
        "veri",
        "kredi",
        "vade",
        "bakiye",
        "ilçe",
        "ülke",
        "kalite",
        "hisse",
        "vergi",
        "kargo",
        "firma",
        "marka",
        "para",
        "süre",
        "bütçe",
        "liste",
        "tablo",
        "şema",
        "soru",
        "kural",
        "ölçüt",
        "birim",
        "ciro",
        "satış",
        "sipariş",
        "ürün",
        "çalışan",
        "hasılat",
        "şehir",
        "adet",
        "tutar",
        "miktar",
        "fiyat",
        "gelir",
        "gider",
        "maliyet",
        "masraf",
        "maaş",
        "borç",
        "stok",
        "hedef",
        "destek",
        "talep",
        "durum",
        "neden",
        "yöntem",
        "tarih",
        "dolar",
        "pazar",
        "fazla",
        "aile",
        "hangi",
        "hangisi",
        "hangileri",
        "bir",
        "iki",
        "üç",
        "dört",
        "beş",
        "altı",
        "yedi",
        "sekiz",
        "dokuz",
        "on",
        "yirmi",
        "otuz",
        "elli",
        "yüz",
        "bin",
        "ile",
        "veya",
        "göre",
        "için",
        "kadar",
        "olan",
        "yapan",
        "en",
        "çok",
        "az",
        "iyi",
        "kötü",
        "yüksek",
        "düşük",
        "büyük",
        "küçük",
        "önemli",
        "geçen",
        "bugün",
        "dün",
        "yarın",
        "ay",
        "yıl",
        "gün",
        "hafta",
        "çeyrek",
    }
)

_UNVOICE_LAST: dict[str, str] = {
    "b": "p",
    "c": "ç",
    "d": "t",
    "ğ": "k",
}

_SOFTENED_STEM_REPAIRS: dict[str, str] = {
    "aded": "adet",
    "borc": "borç",
    "sonuc": "sonuç",
    "amac": "amaç",
    "ilac": "ilaç",
    "stoğ": "stok",
    "kitab": "kitap",
    "reng": "renk",
    "hesab": "hesap",
    "kayb": "kayıp",
    "nakd": "nakit",
    "şehr": "şehir",
    "ism": "isim",
    "ömr": "ömür",
    "vakt": "vakit",
    "kısm": "kısım",
    "hacm": "hacim",
    "resm": "resim",
    "metn": "metin",
}

_COPULA_SUFFIXES = ("dır", "dir", "dur", "dür", "tır", "tir", "tur", "tür")

_KI_LOCATIVE_SUFFIXES = (
    "sındaki",
    "sindeki",
    "sundaki",
    "sündeki",
    "ndaki",
    "ndeki",
    "daki",
    "deki",
    "taki",
    "teki",
)

_PRONOMINAL_CASE_SUFFIXES = (
    "ndan",
    "nden",
    "nda",
    "nde",
    "na",
    "ne",
    "nı",
    "ni",
    "nu",
    "nü",
)

_MULTI_CASE_SUFFIXES = (
    "dan",
    "den",
    "tan",
    "ten",
    "nın",
    "nin",
    "nun",
    "nün",
    "da",
    "de",
    "ta",
    "te",
    "yı",
    "yi",
    "yu",
    "yü",
    "ya",
    "ye",
    "ın",
    "in",
    "un",
    "ün",
)

_INST_SUFFIXES = ("yla", "yle", "la", "le")

_POSSESSIVE_PLURAL_SUFFIXES = (
    "larımız",
    "lerimiz",
    "larınız",
    "leriniz",
    "ları",
    "leri",
)

_POSSESSIVE_SUFFIXES = (
    "ımız",
    "imiz",
    "umuz",
    "ümüz",
    "ınız",
    "iniz",
    "unuz",
    "ünüz",
    "mız",
    "miz",
    "muz",
    "müz",
    "nız",
    "niz",
    "nuz",
    "nüz",
    "sı",
    "si",
    "su",
    "sü",
    "ım",
    "im",
    "um",
    "üm",
)

_PLURAL_SUFFIXES = ("lar", "ler")
_SINGLE_VOWEL_SUFFIXES = ("a", "e", "ı", "i", "u", "ü")


@runtime_checkable
class ZemberekPort(Protocol):
    """Minimal structural interface for optional ``zemberek-python`` analyzers."""

    def analyze(self, word: str) -> object: ...


def is_zemberek_available() -> bool:
    """Return True if optional ``zemberek`` package can be imported."""
    try:
        importlib.import_module("zemberek")
    except Exception:
        return False
    return True


def _try_load_zemberek() -> ZemberekPort | None:
    try:
        mod = importlib.import_module("zemberek")
        cls = getattr(mod, "TurkishMorphology", None)
        if cls is None:
            return None
        morph = cls.create_with_defaults()
        return morph if isinstance(morph, ZemberekPort) else None
    except Exception:
        return None


def _last_vowel(word: str) -> str | None:
    for ch in reversed(word):
        if ch in _VOWELS:
            return ch
    return None


def _harmony_matches(stem: str, suffix: str) -> bool:
    stem_v = _last_vowel(stem)
    suf_v = next((ch for ch in suffix if ch in _VOWELS), None)
    if stem_v is None or suf_v is None:
        return True
    if stem_v in _BACK_VOWELS:
        return suf_v in _BACK_VOWELS
    return suf_v in _FRONT_VOWELS


def _ends_with_vowel(word: str) -> bool:
    return bool(word) and word[-1] in _VOWELS


def _repair_stem(stem: str, protected: frozenset[str]) -> str:
    if stem in protected:
        return stem
    repaired = _SOFTENED_STEM_REPAIRS.get(stem)
    if repaired is not None:
        return repaired
    if stem and stem[-1] in _UNVOICE_LAST:
        cand = stem[:-1] + _UNVOICE_LAST[stem[-1]]
        if cand in protected:
            return cand
    return stem


def _try_strip(
    word: str,
    suffixes: tuple[str, ...],
    protected: frozenset[str],
    *,
    require_vowel_stem: bool = False,
    min_len: int = 3,
) -> tuple[str, bool]:
    for suf in suffixes:
        if not word.endswith(suf):
            continue
        cand = word[: -len(suf)]
        if len(cand) < min_len:
            continue
        if require_vowel_stem and not _ends_with_vowel(cand):
            continue
        repaired = _repair_stem(cand, protected)
        if cand in protected or repaired in protected:
            return repaired, True
        if _harmony_matches(cand, suf):
            return repaired, True
    return word, False


def strip_turkish_suffixes(token: str, known_stems: Iterable[str] = ()) -> str:
    """Rule-based Turkish agglutinative lemmatizer / suffix stripper.

    Handles apostrophe-separated case suffixes (``istanbul'daki`` -> ``istanbul``)
    and stacked nominal inflectional suffixes (``müşterilerimizin`` -> ``müşteri``,
    ``siparişlerinden`` -> ``sipariş``).
    """
    protected = _PROTECTED_STEMS | frozenset(tr_casefold(s) for s in known_stems if s)
    cleaned = normalize_ascii_turkish(token).strip(".,;:!?\"'()[]{}")
    if not cleaned:
        return ""
    if "'" in cleaned:
        head = strip_suffix(cleaned)
        return _repair_stem(head, protected)

    cur = cleaned
    if cur in protected:
        return cur

    # 1. Optional copula (-dIr / -tIr)
    cur, _ = _try_strip(cur, _COPULA_SUFFIXES, protected)
    if cur in protected:
        return cur

    # 2. Locative + relative -ki (-dAkI / -ndAkI / -sIndAkI) or bare -ki
    stripped_ki = False
    cur, stripped_ki = _try_strip(cur, _KI_LOCATIVE_SUFFIXES, protected)
    if cur in protected:
        return cur
    if not stripped_ki and cur.endswith("ki") and len(cur) > 4:
        cand = cur[:-2]
        if cand in protected or cand.endswith(("da", "de", "ta", "te", "dün", "gün", "önce", "sonra")):
            cur = cand
            if cur in protected:
                return cur

    # 3. Case suffixes (pronominal-n + case, multi-char case, instrumental, single vowel)
    cur, stripped_pronominal = _try_strip(cur, _PRONOMINAL_CASE_SUFFIXES, protected)
    if cur in protected:
        return cur

    if not stripped_pronominal:
        cur, stripped_case = _try_strip(cur, _MULTI_CASE_SUFFIXES, protected)
        if cur in protected:
            return cur
        if not stripped_case:
            cur, _ = _try_strip(cur, _INST_SUFFIXES, protected)
            if cur in protected:
                return cur
            # Single-vowel case (-a/-e/-ı/-i/-u/-ü)
            for suf in _SINGLE_VOWEL_SUFFIXES:
                if cur.endswith(suf) and len(cur) - 1 >= 3:
                    cand = cur[:-1]
                    repaired = _repair_stem(cand, protected)
                    if cand in protected or repaired in protected:
                        return repaired
                    if len(cand) >= 4 and not _ends_with_vowel(cand) and _harmony_matches(cand, suf):
                        cur = repaired
                        break

    # 4. Possessive + plural combined (e.g. -larımız, -leri)
    cur, stripped_poss_pl = _try_strip(cur, _POSSESSIVE_PLURAL_SUFFIXES, protected)
    if cur in protected:
        return cur

    # 5. Possessive (-ımız/-miz/-si/-ım)
    if not stripped_poss_pl:
        # Prefer vowel-final stem match for -mIz/-nIz/-sI before consonant-final -ImIz
        for suf in ("mız", "miz", "muz", "müz", "nız", "niz", "nuz", "nüz", "sı", "si", "su", "sü"):
            if cur.endswith(suf) and len(cur) - len(suf) >= 3:
                cand = cur[: -len(suf)]
                if _ends_with_vowel(cand) and (cand in protected or _harmony_matches(cand, suf)):
                    cur = cand
                    break
        else:
            cur, _ = _try_strip(cur, _POSSESSIVE_SUFFIXES, protected)
        if cur in protected:
            return cur

        # Bare -m/-n possessive on vowel-final stem (e.g. müşterim -> müşteri)
        if cur.endswith(("m", "n")) and len(cur) >= 4 and _ends_with_vowel(cur[:-1]):
            cand = cur[:-1]
            if cand in protected:
                return cand

        # Trailing 3sg possessive vowel exposed after stripping pronominal-n case
        if stripped_pronominal:
            for suf in _SINGLE_VOWEL_SUFFIXES:
                if cur.endswith(suf) and len(cur) - 1 >= 3:
                    cand = cur[:-1]
                    repaired = _repair_stem(cand, protected)
                    if cand in protected or repaired in protected or _harmony_matches(cand, suf):
                        cur = repaired
                        break

    # 6. Plural (-lAr)
    if cur not in protected:
        cur, _ = _try_strip(cur, _PLURAL_SUFFIXES, protected)

    return _repair_stem(cur, protected)


class TurkishMorphologyAnalyzer:
    """Turkish agglutinative lemmatizer with optional lazy ``zemberek-python`` hook."""

    def __init__(
        self,
        known_stems: Iterable[str] = (),
        *,
        use_zemberek: bool = False,
        zemberek_analyzer: ZemberekPort | None = None,
    ) -> None:
        self._known_stems = frozenset(tr_casefold(s) for s in known_stems if s)
        self._zemberek: ZemberekPort | None = zemberek_analyzer
        if self._zemberek is None and use_zemberek:
            self._zemberek = _try_load_zemberek()

    @property
    def using_zemberek(self) -> bool:
        return self._zemberek is not None

    def lemmatize(self, token: str) -> str:
        """Return the base Turkish lemma of ``token``."""
        cleaned = normalize_ascii_turkish(token).strip(".,;:!?\"'()[]{}")
        if not cleaned:
            return ""
        if "'" in cleaned:
            return strip_turkish_suffixes(cleaned, self._known_stems)
        if cleaned in self._known_stems or cleaned in _PROTECTED_STEMS:
            return cleaned

        if self._zemberek is not None:
            lemma = self._lemmatize_with_zemberek(cleaned)
            if lemma is not None:
                return lemma

        return strip_turkish_suffixes(cleaned, self._known_stems)

    def lemmatize_tokens(self, text: str) -> list[str]:
        """Normalize and lemmatize every whitespace token in ``text``."""
        normalized = normalize_ascii_turkish(text)
        return [self.lemmatize(tok) for tok in normalized.split() if self.lemmatize(tok)]

    def _lemmatize_with_zemberek(self, token: str) -> str | None:
        if self._zemberek is None:
            return None
        try:
            analysis = self._zemberek.analyze(token)
            results = getattr(analysis, "analysis_results", None)
            if results:
                first = results[0]
                item = getattr(first, "item", None)
                root = getattr(item, "root", None) or getattr(first, "lemma", None)
                if isinstance(root, str) and root and root != "UNK":
                    return tr_casefold(root)
        except Exception:
            return None
        return None


def lemmatize_token(token: str, known_stems: Iterable[str] = ()) -> str:
    """Pure-Python Turkish agglutinative lemmatizer for a single token."""
    return strip_turkish_suffixes(token, known_stems)


def lemmatize_text(text: str, known_stems: Iterable[str] = ()) -> list[str]:
    """Pure-Python Turkish lemmatizer for all tokens in ``text``."""
    return TurkishMorphologyAnalyzer(known_stems).lemmatize_tokens(text)
