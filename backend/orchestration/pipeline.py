from __future__ import annotations

from dataclasses import dataclass

from backend.auth import scope_schema
from backend.core.config import RetrySettings
from backend.core.contracts import (
    AuthContext,
    OutcomeStatus,
    PipelineOutcome,
    QueryRequest,
    SchemaSnapshot,
    Verdict,
)
from backend.core.errors import ExecutionError, SecurityViolation
from backend.core.ports import (
    KnowledgeProvider,
    PolicyEnforcer,
    PromptBuilderPort,
    QueryExecutor,
    QueryPlannerPort,
    QuestionParser,
    ResultBuilderPort,
    SchemaLinker,
    SQLGeneratorPort,
    SQLValidatorPort,
)
from backend.observability import AuditLogger

REJECTED_MESSAGE = "Bu istek güvenlik politikası nedeniyle yerine getirilemedi."


@dataclass(frozen=True)
class PipelineStages:
    parser: QuestionParser
    linker: SchemaLinker
    knowledge: KnowledgeProvider
    planner: QueryPlannerPort
    prompts: PromptBuilderPort
    generator: SQLGeneratorPort
    validator: SQLValidatorPort
    policy: PolicyEnforcer
    executor: QueryExecutor
    results: ResultBuilderPort


class Pipeline:
    """One request, start to finish.

    Three failure classes are handled differently (ADR-0005, ADR-0006):

    * ambiguous question     → ``NEEDS_CLARIFICATION`` (ask the user, no SQL)
    * repairable SQL error   → regenerate with feedback, at most
      ``retry.max_attempts`` attempts in total, then ``RETRY_BUDGET_EXHAUSTED``
    * security violation     → ``REJECTED`` immediately, never retried, and
      the model never sees why
    """

    def __init__(
        self,
        stages: PipelineStages,
        schema: SchemaSnapshot,
        audit: AuditLogger,
        retry: RetrySettings | None = None,
    ) -> None:
        self._s = stages
        self._schema = schema
        self._audit = audit
        self._retry = retry or RetrySettings()

    def run(self, request: QueryRequest, auth: AuthContext) -> PipelineOutcome:
        rid = request.request_id
        log = self._audit.record

        def outcome(status: OutcomeStatus, attempts: int = 0, **kw: object) -> PipelineOutcome:
            log(rid, auth, "outcome", status.value, attempts=attempts)
            return PipelineOutcome(request_id=rid, status=status, attempts=attempts, **kw)

        log(rid, auth, "received", "ok", question=request.question)

        # L1: RBAC before any schema access (ADR-0004)
        scoped = scope_schema(self._schema, auth)
        log(rid, auth, "scope_schema", "ok", tables=len(scoped.tables))

        # L2
        parsed = self._s.parser.parse(request.question)
        log(rid, auth, "parse", "ok", intent=parsed.intent.value)
        if parsed.is_ambiguous:
            return outcome(OutcomeStatus.NEEDS_CLARIFICATION, clarification=" ".join(parsed.ambiguities))

        # L3 + L4
        linked = self._s.linker.link(parsed, scoped)
        knowledge = self._s.knowledge.context_for(parsed, linked)
        plan = self._s.planner.plan(parsed, linked, knowledge)
        log(rid, auth, "plan", "ok", tables=",".join(plan.tables), metrics=len(plan.metrics))

        # L5 + L6 with bounded retry
        feedback: tuple[str, ...] = ()
        for attempt in range(1, self._retry.max_attempts + 1):
            prompt = self._s.prompts.build(plan, scoped, knowledge, parsed, feedback)
            candidate = self._s.generator.generate(prompt, scoped.dialect, attempt)
            report = self._s.validator.validate(candidate, self._schema, auth)
            log(rid, auth, "validate", report.verdict.value, attempt=attempt, sql=candidate.sql)

            if report.verdict is Verdict.REJECTED:
                return outcome(OutcomeStatus.REJECTED, attempt, reason=REJECTED_MESSAGE)
            if report.verdict is Verdict.REPAIRABLE:
                feedback = tuple(f.message for f in report.failures)
                continue

            # L6 policy → L7 → L8
            try:
                approved = self._s.policy.approve(report, auth)
                result = self._s.executor.run(approved)
            except SecurityViolation:
                return outcome(OutcomeStatus.REJECTED, attempt, reason=REJECTED_MESSAGE)
            except ExecutionError as exc:
                return outcome(OutcomeStatus.ERROR, attempt, reason=str(exc))
            log(rid, auth, "execute", "ok", rows=result.row_count, ms=round(result.elapsed_ms, 1))
            report_out = self._s.results.build(parsed, plan, approved, result)
            return outcome(OutcomeStatus.ANSWERED, attempt, report=report_out)

        return outcome(
            OutcomeStatus.RETRY_BUDGET_EXHAUSTED,
            self._retry.max_attempts,
            reason="Geçerli bir sorgu üretilemedi; lütfen soruyu yeniden ifade edin.",
        )
