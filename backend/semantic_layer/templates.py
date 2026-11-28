"""Approved deterministic KPI SQL templates (ADR-0008).

Frequently asked enterprise KPIs (``net satış / ciro``, ``iade oranı``,
``aktif müşteri``, ``vadesi geçmiş borç``) resolve directly to verified,
dialect-aware SQL templates instead of risking LLM metric improvisation.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta

from backend.core.contracts import (
    Dialect,
    Intent,
    LinkedSchema,
    MentionKind,
    ParsedQuestion,
    SchemaSnapshot,
    SQLCandidate,
)
from backend.knowledge_base import fold_turkish_diacritics, tr_casefold

_WORD_BOUNDARY_FMT = r"(?<![0-9a-zçğıöşü_]){term}(?![0-9a-zçğıöşü_])"


def _phrase_in_text(phrase: str, text: str) -> bool:
    pattern = _WORD_BOUNDARY_FMT.format(term=re.escape(phrase))
    return re.search(pattern, text) is not None


@dataclass(frozen=True)
class MetricTemplate:
    """Approved, dialect-aware deterministic SQL template for a KPI metric."""

    template_id: str
    metric_id: str
    name: str
    synonyms: tuple[str, ...]
    required_tables: tuple[str, ...]
    sqlite_sql: str
    postgres_sql: str
    required_columns: tuple[str, ...] = ()
    date_column: str | None = None
    rolling_days: int | None = None
    uses_today: bool = False
    version: int = 1
    approved: bool = True
    description: str = ""

    def __post_init__(self) -> None:
        for dialect_name, sql in (("sqlite", self.sqlite_sql), ("postgres", self.postgres_sql)):
            stripped = sql.strip()
            upper = stripped.upper()
            if not (upper.startswith("SELECT") or upper.startswith("WITH")):
                raise ValueError(f"{dialect_name} template must start with SELECT or WITH")
            if ";" in stripped:
                raise ValueError(f"{dialect_name} template must be a single statement without ';'")


@dataclass(frozen=True)
class TemplateMatch:
    """Deterministic SQL produced by matching an approved KPI template."""

    template_id: str
    metric_id: str
    version: int
    dialect: Dialect
    sql: str
    parameterized_sql: str
    parameters: tuple[tuple[str, str | int | float], ...] = ()
    tables: tuple[str, ...] = ()
    matched_term: str = ""
    bypass_llm: bool = True

    def to_sql_candidate(
        self,
        *,
        attempt: int = 1,
        model_id: str = "semantic_layer/template",
    ) -> SQLCandidate:
        """Wrap deterministic SQL in a ``SQLCandidate`` for L6 validation & policy."""
        return SQLCandidate(
            sql=self.sql,
            dialect=self.dialect,
            model_id=model_id,
            attempt=attempt,
            latency_ms=0.0,
        )


def default_metric_templates() -> tuple[MetricTemplate, ...]:
    """Return the built-in approved enterprise KPI templates."""
    return (
        MetricTemplate(
            template_id="kpi_net_sales_v1",
            metric_id="net_sales",
            name="net satış",
            synonyms=(
                "net satış tutarı",
                "net satış",
                "net ciro",
                "toplam ciro",
                "satış tutarı",
                "satış geliri",
                "hasılat",
                "ciro",
            ),
            required_tables=("sales",),
            required_columns=("sales.total_amount", "sales.return_amount", "sales.status"),
            date_column="sales.sale_date",
            sqlite_sql=(
                "SELECT COALESCE(SUM(sales.total_amount - sales.return_amount), 0) AS net_sales "
                "FROM sales WHERE sales.status <> 'cancelled'{date_filter}"
            ),
            postgres_sql=(
                "SELECT COALESCE(SUM(sales.total_amount - sales.return_amount), 0)::numeric(18, 2) "
                "AS net_sales FROM sales WHERE sales.status <> 'cancelled'{date_filter}"
            ),
            description="İptal edilmemiş satışlardan iade tutarı düşülmüş net ciro",
        ),
        MetricTemplate(
            template_id="kpi_return_rate_v1",
            metric_id="return_rate",
            name="iade oranı",
            synonyms=(
                "iade oranı",
                "iade yüzdesi",
                "geri dönüş oranı",
            ),
            required_tables=("sales",),
            required_columns=("sales.total_amount", "sales.return_amount", "sales.status"),
            date_column="sales.sale_date",
            sqlite_sql=(
                "SELECT ROUND(CASE WHEN COALESCE(SUM(sales.total_amount), 0) = 0 THEN 0.0 "
                "ELSE CAST(SUM(sales.return_amount) AS REAL) * 100.0 / SUM(sales.total_amount) "
                "END, 2) AS return_rate_pct "
                "FROM sales WHERE sales.status <> 'cancelled'{date_filter}"
            ),
            postgres_sql=(
                "SELECT ROUND(CASE WHEN COALESCE(SUM(sales.total_amount), 0) = 0 THEN 0 "
                "ELSE SUM(sales.return_amount)::numeric * 100.0 / NULLIF(SUM(sales.total_amount), 0) "
                "END, 2) AS return_rate_pct "
                "FROM sales WHERE sales.status <> 'cancelled'{date_filter}"
            ),
            description="İptal edilmemiş satışlarda iade tutarının toplam satış tutarına yüzdesi",
        ),
        MetricTemplate(
            template_id="kpi_active_customers_v1",
            metric_id="active_customers",
            name="aktif müşteri",
            synonyms=(
                "aktif müşteri sayısı",
                "aktif müşteriler",
                "aktif müşteri",
                "etkin müşteri",
            ),
            required_tables=("customers",),
            required_columns=("customers.customer_id", "customers.last_purchase_date"),
            rolling_days=90,
            uses_today=True,
            sqlite_sql=(
                "SELECT COUNT(DISTINCT customers.customer_id) AS active_customer_count "
                "FROM customers WHERE customers.last_purchase_date >= {cutoff_expr}"
            ),
            postgres_sql=(
                "SELECT COUNT(DISTINCT customers.customer_id) AS active_customer_count "
                "FROM customers WHERE customers.last_purchase_date >= {cutoff_expr}"
            ),
            description="Son 90 günde alışveriş yapan tekil müşteri sayısı",
        ),
        MetricTemplate(
            template_id="kpi_overdue_debt_v1",
            metric_id="overdue_debt",
            name="vadesi geçmiş borç",
            synonyms=(
                "vadesi geçmiş cari borç",
                "vadesi geçmiş borç",
                "vadesi dolmuş borç",
                "gecikmiş cari borç",
                "gecikmiş borç",
                "vadesi geçmiş alacak",
            ),
            required_tables=("invoices",),
            required_columns=(
                "invoices.total_amount",
                "invoices.paid_amount",
                "invoices.due_date",
                "invoices.status",
            ),
            uses_today=True,
            sqlite_sql=(
                "SELECT COALESCE(SUM(invoices.total_amount - invoices.paid_amount), 0) AS overdue_debt "
                "FROM invoices WHERE invoices.due_date < {today_expr} "
                "AND invoices.status IN ('unpaid', 'partial', 'overdue')"
            ),
            postgres_sql=(
                "SELECT COALESCE(SUM(invoices.total_amount - invoices.paid_amount), 0)::numeric(18, 2) "
                "AS overdue_debt FROM invoices WHERE invoices.due_date < {today_expr} "
                "AND invoices.status IN ('unpaid', 'partial', 'overdue')"
            ),
            description="Vadesi bugünden önce olan ödenmemiş veya kısmi ödenmiş fatura bakiyesi",
        ),
    )


class MetricTemplateRegistry:
    """Registry that matches KPI questions to RBAC-verified deterministic SQL templates."""

    def __init__(self, templates: Iterable[MetricTemplate] | None = None) -> None:
        initial = default_metric_templates() if templates is None else tuple(templates)
        self._templates: dict[str, MetricTemplate] = {t.template_id: t for t in initial}

    @property
    def templates(self) -> tuple[MetricTemplate, ...]:
        return tuple(self._templates.values())

    def register(self, template: MetricTemplate) -> None:
        """Add or replace a ``MetricTemplate`` by ``template_id``."""
        self._templates[template.template_id] = template

    def _is_rbac_allowed(
        self,
        template: MetricTemplate,
        linked: LinkedSchema,
        schema: SchemaSnapshot | None,
        denied_columns: frozenset[str],
    ) -> bool:
        linked_tables = {t.lower() for t in linked.tables}
        required_tables = {t.lower() for t in template.required_tables}
        if not required_tables.issubset(linked_tables):
            return False

        denied_low = {c.lower() for c in denied_columns}
        required_cols = {c.lower() for c in template.required_columns}
        if not required_cols.isdisjoint(denied_low):
            return False

        if schema is not None:
            if not required_tables.issubset(schema.table_names):
                return False
            for qual in template.required_columns:
                table_name, _, col_name = qual.partition(".")
                tbl = schema.table(table_name)
                if tbl is None or tbl.column(col_name) is None:
                    return False
        return True

    def _matched_term(self, template: MetricTemplate, question: ParsedQuestion) -> str | None:
        candidates = (template.name, *template.synonyms)
        ordered = sorted(dict.fromkeys(candidates), key=len, reverse=True)
        q_tr = tr_casefold(question.normalized_text or question.original_text)
        q_ascii = fold_turkish_diacritics(q_tr)
        mention_terms = {
            tr_casefold(m.lemma or m.text) for m in question.mentions if m.kind is MentionKind.METRIC
        }
        mention_ascii = {fold_turkish_diacritics(w) for w in mention_terms}

        for term in ordered:
            t_tr = tr_casefold(term)
            t_ascii = fold_turkish_diacritics(t_tr)
            if t_tr in mention_terms or t_ascii in mention_ascii:
                return term
            if _phrase_in_text(t_tr, q_tr) or _phrase_in_text(t_ascii, q_ascii):
                return term
        return None

    def _render_sql(
        self,
        template: MetricTemplate,
        question: ParsedQuestion,
        dialect: Dialect,
        today: date | None,
    ) -> tuple[str, str, tuple[tuple[str, str | int | float], ...]] | None:
        raw_template = template.sqlite_sql if dialect is Dialect.SQLITE else template.postgres_sql
        params: list[tuple[str, str | int | float]] = []

        date_filter_sql = ""
        date_filter_param_sql = ""
        if question.temporal:
            if template.date_column is None or len(question.temporal) > 1:
                return None
            t_expr = question.temporal[0]
            if t_expr.start is not None:
                start_iso = t_expr.start.isoformat()
                date_filter_sql += f" AND {template.date_column} >= '{start_iso}'"
                date_filter_param_sql += f" AND {template.date_column} >= :start_date"
                params.append(("start_date", start_iso))
            if t_expr.end is not None:
                end_iso = t_expr.end.isoformat()
                date_filter_sql += f" AND {template.date_column} < '{end_iso}'"
                date_filter_param_sql += f" AND {template.date_column} < :end_date"
                params.append(("end_date", end_iso))

        cutoff_sql = ""
        cutoff_param_sql = ":cutoff_date"
        today_sql = ""
        today_param_sql = ":as_of_date"

        if template.rolling_days is not None:
            if today is not None:
                today_iso = today.isoformat()
                cutoff_iso = (today - timedelta(days=template.rolling_days)).isoformat()
                params.append(("cutoff_date", cutoff_iso))
                if dialect is Dialect.SQLITE:
                    cutoff_sql = f"date('{today_iso}', '-{template.rolling_days} days')"
                else:
                    cutoff_sql = f"DATE '{today_iso}' - INTERVAL '{template.rolling_days} days'"
            else:
                if dialect is Dialect.SQLITE:
                    cutoff_sql = f"date('now', '-{template.rolling_days} days')"
                    cutoff_param_sql = cutoff_sql
                else:
                    cutoff_sql = f"CURRENT_DATE - INTERVAL '{template.rolling_days} days'"
                    cutoff_param_sql = cutoff_sql

        if template.uses_today:
            if today is not None:
                today_iso = today.isoformat()
                if template.rolling_days is None:
                    params.append(("as_of_date", today_iso))
                today_sql = f"'{today_iso}'" if dialect is Dialect.SQLITE else f"DATE '{today_iso}'"
            else:
                today_sql = "date('now')" if dialect is Dialect.SQLITE else "CURRENT_DATE"
                today_param_sql = today_sql

        sql = raw_template.format(
            date_filter=date_filter_sql,
            cutoff_expr=cutoff_sql,
            today_expr=today_sql,
        )
        param_sql = raw_template.format(
            date_filter=date_filter_param_sql,
            cutoff_expr=cutoff_param_sql,
            today_expr=today_param_sql,
        )
        return sql, param_sql, tuple(params)

    def match(
        self,
        question: ParsedQuestion,
        linked: LinkedSchema,
        *,
        dialect: Dialect = Dialect.SQLITE,
        schema: SchemaSnapshot | None = None,
        denied_columns: frozenset[str] = frozenset(),
        today: date | None = None,
    ) -> TemplateMatch | None:
        """Return a deterministic ``TemplateMatch`` when a KPI template safely applies.

        Returns ``None`` if the question is ambiguous, requests ranking/grouping/
        location filtering beyond a scalar KPI, lacks RBAC table/column access,
        or does not match an approved template.
        """
        if question.is_ambiguous:
            return None
        if question.intent in (Intent.RANKING, Intent.COMPARISON, Intent.TREND):
            return None
        if question.limit is not None or question.sort is not None:
            return None
        if any(m.kind in (MentionKind.LOCATION, MentionKind.VALUE) for m in question.mentions):
            return None

        best_match: tuple[int, TemplateMatch] | None = None
        for template in self._templates.values():
            if not template.approved:
                continue
            matched_term = self._matched_term(template, question)
            if matched_term is None:
                continue
            if not self._is_rbac_allowed(template, linked, schema, denied_columns):
                continue
            rendered = self._render_sql(template, question, dialect, today)
            if rendered is None:
                continue
            sql, param_sql, params = rendered
            match = TemplateMatch(
                template_id=template.template_id,
                metric_id=template.metric_id,
                version=template.version,
                dialect=dialect,
                sql=sql,
                parameterized_sql=param_sql,
                parameters=params,
                tables=template.required_tables,
                matched_term=matched_term,
                bypass_llm=True,
            )
            term_len = len(matched_term)
            if best_match is None or term_len > best_match[0]:
                best_match = (term_len, match)

        return best_match[1] if best_match is not None else None
