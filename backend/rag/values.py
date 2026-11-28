"""Turkish-aware cell value linking via lemmas, MinHash-LSH, and edit distance.

Strictly excludes PII and ``denied_columns`` at both index and query time.
"""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from backend.core.contracts import MentionKind, ParsedQuestion, SchemaSnapshot
from backend.knowledge_base import fold_turkish_diacritics, tr_casefold

_APOSTROPHE_RE = re.compile(r"[’'`´]")
_EDGE_PUNCT = ".,;:!?\"'()[]{}"

_VOWELS = frozenset("aeıioöuü")
_BACK_VOWELS = frozenset("aıou")
_FRONT_VOWELS = frozenset("eiöü")

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
    "ki",
)
_CASE_SUFFIXES = (
    "ndan",
    "nden",
    "nda",
    "nde",
    "dan",
    "den",
    "tan",
    "ten",
    "nın",
    "nin",
    "nun",
    "nün",
    "yla",
    "yle",
    "da",
    "de",
    "ta",
    "te",
    "ya",
    "ye",
    "yı",
    "yi",
    "yu",
    "yü",
    "na",
    "ne",
    "nı",
    "ni",
    "nu",
    "nü",
    "la",
    "le",
    "ın",
    "in",
    "un",
    "ün",
    "a",
    "e",
    "ı",
    "i",
    "u",
    "ü",
)
_POSSESSIVE_PLURAL_SUFFIXES = (
    "larımız",
    "lerimiz",
    "larınız",
    "leriniz",
    "ları",
    "leri",
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
    "sı",
    "si",
    "su",
    "sü",
    "lar",
    "ler",
)
_DERIVATIONAL_SUFFIXES = ("lı", "li", "lu", "lü", "sız", "siz", "suz", "süz")
_UNVOICE_LAST = {"b": "p", "c": "ç", "d": "t", "ğ": "k"}

_STOPWORDS = frozenset(
    {
        "ve",
        "veya",
        "ile",
        "için",
        "göre",
        "olan",
        "yapan",
        "kaç",
        "ne",
        "nedir",
        "hangi",
        "hangisi",
        "hangileri",
        "tüm",
        "bütün",
        "en",
        "çok",
        "az",
        "var",
        "yok",
        "bu",
        "şu",
        "o",
        "bir",
        "iki",
        "üç",
        "dört",
        "beş",
        "son",
        "geçen",
        "ay",
        "yıl",
        "gün",
        "hafta",
    }
)

DEFAULT_PII_COLUMN_TOKENS: frozenset[str] = frozenset(
    {
        "tax_number",
        "vergi_no",
        "vergi_numarasi",
        "tckn",
        "tc_kimlik",
        "tc_no",
        "kimlik_no",
        "iban",
        "telefon",
        "phone",
        "cep_telefonu",
        "mobile",
        "email",
        "eposta",
        "e_posta",
        "maas",
        "salary",
        "ucret",
        "password",
        "sifre",
        "kart_no",
        "card_number",
        "pasaport",
        "passport",
        "dogum_tarihi",
        "birth_date",
        "adres",
        "address",
    }
)

_MERSENNE_61 = (1 << 61) - 1


def _last_vowel(word: str) -> str | None:
    for ch in reversed(word):
        if ch in _VOWELS:
            return ch
    return None


def _harmony_ok(stem: str, suffix: str) -> bool:
    sv = _last_vowel(stem)
    fv = next((ch for ch in suffix if ch in _VOWELS), None)
    if sv is None or fv is None:
        return True
    if sv in _BACK_VOWELS:
        return fv in _BACK_VOWELS
    return fv in _FRONT_VOWELS


def _unvoice_variants(stem: str) -> list[str]:
    if stem and stem[-1] in _UNVOICE_LAST:
        return [stem, stem[:-1] + _UNVOICE_LAST[stem[-1]]]
    return [stem]


def turkish_lemma_candidates(token: str) -> tuple[str, ...]:
    """Generate ordered Turkish lemma/stem candidates without discarding the surface root.

    For apostrophe-separated proper nouns (``İstanbul'daki`` -> ``istanbul``),
    the pre-apostrophe root comes first.  For non-apostrophe inflected words
    (``istanbuldaki`` or ``müşterilerimizin``), both the surface form and
    progressively stripped nominal stems are returned so proper nouns ending in
    suffix-like letters (``Mardin``, ``Isparta``, ``Burdur``) are never lost.
    """
    cleaned = _APOSTROPHE_RE.sub("'", tr_casefold(token)).strip(_EDGE_PUNCT)
    if not cleaned:
        return ()

    candidates: list[str] = []

    def _add(item: str) -> None:
        for variant in _unvoice_variants(item):
            if variant and variant not in candidates:
                candidates.append(variant)

    if "'" in cleaned:
        head = cleaned.split("'", 1)[0].strip(_EDGE_PUNCT)
        _add(head)
        if head != cleaned:
            _add(cleaned.replace("'", ""))
        return tuple(candidates)

    _add(cleaned)
    cur = cleaned

    for layer in (_COPULA_SUFFIXES, _KI_LOCATIVE_SUFFIXES, _CASE_SUFFIXES):
        for suf in layer:
            if cur.endswith(suf) and len(cur) - len(suf) >= 3:
                cand = cur[: -len(suf)]
                if _harmony_ok(cand, suf) or len(suf) >= 3:
                    cur = cand
                    _add(cur)
                    break

    for deriv_layer in (_POSSESSIVE_PLURAL_SUFFIXES, _DERIVATIONAL_SUFFIXES):
        for suf in deriv_layer:
            if cur.endswith(suf) and len(cur) - len(suf) >= 3:
                cand = cur[: -len(suf)]
                if _harmony_ok(cand, suf):
                    cur = cand
                    _add(cur)
                    break

    return tuple(candidates)


def lemmatize_turkish_token(token: str) -> str:
    """Return the primary stripped Turkish lemma for ``token``."""
    cands = turkish_lemma_candidates(token)
    if not cands:
        return ""
    if "'" in _APOSTROPHE_RE.sub("'", token):
        return cands[0]
    return cands[-1]


def levenshtein_distance(source: str, target: str) -> int:
    """Compute Levenshtein edit distance in O(min(|source|, |target|)) space."""
    if source == target:
        return 0
    if len(source) < len(target):
        source, target = target, source
    if not target:
        return len(source)

    prev = list(range(len(target) + 1))
    for i, sc in enumerate(source, start=1):
        curr = [i]
        for j, tc in enumerate(target, start=1):
            cost = 0 if sc == tc else 1
            curr.append(min(curr[j - 1] + 1, prev[j] + 1, prev[j - 1] + cost))
        prev = curr
    return prev[-1]


def _char_ngrams(text: str, n: int = 3) -> frozenset[str]:
    padded = f"^{text}$"
    grams = {padded} if len(padded) <= n else {padded[i : i + n] for i in range(len(padded) - n + 1)}
    if len(text) >= 2:
        grams |= {text[i : i + 2] for i in range(len(text) - 1)}
    else:
        grams.add(text)
    return frozenset(grams)


def _stable_hash64(value: str) -> int:
    digest = hashlib.blake2b(value.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "little") & ((1 << 61) - 1)


class MinHashLSHIndex:
    """Pure-Python deterministic MinHash-LSH index over character n-grams."""

    def __init__(self, *, num_perm: int = 64, bands: int = 32, ngram_size: int = 3) -> None:
        if num_perm <= 0 or bands <= 0 or num_perm % bands != 0:
            raise ValueError("num_perm must be positive and divisible by bands")
        self._num_perm = num_perm
        self._bands = bands
        self._rows = num_perm // bands
        self._ngram_size = ngram_size
        self._coeffs = tuple(
            (
                (_stable_hash64(f"a:{i}") | 1) % _MERSENNE_61,
                _stable_hash64(f"b:{i}") % _MERSENNE_61,
            )
            for i in range(num_perm)
        )
        self._buckets: dict[tuple[int, tuple[int, ...]], list[int]] = defaultdict(list)
        self._exact_map: dict[str, list[int]] = defaultdict(list)

    def _signature(self, text: str) -> tuple[int, ...]:
        shingles = [_stable_hash64(g) for g in _char_ngrams(text, self._ngram_size)]
        if not shingles:
            return (0,) * self._num_perm
        sig: list[int] = []
        for a, b in self._coeffs:
            sig.append(min((a * h + b) % _MERSENNE_61 for h in shingles))
        return tuple(sig)

    def add(self, item_id: int, key: str) -> None:
        """Insert ``item_id`` under normalized string ``key``."""
        if not key:
            return
        if item_id not in self._exact_map[key]:
            self._exact_map[key].append(item_id)
        sig = self._signature(key)
        for band_idx in range(self._bands):
            start = band_idx * self._rows
            band_slice = sig[start : start + self._rows]
            bucket = self._buckets[(band_idx, band_slice)]
            if item_id not in bucket:
                bucket.append(item_id)

    def query(self, key: str) -> set[int]:
        """Return candidate item IDs sharing at least one LSH band or exact key."""
        if not key:
            return set()
        hits: set[int] = set(self._exact_map.get(key, ()))
        sig = self._signature(key)
        for band_idx in range(self._bands):
            start = band_idx * self._rows
            band_slice = sig[start : start + self._rows]
            hits.update(self._buckets.get((band_idx, band_slice), ()))
        return hits


@dataclass(frozen=True)
class ValueMatch:
    """Resolved database cell value linked to a question mention or phrase."""

    mention: str
    matched_value: str
    table: str
    column: str
    score: float
    edit_distance: int


@dataclass(frozen=True)
class _IndexedValue:
    table: str
    column: str
    raw_value: str
    norm_value: str
    folded_value: str

    @property
    def qualified_column(self) -> str:
        return f"{self.table.lower()}.{self.column.lower()}"


class ValueLinker:
    """Links inflected/misspelled Turkish question values to DB cell values.

    Pipeline: Turkish casefold + suffix stripping -> MinHash-LSH candidate
    lookup -> Levenshtein edit distance ranking. PII and ``denied_columns``
    are never indexed and are double-checked at query time.
    """

    def __init__(
        self,
        *,
        min_similarity: float = 0.72,
        num_perm: int = 64,
        bands: int = 32,
        auto_exclude_pii: bool = True,
        pii_columns: frozenset[str] = frozenset(),
    ) -> None:
        if not 0.0 < min_similarity <= 1.0:
            raise ValueError("min_similarity must be in (0.0, 1.0]")
        self._min_similarity = min_similarity
        self._auto_exclude_pii = auto_exclude_pii
        self._pii_columns = frozenset(c.lower() for c in pii_columns)
        self._entries: list[_IndexedValue] = []
        self._seen_keys: set[tuple[str, str, str]] = set()
        self._lsh_tr = MinHashLSHIndex(num_perm=num_perm, bands=bands)
        self._lsh_ascii = MinHashLSHIndex(num_perm=num_perm, bands=bands)

    def is_pii_column(
        self,
        table: str,
        column: str,
        *,
        denied_columns: frozenset[str] = frozenset(),
    ) -> bool:
        """Return True if ``table.column`` is denied or matches PII rules."""
        qual = f"{table.lower()}.{column.lower()}"
        denied = {d.lower() for d in denied_columns}
        if qual in denied or qual in self._pii_columns:
            return True
        if not self._auto_exclude_pii:
            return False
        col_low = column.lower()
        return col_low in DEFAULT_PII_COLUMN_TOKENS or any(
            tok in col_low for tok in ("tax_number", "tckn", "tc_kimlik", "iban", "password", "sifre")
        )

    def index_column(
        self,
        table: str,
        column: str,
        values: Iterable[str],
        *,
        denied_columns: frozenset[str] = frozenset(),
    ) -> int:
        """Index cell values for ``table.column``. Returns indexed item count."""
        if self.is_pii_column(table, column, denied_columns=denied_columns):
            return 0
        added = 0
        for raw in values:
            val = str(raw).strip()
            if not val:
                continue
            dedup_key = (table.lower(), column.lower(), val)
            if dedup_key in self._seen_keys:
                continue
            self._seen_keys.add(dedup_key)
            norm = tr_casefold(val)
            folded = fold_turkish_diacritics(val)
            idx = len(self._entries)
            self._entries.append(
                _IndexedValue(
                    table=table,
                    column=column,
                    raw_value=val,
                    norm_value=norm,
                    folded_value=folded,
                )
            )
            self._lsh_tr.add(idx, norm)
            self._lsh_ascii.add(idx, folded)
            added += 1
        return added

    def index_table_values(
        self,
        table_values: Mapping[tuple[str, str], Iterable[str]],
        *,
        denied_columns: frozenset[str] = frozenset(),
    ) -> int:
        """Bulk-index a mapping of ``(table, column) -> cell values``."""
        total = 0
        for (table, column), vals in table_values.items():
            total += self.index_column(table, column, vals, denied_columns=denied_columns)
        return total

    def index_schema_samples(
        self,
        schema: SchemaSnapshot,
        samples: Mapping[tuple[str, str], Iterable[str]],
        *,
        denied_columns: frozenset[str] = frozenset(),
    ) -> int:
        """Index sample values strictly for columns visible in ``schema``."""
        total = 0
        for (table, column), vals in samples.items():
            tbl = schema.table(table)
            if tbl is None or tbl.column(column) is None:
                continue
            total += self.index_column(tbl.name, column, vals, denied_columns=denied_columns)
        return total

    def _candidate_spans(self, question: ParsedQuestion) -> list[tuple[str, tuple[str, ...]]]:
        spans: list[tuple[str, tuple[str, ...]]] = []
        seen_raw: set[str] = set()

        for mention in question.mentions:
            if mention.kind not in (MentionKind.LOCATION, MentionKind.VALUE, MentionKind.ENTITY):
                continue
            cands = tuple(
                dict.fromkeys(
                    c
                    for src in (mention.text, mention.lemma or "")
                    if src
                    for c in turkish_lemma_candidates(src)
                )
            )
            if cands and mention.text not in seen_raw:
                seen_raw.add(mention.text)
                spans.append((mention.text, cands))

        words = [w.strip(_EDGE_PUNCT) for w in question.original_text.split() if w.strip(_EDGE_PUNCT)]
        for w in words:
            if tr_casefold(w) in _STOPWORDS or w in seen_raw:
                continue
            cands = turkish_lemma_candidates(w)
            if cands and not all(c in _STOPWORDS for c in cands):
                seen_raw.add(w)
                spans.append((w, cands))

        for n in (2, 3):
            for i in range(len(words) - n + 1):
                phrase = " ".join(words[i : i + n])
                if phrase in seen_raw:
                    continue
                last_cands = turkish_lemma_candidates(words[i + n - 1])
                prefix = " ".join(tr_casefold(w) for w in words[i : i + n - 1])
                phrase_cands = tuple(dict.fromkeys(f"{prefix} {lc}" for lc in last_cands))
                if phrase_cands:
                    seen_raw.add(phrase)
                    spans.append((phrase, phrase_cands))
        return spans

    def link(
        self,
        question: ParsedQuestion,
        *,
        allowed_tables: frozenset[str] | None = None,
        denied_columns: frozenset[str] = frozenset(),
        top_k: int = 5,
    ) -> tuple[ValueMatch, ...]:
        """Return top cell-value matches for ``question``, respecting RBAC/PII."""
        if top_k <= 0 or not self._entries:
            return ()

        allowed = {t.lower() for t in allowed_tables} if allowed_tables is not None else None
        denied = {d.lower() for d in denied_columns}
        best_by_entry: dict[int, ValueMatch] = {}

        for raw_span, candidates in self._candidate_spans(question):
            for cand in candidates:
                if len(cand) < 2 or cand in _STOPWORDS:
                    continue
                folded_cand = fold_turkish_diacritics(cand)
                cand_ids = self._lsh_tr.query(cand) | self._lsh_ascii.query(folded_cand)
                for idx in cand_ids:
                    entry = self._entries[idx]
                    if allowed is not None and entry.table.lower() not in allowed:
                        continue
                    if entry.qualified_column in denied or self.is_pii_column(
                        entry.table, entry.column, denied_columns=denied_columns
                    ):
                        continue

                    dist_tr = levenshtein_distance(cand, entry.norm_value)
                    sim_tr = 1.0 - (dist_tr / max(len(cand), len(entry.norm_value), 1))

                    dist_ascii = levenshtein_distance(folded_cand, entry.folded_value)
                    sim_ascii = (
                        1.0 - (dist_ascii / max(len(folded_cand), len(entry.folded_value), 1))
                    ) * 0.98

                    if sim_tr >= sim_ascii:
                        score, dist = sim_tr, dist_tr
                    else:
                        score, dist = sim_ascii, dist_ascii

                    if score < self._min_similarity:
                        continue

                    match = ValueMatch(
                        mention=raw_span,
                        matched_value=entry.raw_value,
                        table=entry.table,
                        column=entry.column,
                        score=round(score, 4),
                        edit_distance=dist,
                    )
                    prev = best_by_entry.get(idx)
                    if prev is None or (match.score, -match.edit_distance) > (
                        prev.score,
                        -prev.edit_distance,
                    ):
                        best_by_entry[idx] = match

        ranked = sorted(
            best_by_entry.values(),
            key=lambda m: (-m.score, m.edit_distance, m.table, m.column, m.matched_value),
        )
        return tuple(ranked[:top_k])
