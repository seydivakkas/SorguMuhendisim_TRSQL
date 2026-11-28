"""Execution-result self-consistency voting across N validated candidates (AR-05)."""

from __future__ import annotations

import inspect
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, TypeAlias

from backend.core.contracts import (
    ApprovedQuery,
    AuthContext,
    ExecutionResult,
    KnowledgeContext,
    SchemaSnapshot,
    SQLCandidate,
    ValidationReport,
    Verdict,
)
from backend.core.errors import ExecutionError, SecurityViolation
from backend.core.ports import PolicyEnforcer, QueryExecutor, SQLValidatorPort

NormalizedCell: TypeAlias = bool | int | float | str | None
NormalizedResultKey: TypeAlias = tuple[int, tuple[tuple[NormalizedCell, ...], ...]]


@dataclass(frozen=True)
class VotingOutcome:
    """Structured outcome of multi-candidate validation and consistency voting."""

    verdict: Verdict
    approved: ApprovedQuery | None = None
    result: ExecutionResult | None = None
    attempts: int = 0
    failures: tuple[str, ...] = ()
    vote_tally: tuple[tuple[str, int], ...] = ()
    winning_votes: int = 0
    execution_error: str | None = None


def _normalize_cell(value: Any) -> NormalizedCell:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return float(value)
    if isinstance(value, Decimal):
        return round(float(value), 6)
    if isinstance(value, float):
        return round(value, 6)
    return str(value)


def normalize_execution_result(result: ExecutionResult) -> NormalizedResultKey:
    """Produce a deterministic hashable key for an :class:`ExecutionResult`."""
    rows = tuple(tuple(_normalize_cell(cell) for cell in row) for row in result.rows)
    return (len(result.columns), rows)


def validate_with_context(
    validator: SQLValidatorPort,
    candidate: SQLCandidate,
    schema: SchemaSnapshot,
    auth: AuthContext,
    *,
    knowledge: KnowledgeContext | None = None,
    question: str | None = None,
) -> ValidationReport:
    """Invoke ``validator.validate`` forwarding ``knowledge`` and ``question`` if supported."""
    try:
        sig = inspect.signature(validator.validate)
        params = sig.parameters
        supports_kwargs = any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values())
        extra: dict[str, object] = {}
        if supports_kwargs or "knowledge" in params:
            extra["knowledge"] = knowledge
        if supports_kwargs or "question" in params:
            extra["question"] = question
    except (TypeError, ValueError):
        extra = {}
    return validator.validate(candidate, schema, auth, **extra)


def vote_candidates(
    candidates: Sequence[SQLCandidate],
    *,
    schema: SchemaSnapshot,
    auth: AuthContext,
    validator: SQLValidatorPort,
    policy: PolicyEnforcer,
    executor: QueryExecutor,
    knowledge: KnowledgeContext | None = None,
    question: str | None = None,
    on_validated: Callable[[SQLCandidate, ValidationReport], None] | None = None,
) -> VotingOutcome:
    """Validate every candidate, execute approved ones, and vote on consistent results.

    Security invariant (ADR-0005):
    - Every candidate is validated BEFORE any candidate is executed.
    - If ANY candidate triggers ``Severity.SECURITY`` (``Verdict.REJECTED``),
      voting stops immediately and returns ``Verdict.REJECTED`` without
      executing anything on the database.
    - Unapproved candidates never reach ``PolicyEngine`` or ``ExecutionEngine``.
    """
    if not candidates:
        return VotingOutcome(
            verdict=Verdict.REPAIRABLE,
            attempts=0,
            failures=("Hiçbir SQL adayı üretilmedi.",),
        )

    approved_reports: list[tuple[SQLCandidate, ValidationReport]] = []
    repairable_messages: list[str] = []

    for idx, candidate in enumerate(candidates, start=1):
        report = validate_with_context(
            validator,
            candidate,
            schema,
            auth,
            knowledge=knowledge,
            question=question,
        )
        if on_validated is not None:
            on_validated(candidate, report)

        if report.verdict is Verdict.REJECTED:
            return VotingOutcome(
                verdict=Verdict.REJECTED,
                attempts=idx,
            )
        if report.verdict is Verdict.REPAIRABLE:
            for failure in report.failures:
                if failure.message and failure.message not in repairable_messages:
                    repairable_messages.append(failure.message)
            continue
        approved_reports.append((candidate, report))

    if not approved_reports:
        return VotingOutcome(
            verdict=Verdict.REPAIRABLE,
            attempts=len(candidates),
            failures=tuple(repairable_messages),
        )

    executed: list[tuple[ApprovedQuery, ExecutionResult]] = []
    last_exec_error: str | None = None

    for _, report in approved_reports:
        try:
            approved = policy.approve(report, auth)
        except SecurityViolation:
            return VotingOutcome(verdict=Verdict.REJECTED, attempts=len(candidates))
        try:
            result = executor.run(approved)
        except ExecutionError as exc:
            last_exec_error = str(exc)
            continue
        executed.append((approved, result))

    if not executed:
        return VotingOutcome(
            verdict=Verdict.REPAIRABLE,
            attempts=len(candidates),
            failures=tuple(repairable_messages),
            execution_error=last_exec_error or "Sorgu yürütülemedi.",
        )

    groups: dict[NormalizedResultKey, list[tuple[ApprovedQuery, ExecutionResult]]] = {}
    for pair in executed:
        key = normalize_execution_result(pair[1])
        groups.setdefault(key, []).append(pair)

    best_key = max(groups.keys(), key=lambda k: len(groups[k]))
    winning_group = groups[best_key]
    winning_approved, winning_result = winning_group[0]
    tally = tuple((repr(k), len(v)) for k, v in groups.items())

    return VotingOutcome(
        verdict=Verdict.APPROVED,
        approved=winning_approved,
        result=winning_result,
        attempts=len(candidates),
        vote_tally=tally,
        winning_votes=len(winning_group),
    )


def select_consistent_candidate(
    candidates: Sequence[SQLCandidate],
    *,
    schema: SchemaSnapshot,
    auth: AuthContext,
    validator: SQLValidatorPort,
    policy: PolicyEnforcer,
    executor: QueryExecutor,
    knowledge: KnowledgeContext | None = None,
    question: str | None = None,
    on_validated: Callable[[SQLCandidate, ValidationReport], None] | None = None,
) -> tuple[ApprovedQuery, ExecutionResult, int]:
    """Validate, execute, and majority-vote across ``candidates``.

    Returns ``(approved, result, attempts)`` for the winning execution result.
    Raises :class:`SecurityViolation` immediately if any candidate violates
    security rules (ADR-0005), or :class:`ExecutionError` if no valid candidate
    could be executed.
    """
    outcome = vote_candidates(
        candidates,
        schema=schema,
        auth=auth,
        validator=validator,
        policy=policy,
        executor=executor,
        knowledge=knowledge,
        question=question,
        on_validated=on_validated,
    )
    if outcome.verdict is Verdict.REJECTED:
        raise SecurityViolation("Bu istek güvenlik politikası nedeniyle yerine getirilemedi.")
    if outcome.approved is None or outcome.result is None:
        detail = (
            outcome.execution_error or "; ".join(outcome.failures) or "Geçerli bir aday sorgu üretilemedi."
        )
        raise ExecutionError(detail)
    return outcome.approved, outcome.result, outcome.attempts
