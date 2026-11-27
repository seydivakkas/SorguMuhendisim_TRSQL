import pytest
from pydantic import ValidationError

from backend.core.contracts import (
    ApprovedQuery,
    CheckName,
    CheckResult,
    Dialect,
    Severity,
    SQLCandidate,
    ValidationReport,
    Verdict,
)

CAND = SQLCandidate(sql="SELECT 1", dialect=Dialect.SQLITE, model_id="m", attempt=1)


def report(*checks: CheckResult) -> ValidationReport:
    return ValidationReport(candidate=CAND, checks=checks)


def test_verdict_security_dominates_repairable() -> None:
    r = report(
        CheckResult(check=CheckName.SCHEMA, passed=False, severity=Severity.REPAIRABLE),
        CheckResult(check=CheckName.AUTHORIZATION, passed=False, severity=Severity.SECURITY),
    )
    assert r.verdict is Verdict.REJECTED


def test_verdict_repairable_and_approved() -> None:
    assert (
        report(CheckResult(check=CheckName.SYNTAX, passed=False, severity=Severity.REPAIRABLE)).verdict
        is Verdict.REPAIRABLE
    )
    assert report(CheckResult(check=CheckName.SYNTAX, passed=True)).verdict is Verdict.APPROVED


def test_approved_query_cannot_be_built_from_unapproved_report() -> None:
    bad = report(CheckResult(check=CheckName.AST, passed=False, severity=Severity.SECURITY))
    with pytest.raises(ValidationError):
        ApprovedQuery(sql="SELECT 1", dialect=Dialect.SQLITE, report=bad, max_rows=10, timeout_ms=100)


def test_approved_query_dialect_must_match() -> None:
    ok = report(CheckResult(check=CheckName.SYNTAX, passed=True))
    with pytest.raises(ValidationError):
        ApprovedQuery(sql="SELECT 1", dialect=Dialect.POSTGRES, report=ok, max_rows=10, timeout_ms=100)


def test_contracts_are_frozen_and_strict() -> None:
    with pytest.raises(ValidationError):
        SQLCandidate(sql="x", dialect=Dialect.SQLITE, model_id="m", attempt=1, extra_field=1)  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        CAND.sql = "DROP TABLE x"  # type: ignore[misc]
