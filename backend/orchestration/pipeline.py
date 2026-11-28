"""Pipeline orchestration: L1 -> L9 request lifecycle, routing, voting, and HITL preview."""

from __future__ import annotations

import inspect
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from backend.auth import scope_schema
from backend.core.config import RetrySettings, RoutingSettings
from backend.core.contracts import (
    AuthContext,
    Dialect,
    Intent,
    JoinStep,
    KnowledgeContext,
    OutcomeStatus,
    ParsedQuestion,
    PipelineOutcome,
    PromptBundle,
    QueryPlan,
    QueryRequest,
    ReasoningMode,
    RoutingDecision,
    SchemaSnapshot,
    SortDirection,
    SQLCandidate,
    TemporalExpression,
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
from backend.observability import AuditLogger, MetricsCollector
from backend.orchestration.routing import ComplexityRouter
from backend.orchestration.voting import validate_with_context, vote_candidates
from backend.semantic_layer import SemanticLayer

REJECTED_MESSAGE = "Bu istek güvenlik politikası nedeniyle yerine getirilemedi."


class PlanPreview(BaseModel):
    """HITL preview returned by ``Pipeline.preview_plan`` without executing SQL."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    request_id: UUID
    status: OutcomeStatus
    intent: Intent
    tables: tuple[str, ...] = ()
    columns: tuple[str, ...] = ()
    join_path: tuple[JoinStep, ...] = ()
    metrics: tuple[str, ...] = ()
    rules: tuple[str, ...] = ()
    temporal: tuple[TemporalExpression, ...] = ()
    sort: SortDirection | None = None
    limit: int | None = None
    clarification: str | None = None
    routing: RoutingDecision | None = None
    template_matched: str | None = None


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


def _build_prompt(
    prompts: PromptBuilderPort,
    plan: QueryPlan,
    scoped: SchemaSnapshot,
    knowledge: KnowledgeContext,
    parsed: ParsedQuestion,
    feedback: tuple[str, ...],
    mode: ReasoningMode,
) -> PromptBundle:
    try:
        sig = inspect.signature(prompts.build)
        params = sig.parameters
        supports_kwargs = any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values())
        if supports_kwargs or "reasoning_mode" in params:
            return prompts.build(
                plan,
                scoped,
                knowledge,
                parsed,
                feedback,
                reasoning_mode=mode,  # type: ignore[call-arg]
            )
    except (TypeError, ValueError):
        pass
    return prompts.build(plan, scoped, knowledge, parsed, feedback)


def _generate_candidates(
    generator: SQLGeneratorPort,
    prompt: PromptBundle,
    dialect: Dialect,
    attempt: int,
    n: int,
) -> list[SQLCandidate]:
    if n <= 1:
        return [generator.generate(prompt, dialect, attempt)]
    gen_multi = getattr(generator, "generate_candidates", None)
    if callable(gen_multi):
        result = gen_multi(prompt, dialect, attempt, n=n)
        if isinstance(result, list):
            return list(result)
    return [generator.generate(prompt, dialect, attempt) for _ in range(n)]


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
        *,
        routing: RoutingSettings | None = None,
        router: ComplexityRouter | None = None,
        semantic_layer: SemanticLayer | None = None,
        metrics: MetricsCollector | None = None,
        today: Callable[[], date] | None = None,
    ) -> None:
        self._s = stages
        self._schema = schema
        self._audit = audit
        self._retry = retry or RetrySettings()
        self._router: ComplexityRouter | None = (
            router if router is not None else (ComplexityRouter(routing) if routing is not None else None)
        )
        self._semantic_layer = semantic_layer
        self._metrics = metrics
        self._today = today

    def _record_latency(self, stage: str, started: float) -> None:
        if self._metrics is not None:
            self._metrics.record_stage_latency(stage, (time.perf_counter() - started) * 1000.0)

    def preview_plan(self, request: QueryRequest, auth: AuthContext) -> PlanPreview:
        """Build an RBAC-scoped table, join, metric, and routing preview without executing SQL."""
        rid = request.request_id
        log = self._audit.record
        log(rid, auth, "received", "ok", question=request.question, mode="preview")

        t0 = time.perf_counter()
        scoped = scope_schema(self._schema, auth)
        self._record_latency("scope_schema", t0)
        log(rid, auth, "scope_schema", "ok", tables=len(scoped.tables))

        t1 = time.perf_counter()
        parsed = self._s.parser.parse(request.question)
        self._record_latency("parse", t1)
        log(rid, auth, "parse", "ok", intent=parsed.intent.value)

        if parsed.is_ambiguous:
            if self._metrics is not None:
                self._metrics.record_clarification()
            log(rid, auth, "plan_preview", "needs_clarification")
            return PlanPreview(
                request_id=rid,
                status=OutcomeStatus.NEEDS_CLARIFICATION,
                intent=parsed.intent,
                temporal=parsed.temporal,
                sort=parsed.sort,
                limit=parsed.limit,
                clarification=" ".join(parsed.ambiguities),
            )

        t2 = time.perf_counter()
        linked = self._s.linker.link(parsed, scoped)
        self._record_latency("link", t2)

        t3 = time.perf_counter()
        knowledge = self._s.knowledge.context_for(parsed, linked)
        self._record_latency("knowledge", t3)

        t4 = time.perf_counter()
        plan = self._s.planner.plan(parsed, linked, knowledge)
        self._record_latency("plan", t4)

        decision: RoutingDecision | None = None
        if self._router is not None:
            decision = self._router.route(parsed, linked, prior_failures=0)

        template_id: str | None = None
        if self._semantic_layer is not None:
            today_val = self._today() if self._today is not None else None
            match = self._semantic_layer.resolve_template(
                parsed,
                linked,
                dialect=scoped.dialect,
                schema=scoped,
                denied_columns=auth.denied_columns,
                today=today_val,
            )
            if match is not None:
                template_id = match.template_id

        linked_cols = tuple(
            dict.fromkeys(f"{lnk.table}.{lnk.column}" for lnk in linked.links if lnk.column is not None)
        )
        log(rid, auth, "plan_preview", "ok", tables=",".join(plan.tables), metrics=len(plan.metrics))
        return PlanPreview(
            request_id=rid,
            status=OutcomeStatus.ANSWERED,
            intent=plan.intent,
            tables=plan.tables,
            columns=linked_cols,
            join_path=linked.join_path,
            metrics=tuple(f"{m.metric_id}@v{m.version}" for m in plan.metrics),
            rules=tuple(r.term for r in knowledge.rules),
            temporal=plan.temporal,
            sort=plan.sort,
            limit=plan.limit,
            routing=decision,
            template_matched=template_id,
        )

    def run(self, request: QueryRequest, auth: AuthContext) -> PipelineOutcome:
        rid = request.request_id
        log = self._audit.record

        def outcome(status: OutcomeStatus, attempts: int = 0, **kw: object) -> PipelineOutcome:
            if self._metrics is not None:
                self._metrics.record_outcome(status)
            log(rid, auth, "outcome", status.value, attempts=attempts)
            return PipelineOutcome(request_id=rid, status=status, attempts=attempts, **kw)

        log(rid, auth, "received", "ok", question=request.question)

        # L1: RBAC before any schema access (ADR-0004)
        t0 = time.perf_counter()
        scoped = scope_schema(self._schema, auth)
        self._record_latency("scope_schema", t0)
        log(rid, auth, "scope_schema", "ok", tables=len(scoped.tables))

        # L2
        t1 = time.perf_counter()
        parsed = self._s.parser.parse(request.question)
        self._record_latency("parse", t1)
        log(rid, auth, "parse", "ok", intent=parsed.intent.value)
        if parsed.is_ambiguous:
            if self._metrics is not None:
                self._metrics.record_clarification()
            return outcome(OutcomeStatus.NEEDS_CLARIFICATION, clarification=" ".join(parsed.ambiguities))

        # L3 + L4 + L5 plan
        t2 = time.perf_counter()
        linked = self._s.linker.link(parsed, scoped)
        self._record_latency("link", t2)

        t3 = time.perf_counter()
        knowledge = self._s.knowledge.context_for(parsed, linked)
        self._record_latency("knowledge", t3)

        t4 = time.perf_counter()
        plan = self._s.planner.plan(parsed, linked, knowledge)
        self._record_latency("plan", t4)
        log(rid, auth, "plan", "ok", tables=",".join(plan.tables), metrics=len(plan.metrics))

        # L4/L6 deterministic KPI template shortcut (ADR-0008): still validated by L6 + PolicyEngine!
        if self._semantic_layer is not None:
            today_val = self._today() if self._today is not None else None
            match = self._semantic_layer.resolve_template(
                parsed,
                linked,
                dialect=scoped.dialect,
                schema=scoped,
                denied_columns=auth.denied_columns,
                today=today_val,
            )
            if match is not None and match.bypass_llm:
                tmpl_candidate = match.to_sql_candidate(attempt=1)
                t_val = time.perf_counter()
                tmpl_report = validate_with_context(
                    self._s.validator,
                    tmpl_candidate,
                    self._schema,
                    auth,
                    knowledge=knowledge,
                    question=request.question,
                )
                self._record_latency("validate", t_val)
                log(
                    rid,
                    auth,
                    "template_bypass",
                    tmpl_report.verdict.value,
                    template_id=match.template_id,
                    sql=tmpl_candidate.sql,
                )
                if tmpl_report.verdict is Verdict.REJECTED:
                    if self._metrics is not None:
                        self._metrics.record_security_violation("template")
                    return outcome(OutcomeStatus.REJECTED, 1, reason=REJECTED_MESSAGE)
                if tmpl_report.verdict is Verdict.APPROVED:
                    try:
                        approved = self._s.policy.approve(tmpl_report, auth)
                        t_exec = time.perf_counter()
                        result = self._s.executor.run(approved)
                        self._record_latency("execute", t_exec)
                    except SecurityViolation:
                        if self._metrics is not None:
                            self._metrics.record_security_violation("policy")
                        return outcome(OutcomeStatus.REJECTED, 1, reason=REJECTED_MESSAGE)
                    except ExecutionError as exc:
                        return outcome(OutcomeStatus.ERROR, 1, reason=str(exc))
                    if self._metrics is not None:
                        self._metrics.record_template_bypass(match.template_id)
                    log(rid, auth, "execute", "ok", rows=result.row_count, ms=round(result.elapsed_ms, 1))
                    t_res = time.perf_counter()
                    report_out = self._s.results.build(parsed, plan, approved, result)
                    self._record_latency("results", t_res)
                    return outcome(OutcomeStatus.ANSWERED, 1, report=report_out)

        # L5 + L6 with bounded retry + optional ComplexityRouter & consistency voting
        feedback: tuple[str, ...] = ()
        for attempt in range(1, self._retry.max_attempts + 1):
            if self._router is not None:
                decision = self._router.route(parsed, linked, prior_failures=attempt - 1)
                if self._metrics is not None:
                    self._metrics.record_routing(decision.mode.value, decision.num_candidates)
                log(
                    rid,
                    auth,
                    "route",
                    decision.mode.value,
                    candidates=decision.num_candidates,
                    score=decision.complexity_score,
                )
            else:
                decision = RoutingDecision(
                    mode=ReasoningMode.DIRECT,
                    num_candidates=1,
                    complexity_score=0.0,
                )

            prompt = _build_prompt(
                self._s.prompts,
                plan,
                scoped,
                knowledge,
                parsed,
                feedback,
                decision.mode,
            )

            if decision.num_candidates <= 1:
                t_gen = time.perf_counter()
                candidate = self._s.generator.generate(prompt, scoped.dialect, attempt)
                self._record_latency("generate", t_gen)

                t_val = time.perf_counter()
                report = validate_with_context(
                    self._s.validator,
                    candidate,
                    self._schema,
                    auth,
                    knowledge=knowledge,
                    question=request.question,
                )
                self._record_latency("validate", t_val)
                log(rid, auth, "validate", report.verdict.value, attempt=attempt, sql=candidate.sql)

                if report.verdict is Verdict.REJECTED:
                    if self._metrics is not None:
                        self._metrics.record_security_violation("validator")
                    return outcome(OutcomeStatus.REJECTED, attempt, reason=REJECTED_MESSAGE)
                if report.verdict is Verdict.REPAIRABLE:
                    if self._metrics is not None:
                        self._metrics.record_retry("validate")
                    feedback = tuple(f.message for f in report.failures)
                    continue

                try:
                    approved = self._s.policy.approve(report, auth)
                    t_exec = time.perf_counter()
                    result = self._s.executor.run(approved)
                    self._record_latency("execute", t_exec)
                except SecurityViolation:
                    if self._metrics is not None:
                        self._metrics.record_security_violation("policy")
                    return outcome(OutcomeStatus.REJECTED, attempt, reason=REJECTED_MESSAGE)
                except ExecutionError as exc:
                    return outcome(OutcomeStatus.ERROR, attempt, reason=str(exc))

                log(rid, auth, "execute", "ok", rows=result.row_count, ms=round(result.elapsed_ms, 1))
                t_res = time.perf_counter()
                report_out = self._s.results.build(parsed, plan, approved, result)
                self._record_latency("results", t_res)
                return outcome(OutcomeStatus.ANSWERED, attempt, report=report_out)

            # Multi-candidate consistency voting path
            t_gen = time.perf_counter()
            candidates = _generate_candidates(
                self._s.generator,
                prompt,
                scoped.dialect,
                attempt,
                decision.num_candidates,
            )
            self._record_latency("generate", t_gen)

            def _audit_candidate(
                cand: SQLCandidate,
                rep: object,
                *,
                _attempt: int = attempt,
            ) -> None:
                from backend.core.contracts import ValidationReport

                if isinstance(rep, ValidationReport):
                    log(rid, auth, "validate", rep.verdict.value, attempt=_attempt, sql=cand.sql)

            t_vote = time.perf_counter()
            voting_out = vote_candidates(
                candidates,
                schema=self._schema,
                auth=auth,
                validator=self._s.validator,
                policy=self._s.policy,
                executor=self._s.executor,
                knowledge=knowledge,
                question=request.question,
                on_validated=_audit_candidate,
            )
            self._record_latency("validate", t_vote)

            if voting_out.verdict is Verdict.REJECTED:
                if self._metrics is not None:
                    self._metrics.record_security_violation("validator")
                return outcome(OutcomeStatus.REJECTED, attempt, reason=REJECTED_MESSAGE)

            if voting_out.verdict is Verdict.REPAIRABLE:
                if voting_out.execution_error is not None and not voting_out.failures:
                    return outcome(OutcomeStatus.ERROR, attempt, reason=voting_out.execution_error)
                if self._metrics is not None:
                    self._metrics.record_retry("vote")
                feedback = voting_out.failures
                continue

            if voting_out.approved is not None and voting_out.result is not None:
                log(
                    rid,
                    auth,
                    "execute",
                    "ok",
                    rows=voting_out.result.row_count,
                    ms=round(voting_out.result.elapsed_ms, 1),
                    votes=voting_out.winning_votes,
                )
                t_res = time.perf_counter()
                report_out = self._s.results.build(parsed, plan, voting_out.approved, voting_out.result)
                self._record_latency("results", t_res)
                return outcome(OutcomeStatus.ANSWERED, attempt, report=report_out)

        return outcome(
            OutcomeStatus.RETRY_BUDGET_EXHAUSTED,
            self._retry.max_attempts,
            reason="Geçerli bir sorgu üretilemedi; lütfen soruyu yeniden ifade edin.",
        )
