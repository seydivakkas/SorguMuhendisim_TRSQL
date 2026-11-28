from __future__ import annotations

import os
import sqlite3
from collections.abc import Callable
from datetime import date
from pathlib import Path

import pytest

from backend.core.contracts import (
    AuthContext,
    BusinessRule,
    Dialect,
    MentionKind,
    MetricDefinition,
    SchemaSnapshot,
    SQLCandidate,
)
from backend.database_adapters import SQLiteAdapter
from backend.knowledge_base import InMemoryKnowledgeBase
from backend.turkish_nlp import RuleBasedTurkishParser

FIXTURES = Path(__file__).parent / "fixtures"
TODAY = date(2026, 11, 27)

NLP_LEXICON: dict[str, MentionKind] = {
    "bayi": MentionKind.ENTITY,
    "satış": MentionKind.METRIC,
    "ciro": MentionKind.METRIC,
}
SCHEMA_LEXICON: dict[str, str] = {
    "bayi": "dealers",
    "satış": "sales",
    "ciro": "sales",
    "__location__": "dealers.city",
}
LOCATIONS = frozenset({"Trabzon", "Rize"})


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "demo.sqlite"
    conn = sqlite3.connect(path)
    conn.executescript((FIXTURES / "demo_schema.sql").read_text(encoding="utf-8"))
    conn.commit()
    conn.close()
    return path


@pytest.fixture
def adapter(db_path: Path) -> SQLiteAdapter:
    return SQLiteAdapter(db_path)


@pytest.fixture
def schema(adapter: SQLiteAdapter) -> SchemaSnapshot:
    return adapter.introspect()


@pytest.fixture
def analyst() -> AuthContext:
    return AuthContext(
        user_id="u-analyst",
        tenant_id="t-demo",
        roles=frozenset({"analyst"}),
        allowed_tables=frozenset({"dealers", "sales"}),
        denied_columns=frozenset({"dealers.tax_number"}),
        max_rows=100,
    )


@pytest.fixture
def parser() -> RuleBasedTurkishParser:
    return RuleBasedTurkishParser(NLP_LEXICON, LOCATIONS, today=lambda: TODAY)


@pytest.fixture
def knowledge() -> InMemoryKnowledgeBase:
    return InMemoryKnowledgeBase(
        rules=(
            BusinessRule(
                rule_id="R-001",
                term="geçerli sipariş",
                definition="iptal edilmemiş satış",
                sql_fragment="sales.status <> 'cancelled'",
                source="demo",
                approved=True,
            ),
            BusinessRule(
                rule_id="R-999",
                term="taslak kural",
                definition="satış onaysız",
                source="demo",
                approved=False,
            ),
        ),
        metrics=(
            MetricDefinition(
                metric_id="net_sales",
                name="net satış",
                synonyms=("satış", "ciro"),
                expression="SUM(sales.total_amount - sales.return_amount)",
                base_table="sales",
                filters=("sales.status <> 'cancelled'",),
            ),
        ),
    )


@pytest.fixture
def candidate() -> Callable[[str], SQLCandidate]:
    def make(sql: str, dialect: Dialect = Dialect.SQLITE) -> SQLCandidate:
        return SQLCandidate(sql=sql, dialect=dialect, model_id="test", attempt=1)

    return make


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Skip optional hardware/service tests unless their local env vars are set.

    Security tests (``@pytest.mark.security``) are NEVER skipped (AGENTS.md §1.8).
    """
    has_gpu_model = bool(os.environ.get("TRSQL_MODEL_PATH", "").strip())
    has_pg_dsn = bool(os.environ.get("TRSQL_PG_TEST_DSN", "").strip())
    skip_gpu = pytest.mark.skip(reason="TRSQL_MODEL_PATH tanımsız; @pytest.mark.gpu atlandı.")
    skip_pg = pytest.mark.skip(reason="TRSQL_PG_TEST_DSN tanımsız; @pytest.mark.postgres atlandı.")

    for item in items:
        if item.get_closest_marker("security") is not None:
            continue
        if item.get_closest_marker("gpu") is not None and not has_gpu_model:
            item.add_marker(skip_gpu)
        if item.get_closest_marker("postgres") is not None and not has_pg_dsn:
            item.add_marker(skip_pg)
