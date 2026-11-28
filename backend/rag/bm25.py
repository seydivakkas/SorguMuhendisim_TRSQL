"""Pure-Python Okapi BM25 retriever + DAIL-SQL masked SQL skeleton similarity."""

from __future__ import annotations

import itertools
import math
import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

from backend.core.contracts import (
    BusinessRule,
    Dialect,
    FewShotExample,
    Intent,
    ParsedQuestion,
    SchemaSnapshot,
)
from backend.knowledge_base import (
    InMemoryKnowledgeBase,
    MetadataEntry,
    fold_turkish_diacritics,
    tr_casefold,
)
from backend.rag.values import turkish_lemma_candidates

_TOKEN_RE = re.compile(r"[0-9a-zçğıöşüâîû_]+")

_SQL_TOKEN_RE = re.compile(
    r"--[^\n]*"
    r"|/\*[\s\S]*?\*/"
    r"|'(?:''|[^'])*'"
    r'|"(?:""|[^"])*"'
    r"|`[^`]*`"
    r"|<>|!=|<=|>=|\|\|"
    r"|\d+(?:\.\d+)?(?:[eE][+-]?\d+)?"
    r"|[A-Za-z_][A-Za-z0-9_]*"
    r"|[^\s]"
)

_SQL_KEYWORDS: frozenset[str] = frozenset(
    {
        "SELECT",
        "DISTINCT",
        "FROM",
        "WHERE",
        "JOIN",
        "INNER",
        "LEFT",
        "RIGHT",
        "FULL",
        "OUTER",
        "CROSS",
        "ON",
        "AS",
        "AND",
        "OR",
        "NOT",
        "IN",
        "IS",
        "NULL",
        "BETWEEN",
        "LIKE",
        "ILIKE",
        "EXISTS",
        "CASE",
        "WHEN",
        "THEN",
        "ELSE",
        "END",
        "GROUP",
        "BY",
        "HAVING",
        "ORDER",
        "ASC",
        "DESC",
        "LIMIT",
        "OFFSET",
        "UNION",
        "ALL",
        "INTERSECT",
        "EXCEPT",
        "WITH",
        "CAST",
        "COALESCE",
        "NULLIF",
        "COUNT",
        "SUM",
        "AVG",
        "MIN",
        "MAX",
        "ROUND",
        "EXTRACT",
        "DATE_TRUNC",
        "DATE",
        "INTERVAL",
        "CURRENT_DATE",
        "NOW",
        "OVER",
        "PARTITION",
        "ROW_NUMBER",
        "RANK",
        "DENSE_RANK",
        "TRUE",
        "FALSE",
    }
)

_CLAUSE_BREAKS: frozenset[str] = frozenset(
    {
        "WHERE",
        "ON",
        "JOIN",
        "INNER",
        "LEFT",
        "RIGHT",
        "FULL",
        "OUTER",
        "CROSS",
        "GROUP",
        "ORDER",
        "HAVING",
        "LIMIT",
        "OFFSET",
        "UNION",
        "INTERSECT",
        "EXCEPT",
        "SET",
    }
)


@dataclass(frozen=True)
class SchemaElement:
    """Searchable table or column metadata derived from a scoped ``SchemaSnapshot``."""

    table: str
    column: str | None = None
    description: str = ""
    data_type: str | None = None

    @property
    def qualified_name(self) -> str:
        return f"{self.table}.{self.column}" if self.column else self.table

    def to_search_text(self) -> str:
        parts = [self.table.replace("_", " ")]
        if self.column:
            parts.append(self.column.replace("_", " "))
        if self.data_type:
            parts.append(self.data_type)
        if self.description:
            parts.append(self.description)
        return " ".join(parts)


def schema_elements_from_snapshot(schema: SchemaSnapshot) -> tuple[SchemaElement, ...]:
    """Flatten tables and columns of a scoped ``SchemaSnapshot`` into ``SchemaElement``s."""
    elements: list[SchemaElement] = []
    for table in schema.tables:
        elements.append(
            SchemaElement(
                table=table.name,
                column=None,
                description=table.description or "",
            )
        )
        for col in table.columns:
            elements.append(
                SchemaElement(
                    table=table.name,
                    column=col.name,
                    description=col.description or "",
                    data_type=col.data_type,
                )
            )
    return tuple(elements)


def tokenize_turkish(text: str) -> list[str]:
    """Tokenize Turkish text into normalized forms, lemma stems, and ASCII-folded stems."""
    folded = tr_casefold(text)
    tokens: list[str] = []
    for match in _TOKEN_RE.finditer(folded):
        raw = match.group(0)
        tokens.append(raw)
        cands = turkish_lemma_candidates(raw)
        if cands:
            stem = cands[-1]
            if stem != raw:
                tokens.append(stem)
        ascii_raw = fold_turkish_diacritics(raw)
        if ascii_raw != raw:
            tokens.append(ascii_raw)
    return tokens


def mask_sql_literals_and_identifiers(sql: str) -> str:
    """Produce a DAIL-SQL style masked SQL skeleton.

    Replaces string literals with ``<VAL>``, numeric literals with ``<NUM>``,
    table names after ``FROM``/``JOIN`` with ``<TAB>`` (omitting bare table
    aliases), and column/alias identifiers with ``<COL>`` / ``<ALIAS>`` while
    preserving SQL keywords, functions, and operators.
    """
    raw_tokens = [
        tok for tok in _SQL_TOKEN_RE.findall(sql) if not tok.startswith("--") and not tok.startswith("/*")
    ]
    out: list[str] = []
    expect_table = False
    just_emitted_table = False
    expect_alias = False
    i = 0

    while i < len(raw_tokens):
        tok = raw_tokens[i]
        upper = tok.upper()

        if tok.startswith("'") and tok.endswith("'"):
            out.append("<VAL>")
            expect_alias = False
            just_emitted_table = False
            i += 1
            continue

        if re.fullmatch(r"\d+(?:\.\d+)?(?:[eE][+-]?\d+)?", tok):
            out.append("<NUM>")
            expect_alias = False
            just_emitted_table = False
            i += 1
            continue

        is_ident = (
            (tok.startswith('"') and tok.endswith('"'))
            or (tok.startswith("`") and tok.endswith("`"))
            or (bool(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", tok)) and upper not in _SQL_KEYWORDS)
        )

        if not is_ident and upper in _SQL_KEYWORDS:
            out.append(upper)
            if upper in ("FROM", "JOIN"):
                expect_table = True
                just_emitted_table = False
                expect_alias = False
            elif upper == "AS":
                expect_alias = True
            elif upper in _CLAUSE_BREAKS:
                expect_table = False
                just_emitted_table = False
                expect_alias = False
            else:
                just_emitted_table = False
                expect_alias = False
            i += 1
            continue

        if is_ident:
            # Collapse qualified `alias.column` or `schema.table.column`
            j = i
            while j + 2 < len(raw_tokens) and raw_tokens[j + 1] == ".":
                j += 2
            if expect_alias:
                if not expect_table:
                    out.append("<ALIAS>")
                expect_alias = False
                just_emitted_table = False
                i = j + 1
                continue
            if expect_table:
                out.append("<TAB>")
                expect_table = False
                just_emitted_table = True
                i = j + 1
                continue
            if just_emitted_table:
                # Skip implicit table alias (`FROM dealers d`)
                just_emitted_table = False
                i = j + 1
                continue
            out.append("<COL>")
            i = j + 1
            continue

        if tok == "," and just_emitted_table:
            expect_table = True
            just_emitted_table = False
        elif tok in ("(", ")", ";"):
            expect_table = False
            just_emitted_table = False
            expect_alias = False
        out.append(tok)
        i += 1

    return " ".join(out)


def infer_question_skeleton(question: ParsedQuestion) -> str:
    """Infer an approximate SQL skeleton from structured ``ParsedQuestion`` signals."""
    tokens: list[str] = ["SELECT"]
    if question.intent is Intent.COUNT:
        tokens.extend(["COUNT", "(", "*", ")"])
    elif question.intent in (Intent.AGGREGATE, Intent.RANKING, Intent.COMPARISON, Intent.TREND):
        tokens.extend(["<COL>", ",", "SUM", "(", "<COL>", ")", "AS", "<ALIAS>"])
    else:
        tokens.append("<COL>")

    tokens.extend(["FROM", "<TAB>"])
    if question.temporal or question.mentions:
        tokens.extend(["WHERE", "<COL>", "=", "<VAL>"])
    if question.temporal:
        tokens.extend(["AND", "<COL>", ">=", "<VAL>", "AND", "<COL>", "<", "<VAL>"])
    if question.intent in (Intent.RANKING, Intent.COMPARISON, Intent.TREND):
        tokens.extend(["GROUP", "BY", "<COL>"])
    if question.sort is not None or question.intent is Intent.RANKING:
        direction = question.sort.value.upper() if question.sort is not None else "DESC"
        tokens.extend(["ORDER", "BY", "<COL>", direction])
    if question.limit is not None:
        tokens.extend(["LIMIT", "<NUM>"])
    return " ".join(tokens)


def skeleton_similarity(
    sql_or_skeleton_a: str,
    sql_or_skeleton_b: str,
    *,
    already_masked: bool = False,
) -> float:
    """Compute DAIL-SQL structural similarity in ``[0.0, 1.0]`` over masked skeletons."""
    skel_a = sql_or_skeleton_a if already_masked else mask_sql_literals_and_identifiers(sql_or_skeleton_a)
    skel_b = sql_or_skeleton_b if already_masked else mask_sql_literals_and_identifiers(sql_or_skeleton_b)
    toks_a = skel_a.split()
    toks_b = skel_b.split()
    if not toks_a or not toks_b:
        return 0.0

    set_a, set_b = set(toks_a), set(toks_b)
    unigram_jaccard = len(set_a & set_b) / len(set_a | set_b)

    bigrams_a = set(itertools.pairwise(toks_a))
    bigrams_b = set(itertools.pairwise(toks_b))
    if bigrams_a and bigrams_b:
        bigram_dice = (2.0 * len(bigrams_a & bigrams_b)) / (len(bigrams_a) + len(bigrams_b))
    else:
        bigram_dice = unigram_jaccard
    return round(0.4 * unigram_jaccard + 0.6 * bigram_dice, 6)


class OkapiBM25:
    """Pure-Python Okapi BM25 scorer with non-negative Lucene IDF."""

    def __init__(self, documents: Sequence[str], *, k1: float = 1.5, b: float = 0.75) -> None:
        self._k1 = k1
        self._b = b
        self._doc_freqs: list[Counter[str]] = []
        self._doc_lens: list[int] = []
        df: Counter[str] = Counter()

        for doc in documents:
            toks = tokenize_turkish(doc)
            tf = Counter(toks)
            self._doc_freqs.append(tf)
            self._doc_lens.append(len(toks))
            for term in tf:
                df[term] += 1

        self._n_docs = len(documents)
        self._avgdl = (sum(self._doc_lens) / self._n_docs) if self._n_docs else 0.0
        self._idf: dict[str, float] = {
            term: math.log(1.0 + (self._n_docs - freq + 0.5) / (freq + 0.5)) for term, freq in df.items()
        }

    def score(self, query: str) -> list[float]:
        """Return raw BM25 scores for every document in the corpus."""
        if self._n_docs == 0:
            return []
        q_terms = list(dict.fromkeys(tokenize_turkish(query)))
        if not q_terms or self._avgdl == 0.0:
            return [0.0] * self._n_docs

        scores: list[float] = []
        for tf, dl in zip(self._doc_freqs, self._doc_lens, strict=True):
            total = 0.0
            norm = 1.0 - self._b + self._b * (dl / self._avgdl)
            for term in q_terms:
                freq = tf.get(term, 0)
                if freq == 0:
                    continue
                idf = self._idf.get(term, 0.0)
                total += idf * (freq * (self._k1 + 1.0)) / (freq + self._k1 * norm)
            scores.append(total)
        return scores


class BM25Retriever:
    """Okapi BM25 retriever across rules, schema elements, masked SQL examples, and metadata."""

    def __init__(
        self,
        kb: InMemoryKnowledgeBase,
        *,
        schema: SchemaSnapshot | None = None,
        k_rules: int = 5,
        k_examples: int = 3,
        k_schema: int = 8,
        k_metadata: int = 5,
        skeleton_weight: float = 0.35,
    ) -> None:
        self._kb = kb
        self._schema = schema
        self._k_rules = k_rules
        self._k_examples = k_examples
        self._k_schema = k_schema
        self._k_metadata = k_metadata
        self._skeleton_weight = skeleton_weight

        self._approved_rules = kb.approved_rules()
        self._rules_bm25 = OkapiBM25(
            [f"{r.term} {r.definition} {r.sql_fragment or ''}" for r in self._approved_rules]
        )

        self._examples = kb.examples
        self._examples_bm25 = OkapiBM25([ex.question for ex in self._examples])
        self._example_skeletons = tuple(mask_sql_literals_and_identifiers(ex.sql) for ex in self._examples)

        self._metadata = kb.approved_metadata()
        self._metadata_bm25 = OkapiBM25(
            [
                " ".join(
                    [
                        m.table,
                        m.column,
                        m.description,
                        m.unit or "",
                        *m.synonyms,
                        *(f"{k} {v}" for k, v in m.code_values),
                    ]
                )
                for m in self._metadata
            ]
        )

        self._schema_elements: tuple[SchemaElement, ...] = ()
        self._schema_bm25: OkapiBM25 | None = None
        if schema is not None:
            self._schema_elements = schema_elements_from_snapshot(schema)
            self._schema_bm25 = OkapiBM25([e.to_search_text() for e in self._schema_elements])

    def _query_text(self, question: ParsedQuestion) -> str:
        mention_text = " ".join(m.lemma or m.text for m in question.mentions)
        return f"{question.original_text} {question.normalized_text} {mention_text}".strip()

    def score_rules(self, question: ParsedQuestion) -> list[tuple[BusinessRule, float]]:
        """Score approved business rules only (``approved=True``)."""
        if not self._approved_rules:
            return []
        raw_scores = self._rules_bm25.score(self._query_text(question))
        scored = [
            (rule, score) for rule, score in zip(self._approved_rules, raw_scores, strict=True) if score > 0.0
        ]
        scored.sort(key=lambda item: (-item[1], item[0].rule_id))
        return scored

    def rules(self, question: ParsedQuestion, *, top_k: int | None = None) -> tuple[BusinessRule, ...]:
        limit = self._k_rules if top_k is None else top_k
        if limit <= 0:
            return ()
        return tuple(rule for rule, _ in self.score_rules(question)[:limit])

    def score_examples(
        self,
        question: ParsedQuestion,
        *,
        candidate_sql: str | None = None,
        dialect: Dialect | None = None,
    ) -> list[tuple[FewShotExample, float]]:
        """Score few-shot examples using question BM25 + DAIL-SQL masked skeleton similarity."""
        if not self._examples:
            return []
        q_scores = self._examples_bm25.score(self._query_text(question))
        max_q = max(q_scores, default=0.0)
        query_skel = (
            mask_sql_literals_and_identifiers(candidate_sql)
            if candidate_sql is not None
            else infer_question_skeleton(question)
        )
        skel_w = 0.65 if candidate_sql is not None else self._skeleton_weight
        text_w = 1.0 - skel_w

        scored: list[tuple[FewShotExample, float]] = []
        for idx, (ex, q_raw, ex_skel) in enumerate(
            zip(self._examples, q_scores, self._example_skeletons, strict=True)
        ):
            if dialect is not None and ex.dialect is not dialect:
                continue
            q_norm = (q_raw / max_q) if max_q > 0.0 else 0.0
            skel_sim = skeleton_similarity(query_skel, ex_skel, already_masked=True)
            if candidate_sql is None and q_raw <= 0.0:
                continue
            combined = text_w * q_norm + skel_w * skel_sim
            if combined > 0.0:
                scored.append((ex, round(combined, 6)))
            elif idx >= 0 and candidate_sql is not None and skel_sim > 0.0:
                scored.append((ex, round(skel_sim, 6)))

        scored.sort(key=lambda item: (-item[1], item[0].question))
        return scored

    def examples(
        self,
        question: ParsedQuestion,
        *,
        candidate_sql: str | None = None,
        dialect: Dialect | None = None,
        top_k: int | None = None,
    ) -> tuple[FewShotExample, ...]:
        limit = self._k_examples if top_k is None else top_k
        if limit <= 0:
            return ()
        return tuple(
            ex
            for ex, _ in self.score_examples(question, candidate_sql=candidate_sql, dialect=dialect)[:limit]
        )

    def score_schema_elements(
        self,
        question: ParsedQuestion,
        *,
        schema: SchemaSnapshot | None = None,
    ) -> list[tuple[SchemaElement, float]]:
        """Score table/column elements from the scoped ``SchemaSnapshot``."""
        if schema is not None:
            elements = schema_elements_from_snapshot(schema)
            bm25 = OkapiBM25([e.to_search_text() for e in elements])
        elif self._schema_bm25 is not None:
            elements = self._schema_elements
            bm25 = self._schema_bm25
        else:
            return []

        if not elements:
            return []
        raw_scores = bm25.score(self._query_text(question))
        scored = [(elem, score) for elem, score in zip(elements, raw_scores, strict=True) if score > 0.0]
        scored.sort(key=lambda item: (-item[1], item[0].qualified_name))
        return scored

    def schema_elements(
        self,
        question: ParsedQuestion,
        *,
        schema: SchemaSnapshot | None = None,
        top_k: int | None = None,
    ) -> tuple[SchemaElement, ...]:
        limit = self._k_schema if top_k is None else top_k
        if limit <= 0:
            return ()
        return tuple(elem for elem, _ in self.score_schema_elements(question, schema=schema)[:limit])

    def score_metadata(
        self,
        question: ParsedQuestion,
        *,
        allowed_tables: frozenset[str] | None = None,
    ) -> list[tuple[MetadataEntry, float]]:
        """Score approved code-lookup / unit metadata entries, respecting RBAC tables."""
        if not self._metadata:
            return []
        allowed = {t.lower() for t in allowed_tables} if allowed_tables is not None else None
        raw_scores = self._metadata_bm25.score(self._query_text(question))
        scored: list[tuple[MetadataEntry, float]] = []
        for entry, score in zip(self._metadata, raw_scores, strict=True):
            if score <= 0.0:
                continue
            if allowed is not None and entry.table.lower() not in allowed:
                continue
            scored.append((entry, score))
        scored.sort(key=lambda item: (-item[1], item[0].entry_id))
        return scored

    def metadata(
        self,
        question: ParsedQuestion,
        *,
        allowed_tables: frozenset[str] | None = None,
        top_k: int | None = None,
    ) -> tuple[MetadataEntry, ...]:
        limit = self._k_metadata if top_k is None else top_k
        if limit <= 0:
            return ()
        return tuple(
            entry for entry, _ in self.score_metadata(question, allowed_tables=allowed_tables)[:limit]
        )
