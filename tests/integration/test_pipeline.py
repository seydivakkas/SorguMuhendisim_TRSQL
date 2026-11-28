from collections.abc import Sequence

import pytest

from backend.core.config import RetrySettings, Settings
from backend.core.contracts import AuthContext, OutcomeStatus, QueryRequest
from backend.database_adapters import SQLiteAdapter
from backend.knowledge_base import InMemoryKnowledgeBase
from backend.model_engine import FakeModelAdapter
from backend.observability import InMemoryAuditSink
from backend.orchestration import Pipeline, build_default_pipeline
from tests.conftest import LOCATIONS, NLP_LEXICON, SCHEMA_LEXICON, TODAY

pytestmark = pytest.mark.integration

QUESTION = "Geçen ay Trabzon'daki en çok satış yapan beş bayimiz hangileri?"
GOOD_SQL = """```sql
SELECT d.name, SUM(s.total_amount - s.return_amount) AS net_sales
FROM dealers d JOIN sales s ON s.dealer_id = d.dealer_id
WHERE d.city = 'Trabzon' AND s.sale_date >= '2026-10-01' AND s.sale_date < '2026-11-01'
  AND s.status <> 'cancelled'
GROUP BY d.name ORDER BY net_sales DESC LIMIT 5
```"""


def build(
    adapter: SQLiteAdapter, knowledge: InMemoryKnowledgeBase, responses: Sequence[str]
) -> tuple[Pipeline, FakeModelAdapter, InMemoryAuditSink]:
    model = FakeModelAdapter(responses)
    sink = InMemoryAuditSink()
    pipeline = build_default_pipeline(
        settings=Settings(retry=RetrySettings(max_attempts=3)),
        database=adapter,
        model=model,
        knowledge=knowledge,
        nlp_lexicon=NLP_LEXICON,
        schema_lexicon=SCHEMA_LEXICON,
        locations=LOCATIONS,
        audit_sink=sink,
    )
    # Deterministic "today" for the parser.
    from backend.turkish_nlp import RuleBasedTurkishParser

    object.__setattr__(pipeline._s, "parser", RuleBasedTurkishParser(NLP_LEXICON, LOCATIONS, lambda: TODAY))
    return pipeline, model, sink


def ask(p: Pipeline, auth: AuthContext, q: str = QUESTION):  # type: ignore[no-untyped-def]
    return p.run(QueryRequest(question=q, connection_id="demo"), auth)


def test_happy_path(adapter: SQLiteAdapter, knowledge: InMemoryKnowledgeBase, analyst: AuthContext) -> None:
    p, model, _ = build(adapter, knowledge, [GOOD_SQL])
    out = ask(p, analyst)
    assert out.status is OutcomeStatus.ANSWERED and out.attempts == 1
    assert out.report is not None
    assert [r[0] for r in out.report.rows] == ["Bayi A", "Bayi B", "Bayi C", "Bayi E"]
    assert "1.250.000" in out.report.summary
    assert out.report.chart.kind == "bar"
    assert "net_sales@v1" in out.report.metrics_used
    prompt = model.prompts[0].user
    assert "salaries" not in prompt and "tax_number" not in prompt  # RBAC before schema
    assert "taslak kural" not in prompt  # only approved rules


def test_security_violation_is_not_retried(
    adapter: SQLiteAdapter, knowledge: InMemoryKnowledgeBase, analyst: AuthContext
) -> None:
    p, model, _ = build(adapter, knowledge, ["DROP TABLE sales", GOOD_SQL])
    out = ask(p, analyst)
    assert out.status is OutcomeStatus.REJECTED
    assert len(model.prompts) == 1


def test_repairable_error_retries_with_feedback(
    adapter: SQLiteAdapter, knowledge: InMemoryKnowledgeBase, analyst: AuthContext
) -> None:
    p, model, _ = build(adapter, knowledge, ["SELECT nme FROM dealers", GOOD_SQL])
    out = ask(p, analyst)
    assert out.status is OutcomeStatus.ANSWERED and out.attempts == 2
    assert "Sütun bulunamadı: nme" in model.prompts[1].user


def test_retry_budget_is_bounded(
    adapter: SQLiteAdapter, knowledge: InMemoryKnowledgeBase, analyst: AuthContext
) -> None:
    p, model, _ = build(adapter, knowledge, ["SELECT nme FROM dealers"])
    out = ask(p, analyst)
    assert out.status is OutcomeStatus.RETRY_BUDGET_EXHAUSTED
    assert len(model.prompts) == 3


def test_ambiguous_question_asks_back(
    adapter: SQLiteAdapter, knowledge: InMemoryKnowledgeBase, analyst: AuthContext
) -> None:
    p, model, _ = build(adapter, knowledge, [GOOD_SQL])
    out = ask(p, analyst, "İyi bayiler hangileri?")
    assert out.status is OutcomeStatus.NEEDS_CLARIFICATION and out.clarification
    assert model.prompts == []


def test_audit_trail_is_masked(
    adapter: SQLiteAdapter, knowledge: InMemoryKnowledgeBase, analyst: AuthContext
) -> None:
    p, _, sink = build(adapter, knowledge, [GOOD_SQL])
    ask(p, analyst, "12345678901 numaralı bayinin en çok satış yaptığı 3 ay")
    stages = [e.stage for e in sink.events]
    assert stages[0] == "received" and stages[-1] == "outcome"
    assert all("12345678901" not in v for e in sink.events for v in e.details.values())
