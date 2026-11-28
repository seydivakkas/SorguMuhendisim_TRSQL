from __future__ import annotations

import pytest

from backend.core.contracts import (
    BusinessRule,
    ColumnInfo,
    Dialect,
    ForeignKey,
    Intent,
    KnowledgeContext,
    MetricDefinition,
    ParsedQuestion,
    QueryPlan,
    ReasoningMode,
    SchemaSnapshot,
    TableInfo,
)
from backend.core.errors import ConfigError
from backend.prompt_engine import (
    DDL_TEMPLATE_ID,
    MSCHEMA_TEMPLATE_ID,
    TEMPLATE_ID,
    PromptBuilder,
    build_gbnf_grammar_for_mode,
    build_sql_gbnf,
    render_ddl,
    render_mschema,
    render_schema,
)


def _sample_schema() -> SchemaSnapshot:
    return SchemaSnapshot(
        dialect=Dialect.POSTGRES,
        tables=(
            TableInfo(
                name="dealers",
                description="Bayi ana tablosu",
                columns=(
                    ColumnInfo(name="dealer_id", data_type="INTEGER", nullable=False, is_primary_key=True),
                    ColumnInfo(name="name", data_type="TEXT", nullable=False, description="Bayi adı"),
                    ColumnInfo(name="city", data_type="TEXT", nullable=False, description="Şehir"),
                    ColumnInfo(name="tax_number", data_type="TEXT", description="Vergi numarası"),
                    ColumnInfo(name="tckn", data_type="TEXT", description="Kimlik no"),
                    ColumnInfo(
                        name="custom_secret", data_type="TEXT", description="Kişisel veri alanı (PII)"
                    ),
                ),
            ),
            TableInfo(
                name="sales",
                description="Satış hareketleri",
                columns=(
                    ColumnInfo(name="sale_id", data_type="INTEGER", nullable=False, is_primary_key=True),
                    ColumnInfo(name="dealer_id", data_type="INTEGER", nullable=False),
                    ColumnInfo(name="total_amount", data_type="NUMERIC", nullable=False),
                ),
                foreign_keys=(ForeignKey(column="dealer_id", ref_table="dealers", ref_column="dealer_id"),),
            ),
        ),
    )


def _sample_plan() -> QueryPlan:
    return QueryPlan(intent=Intent.AGGREGATE, tables=("dealers", "sales"))


def _sample_question() -> ParsedQuestion:
    return ParsedQuestion(
        original_text="Trabzon bayilerinin toplam satışı nedir?",
        normalized_text="trabzon bayilerinin toplam satisi nedir",
        intent=Intent.AGGREGATE,
    )


def _sample_knowledge() -> KnowledgeContext:
    return KnowledgeContext(
        rules=(
            BusinessRule(
                rule_id="R1",
                term="geçerli satış",
                definition="iptal edilmemiş satışlar",
                sql_fragment="sales.status <> 'cancelled'",
                source="erp",
                approved=True,
            ),
        ),
        metrics=(
            MetricDefinition(
                metric_id="total_sales",
                name="toplam satış",
                expression="SUM(sales.total_amount)",
                base_table="sales",
            ),
        ),
    )


def test_ddl_v1_renders_create_table_and_suppresses_pii_samples() -> None:
    schema = _sample_schema()
    samples = {
        "dealers.city": ["Trabzon", "Rize"],
        "dealers.tax_number": ["1111111111"],
        "dealers.tckn": ["12345678901"],
        "dealers.custom_secret": ["GIZLI_DEGER"],
        "dealers.name": ["Bayi A", "Bayi B"],
    }
    ddl = render_ddl(
        schema,
        denied_columns={"dealers.name"},
        sample_values=samples,
    )
    assert "CREATE TABLE dealers (" in ddl
    assert "CREATE TABLE sales (" in ddl
    assert "dealer_id INTEGER PRIMARY KEY" in ddl
    assert "FOREIGN KEY (dealer_id) REFERENCES dealers(dealer_id)" in ddl
    assert "1111111111" not in ddl
    assert "12345678901" not in ddl
    assert "GIZLI_DEGER" not in ddl
    assert "Bayi A" not in ddl  # denied_columns suppressed


def test_mschema_v1_renders_types_descriptions_samples_fks_and_blocks_pii() -> None:
    schema = _sample_schema()
    samples = {
        "dealers.dealer_id": [1, 2, 3, 4],
        "dealers.name": ["Bayi A", "Bayi B", "Bayi C", "Bayi D"],
        "dealers.city": ["Trabzon", "Rize", "Trabzon"],  # deduplicated
        "dealers.tax_number": ["9999999999"],
        "dealers.tckn": ["12345678901"],
        "dealers.custom_secret": ["SECRET_PII_ROW"],
        "sales.total_amount": [1250.5, 980.0],
    }
    rendered = render_mschema(
        schema,
        sample_values=samples,
        denied_columns={"dealers.tax_number"},
    )
    assert "【DB_DIALECT】postgres" in rendered
    assert "【Schema】" in rendered
    assert "# Table: dealers, Bayi ana tablosu" in rendered
    assert "(dealer_id: INTEGER, Primary Key, Examples: [1, 2, 3])" in rendered
    assert "(name: TEXT, Bayi adı, Examples: [Bayi A, Bayi B, Bayi C])" in rendered
    assert "(city: TEXT, Şehir, Examples: [Trabzon, Rize])" in rendered
    assert "Bayi D" not in rendered  # capped to 3 samples
    assert "9999999999" not in rendered
    assert "12345678901" not in rendered
    assert "SECRET_PII_ROW" not in rendered
    assert "【Foreign keys】" in rendered
    assert "sales.dealer_id = dealers.dealer_id" in rendered


def test_prompt_builder_templates_and_reasoning_modes() -> None:
    schema = _sample_schema()
    plan = _sample_plan()
    knowledge = _sample_knowledge()
    question = _sample_question()

    # Default remains sql-gen/v1 for full backward compatibility.
    default_builder = PromptBuilder()
    default_bundle = default_builder.build(plan, schema, knowledge, question)
    assert default_bundle.template_id == TEMPLATE_ID
    assert render_schema(schema, plan.tables) in default_bundle.user
    assert "<think>" not in default_bundle.system
    assert "【MODE】" not in default_bundle.user

    # D0 DDL + THINKING mode
    ddl_thinking = PromptBuilder(
        template_id=DDL_TEMPLATE_ID,
        reasoning_mode=ReasoningMode.THINKING,
    )
    ddl_bundle = ddl_thinking.build(plan, schema, knowledge, question)
    assert ddl_bundle.template_id == "ddl_v1"
    assert "CREATE TABLE dealers" in ddl_bundle.user
    assert "<think>" in ddl_bundle.system
    assert "【MODE】thinking" in ddl_bundle.user

    # D1 M-Schema + DIRECT mode
    mschema_builder = PromptBuilder(
        template_id=MSCHEMA_TEMPLATE_ID,
        reasoning_mode=ReasoningMode.DIRECT,
        sample_values={"dealers.city": ["Trabzon", "Rize"], "dealers.tckn": ["12345678901"]},
    )
    mschema_bundle = mschema_builder.build(plan, schema, knowledge, question)
    assert mschema_bundle.template_id == "mschema_v1"
    assert "Examples: [Trabzon, Rize]" in mschema_bundle.user
    assert "12345678901" not in mschema_bundle.user
    assert "<think>" not in mschema_bundle.system

    with pytest.raises(ConfigError):
        PromptBuilder(template_id="unknown_v99")


def test_gbnf_grammar_generation_for_dialects_and_thinking_mode() -> None:
    schema = _sample_schema()
    sqlite_direct = build_sql_gbnf(Dialect.SQLITE, schema=schema, allow_thinking=False)
    assert "STRFTIME" in sqlite_direct
    assert "ILIKE" not in sqlite_direct
    assert 'table-name ::= "dealers" | "sales"' in sqlite_direct
    assert "think-block" not in sqlite_direct
    for forbidden in ('"DROP"', '"DELETE"', '"INSERT"', '"UPDATE"'):
        assert forbidden not in sqlite_direct

    pg_thinking = build_gbnf_grammar_for_mode(
        Dialect.POSTGRES,
        ReasoningMode.THINKING,
        schema=schema,
        fenced=True,
    )
    assert "ILIKE" in pg_thinking
    assert "DATE_TRUNC" in pg_thinking
    assert "think-block" in pg_thinking
    assert "unconstrained" in pg_thinking
    assert "```sql" in pg_thinking
