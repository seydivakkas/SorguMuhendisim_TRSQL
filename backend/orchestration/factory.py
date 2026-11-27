from __future__ import annotations

from collections.abc import Mapping

from backend.core.config import Settings
from backend.core.contracts import MentionKind
from backend.core.ports import AuditSink, DatabaseAdapter, ModelAdapter
from backend.execution_engine import ExecutionEngine
from backend.knowledge_base import InMemoryKnowledgeBase
from backend.observability import AuditLogger
from backend.orchestration.knowledge import KnowledgeAssembler
from backend.orchestration.pipeline import Pipeline, PipelineStages
from backend.policy_engine import PolicyEngine
from backend.prompt_engine import PromptBuilder
from backend.query_planner import RuleBasedPlanner
from backend.result_engine import ResultBuilder
from backend.schema_linking import LexiconSchemaLinker
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
    """Wire the baseline implementation of every stage.

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
