"""Configurable business-rule checks on validated SQL ASTs (L6)."""

from __future__ import annotations

import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

from backend.core.contracts import (
    CheckName,
    CheckResult,
    KnowledgeContext,
    SchemaSnapshot,
    Severity,
)

_TR_UPPER_MAP = str.maketrans({"I": "ı", "İ": "i"})

_RETURN_COLUMN_CANDIDATES = frozenset({"return_amount", "iade_tutari", "iade_tutar", "ret_amt"})
_RETURN_TABLE_CANDIDATES = frozenset({"iadeler", "iade_kalemleri", "returns", "return_items"})
_GROSS_COLUMN_CANDIDATES = frozenset({"total_amount", "brut_tutar", "toplam_tutar", "satis_tutari", "tutar"})
_STATUS_COLUMN_CANDIDATES = frozenset({"status", "durum"})
_ACTIVE_COLUMN_CANDIDATES = frozenset({"is_active", "aktif", "status", "durum", "last_purchase_date"})
_DUE_COLUMN_CANDIDATES = frozenset({"due_date", "vade_tarihi", "status", "durum"})


def _tr_casefold(text: str) -> str:
    return unicodedata.normalize("NFC", text).translate(_TR_UPPER_MAP).lower()


def _ok(message: str = "") -> CheckResult:
    return CheckResult(check=CheckName.BUSINESS_RULE, passed=True, message=message)


def _fail(message: str) -> CheckResult:
    return CheckResult(
        check=CheckName.BUSINESS_RULE,
        passed=False,
        severity=Severity.REPAIRABLE,
        message=message,
    )


@dataclass(frozen=True)
class BusinessRuleSpec:
    """Configurable declarative business rule checked against question/schema/SQL."""

    rule_id: str
    trigger_terms: tuple[str, ...]
    exclude_terms: tuple[str, ...] = ()
    require_return_deduction: bool = False
    require_filter_columns: tuple[str, ...] = ()
    message: str = ""


DEFAULT_BUSINESS_RULE_SPECS: tuple[BusinessRuleSpec, ...] = (
    BusinessRuleSpec(
        rule_id="net_revenue",
        trigger_terms=("net ciro", "net satış", "net satiş", "net hasılat", "net gelir", "net tutar"),
        exclude_terms=("brüt", "brut"),
        require_return_deduction=True,
        require_filter_columns=tuple(sorted(_STATUS_COLUMN_CANDIDATES)),
        message=(
            "İş kuralı ihlali: 'net ciro / net satış' sorgusunda "
            "iade düşümü ve geçerli durum filtresi gereklidir."
        ),
    ),
    BusinessRuleSpec(
        rule_id="active_customer",
        trigger_terms=("aktif müşteri", "aktif musteri"),
        require_filter_columns=tuple(sorted(_ACTIVE_COLUMN_CANDIDATES)),
        message=(
            "İş kuralı ihlali: 'aktif müşteri' sorgusunda aktiflik veya son işlem filtresi uygulanmalıdır."
        ),
    ),
    BusinessRuleSpec(
        rule_id="overdue_debt",
        trigger_terms=("vadesi geçmiş", "vadesi gecmis", "gecikmiş borç", "gecikmis borc"),
        require_filter_columns=tuple(sorted(_DUE_COLUMN_CANDIDATES)),
        message=(
            "İş kuralı ihlali: 'vadesi geçmiş' sorgusunda vade tarihi veya durum filtresi uygulanmalıdır."
        ),
    ),
)


def _queried_tables(tree: exp.Expression, schema: SchemaSnapshot) -> set[str]:
    cte_names = {cte.alias_or_name.lower() for cte in tree.find_all(exp.CTE)}
    tables: set[str] = set()
    for tbl in tree.find_all(exp.Table):
        name = tbl.name.lower()
        if not name or (name in cte_names and not tbl.db):
            continue
        if schema.table(name) is not None:
            tables.add(name)
    return tables


def _filter_columns(tree: exp.Expression) -> set[str]:
    """Return lower-case column names referenced inside WHERE or JOIN ON/USING predicates."""
    cols: set[str] = set()
    for where in tree.find_all(exp.Where):
        for col in where.find_all(exp.Column):
            if not isinstance(col.this, exp.Star):
                cols.add(col.name.lower())
    for join in tree.find_all(exp.Join):
        on = join.args.get("on")
        if isinstance(on, exp.Expression):
            for col in on.find_all(exp.Column):
                if not isinstance(col.this, exp.Star):
                    cols.add(col.name.lower())
        for u in join.args.get("using") or ():
            if isinstance(u, (exp.Identifier, exp.Column)):
                cols.add(u.name.lower())
    return cols


def _all_columns(tree: exp.Expression) -> set[str]:
    return {col.name.lower() for col in tree.find_all(exp.Column) if not isinstance(col.this, exp.Star)}


def _has_return_deduction(tree: exp.Expression, queried: set[str], schema: SchemaSnapshot) -> bool:
    all_cols = _all_columns(tree)
    has_ret_col = bool(all_cols & _RETURN_COLUMN_CANDIDATES)
    has_ret_table = bool(queried & _RETURN_TABLE_CANDIDATES)
    has_subtraction = any(tree.find_all(exp.Sub))
    if has_ret_col and has_subtraction:
        return True
    if has_ret_table and has_subtraction:
        return True
    # Also accept return column referenced inside CTE/subquery subtraction
    if has_ret_col and any(schema.table(t) and schema.table(t) is not None for t in queried):
        for sub in tree.find_all(exp.Sub):
            sub_cols = {c.name.lower() for c in sub.find_all(exp.Column)}
            if sub_cols & _RETURN_COLUMN_CANDIDATES:
                return True
    return False


def _table_has_any_column(schema: SchemaSnapshot, tables: set[str], candidates: Sequence[str]) -> list[str]:
    found: list[str] = []
    for tname in tables:
        info = schema.table(tname)
        if info is None:
            continue
        for cand in candidates:
            if info.column(cand) is not None and cand not in found:
                found.append(cand)
    return found


def _extract_fragment_columns(fragment: str, dialect_value: str) -> set[str]:
    try:
        parsed = sqlglot.parse_one(fragment, read=dialect_value)
    except ParseError:
        return set()
    return {c.name.lower() for c in parsed.find_all(exp.Column) if not isinstance(c.this, exp.Star)}


def _extract_fragment_tables(fragment: str, dialect_value: str) -> set[str]:
    try:
        parsed = sqlglot.parse_one(fragment, read=dialect_value)
    except ParseError:
        return set()
    tables: set[str] = set()
    for c in parsed.find_all(exp.Column):
        if c.table:
            tables.add(c.table.lower())
    for t in parsed.find_all(exp.Table):
        if t.name:
            tables.add(t.name.lower())
    return tables


def _question_mentions_cancellation(q_norm: str) -> bool:
    return any(tok in q_norm for tok in ("iptal", "cancelled", "canceled", "tüm durum", "tum durum"))


def _check_knowledge_metrics(
    tree: exp.Expression,
    schema: SchemaSnapshot,
    queried: set[str],
    filtered_cols: set[str],
    all_cols: set[str],
    knowledge: KnowledgeContext,
    q_norm: str | None,
) -> CheckResult | None:
    dialect_val = schema.dialect.value
    for metric in knowledge.metrics:
        base = metric.base_table.lower()
        if base not in queried:
            continue
        names = {_tr_casefold(metric.name), *(_tr_casefold(s) for s in metric.synonyms)}
        if q_norm is not None:
            if any(ex in q_norm for ex in ("brüt", "brut")):
                continue
            if not any(name in q_norm for name in names):
                continue

        # Check deduction expression if metric defines one (e.g., total_amount - return_amount)
        try:
            expr_ast = sqlglot.parse_one(metric.expression, read=dialect_val)
        except ParseError:
            expr_ast = None
        if expr_ast is not None and any(expr_ast.find_all(exp.Sub)):
            expr_cols = {c.name.lower() for c in expr_ast.find_all(exp.Column)}
            ret_cols = expr_cols & _RETURN_COLUMN_CANDIDATES
            gross_cols = expr_cols & _GROSS_COLUMN_CANDIDATES
            if ret_cols and (all_cols & gross_cols) and not _has_return_deduction(tree, queried, schema):
                return _fail(f"İş kuralı ihlali ('{metric.name}'): iade tutarı düşümü uygulanmalıdır.")

        # Check required filters on the metric
        if q_norm is None or not _question_mentions_cancellation(q_norm):
            base_info = schema.table(base)
            for flt in metric.filters:
                req_cols = _extract_fragment_columns(flt, dialect_val)
                if not req_cols:
                    continue
                if base_info is not None and all(base_info.column(c) is None for c in req_cols):
                    continue
                if not (req_cols & filtered_cols):
                    col_list = ", ".join(sorted(req_cols))
                    return _fail(f"İş kuralı ihlali ('{metric.name}'): '{col_list}' filtresi uygulanmalıdır.")
    return None


def _check_knowledge_rules(
    schema: SchemaSnapshot,
    queried: set[str],
    filtered_cols: set[str],
    knowledge: KnowledgeContext,
    q_norm: str | None,
) -> CheckResult | None:
    dialect_val = schema.dialect.value
    for rule in knowledge.rules:
        if not rule.approved or not rule.sql_fragment:
            continue
        rule_tables = _extract_fragment_tables(rule.sql_fragment, dialect_val)
        if rule_tables and not (rule_tables & queried):
            continue
        if q_norm is not None:
            term_norm = _tr_casefold(rule.term)
            if _question_mentions_cancellation(q_norm):
                continue
            if term_norm not in q_norm and not (rule_tables & queried):
                continue
        req_cols = _extract_fragment_columns(rule.sql_fragment, dialect_val)
        if req_cols and not (req_cols & filtered_cols):
            return _fail(
                f"İş kuralı ihlali ('{rule.term}'): {rule.definition} ({rule.sql_fragment}) uygulanmalıdır."
            )
    return None


def validate_business_rules(
    tree: exp.Expression,
    schema: SchemaSnapshot,
    knowledge: KnowledgeContext | None = None,
    question: str | None = None,
    *,
    rule_specs: Sequence[BusinessRuleSpec] | None = None,
) -> CheckResult:
    """Validate configurable enterprise business rules against *tree*, *knowledge*, and *question*."""
    if knowledge is None and question is None and rule_specs is None:
        return _ok()

    queried = _queried_tables(tree, schema)
    if not queried:
        return _ok()

    filtered_cols = _filter_columns(tree)
    all_cols = _all_columns(tree)
    q_norm = _tr_casefold(question) if question is not None else None

    if knowledge is not None:
        metric_err = _check_knowledge_metrics(
            tree, schema, queried, filtered_cols, all_cols, knowledge, q_norm
        )
        if metric_err is not None:
            return metric_err

        rule_err = _check_knowledge_rules(schema, queried, filtered_cols, knowledge, q_norm)
        if rule_err is not None:
            return rule_err

    if q_norm is not None:
        specs = DEFAULT_BUSINESS_RULE_SPECS if rule_specs is None else rule_specs
        for spec in specs:
            if not any(_tr_casefold(t) in q_norm for t in spec.trigger_terms):
                continue
            if any(_tr_casefold(ex) in q_norm for ex in spec.exclude_terms):
                continue

            if spec.require_return_deduction:
                ret_in_schema = _table_has_any_column(
                    schema, queried, tuple(sorted(_RETURN_COLUMN_CANDIDATES))
                )
                gross_in_sql = bool(all_cols & _GROSS_COLUMN_CANDIDATES)
                has_ret_table_in_schema = any(schema.table(rt) is not None for rt in _RETURN_TABLE_CANDIDATES)
                if (
                    ret_in_schema or (gross_in_sql and has_ret_table_in_schema)
                ) and not _has_return_deduction(tree, queried, schema):
                    return _fail(
                        "İş kuralı ihlali: 'net ciro / net satış' sorgusunda iade tutarı düşümü yapılmalıdır."
                    )

            if spec.require_filter_columns and not _question_mentions_cancellation(q_norm):
                present_cols = _table_has_any_column(schema, queried, spec.require_filter_columns)
                if present_cols and not (set(present_cols) & filtered_cols):
                    return _fail(spec.message or f"İş kuralı ihlali ({spec.rule_id}).")

    return _ok()
