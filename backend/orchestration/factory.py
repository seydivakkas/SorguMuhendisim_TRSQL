"""Pipeline factories: baseline ``build_default_pipeline`` and v1.0 ``build_hybrid_pipeline``."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import date

from backend.core.config import Settings
from backend.core.contracts import MentionKind
from backend.core.ports import AuditSink, DatabaseAdapter, EmbeddingAdapter, ModelAdapter
from backend.execution_engine import ExecutionEngine
from backend.knowledge_base import InMemoryKnowledgeBase
from backend.observability import AuditLogger, MetricsCollector
from backend.orchestration.knowledge import KnowledgeAssembler
from backend.orchestration.pipeline import Pipeline, PipelineStages
from backend.orchestration.routing import ComplexityRouter
from backend.policy_engine import PolicyEngine
from backend.prompt_engine import MSCHEMA_TEMPLATE_ID, PromptBuilder
from backend.query_planner import RuleBasedPlanner
from backend.rag import DeterministicHashEmbedder, HybridKnowledgeRetriever
from backend.result_engine import ResultBuilder
from backend.schema_linking import HybridSchemaLinker, LexiconSchemaLinker
from backend.semantic_layer import SemanticLayer
from backend.sql_generator import SQLGenerator
from backend.sql_validator import SQLValidator
from backend.turkish_nlp import RuleBasedTurkishParser


def build_default_pipeline(
    *,
    settings: Settings,
    database: DatabaseAdapter,
    model: ModelAdapter,
    knowledge: InMemoryKnowledgeBase,
    nlp_lexicon: Mapping[str, MentionKind],
    schema_lexicon: Mapping[str, str],
    locations: frozenset[str],
    audit_sink: AuditSink,
) -> Pipeline:
    """Wire the baseline implementation of every stage (backward-compatible).

    Swapping a stage (e.g. a Zemberek parser, a hybrid linker, a different
    model) means passing another object that satisfies the same port.
    """
    stages = PipelineStages(
        parser=RuleBasedTurkishParser(nlp_lexicon, locations),
        linker=LexiconSchemaLinker(schema_lexicon),
        knowledge=KnowledgeAssembler(knowledge),
        planner=RuleBasedPlanner(),
        prompts=PromptBuilder(),
        generator=SQLGenerator(model),
        validator=SQLValidator(settings.validation),
        policy=PolicyEngine(settings.execution),
        executor=ExecutionEngine(database),
        results=ResultBuilder(),
    )
    return Pipeline(
        stages=stages,
        schema=database.introspect(),
        audit=AuditLogger(audit_sink),
        retry=settings.retry,
    )


def build_hybrid_pipeline(
    *,
    settings: Settings,
    database: DatabaseAdapter,
    model: ModelAdapter,
    knowledge: InMemoryKnowledgeBase,
    nlp_lexicon: Mapping[str, MentionKind],
    schema_lexicon: Mapping[str, str],
    locations: frozenset[str],
    audit_sink: AuditSink,
    embedder: EmbeddingAdapter | None = None,
    prompt_template_id: str = MSCHEMA_TEMPLATE_ID,
    use_zemberek: bool = False,
    bidirectional_linking: bool = True,
    use_kpi_templates: bool = True,
    metrics: MetricsCollector | None = None,
    today: Callable[[], date] | None = None,
) -> Pipeline:
    """Wire the full v1.0 hybrid TRSQL stack:

    * L2: Turkish morphology-aware parser (optional Zemberek hook)
    * L3: HybridSchemaLinker (lexical + fuzzy + dense + Steiner FK + bidirectional)
    * L4: HybridKnowledgeRetriever (BM25 + Dense + RRF) + SemanticLayer KPI templates
    * L5: Versioned M-Schema prompt builder + ComplexityRouter + consistency voting
    * L6: 8-stage SQLValidator (with knowledge/question) + PolicyEngine
    * L7: ExecutionEngine -> DatabaseAdapter
    * L8/L9: Deterministic ResultBuilder + AuditLogger + MetricsCollector
    """
    schema = database.introspect()
    active_embedder: EmbeddingAdapter = embedder or DeterministicHashEmbedder()
    semantic = SemanticLayer(knowledge)
    retriever = HybridKnowledgeRetriever(
        knowledge,
        embedder=active_embedder,
        settings=settings.rag,
    )
    stages = PipelineStages(
        parser=RuleBasedTurkishParser(
            nlp_lexicon,
            locations,
            today=today or date.today,
            use_zemberek=use_zemberek,
        ),
        linker=HybridSchemaLinker(
            schema_lexicon,
            embedder=active_embedder,
            bidirectional=bidirectional_linking,
        ),
        knowledge=KnowledgeAssembler(
            knowledge,
            retriever=retriever,
            semantic_layer=semantic,
        ),
        planner=RuleBasedPlanner(),
        prompts=PromptBuilder(template_id=prompt_template_id),
        generator=SQLGenerator(model),
        validator=SQLValidator(settings.validation),
        policy=PolicyEngine(settings.execution),
        executor=ExecutionEngine(database),
        results=ResultBuilder(),
    )
    return Pipeline(
        stages=stages,
        schema=schema,
        audit=AuditLogger(audit_sink),
        retry=settings.retry,
        routing=settings.routing,
        router=ComplexityRouter(settings.routing),
        semantic_layer=semantic if use_kpi_templates else None,
        metrics=metrics,
        today=today,
    )
