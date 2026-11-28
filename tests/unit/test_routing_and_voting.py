from __future__ import annotations

from collections.abc import Sequence

import pytest

from backend.core.config import ExecutionSettings, RetrySettings, RoutingSettings, ValidationSettings
from backend.core.contracts import (
    AuthContext,
    Dialect,
    Intent,
    JoinStep,
    LinkedSchema,
    OutcomeStatus,
    ParsedQuestion,
    QueryRequest,
    ReasoningMode,
    SchemaSnapshot,
    SQLCandidate,
    TemporalExpression,
)
from backend.core.errors import SecurityViolation
from backend.database_adapters import SQLiteAdapter
from backend.execution_engine import ExecutionEngine
from backend.knowledge_base import InMemoryKnowledgeBase
from backend.model_engine import FakeModelAdapter
from backend.observability import AuditLogger, InMemoryAuditSink
from backend.orchestration import (
    ComplexityRouter,
    KnowledgeAssembler,
    Pipeline,
    PipelineStages,
    select_consistent_candidate,
    vote_candidates,
)
from backend.policy_engine import PolicyEngine
from backend.prompt_engine import PromptBuilder
from backend.query_planner import RuleBasedPlanner
from backend.result_engine import ResultBuilder
from backend.schema_linking import LexiconSchemaLinker
from backend.semantic_layer import SemanticLayer
from backend.sql_generator import SQLGenerator
from backend.sql_validator import SQLValidator
from backend.turkish_nlp import RuleBasedTurkishParser
from tests.conftest import LOCATIONS, NLP_LEXICON, SCHEMA_LEXICON, TODAY


def _make_parsed(
    intent: Intent = Intent.COUNT,
    *,
    temporal_count: int = 0,
    ambiguities: tuple[str, ...] = (),
) -> ParsedQuestion:
    temporals = tuple(TemporalExpression(text=f"t{i}") for i in range(temporal_count))
    return ParsedQuestion(
        original_text="soru",
        normalized_text="soru",
        intent=intent,
        temporal=temporals,
        ambiguities=ambiguities,
    )


def _make_linked(table_count: int, join_count: int) -> LinkedSchema:
    tables = tuple(f"t{i}" for i in range(table_count))
    joins = tuple(
        JoinStep(
            left_table=f"t{i}",
            left_column="id",
            right_table=f"t{i + 1}",
            right_column="id",
        )
        for i in range(join_count)
    )
    return LinkedSchema(tables=tables, join_path=joins)


def test_complexity_router_direct_vs_thinking_escalation() -> None:
    router = ComplexityRouter(
        RoutingSettings(enabled=True, thinking_threshold=0.5, vote_candidates=4, vote_threshold=0.7)
    )

    simple = router.route(_make_parsed(Intent.COUNT), _make_linked(1, 0), prior_failures=0)
    assert simple.mode is ReasoningMode.DIRECT
    assert simple.num_candidates == 1
    assert simple.complexity_score < 0.5

    medium = router.route(
        _make_parsed(Intent.AGGREGATE, temporal_count=1), _make_linked(3, 2), prior_failures=0
    )
    assert medium.mode is ReasoningMode.THINKING
    assert medium.complexity_score >= 0.5
    assert medium.num_candidates == 1

    hard = router.route(
        _make_parsed(Intent.COMPARISON, temporal_count=2), _make_linked(4, 3), prior_failures=0
    )
    assert hard.mode is ReasoningMode.THINKING
    assert hard.complexity_score >= 0.7
    assert hard.num_candidates == 4


def test_complexity_router_escalates_after_repairable_failure() -> None:
    router = ComplexityRouter(
        RoutingSettings(enabled=True, thinking_threshold=0.5, vote_candidates=3, vote_threshold=0.7)
    )
    decision = router.route(_make_parsed(Intent.COUNT), _make_linked(1, 0), prior_failures=1)
    assert decision.mode is ReasoningMode.THINKING
    assert decision.num_candidates == 3
    assert any("düzeltilebilir" in r for r in decision.reasons)


def test_complexity_router_disabled_stays_direct() -> None:
    router = ComplexityRouter(RoutingSettings(enabled=False, vote_candidates=4))
    decision = router.route(
        _make_parsed(Intent.TREND, temporal_count=2), _make_linked(4, 3), prior_failures=2
    )
    assert decision.mode is ReasoningMode.DIRECT
    assert decision.num_candidates == 1


def test_consistency_voting_majority_wins(
    adapter: SQLiteAdapter,
    schema: SchemaSnapshot,
    analyst: AuthContext,
) -> None:
    validator = SQLValidator(ValidationSettings())
    policy = PolicyEngine(ExecutionSettings())
    executor = ExecutionEngine(adapter)

    candidates = [
        SQLCandidate(
            sql="SELECT COUNT(dealer_id) AS adet FROM dealers WHERE city = 'Rize'",
            dialect=Dialect.SQLITE,
            model_id="m",
            attempt=1,
        ),
        SQLCandidate(
            sql="SELECT COUNT(dealer_id) AS sayi FROM dealers WHERE city = 'Trabzon'",
            dialect=Dialect.SQLITE,
            model_id="m",
            attempt=1,
        ),
        SQLCandidate(
            sql="SELECT nonexistent_col FROM dealers",
            dialect=Dialect.SQLITE,
            model_id="m",
            attempt=1,
        ),
        SQLCandidate(
            sql="SELECT COUNT(dealer_id) AS toplam FROM dealers WHERE city = 'Trabzon'",
            dialect=Dialect.SQLITE,
            model_id="m",
            attempt=1,
        ),
    ]

    approved, result, attempts = select_consistent_candidate(
        candidates,
        schema=schema,
        auth=analyst,
        validator=validator,
        policy=policy,
        executor=executor,
    )
    assert attempts == 4
    assert result.rows == ((4,),)
    assert "Trabzon" in approved.sql


def test_consistency_voting_security_stops_immediately_without_execution(
    schema: SchemaSnapshot,
    analyst: AuthContext,
) -> None:
    class _ForbiddenExecutor:
        def __init__(self) -> None:
            self.calls = 0

        def run(self, query: object) -> object:
            self.calls += 1
            raise AssertionError("Executor must NEVER be called when any candidate triggers SECURITY")

    validator = SQLValidator(ValidationSettings())
    policy = PolicyEngine(ExecutionSettings())
    executor = _ForbiddenExecutor()

    candidates = [
        SQLCandidate(sql="SELECT name FROM dealers", dialect=Dialect.SQLITE, model_id="m", attempt=1),
        SQLCandidate(sql="DROP TABLE sales", dialect=Dialect.SQLITE, model_id="m", attempt=1),
        SQLCandidate(sql="SELECT city FROM dealers", dialect=Dialect.SQLITE, model_id="m", attempt=1),
    ]

    outcome = vote_candidates(
        candidates,
        schema=schema,
        auth=analyst,
        validator=validator,
        policy=policy,
        executor=executor,  # type: ignore[arg-type]
    )
    assert outcome.verdict is not None and outcome.verdict.value == "rejected"
    assert executor.calls == 0

    with pytest.raises(SecurityViolation):
        select_consistent_candidate(
            candidates,
            schema=schema,
            auth=analyst,
            validator=validator,
            policy=policy,
            executor=executor,  # type: ignore[arg-type]
        )
    assert executor.calls == 0


def test_deterministic_kpi_template_shortcut_skips_llm(
    adapter: SQLiteAdapter,
    schema: SchemaSnapshot,
    knowledge: InMemoryKnowledgeBase,
    analyst: AuthContext,
) -> None:
    def _build(responses: Sequence[str]) -> tuple[Pipeline, FakeModelAdapter]:
        model = FakeModelAdapter(responses)
        stages = PipelineStages(
            parser=RuleBasedTurkishParser(NLP_LEXICON, LOCATIONS, today=lambda: TODAY),
            linker=LexiconSchemaLinker(SCHEMA_LEXICON),
            knowledge=KnowledgeAssembler(knowledge),
            planner=RuleBasedPlanner(),
            prompts=PromptBuilder(),
            generator=SQLGenerator(model),
            validator=SQLValidator(ValidationSettings()),
            policy=PolicyEngine(ExecutionSettings()),
            executor=ExecutionEngine(adapter),
            results=ResultBuilder(),
        )
        pipe = Pipeline(
            stages=stages,
            schema=schema,
            audit=AuditLogger(InMemoryAuditSink()),
            retry=RetrySettings(max_attempts=3),
            semantic_layer=SemanticLayer(knowledge),
            today=lambda: TODAY,
        )
        return pipe, model

    pipeline, model = _build(["SELECT 1"])
    out = pipeline.run(QueryRequest(question="Net satış tutarı nedir?", connection_id="demo"), analyst)
    assert out.status is OutcomeStatus.ANSWERED
    assert model.prompts == []
    assert out.report is not None
    assert out.report.rows == ((5459999.0,),)

    # Unauthorized user without access to `sales` must not use template shortcut.
    no_sales_auth = analyst.model_copy(update={"allowed_tables": frozenset({"dealers"})})
    out_denied = pipeline.run(
        QueryRequest(question="Net satış tutarı nedir?", connection_id="demo"),
        no_sales_auth,
    )
    assert out_denied.status is OutcomeStatus.ANSWERED
    assert len(model.prompts) == 1
