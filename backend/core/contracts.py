"""Data contracts shared by every TRSQL module.

These Pydantic models are the *only* objects that cross module boundaries.
They are immutable (``frozen=True``) and reject unknown fields
(``extra="forbid"``) so that a layer cannot silently smuggle data into
another layer.  See ``docs/architecture/data-contracts.md``.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Contract(BaseModel):
    """Base class for all cross-module contracts."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class Dialect(StrEnum):
    SQLITE = "sqlite"
    POSTGRES = "postgres"


# --------------------------------------------------------------------------- #
# L1 — API & Security Gateway
# --------------------------------------------------------------------------- #


class AuthContext(Contract):
    """Who is asking and what they may see.  Built *before* any schema access."""

    user_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    roles: frozenset[str] = frozenset()
    allowed_tables: frozenset[str]
    """Lower-case table names the user may read. Empty set means: nothing."""
    denied_columns: frozenset[str] = frozenset()
    """Lower-case ``table.column`` names that must never be returned."""
    max_rows: int = Field(default=1000, gt=0)


class QueryRequest(Contract):
    request_id: UUID = Field(default_factory=uuid4)
    question: str = Field(min_length=1, max_length=2000)
    connection_id: str = Field(min_length=1)
    session_id: str | None = None


# --------------------------------------------------------------------------- #
# Database schema (produced by database_adapters, enriched by schema_intelligence)
# --------------------------------------------------------------------------- #


class ColumnInfo(Contract):
    name: str
    data_type: str
    nullable: bool = True
    is_primary_key: bool = False
    description: str | None = None


class ForeignKey(Contract):
    column: str
    ref_table: str
    ref_column: str


class TableInfo(Contract):
    name: str
    columns: tuple[ColumnInfo, ...]
    foreign_keys: tuple[ForeignKey, ...] = ()
    description: str | None = None
    schema_name: str | None = None

    def column(self, name: str) -> ColumnInfo | None:
        lowered = name.lower()
        return next((c for c in self.columns if c.name.lower() == lowered), None)

    @property
    def resolved_schema(self) -> str | None:
        if self.schema_name:
            return self.schema_name.lower()
        if "." in self.name:
            return self.name.split(".", 1)[0].lower()
        return None

    @property
    def unqualified_name(self) -> str:
        return self.name.rsplit(".", 1)[-1].lower()

    @property
    def qualified_name(self) -> str:
        schema = self.resolved_schema
        base = self.unqualified_name
        return f"{schema}.{base}" if schema else base


class SchemaSnapshot(Contract):
    dialect: Dialect
    tables: tuple[TableInfo, ...]

    def table(self, name: str) -> TableInfo | None:
        lowered = name.lower()
        exact = next((t for t in self.tables if t.name.lower() == lowered), None)
        if exact is not None:
            return exact
        return next((t for t in self.tables if t.qualified_name == lowered), None)

    def tables_for_name(self, name: str) -> tuple[TableInfo, ...]:
        lowered = name.lower()
        return tuple(
            t
            for t in self.tables
            if t.unqualified_name == lowered or t.qualified_name == lowered or t.name.lower() == lowered
        )

    @property
    def table_names(self) -> frozenset[str]:
        return frozenset(t.name.lower() for t in self.tables)


# --------------------------------------------------------------------------- #
# L2 — Turkish NLP Intelligence
# --------------------------------------------------------------------------- #


class Intent(StrEnum):
    LOOKUP = "lookup"
    COUNT = "count"
    AGGREGATE = "aggregate"
    RANKING = "ranking"
    COMPARISON = "comparison"
    TREND = "trend"
    UNKNOWN = "unknown"


class SortDirection(StrEnum):
    ASC = "asc"
    DESC = "desc"


class MentionKind(StrEnum):
    ENTITY = "entity"
    LOCATION = "location"
    METRIC = "metric"
    VALUE = "value"


class Mention(Contract):
    text: str
    kind: MentionKind
    lemma: str | None = None


class TemporalExpression(Contract):
    text: str
    start: date | None = None
    end: date | None = None
    """Inclusive start, exclusive end."""


class ParsedQuestion(Contract):
    original_text: str
    normalized_text: str
    intent: Intent = Intent.UNKNOWN
    mentions: tuple[Mention, ...] = ()
    temporal: tuple[TemporalExpression, ...] = ()
    sort: SortDirection | None = None
    limit: int | None = Field(default=None, gt=0)
    ambiguities: tuple[str, ...] = ()
    """Human-readable Turkish descriptions of unresolved ambiguity."""

    @property
    def is_ambiguous(self) -> bool:
        return bool(self.ambiguities)


# --------------------------------------------------------------------------- #
# L3 — Schema Linking Intelligence
# --------------------------------------------------------------------------- #


class SchemaLink(Contract):
    mention: str
    table: str
    column: str | None = None
    score: float = Field(ge=0.0, le=1.0)


class JoinStep(Contract):
    left_table: str
    left_column: str
    right_table: str
    right_column: str


class LinkedSchema(Contract):
    tables: tuple[str, ...]
    links: tuple[SchemaLink, ...] = ()
    join_path: tuple[JoinStep, ...] = ()


# --------------------------------------------------------------------------- #
# L4 — Enterprise RAG & Semantic Layer
# --------------------------------------------------------------------------- #


class BusinessRule(Contract):
    rule_id: str
    term: str
    definition: str
    sql_fragment: str | None = None
    source: str
    approved: bool = False


class MetricDefinition(Contract):
    metric_id: str
    name: str
    expression: str
    base_table: str
    filters: tuple[str, ...] = ()
    version: int = Field(default=1, ge=1)
    synonyms: tuple[str, ...] = ()


class FewShotExample(Contract):
    question: str
    sql: str
    dialect: Dialect


class KnowledgeContext(Contract):
    rules: tuple[BusinessRule, ...] = ()
    metrics: tuple[MetricDefinition, ...] = ()
    examples: tuple[FewShotExample, ...] = ()


# --------------------------------------------------------------------------- #
# L5 — SQL Generation Intelligence
# --------------------------------------------------------------------------- #


class QueryPlan(Contract):
    intent: Intent
    tables: tuple[str, ...]
    metrics: tuple[MetricDefinition, ...] = ()
    filters: tuple[str, ...] = ()
    temporal: tuple[TemporalExpression, ...] = ()
    sort: SortDirection | None = None
    limit: int | None = None


class PromptBundle(Contract):
    template_id: str
    system: str
    user: str


class GenerationParams(Contract):
    max_tokens: int = Field(default=512, gt=0)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    stop: tuple[str, ...] = ()


class ModelInfo(Contract):
    model_id: str
    quantization: str | None = None
    context_length: int = Field(gt=0)
    vram_mb_estimate: int | None = None
    sha256: str | None = None


class ReasoningMode(StrEnum):
    DIRECT = "direct"
    THINKING = "thinking"


class RoutingDecision(Contract):
    mode: ReasoningMode
    num_candidates: int = Field(ge=1)
    complexity_score: float = Field(ge=0.0, le=1.0)
    reasons: tuple[str, ...] = ()


class SQLCandidate(Contract):
    sql: str
    dialect: Dialect
    model_id: str
    attempt: int = Field(ge=1)
    latency_ms: float = Field(default=0.0, ge=0.0)
    reasoning: str | None = None


# --------------------------------------------------------------------------- #
# L6 — SQL Verification & Security
# --------------------------------------------------------------------------- #


class CheckName(StrEnum):
    SYNTAX = "syntax"
    AST = "ast"
    SCHEMA = "schema"
    SEMANTIC = "semantic"
    AUTHORIZATION = "authorization"
    BUSINESS_RULE = "business_rule"
    COST = "cost"
    INJECTION = "injection"


class Severity(StrEnum):
    INFO = "info"
    REPAIRABLE = "repairable"
    """The model may try again with feedback (bounded by the retry budget)."""
    SECURITY = "security"
    """Hard stop. Never sent back to the model. See ADR-0005."""


class CheckResult(Contract):
    check: CheckName
    passed: bool
    severity: Severity = Severity.INFO
    message: str = ""


class Verdict(StrEnum):
    APPROVED = "approved"
    REPAIRABLE = "repairable"
    REJECTED = "rejected"


class ValidationReport(Contract):
    candidate: SQLCandidate
    checks: tuple[CheckResult, ...]

    @property
    def verdict(self) -> Verdict:
        failed = [c for c in self.checks if not c.passed]
        if any(c.severity is Severity.SECURITY for c in failed):
            return Verdict.REJECTED
        if failed:
            return Verdict.REPAIRABLE
        return Verdict.APPROVED

    @property
    def failures(self) -> tuple[CheckResult, ...]:
        return tuple(c for c in self.checks if not c.passed)


class ApprovedQuery(Contract):
    """The only object the execution engine accepts.

    It cannot be constructed from a report that is not APPROVED, so the
    model's raw text can never reach the database (ADR-0004).
    """

    sql: str
    dialect: Dialect
    report: ValidationReport
    max_rows: int = Field(gt=0)
    timeout_ms: int = Field(gt=0)
    # Identity the query was approved for. Adapters use it for database-level
    # defense in depth (SQLite authorizer allow-list, PostgreSQL RLS context).
    auth: AuthContext | None = None

    @model_validator(mode="after")
    def _must_be_approved(self) -> ApprovedQuery:
        if self.report.verdict is not Verdict.APPROVED:
            raise ValueError("ApprovedQuery requires an APPROVED validation report")
        if self.dialect is not self.report.candidate.dialect:
            raise ValueError("dialect mismatch between query and validated candidate")
        return self


# --------------------------------------------------------------------------- #
# L7 — Database Execution Engine
# --------------------------------------------------------------------------- #


class ExecutionResult(Contract):
    columns: tuple[str, ...]
    rows: tuple[tuple[Any, ...], ...]
    truncated: bool = False
    elapsed_ms: float = Field(default=0.0, ge=0.0)

    @property
    def row_count(self) -> int:
        return len(self.rows)


# --------------------------------------------------------------------------- #
# L8 — Result Intelligence
# --------------------------------------------------------------------------- #


class ChartSpec(Contract):
    kind: Literal["bar", "line", "pie", "table"]
    x: str | None = None
    y: str | None = None


class ResultReport(Contract):
    title: str
    summary: str
    """Turkish explanation built deterministically from the result rows."""
    columns: tuple[str, ...]
    rows: tuple[tuple[Any, ...], ...]
    chart: ChartSpec
    sql: str
    metrics_used: tuple[str, ...] = ()
    truncated: bool = False


# --------------------------------------------------------------------------- #
# Pipeline outcome & L9 — Evaluation & Observability
# --------------------------------------------------------------------------- #


class OutcomeStatus(StrEnum):
    ANSWERED = "answered"
    NEEDS_CLARIFICATION = "needs_clarification"
    REJECTED = "rejected"
    RETRY_BUDGET_EXHAUSTED = "retry_budget_exhausted"
    ERROR = "error"


class PipelineOutcome(Contract):
    request_id: UUID
    status: OutcomeStatus
    attempts: int = Field(default=0, ge=0)
    report: ResultReport | None = None
    clarification: str | None = None
    reason: str | None = None


class AuditEvent(Contract):
    request_id: UUID
    stage: str
    status: str
    user_id: str
    tenant_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    details: dict[str, str] = Field(default_factory=dict)
