"""Ports (interfaces) between layers.

Modules implement these Protocols; ``orchestration`` depends only on the
Protocols, never on concrete classes.  This is what keeps the system
model-agnostic (ADR-0003) and database-agnostic (principle 08).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from backend.core.contracts import (
    ApprovedQuery,
    AuditEvent,
    AuthContext,
    Dialect,
    ExecutionResult,
    GenerationParams,
    KnowledgeContext,
    LinkedSchema,
    ModelInfo,
    ParsedQuestion,
    PromptBundle,
    QueryPlan,
    ResultReport,
    SchemaSnapshot,
    SQLCandidate,
    ValidationReport,
)


@runtime_checkable
class ModelAdapter(Protocol):
    """Any local LLM backend (llama.cpp, ONNX Runtime, a test fake...).

    A ModelAdapter receives a prompt and returns text. It has **no** access
    to a database connection, credentials, or the file system of the data
    sources. Its output is untrusted input for L6.
    """

    @property
    def info(self) -> ModelInfo: ...

    def generate(self, prompt: PromptBundle, params: GenerationParams) -> str: ...


@runtime_checkable
class DatabaseAdapter(Protocol):
    """Dialect-specific database access. Only ``execution_engine`` calls
    :meth:`execute`; introspection runs when a connection is registered."""

    @property
    def dialect(self) -> Dialect: ...

    def introspect(self) -> SchemaSnapshot: ...

    def execute(self, query: ApprovedQuery) -> ExecutionResult: ...


class AuditSink(Protocol):
    def emit(self, event: AuditEvent) -> None: ...


# --- Pipeline stage ports (used by orchestration) ---------------------------


class QuestionParser(Protocol):
    def parse(self, question: str) -> ParsedQuestion: ...


class SchemaLinker(Protocol):
    def link(self, question: ParsedQuestion, schema: SchemaSnapshot) -> LinkedSchema: ...


class KnowledgeProvider(Protocol):
    def context_for(self, question: ParsedQuestion, linked: LinkedSchema) -> KnowledgeContext: ...


class QueryPlannerPort(Protocol):
    def plan(
        self, question: ParsedQuestion, linked: LinkedSchema, knowledge: KnowledgeContext
    ) -> QueryPlan: ...


class PromptBuilderPort(Protocol):
    def build(
        self,
        plan: QueryPlan,
        schema: SchemaSnapshot,
        knowledge: KnowledgeContext,
        question: ParsedQuestion,
        feedback: tuple[str, ...] = (),
    ) -> PromptBundle: ...


class SQLGeneratorPort(Protocol):
    def generate(self, prompt: PromptBundle, dialect: Dialect, attempt: int) -> SQLCandidate: ...


class SQLValidatorPort(Protocol):
    def validate(
        self, candidate: SQLCandidate, schema: SchemaSnapshot, auth: AuthContext
    ) -> ValidationReport: ...


class PolicyEnforcer(Protocol):
    def approve(self, report: ValidationReport, auth: AuthContext) -> ApprovedQuery: ...


class QueryExecutor(Protocol):
    def run(self, query: ApprovedQuery) -> ExecutionResult: ...


class ResultBuilderPort(Protocol):
    def build(
        self, question: ParsedQuestion, plan: QueryPlan, query: ApprovedQuery, result: ExecutionResult
    ) -> ResultReport: ...
