import pytest
from pydantic import ValidationError

from backend.core.contracts import (
    ApprovedQuery,
    CheckName,
    CheckResult,
    Dialect,
    ModelInfo,
    ReasoningMode,
    RoutingDecision,
    Severity,
    SQLCandidate,
    ValidationReport,
    Verdict,
)
from backend.core.ports import EmbeddingAdapter

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


def test_model_info_sha256_backward_compatible() -> None:
    base = ModelInfo(model_id="qwen3-4b", context_length=4096)
    assert base.sha256 is None
    assert base.quantization is None

    digest = "a" * 64
    with_hash = ModelInfo(
        model_id="hati-9b",
        quantization="Q4_K_M",
        context_length=8192,
        vram_mb_estimate=6400,
        sha256=digest,
    )
    assert with_hash.sha256 == digest
    with pytest.raises(ValidationError):
        with_hash.sha256 = "b" * 64  # type: ignore[misc]


def test_sql_candidate_optional_reasoning() -> None:
    assert CAND.reasoning is None
    thinking_cand = SQLCandidate(
        sql="SELECT COUNT(*) FROM dealers",
        dialect=Dialect.POSTGRES,
        model_id="arctic-r1-7b",
        attempt=1,
        reasoning="Bayi sayısını bulmak için dealers tablosu sayılır.",
    )
    assert thinking_cand.reasoning is not None


def test_reasoning_mode_and_routing_decision() -> None:
    assert ReasoningMode.DIRECT == "direct"
    assert ReasoningMode.THINKING == "thinking"

    decision = RoutingDecision(
        mode=ReasoningMode.DIRECT,
        num_candidates=1,
        complexity_score=0.25,
    )
    assert decision.reasons == ()

    thinking = RoutingDecision(
        mode=ReasoningMode.THINKING,
        num_candidates=4,
        complexity_score=0.85,
        reasons=("multi_join", "subquery"),
    )
    assert thinking.mode is ReasoningMode.THINKING
    assert thinking.num_candidates == 4

    with pytest.raises(ValidationError):
        RoutingDecision(mode=ReasoningMode.DIRECT, num_candidates=0, complexity_score=0.2)
    with pytest.raises(ValidationError):
        RoutingDecision(mode=ReasoningMode.DIRECT, num_candidates=1, complexity_score=1.5)
    with pytest.raises(ValidationError):
        RoutingDecision(
            mode=ReasoningMode.DIRECT,
            num_candidates=1,
            complexity_score=0.5,
            extra_field=True,  # type: ignore[call-arg]
        )


def test_embedding_adapter_runtime_protocol() -> None:
    class DummyEmbedder:
        def embed(self, texts: list[str]) -> list[list[float]]:
            return [[float(len(t))] for t in texts]

    class NotAnEmbedder:
        pass

    embedder = DummyEmbedder()
    assert isinstance(embedder, EmbeddingAdapter)
    assert not isinstance(NotAnEmbedder(), EmbeddingAdapter)
    assert embedder.embed(["merhaba"]) == [[7.0]]
