from __future__ import annotations

import math
import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from backend.core.contracts import (
    JoinStep,
    LinkedSchema,
    MentionKind,
    ParsedQuestion,
    SchemaLink,
    SchemaSnapshot,
)
from backend.schema_intelligence import SchemaGraph

_TR_UPPER_MAP = str.maketrans({"I": "ı", "İ": "i"})
_TR_TO_ASCII_MAP = str.maketrans(
    {
        "ç": "c",
        "ğ": "g",
        "ı": "i",
        "ö": "o",
        "ş": "s",
        "ü": "u",
    }
)
_NON_ALNUM_RE = re.compile(r"[^a-z0-9_çğıöşü]+")
_COMMON_SUFFIXES = (
    "larimizdan",
    "lerimizdan",
    "larimiz",
    "lerimiz",
    "larindan",
    "lerinden",
    "larinda",
    "lerinde",
    "lari",
    "leri",
    "larin",
    "lerin",
    "imiz",
    "iniz",
    "umuz",
    "unuz",
    "ndan",
    "nden",
    "daki",
    "deki",
    "taki",
    "teki",
    "dan",
    "den",
    "tan",
    "ten",
    "lar",
    "ler",
    "miz",
    "niz",
    "sin",
    "nin",
    "da",
    "de",
    "ta",
    "te",
    "si",
    "su",
    "yi",
    "yu",
    "ya",
    "ye",
    "in",
    "un",
    "im",
    "um",
)

# Cross-lingual and domain hints mapping Turkish stems -> schema tokens (and vice versa).
_DEFAULT_SYNONYMS: dict[str, tuple[str, ...]] = {
    "bayi": ("dealer", "dealers", "sube", "magaza"),
    "sube": ("branch", "dealer", "dealers", "bayi", "magaza"),
    "magaza": ("store", "branch", "dealer", "sube"),
    "satis": ("sale", "sales", "ciro", "hasilat", "tutar", "total_amount", "amt"),
    "ciro": ("sale", "sales", "hasilat", "revenue", "total_amount", "net_sales", "amt"),
    "hasilat": ("sale", "sales", "ciro", "revenue", "total_amount", "amt"),
    "sehir": ("city", "il", "lokasyon"),
    "lokasyon": ("city", "region", "bolge", "sehir"),
    "musteri": ("customer", "customers", "cust", "client", "musteriler"),
    "siparis": ("order", "orders", "siparisler", "kalem", "kalemler"),
    "urun": ("product", "products", "urunler", "item"),
    "kategori": ("category", "categories", "kategoriler"),
    "fatura": ("invoice", "invoices", "inv", "faturalar"),
    "odeme": ("payment", "payments", "odemeler"),
    "iade": ("return", "returns", "ret", "iadeler", "return_amount", "ret_qty"),
    "tutar": ("amount", "amt", "total", "total_amount", "inv_amt", "fiyat"),
    "miktar": ("quantity", "qty", "adet", "ret_qty", "sayisi"),
    "adet": ("quantity", "qty", "miktar", "count", "ret_qty"),
    "calisan": ("employee", "employees", "staff", "personel", "calisanlar"),
    "maas": ("salary", "salaries", "maaslar", "ucret"),
    "depo": ("warehouse", "warehouses", "depolar", "stok"),
    "stok": ("stock", "inventory", "inv", "stok_hareketleri", "inv_ledger"),
    "bolge": ("region", "regions", "bolgeler", "area"),
    "tedarikci": ("supplier", "suppliers", "vendor", "tedarikciler"),
    "sevkiyat": ("shipment", "shipments", "delivery", "sevkiyatlar"),
    "kampanya": ("campaign", "campaigns", "kampanyalar"),
    "masraf": ("expense", "expenses", "cost", "masraflar"),
    "destek": ("support", "ticket", "tickets", "destek_talepleri"),
    "sadakat": ("loyalty", "cust_loyalty", "puan"),
    "defter": ("ledger", "inv_ledger", "kayit"),
    "__location__": ("city", "sehir", "il", "region", "bolge"),
}


@runtime_checkable
class EmbeddingPort(Protocol):
    """Duck-typed dense embedding interface (compatible with ``core.ports.EmbeddingAdapter``)."""

    def embed(self, texts: list[str]) -> list[list[float]]: ...


@dataclass(frozen=True)
class BidirectionalLinkResult:
    """Comparison and reconciliation output of bidirectional schema linking."""

    pruned: LinkedSchema
    full: LinkedSchema
    merged: LinkedSchema
    added_tables: tuple[str, ...]
    dropped_tables: tuple[str, ...]
    agreement: float

    @property
    def tables(self) -> tuple[str, ...]:
        return self.merged.tables

    @property
    def links(self) -> tuple[SchemaLink, ...]:
        return self.merged.links

    @property
    def join_path(self) -> tuple[JoinStep, ...]:
        return self.merged.join_path


def _tr_fold(text: str) -> str:
    return unicodedata.normalize("NFC", text).translate(_TR_UPPER_MAP).lower()


def _ascii_fold(text: str) -> str:
    return _tr_fold(text).translate(_TR_TO_ASCII_MAP)


def _stem_ascii(token: str) -> str:
    tok = _ascii_fold(token).split("'", 1)[0]
    tok = _NON_ALNUM_RE.sub("", tok)
    if len(tok) <= 3:
        return tok
    for suf in _COMMON_SUFFIXES:
        if tok.endswith(suf) and len(tok) - len(suf) >= 3:
            return tok[: -len(suf)]
    return tok


def _tokenize_identifier(name: str) -> list[str]:
    parts = [p for p in _NON_ALNUM_RE.split(_ascii_fold(name).replace("_", " ")) if p]
    tokens: list[str] = []
    for part in parts:
        tokens.append(part)
        stemmed = _stem_ascii(part)
        if stemmed and stemmed != part:
            tokens.append(stemmed)
    return tokens


def _char_ngrams(text: str, n: int = 3) -> set[str]:
    cleaned = _ascii_fold(text)
    cleaned = re.sub(r"[^a-z0-9]", "", cleaned)
    if not cleaned:
        return set()
    if len(cleaned) < n:
        return {cleaned}
    return {cleaned[i : i + n] for i in range(len(cleaned) - n + 1)}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    union = len(a | b)
    return len(a & b) / union if union else 0.0


def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    dot = sum(x * y for x, y in zip(vec_a, vec_b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in vec_a))
    norm_b = math.sqrt(sum(y * y for y in vec_b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    sim = dot / (norm_a * norm_b)
    return max(0.0, min(1.0, sim))


def _repair_tables_and_joins(
    ranked_tables: list[str],
    schema: SchemaSnapshot,
    graph: SchemaGraph,
) -> tuple[tuple[str, ...], tuple[JoinStep, ...]]:
    """Connect ranked tables via Steiner FK paths and append intermediate bridge tables."""
    if not ranked_tables:
        return (), ()

    canonical = {t.name.lower(): t.name for t in schema.tables}
    valid_lower = [t.lower() for t in ranked_tables if t.lower() in canonical]
    if not valid_lower:
        return (), ()

    full_steps = graph.connect(tuple(valid_lower))
    if full_steps is None:
        # Connect the maximal subset reachable from the highest-scoring anchor table.
        anchor = valid_lower[0]
        reachable = [anchor]
        steps_acc: list[JoinStep] = []
        tree = {anchor}
        for tbl in valid_lower[1:]:
            if tbl in tree:
                reachable.append(tbl)
                continue
            best: tuple[JoinStep, ...] | None = None
            for node in sorted(tree):
                path = graph.shortest_path(node, tbl)
                if path is not None and (best is None or len(path) < len(best)):
                    best = path
            if best is not None:
                reachable.append(tbl)
                for step in best:
                    if step.right_table not in tree:
                        steps_acc.append(step)
                        tree.add(step.right_table)
        full_steps = tuple(steps_acc)
        valid_lower = reachable

    ordered_lower: dict[str, None] = dict.fromkeys(valid_lower)
    for step in full_steps:
        ordered_lower[step.left_table.lower()] = None
        ordered_lower[step.right_table.lower()] = None

    tables_out = tuple(canonical[t] for t in ordered_lower if t in canonical)
    return tables_out, full_steps


class HybridSchemaLinker:
    """Hybrid Turkish-aware schema linker (AR-03).

    Combines:
      1. Curated lexicon matches (strictly scoped to ``SchemaSnapshot``).
      2. Morphological stem + ASCII-folded lexical matching + bilingual hints.
      3. Character n-gram Jaccard fuzzy similarity.
      4. Optional dense embeddings via any duck-typed ``EmbeddingPort``.
      5. Multi-hop FK Steiner join repair via :class:`SchemaGraph`.
      6. Optional RSL-SQL-inspired bidirectional linking (``link_bidirectional``).
    """

    def __init__(
        self,
        lexicon: Mapping[str, str] | None = None,
        *,
        embedder: EmbeddingPort | None = None,
        synonyms: Mapping[str, tuple[str, ...]] | None = None,
        min_score: float = 0.28,
        top_k_tables: int = 6,
        embed_weight: float = 0.35,
        bidirectional: bool = False,
    ) -> None:
        self._lexicon = {_tr_fold(k): v for k, v in (lexicon or {}).items()}
        self._embedder = embedder
        merged_syns: dict[str, tuple[str, ...]] = dict(_DEFAULT_SYNONYMS)
        if synonyms:
            for key, vals in synonyms.items():
                merged_syns[_ascii_fold(key)] = tuple(_ascii_fold(v) for v in vals)
        self._synonyms = merged_syns
        self._min_score = min_score
        self._top_k_tables = max(1, top_k_tables)
        self._embed_weight = max(0.0, min(1.0, embed_weight))
        self._bidirectional = bidirectional

    def link(self, question: ParsedQuestion, schema: SchemaSnapshot) -> LinkedSchema:
        """Link a parsed Turkish question against the RBAC-scoped ``schema``."""
        if self._bidirectional:
            return self.link_bidirectional(question, schema).merged
        return self._link_with_params(
            question,
            schema,
            min_score=self._min_score,
            max_tables=self._top_k_tables,
            expand_neighbors=False,
        )

    def link_bidirectional(
        self,
        question: ParsedQuestion,
        schema: SchemaSnapshot,
    ) -> BidirectionalLinkResult:
        """Compare pruned (high-precision) vs full (high-recall) schema candidates
        and return a reconciled :class:`LinkedSchema`."""
        pruned = self._link_with_params(
            question,
            schema,
            min_score=max(self._min_score, 0.45),
            max_tables=min(self._top_k_tables, 4),
            expand_neighbors=False,
        )
        full = self._link_with_params(
            question,
            schema,
            min_score=min(self._min_score, 0.22),
            max_tables=max(self._top_k_tables, len(schema.tables)),
            expand_neighbors=True,
        )

        best_links: dict[tuple[str, str | None], SchemaLink] = {}
        for lnk in (*pruned.links, *full.links):
            key = (lnk.table.lower(), lnk.column.lower() if lnk.column else None)
            prev = best_links.get(key)
            if prev is None or lnk.score > prev.score:
                best_links[key] = lnk

        sorted_links = tuple(sorted(best_links.values(), key=lambda x: x.score, reverse=True))
        merged_seed_tables = list(dict.fromkeys([*pruned.tables, *full.tables]))
        graph = SchemaGraph(schema)
        merged_tables, merged_joins = _repair_tables_and_joins(merged_seed_tables, schema, graph)
        merged = LinkedSchema(tables=merged_tables, links=sorted_links, join_path=merged_joins)

        pruned_set = {t.lower() for t in pruned.tables}
        full_set = {t.lower() for t in full.tables}
        merged_set = {t.lower() for t in merged.tables}
        added = tuple(t for t in merged.tables if t.lower() not in pruned_set)
        dropped = tuple(t for t in pruned.tables if t.lower() not in full_set)
        union = len(pruned_set | merged_set)
        agreement = len(pruned_set & merged_set) / union if union else 1.0

        return BidirectionalLinkResult(
            pruned=pruned,
            full=full,
            merged=merged,
            added_tables=added,
            dropped_tables=dropped,
            agreement=round(agreement, 4),
        )

    def _link_with_params(
        self,
        question: ParsedQuestion,
        schema: SchemaSnapshot,
        *,
        min_score: float,
        max_tables: int,
        expand_neighbors: bool,
    ) -> LinkedSchema:
        if not schema.tables:
            return LinkedSchema(tables=(), links=(), join_path=())

        query_terms = self._extract_query_terms(question)
        dense_scores = self._compute_dense_scores(question, schema)

        # Track highest link per (table_lower, column_lower | None)
        best_links: dict[tuple[str, str | None], SchemaLink] = {}

        def _record(mention: str, table_name: str, column_name: str | None, score: float) -> None:
            clamped = round(max(0.0, min(1.0, score)), 4)
            if clamped < min_score:
                return
            key = (table_name.lower(), column_name.lower() if column_name else None)
            prev = best_links.get(key)
            if prev is None or clamped > prev.score:
                best_links[key] = SchemaLink(
                    mention=mention,
                    table=table_name,
                    column=column_name,
                    score=clamped,
                )

        # 1. Lexicon links (strictly verified against scoped SchemaSnapshot)
        for mention in question.mentions:
            keys_to_check = [
                _tr_fold(mention.lemma or mention.text),
                _tr_fold(mention.text),
                _stem_ascii(mention.text),
            ]
            if mention.kind is MentionKind.LOCATION:
                keys_to_check.insert(0, "__location__")
            for k in keys_to_check:
                target = self._lexicon.get(k)
                if target is None:
                    continue
                tbl_name, _, col_name = target.partition(".")
                info = schema.table(tbl_name)
                if info is None:
                    continue
                resolved_col: str | None = None
                if col_name:
                    col_obj = info.column(col_name)
                    if col_obj is None:
                        continue
                    resolved_col = col_obj.name
                _record(mention.text, info.name, resolved_col, 1.0)

        for raw_tok, stem_tok in query_terms:
            for k in (raw_tok, stem_tok):
                target = self._lexicon.get(k)
                if target is None:
                    continue
                tbl_name, _, col_name = target.partition(".")
                info = schema.table(tbl_name)
                if info is None:
                    continue
                resolved_col = None
                if col_name:
                    col_obj = info.column(col_name)
                    if col_obj is None:
                        continue
                    resolved_col = col_obj.name
                _record(raw_tok, info.name, resolved_col, 0.95)

        # 2. Lexical + morphological + n-gram fuzzy + dense scoring across scoped schema
        for table in schema.tables:
            t_low = table.name.lower()
            t_tokens = _tokenize_identifier(table.name)
            if table.description:
                t_tokens.extend(_tokenize_identifier(table.description))
            t_mention, t_lex_score = self._score_target(query_terms, t_tokens, table.name)
            t_dense = dense_scores.get((t_low, None), 0.0)
            t_score = self._fuse_score(t_lex_score, t_dense)
            if t_score >= min_score:
                _record(t_mention or table.name, table.name, None, t_score)

            for col in table.columns:
                c_low = col.name.lower()
                c_tokens = _tokenize_identifier(col.name)
                if col.description:
                    c_tokens.extend(_tokenize_identifier(col.description))
                c_mention, c_lex_score = self._score_target(query_terms, c_tokens, col.name)
                c_dense = dense_scores.get((t_low, c_low), 0.0)
                c_score = self._fuse_score(c_lex_score, c_dense)
                if c_score >= min_score:
                    _record(c_mention or col.name, table.name, col.name, c_score)

        # Rank tables by max link score + count of distinct matched columns
        table_agg: dict[str, float] = {}
        for lnk in best_links.values():
            t_low = lnk.table.lower()
            cur = table_agg.get(t_low, 0.0)
            bonus = 0.05 if lnk.column is not None else 0.0
            table_agg[t_low] = max(cur, lnk.score) + bonus

        sorted_table_lows = sorted(table_agg, key=lambda t: table_agg[t], reverse=True)
        selected_lows = sorted_table_lows[:max_tables]

        canonical = {t.name.lower(): t.name for t in schema.tables}
        graph = SchemaGraph(schema)
        if expand_neighbors and selected_lows:
            # In full-recall mode, inspect 1-hop FK neighbors for mild secondary support
            neighbors = graph.neighborhood(selected_lows, hops=1)
            for nb in neighbors:
                if nb not in selected_lows:
                    selected_lows.append(nb)

        seed_names = [canonical[t] for t in selected_lows if t in canonical]
        tables_out, join_path = _repair_tables_and_joins(seed_names, schema, graph)

        kept_table_set = {t.lower() for t in tables_out}
        kept_links = tuple(
            sorted(
                (lnk for lnk in best_links.values() if lnk.table.lower() in kept_table_set),
                key=lambda x: x.score,
                reverse=True,
            )
        )
        return LinkedSchema(tables=tables_out, links=kept_links, join_path=join_path)

    def _extract_query_terms(self, question: ParsedQuestion) -> list[tuple[str, str]]:
        terms: list[tuple[str, str]] = []
        seen: set[str] = set()
        for m in question.mentions:
            raw = _ascii_fold(m.lemma or m.text)
            stem = _stem_ascii(m.lemma or m.text)
            key = f"{raw}|{stem}"
            if key not in seen:
                seen.add(key)
                terms.append((raw, stem))
            if m.kind is MentionKind.LOCATION and "__location__|__location__" not in seen:
                seen.add("__location__|__location__")
                terms.append(("__location__", "__location__"))

        for tok in _NON_ALNUM_RE.split(_ascii_fold(question.normalized_text)):
            if len(tok) < 2:
                continue
            stem = _stem_ascii(tok)
            key = f"{tok}|{stem}"
            if key not in seen:
                seen.add(key)
                terms.append((tok, stem))
        return terms

    def _score_target(
        self,
        query_terms: list[tuple[str, str]],
        target_tokens: list[str],
        raw_target: str,
    ) -> tuple[str, float]:
        target_set = set(target_tokens)
        target_ascii = _ascii_fold(raw_target)
        target_grams = _char_ngrams(target_ascii)
        target_token_grams = [(tok, _char_ngrams(tok)) for tok in target_tokens]

        best_score = 0.0
        best_mention = ""

        for raw_tok, stem_tok in query_terms:
            # 1. Exact identifier / token stem match
            if raw_tok == target_ascii or stem_tok == target_ascii:
                score = 0.92
            elif raw_tok in target_set or stem_tok in target_set:
                score = 0.88
            else:
                score = 0.0

            # 2. Synonym / cross-lingual expansion match
            syns = self._synonyms.get(stem_tok) or self._synonyms.get(raw_tok) or ()
            for syn in syns:
                if syn == target_ascii or syn in target_set:
                    score = max(score, 0.82)
                    break
                syn_grams = _char_ngrams(syn)
                for tok, t_grams in target_token_grams:
                    if len(syn) >= 3 and (tok.startswith(syn) or syn.startswith(tok)):
                        score = max(score, 0.72)
                    else:
                        j = _jaccard(syn_grams, t_grams)
                        if j >= 0.45:
                            score = max(score, 0.65 * j + 0.15)

            # 3. Prefix & character n-gram Jaccard fuzzy similarity
            if len(stem_tok) >= 3:
                q_grams = _char_ngrams(stem_tok)
                full_j = _jaccard(q_grams, target_grams)
                if full_j > 0.0:
                    score = max(score, full_j * 0.85)
                for tok, t_grams in target_token_grams:
                    if len(tok) >= 3 and (tok.startswith(stem_tok) or stem_tok.startswith(tok)):
                        overlap = min(len(tok), len(stem_tok)) / max(len(tok), len(stem_tok))
                        score = max(score, 0.55 + 0.30 * overlap)
                    else:
                        j = _jaccard(q_grams, t_grams)
                        if j >= 0.35:
                            score = max(score, j * 0.82)

            if score > best_score:
                best_score = score
                best_mention = raw_tok

        return best_mention, best_score

    def _compute_dense_scores(
        self,
        question: ParsedQuestion,
        schema: SchemaSnapshot,
    ) -> dict[tuple[str, str | None], float]:
        if self._embedder is None:
            return {}
        items: list[tuple[str, str | None, str]] = []
        for table in schema.tables:
            t_low = table.name.lower()
            t_desc = f"table {table.name} {table.description or ''}".strip()
            items.append((t_low, None, t_desc))
            for col in table.columns:
                c_desc = f"column {table.name}.{col.name} {col.data_type} {col.description or ''}".strip()
                items.append((t_low, col.name.lower(), c_desc))

        if not items:
            return {}
        texts = [question.normalized_text or question.original_text, *(txt for _, _, txt in items)]
        vectors = self._embedder.embed(texts)
        if len(vectors) != len(texts):
            return {}
        q_vec = vectors[0]
        scores: dict[tuple[str, str | None], float] = {}
        for (t_low, c_low, _), vec in zip(items, vectors[1:], strict=True):
            scores[(t_low, c_low)] = _cosine_similarity(q_vec, vec)
        return scores

    def _fuse_score(self, lexical: float, dense: float) -> float:
        if self._embedder is None:
            return lexical
        w = self._embed_weight
        blended = (1.0 - w) * lexical + w * dense
        # Preserve strong exact lexical or strong dense signal without diluting hits
        return max(blended, lexical * 0.9, dense * 0.85)
