"""Stage metrics, counters, and optional OpenTelemetry bridge (L9)."""

from __future__ import annotations

import importlib
import importlib.util
import threading
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from backend.core.contracts import OutcomeStatus


@runtime_checkable
class _OTelCounter(Protocol):
    def add(self, amount: int | float, attributes: dict[str, str] | None = None) -> None: ...


@runtime_checkable
class _OTelHistogram(Protocol):
    def record(self, amount: int | float, attributes: dict[str, str] | None = None) -> None: ...


@runtime_checkable
class _OTelMeter(Protocol):
    def create_counter(self, name: str, *, unit: str = "", description: str = "") -> _OTelCounter: ...

    def create_histogram(self, name: str, *, unit: str = "", description: str = "") -> _OTelHistogram: ...


@dataclass(frozen=True)
class StageLatencyStats:
    """Aggregated latency metrics (in milliseconds) for a single pipeline stage."""

    count: int
    total_ms: float
    min_ms: float
    max_ms: float
    avg_ms: float


@dataclass(frozen=True)
class MetricsSnapshot:
    """Point-in-time immutable view of L9 runtime metrics."""

    requests_total: int
    retries_total: int
    security_violations_total: int
    clarifications_total: int
    template_bypasses_total: int
    outcomes_by_status: dict[str, int]
    routing_modes: dict[str, int]
    stage_latencies_ms: dict[str, StageLatencyStats]
    otel_enabled: bool = False


class _OpenTelemetryBridge:
    """Optional guarded OpenTelemetry meter wrapper."""

    def __init__(self, meter: _OTelMeter | None = None) -> None:
        self._meter = meter if meter is not None else self._discover_meter()
        self._enabled = self._meter is not None
        self._stage_latency: _OTelHistogram | None = None
        self._retries: _OTelCounter | None = None
        self._security_violations: _OTelCounter | None = None
        self._clarifications: _OTelCounter | None = None
        self._outcomes: _OTelCounter | None = None
        self._template_bypasses: _OTelCounter | None = None

        if self._meter is not None:
            self._stage_latency = self._meter.create_histogram(
                "trsql.stage.latency_ms",
                unit="ms",
                description="TRSQL pipeline stage latency in milliseconds",
            )
            self._retries = self._meter.create_counter(
                "trsql.retries.total",
                description="Total repairable SQL regeneration retries",
            )
            self._security_violations = self._meter.create_counter(
                "trsql.security_violations.total",
                description="Total hard-rejected security violations",
            )
            self._clarifications = self._meter.create_counter(
                "trsql.clarifications.total",
                description="Total ambiguity clarification responses",
            )
            self._outcomes = self._meter.create_counter(
                "trsql.outcomes.total",
                description="Total pipeline outcomes by status",
            )
            self._template_bypasses = self._meter.create_counter(
                "trsql.template_bypasses.total",
                description="Total deterministic KPI template bypasses",
            )

    @staticmethod
    def _discover_meter() -> _OTelMeter | None:
        if importlib.util.find_spec("opentelemetry") is None:
            return None
        try:
            otel_metrics = importlib.import_module("opentelemetry.metrics")
            get_meter = getattr(otel_metrics, "get_meter", None)
            if callable(get_meter):
                meter = get_meter("trsql")
                if isinstance(meter, _OTelMeter):
                    return meter
        except ImportError:
            return None
        return None

    @property
    def enabled(self) -> bool:
        return self._enabled

    def record_stage_latency(self, stage: str, elapsed_ms: float) -> None:
        if self._stage_latency is not None:
            self._stage_latency.record(elapsed_ms, {"stage": stage})

    def record_retry(self, stage: str) -> None:
        if self._retries is not None:
            self._retries.add(1, {"stage": stage})

    def record_security_violation(self, check: str) -> None:
        if self._security_violations is not None:
            self._security_violations.add(1, {"check": check})

    def record_clarification(self) -> None:
        if self._clarifications is not None:
            self._clarifications.add(1, None)

    def record_template_bypass(self, template_id: str) -> None:
        if self._template_bypasses is not None:
            self._template_bypasses.add(1, {"template_id": template_id})

    def record_outcome(self, status: str) -> None:
        if self._outcomes is not None:
            self._outcomes.add(1, {"status": status})


class MetricsCollector:
    """Thread-safe stage latency, retry, security, and clarification metrics (L9).

    Works offline in pure Python and optionally forwards events to
    ``opentelemetry-api`` when installed and enabled.
    """

    def __init__(self, *, enable_otel: bool = False, otel_meter: _OTelMeter | None = None) -> None:
        self._lock = threading.Lock()
        self._bridge = (
            _OpenTelemetryBridge(meter=otel_meter) if (enable_otel or otel_meter is not None) else None
        )
        self._requests_total = 0
        self._retries_total = 0
        self._security_violations_total = 0
        self._clarifications_total = 0
        self._template_bypasses_total = 0
        self._outcomes_by_status: dict[str, int] = {}
        self._routing_modes: dict[str, int] = {}
        self._latencies: dict[str, list[float]] = {}

    @property
    def otel_enabled(self) -> bool:
        return self._bridge is not None and self._bridge.enabled

    def record_stage_latency(self, stage: str, elapsed_ms: float) -> None:
        value = max(0.0, float(elapsed_ms))
        with self._lock:
            self._latencies.setdefault(stage, []).append(value)
        if self._bridge is not None:
            self._bridge.record_stage_latency(stage, value)

    def record_retry(self, stage: str = "validate") -> None:
        with self._lock:
            self._retries_total += 1
        if self._bridge is not None:
            self._bridge.record_retry(stage)

    def record_security_violation(self, check: str = "security") -> None:
        with self._lock:
            self._security_violations_total += 1
        if self._bridge is not None:
            self._bridge.record_security_violation(check)

    def record_clarification(self) -> None:
        with self._lock:
            self._clarifications_total += 1
        if self._bridge is not None:
            self._bridge.record_clarification()

    def record_template_bypass(self, template_id: str) -> None:
        with self._lock:
            self._template_bypasses_total += 1
        if self._bridge is not None:
            self._bridge.record_template_bypass(template_id)

    def record_routing(self, mode: str, num_candidates: int = 1) -> None:
        del num_candidates
        with self._lock:
            self._routing_modes[mode] = self._routing_modes.get(mode, 0) + 1

    def record_outcome(self, status: OutcomeStatus | str) -> None:
        status_str = status.value if isinstance(status, OutcomeStatus) else str(status)
        with self._lock:
            self._requests_total += 1
            self._outcomes_by_status[status_str] = self._outcomes_by_status.get(status_str, 0) + 1
        if self._bridge is not None:
            self._bridge.record_outcome(status_str)

    def snapshot(self) -> MetricsSnapshot:
        with self._lock:
            latency_stats: dict[str, StageLatencyStats] = {}
            for stage, samples in self._latencies.items():
                total = sum(samples)
                count = len(samples)
                latency_stats[stage] = StageLatencyStats(
                    count=count,
                    total_ms=round(total, 4),
                    min_ms=round(min(samples), 4),
                    max_ms=round(max(samples), 4),
                    avg_ms=round(total / count, 4),
                )
            return MetricsSnapshot(
                requests_total=self._requests_total,
                retries_total=self._retries_total,
                security_violations_total=self._security_violations_total,
                clarifications_total=self._clarifications_total,
                template_bypasses_total=self._template_bypasses_total,
                outcomes_by_status=dict(self._outcomes_by_status),
                routing_modes=dict(self._routing_modes),
                stage_latencies_ms=latency_stats,
                otel_enabled=self.otel_enabled,
            )

    def reset(self) -> None:
        with self._lock:
            self._requests_total = 0
            self._retries_total = 0
            self._security_violations_total = 0
            self._clarifications_total = 0
            self._template_bypasses_total = 0
            self._outcomes_by_status.clear()
            self._routing_modes.clear()
            self._latencies.clear()
