from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping

_TR_UPPER_MAP = str.maketrans({"I": "ı", "İ": "i"})
_APOSTROPHES = re.compile(r"[’'`´]")
_SPACES = re.compile(r"\s+")
_TOKEN_RE = re.compile(r"[^\s]+")

ASCII_TURKISH_MAP: dict[str, str] = {
    "musteri": "müşteri",
    "musteriler": "müşteriler",
    "musterisi": "müşterisi",
    "satis": "satış",
    "satislar": "satışlar",
    "satisi": "satışı",
    "sube": "şube",
    "subeler": "şubeler",
    "subesi": "şubesi",
    "sehir": "şehir",
    "sehirler": "şehirler",
    "sehri": "şehri",
    "sehrin": "şehrin",
    "sehre": "şehre",
    "odeme": "ödeme",
    "odemeler": "ödemeler",
    "urun": "ürün",
    "urunler": "ürünler",
    "hasilat": "hasılat",
    "hasilati": "hasılatı",
    "magaza": "mağaza",
    "magazalar": "mağazalar",
    "calisan": "çalışan",
    "calisanlar": "çalışanlar",
    "calisani": "çalışanı",
    "siparis": "sipariş",
    "siparisler": "siparişler",
    "bolge": "bölge",
    "bolgeler": "bölgeler",
    "sirket": "şirket",
    "tedarikci": "tedarikçi",
    "borc": "borç",
    "borclari": "borçları",
    "odenen": "ödenen",
    "gecen": "geçen",
    "gectigimiz": "geçtiğimiz",
    "onumuzdeki": "önümüzdeki",
    "onceki": "önceki",
    "yil": "yıl",
    "yili": "yılı",
    "yilin": "yılın",
    "yillar": "yıllar",
    "yillik": "yıllık",
    "yilbasi": "yılbaşı",
    "yilbasindan": "yılbaşından",
    "aylik": "aylık",
    "aybasi": "aybaşı",
    "aybasindan": "aybaşından",
    "gun": "gün",
    "gunluk": "günlük",
    "bugun": "bugün",
    "bugune": "bugüne",
    "dun": "dün",
    "yarin": "yarın",
    "ceyrek": "çeyrek",
    "ceyregi": "çeyreği",
    "donem": "dönem",
    "donemi": "dönemi",
    "donemini": "dönemini",
    "ayni": "aynı",
    "yarisi": "yarısı",
    "yariyil": "yarıyıl",
    "ucuncu": "üçüncü",
    "dorduncu": "dördüncü",
    "subat": "şubat",
    "agustos": "ağustos",
    "eylul": "eylül",
    "mayis": "mayıs",
    "kasim": "kasım",
    "aralik": "aralık",
    "uc": "üç",
    "dort": "dört",
    "bes": "beş",
    "alti": "altı",
    "yuz": "yüz",
    "kac": "kaç",
    "cok": "çok",
    "yuksek": "yüksek",
    "dusuk": "düşük",
    "kucuk": "küçük",
    "buyuk": "büyük",
    "kotu": "kötü",
    "onemli": "önemli",
    "basarili": "başarılı",
    "karli": "kârlı",
    "karsilastir": "karşılaştır",
    "karsilastirma": "karşılaştırma",
    "kiyasla": "kıyasla",
    "degisim": "değişim",
    "degisimi": "değişimi",
    "gidisat": "gidişat",
    "gidisati": "gidişatı",
    "tutari": "tutarı",
    "miktari": "miktarı",
    "sayisi": "sayısı",
    "ortalamasi": "ortalaması",
    "toplami": "toplamı",
    "fiyati": "fiyatı",
    "numarali": "numaralı",
    "yaptigi": "yaptığı",
    "olcut": "ölçüt",
}

# (ascii_stem, turkish_stem, is_back_vowel_stem)
_ASCII_STEM_RULES: tuple[tuple[str, str, bool], ...] = (
    ("tedarikci", "tedarikçi", False),
    ("musteri", "müşteri", False),
    ("calisan", "çalışan", True),
    ("hasilat", "hasılat", True),
    ("siparis", "sipariş", False),
    ("magaza", "mağaza", True),
    ("agustos", "ağustos", True),
    ("sirket", "şirket", False),
    ("aralik", "aralık", True),
    ("sehir", "şehir", False),
    ("odeme", "ödeme", False),
    ("satis", "satış", True),
    ("bolge", "bölge", False),
    ("subat", "şubat", True),
    ("eylul", "eylül", False),
    ("kasim", "kasım", True),
    ("mayis", "mayıs", True),
    ("sube", "şube", False),
    ("urun", "ürün", False),
    ("borc", "borç", True),
    ("gun", "gün", False),
    ("yil", "yıl", True),
)

_BACK_VOWEL_SUFFIX_MAP: dict[str, str] = {
    "larimizindan": "larımızdan",
    "larimizdaki": "larımızdaki",
    "larimizda": "larımızda",
    "larimizin": "larımızın",
    "larimizi": "larımızı",
    "larimiza": "larımıza",
    "larimiz": "larımız",
    "lariniz": "larınız",
    "larindan": "larından",
    "larindaki": "larındaki",
    "larinda": "larında",
    "larinin": "larının",
    "larina": "larına",
    "lari": "ları",
    "larin": "ların",
    "larim": "larım",
    "imizdan": "ımızdan",
    "imizdaki": "ımızdaki",
    "imizda": "ımızda",
    "imizin": "ımızın",
    "imizi": "ımızı",
    "imiza": "ımıza",
    "imiz": "ımız",
    "iniz": "ınız",
    "sindan": "sından",
    "sindaki": "sındaki",
    "sinda": "sında",
    "sinin": "sının",
    "sina": "sına",
    "si": "sı",
    "ndan": "ndan",
    "nda": "nda",
    "nin": "nın",
    "ni": "nı",
    "yi": "yı",
    "lik": "lık",
    "siz": "sız",
    "ci": "cı",
    "li": "lı",
    "in": "ın",
    "im": "ım",
    "i": "ı",
}

_FRONT_ROUNDED_U_MAP: dict[str, str] = {
    "umuz": "ümüz",
    "unuz": "ünüz",
    "um": "üm",
    "un": "ün",
    "luk": "lük",
    "lu": "lü",
    "suz": "süz",
    "u": "ü",
}

_VALID_SUFFIX_STARTS = frozenset("ldtmsyniaeouck")

SYNONYM_GROUPS: tuple[tuple[str, ...], ...] = (
    ("ciro", "hasılat", "satış tutarı", "net satış", "satış geliri", "gelir", "satış"),
    ("miktar", "adet", "sayı"),
    ("çalışan", "personel", "eleman"),
    ("müşteri", "alıcı"),
    ("gider", "masraf", "harcama", "maliyet"),
    ("kâr", "kar", "kazanç", "net kâr"),
    ("bayi", "acente"),
    ("şube", "mağaza"),
    ("fatura", "makbuz"),
)

SYNONYM_MAP: dict[str, str] = {
    "ciro": "ciro",
    "hasılat": "ciro",
    "satış tutarı": "ciro",
    "net satış": "ciro",
    "satış geliri": "ciro",
    "gelir": "ciro",
    "miktar": "miktar",
    "adet": "miktar",
    "sayı": "miktar",
    "çalışan": "çalışan",
    "personel": "çalışan",
    "eleman": "çalışan",
    "müşteri": "müşteri",
    "alıcı": "müşteri",
    "gider": "gider",
    "masraf": "gider",
    "harcama": "gider",
    "maliyet": "gider",
    "kâr": "kâr",
    "kar": "kâr",
    "kazanç": "kâr",
    "net kâr": "kâr",
    "bayi": "bayi",
    "acente": "bayi",
    "şube": "şube",
    "mağaza": "şube",
    "fatura": "fatura",
    "makbuz": "fatura",
}


def tr_casefold(text: str) -> str:
    """Turkish-aware lowercase.

    Python's ``str.lower`` maps ``I`` to ``i`` and ``İ`` to ``i̇`` (with a
    combining dot), which is wrong for Turkish. Always use this function
    instead of ``.lower()`` on user text.
    """
    text = unicodedata.normalize("NFC", text).translate(_TR_UPPER_MAP)
    return text.lower()


def _is_pure_ascii_alpha(word: str) -> bool:
    return bool(word) and all("a" <= ch <= "z" for ch in word)


def _normalize_ascii_word(word: str) -> str:
    if "_" in word or any(ch.isdigit() for ch in word):
        return word
    if "'" in word:
        stem, rest = word.split("'", 1)
        fixed_stem = _normalize_ascii_word(stem)
        return f"{fixed_stem}'{rest}"
    if not _is_pure_ascii_alpha(word):
        return word
    exact = ASCII_TURKISH_MAP.get(word)
    if exact is not None:
        return exact
    for ascii_stem, tr_stem, is_back in _ASCII_STEM_RULES:
        if word.startswith(ascii_stem) and len(word) > len(ascii_stem):
            rem = word[len(ascii_stem) :]
            if rem[0] not in _VALID_SUFFIX_STARTS:
                continue
            if is_back:
                rem = _BACK_VOWEL_SUFFIX_MAP.get(rem, rem)
            elif tr_stem in {"ürün", "gün"}:
                rem = _FRONT_ROUNDED_U_MAP.get(rem, rem)
            return f"{tr_stem}{rem}"
    return word


def normalize_ascii_turkish(text: str) -> str:
    """Restore Turkish diacritics on common ASCII-typed Turkish words."""
    folded = tr_casefold(text)
    folded = _APOSTROPHES.sub("'", folded)

    def _replace(match: re.Match[str]) -> str:
        tok = match.group(0)
        leading = ""
        trailing = ""
        while tok and tok[0] in "([{\"'":
            leading += tok[0]
            tok = tok[1:]
        while tok and tok[-1] in ".,;:!?)]}\"'":
            trailing = tok[-1] + trailing
            tok = tok[:-1]
        if not tok:
            return match.group(0)
        return f"{leading}{_normalize_ascii_word(tok)}{trailing}"

    return _TOKEN_RE.sub(_replace, folded)


def normalize_question(text: str, *, fix_ascii: bool = True) -> str:
    """Casefold, unify apostrophes (``Trabzon'daki`` -> ``trabzon'daki``),
    normalize ASCII-typed Turkish words, and collapse whitespace."""
    cleaned = tr_casefold(text)
    cleaned = _APOSTROPHES.sub("'", cleaned)
    cleaned = _SPACES.sub(" ", cleaned).strip(" ?!.")
    if fix_ascii and cleaned:
        cleaned = normalize_ascii_turkish(cleaned)
    return cleaned


def strip_suffix(token: str) -> str:
    """Drop the case suffix after an apostrophe: ``trabzon'daki`` -> ``trabzon``."""
    return token.split("'", 1)[0]


def resolve_synonym(term: str, mapping: Mapping[str, str] | None = None) -> str:
    """Resolve a Turkish business term or phrase to its canonical synonym."""
    normalized = normalize_question(term)
    table = mapping if mapping is not None else SYNONYM_MAP
    return table.get(normalized, normalized)


def synonym_candidates(term: str) -> tuple[str, ...]:
    """Return all known Turkish synonym variants for ``term`` (itself first)."""
    normalized = normalize_question(term)
    seen: list[str] = [normalized]
    for group in SYNONYM_GROUPS:
        if normalized in group:
            for item in group:
                if item not in seen:
                    seen.append(item)
    canonical = SYNONYM_MAP.get(normalized)
    if canonical is not None and canonical not in seen:
        seen.append(canonical)
    return tuple(seen)
