from __future__ import annotations

from datetime import date

import pytest

from backend.auth import scope_schema
from backend.core.contracts import (
    AuthContext,
    ColumnInfo,
    Dialect,
    Intent,
    LinkedSchema,
    Mention,
    MentionKind,
    MetricDefinition,
    ParsedQuestion,
    SchemaSnapshot,
    TableInfo,
    TemporalExpression,
    Verdict,
)
from backend.database_adapters import SQLiteAdapter
from backend.knowledge_base import InMemoryKnowledgeBase, tr_casefold
from backend.semantic_layer import (
    MetricTemplate,
    MetricTemplateRegistry,
    SemanticLayer,
    TemplateMatch,
    default_metric_templates,
)
from backend.sql_validator import SQLValidator


def _pq(
    text: str,
    *,
    intent: Intent = Intent.AGGREGATE,
    mentions: tuple[Mention, ...] = (),
    temporal: tuple[TemporalExpression, ...] = (),
    ambiguities: tuple[str, ...] = (),
    limit: int | None = None,
) -> ParsedQuestion:
    return ParsedQuestion(
        original_text=text,
        normalized_text=tr_casefold(text),
        intent=intent,
        mentions=mentions,
        temporal=temporal,
        ambiguities=ambiguities,
        limit=limit,
    )


def _enterprise_schema() -> SchemaSnapshot:
    return SchemaSnapshot(
        dialect=Dialect.SQLITE,
        tables=(
            TableInfo(
                name="dealers",
                columns=(
                    ColumnInfo(name="dealer_id", data_type="INTEGER", is_primary_key=True),
                    ColumnInfo(name="name", data_type="TEXT"),
                    ColumnInfo(name="city", data_type="TEXT"),
                ),
            ),
            TableInfo(
                name="sales",
                columns=(
                    ColumnInfo(name="sale_id", data_type="INTEGER", is_primary_key=True),
                    ColumnInfo(name="dealer_id", data_type="INTEGER"),
                    ColumnInfo(name="sale_date", data_type="TEXT"),
                    ColumnInfo(name="total_amount", data_type="REAL"),
                    ColumnInfo(name="return_amount", data_type="REAL"),
                    ColumnInfo(name="status", data_type="TEXT"),
                ),
            ),
            TableInfo(
                name="customers",
                columns=(
                    ColumnInfo(name="customer_id", data_type="INTEGER", is_primary_key=True),
                    ColumnInfo(name="full_name", data_type="TEXT"),
                    ColumnInfo(name="last_purchase_date", data_type="TEXT"),
                ),
            ),
            TableInfo(
                name="invoices",
                columns=(
                    ColumnInfo(name="invoice_id", data_type="INTEGER", is_primary_key=True),
                    ColumnInfo(name="customer_id", data_type="INTEGER"),
                    ColumnInfo(name="total_amount", data_type="REAL"),
                    ColumnInfo(name="paid_amount", data_type="REAL"),
                    ColumnInfo(name="due_date", data_type="TEXT"),
                    ColumnInfo(name="status", data_type="TEXT"),
                ),
            ),
        ),
    )


def test_semantic_layer_resolves_turkish_synonyms_and_respects_rbac(
    knowledge: InMemoryKnowledgeBase,
) -> None:
    layer = SemanticLayer(knowledge)
    linked_sales = LinkedSchema(tables=("dealers", "sales"))

    resolved = layer.resolve(_pq("Geçen ay toplam hasılat ne kadar?"), linked_sales)
    assert [m.metric_id for m in resolved] == ["net_sales"]

    resolved_upper = layer.resolve(
        _pq("İADE ORANI ve CİRO nedir?", mentions=(Mention(text="CİRO", kind=MentionKind.METRIC),)),
        linked_sales,
    )
    assert [m.metric_id for m in resolved_upper] == ["net_sales"]

    # RBAC: if sales is not visible in linked schema, metric must NOT resolve
    linked_only_dealers = LinkedSchema(tables=("dealers",))
    assert layer.resolve(_pq("Toplam ciro nedir?"), linked_only_dealers) == ()


def test_all_four_deterministic_kpi_templates_sqlite_and_postgres() -> None:
    registry = MetricTemplateRegistry(default_metric_templates())
    schema = _enterprise_schema()
    linked = LinkedSchema(tables=("sales", "customers", "invoices"))
    today = date(2026, 11, 27)

    cases = [
        (
            "Toplam net satış ve ciro nedir?",
            "net_sales",
            "COALESCE(SUM(sales.total_amount - sales.return_amount), 0)",
        ),
        ("İade oranı yüzde kaç?", "return_rate", "return_rate_pct"),
        ("Aktif müşteri sayısı kaç?", "active_customers", "COUNT(DISTINCT customers.customer_id)"),
        ("Vadesi geçmiş borç toplamı ne kadar?", "overdue_debt", "invoices.due_date <"),
    ]
    for prompt_text, expected_metric, expected_fragment in cases:
        m_sqlite = registry.match(
            _pq(prompt_text),
            linked,
            dialect=Dialect.SQLITE,
            schema=schema,
            today=today,
        )
        assert isinstance(m_sqlite, TemplateMatch)
        assert m_sqlite.metric_id == expected_metric
        assert m_sqlite.bypass_llm is True
        assert expected_fragment in m_sqlite.sql

        m_pg = registry.match(
            _pq(prompt_text),
            linked,
            dialect=Dialect.POSTGRES,
            schema=schema,
            today=today,
        )
        assert m_pg is not None
        assert m_pg.dialect is Dialect.POSTGRES
        assert expected_fragment in m_pg.sql

    # Turkish capital I/İ handling even if normalized_text used naive .lower()
    naive_lower_q = ParsedQuestion(
        original_text="İADE ORANI nedir?",
        normalized_text="İADE ORANI nedir?".lower(),
        intent=Intent.AGGREGATE,
    )
    recovered = registry.match(naive_lower_q, linked, dialect=Dialect.SQLITE, schema=schema)
    assert recovered is not None and recovered.metric_id == "return_rate"

    # Dialect-specific date expressions
    active_pg = registry.match(
        _pq("Aktif müşteri sayısı"),
        linked,
        dialect=Dialect.POSTGRES,
        schema=schema,
        today=today,
    )
    active_sq = registry.match(
        _pq("Aktif müşteri sayısı"),
        linked,
        dialect=Dialect.SQLITE,
        schema=schema,
        today=today,
    )
    assert active_pg is not None and "INTERVAL '90 days'" in active_pg.sql
    assert active_sq is not None and "date('2026-11-27', '-90 days')" in active_sq.sql
    assert dict(active_sq.parameters) == {"cutoff_date": "2026-08-29"}


def test_template_temporal_filtering_and_parameterized_output() -> None:
    registry = MetricTemplateRegistry()
    schema = _enterprise_schema()
    linked = LinkedSchema(tables=("sales",))
    q = _pq(
        "Geçen ay net satış ne kadar?",
        temporal=(
            TemporalExpression(
                text="geçen ay",
                start=date(2026, 10, 1),
                end=date(2026, 11, 1),
            ),
        ),
    )
    match = registry.match(q, linked, dialect=Dialect.SQLITE, schema=schema)
    assert match is not None
    assert "sales.sale_date >= '2026-10-01'" in match.sql
    assert "sales.sale_date < '2026-11-01'" in match.sql
    assert ":start_date" in match.parameterized_sql
    assert dict(match.parameters) == {"start_date": "2026-10-01", "end_date": "2026-11-01"}


def test_template_rbac_and_granularity_guards(schema: SchemaSnapshot, analyst: AuthContext) -> None:
    kb = InMemoryKnowledgeBase(
        metrics=(
            MetricDefinition(
                metric_id="net_sales",
                name="net satış",
                synonyms=("ciro",),
                expression="SUM(sales.total_amount - sales.return_amount)",
                base_table="sales",
            ),
        )
    )
    layer = SemanticLayer(kb)
    scoped = scope_schema(schema, analyst)

    # Analyst does NOT have customers or invoices tables -> must return None
    linked_analyst = LinkedSchema(tables=("dealers", "sales"))
    assert layer.resolve_template(_pq("Aktif müşteri sayısı"), linked_analyst, schema=scoped) is None
    assert layer.resolve_template(_pq("Vadesi geçmiş borç"), linked_analyst, schema=scoped) is None

    # Denied required column -> must return None
    restricted_auth = AuthContext(
        user_id="u-limited",
        tenant_id="t-demo",
        allowed_tables=frozenset({"sales"}),
        denied_columns=frozenset({"sales.return_amount"}),
    )
    scoped_restricted = scope_schema(schema, restricted_auth)
    assert (
        layer.resolve_template(
            _pq("Net satış nedir?"),
            LinkedSchema(tables=("sales",)),
            schema=scoped_restricted,
            denied_columns=restricted_auth.denied_columns,
        )
        is None
    )

    # Ambiguous or ranked/location queries must NOT hijack via scalar template
    assert layer.resolve_template(_pq("İyi ciro?", ambiguities=("belirsiz",)), linked_analyst) is None
    assert (
        layer.resolve_template(
            _pq(
                "Trabzon'daki en çok ciro yapan 5 bayi",
                intent=Intent.RANKING,
                mentions=(Mention(text="Trabzon'daki", kind=MentionKind.LOCATION),),
                limit=5,
            ),
            linked_analyst,
            schema=scoped,
        )
        is None
    )


def test_template_executes_deterministically_through_validator_and_sqlite(
    adapter: SQLiteAdapter,
    schema: SchemaSnapshot,
    analyst: AuthContext,
    knowledge: InMemoryKnowledgeBase,
) -> None:
    layer = SemanticLayer(knowledge)
    scoped = scope_schema(schema, analyst)
    linked = LinkedSchema(tables=("sales",))
    match = layer.resolve_template(
        _pq("Net satış tutarı ne kadar?"),
        linked,
        dialect=Dialect.SQLITE,
        schema=scoped,
    )
    assert match is not None
    candidate = match.to_sql_candidate()
    report = SQLValidator().validate(candidate, schema, analyst)
    assert report.verdict is Verdict.APPROVED

    # Validate execution against demo_schema.sql (5,459,999 excluding cancelled 100,000)
    from backend.policy_engine import PolicyEngine

    approved = PolicyEngine().approve(report, analyst)
    result = adapter.execute(approved)
    assert result.rows[0][0] == pytest.approx(5_459_999.0)


def test_custom_template_validation_and_unapproved_exclusion() -> None:
    with pytest.raises(ValueError):
        MetricTemplate(
            template_id="bad_dml",
            metric_id="bad",
            name="bad",
            synonyms=("bad",),
            required_tables=("sales",),
            sqlite_sql="DELETE FROM sales",
            postgres_sql="DELETE FROM sales",
        )
    with pytest.raises(ValueError):
        MetricTemplate(
            template_id="bad_multi",
            metric_id="bad",
            name="bad",
            synonyms=("bad",),
            required_tables=("sales",),
            sqlite_sql="SELECT 1; DROP TABLE sales",
            postgres_sql="SELECT 1",
        )

    draft = MetricTemplate(
        template_id="draft_kpi",
        metric_id="draft",
        name="taslak metrik",
        synonyms=("taslak metrik",),
        required_tables=("sales",),
        sqlite_sql="SELECT 1 AS v FROM sales",
        postgres_sql="SELECT 1 AS v FROM sales",
        approved=False,
    )
    registry = MetricTemplateRegistry([draft])
    assert registry.match(_pq("taslak metrik nedir?"), LinkedSchema(tables=("sales",))) is None
