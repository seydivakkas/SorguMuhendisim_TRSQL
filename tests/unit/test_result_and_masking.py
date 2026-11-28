from decimal import Decimal

from backend.core.contracts import OutcomeStatus
from backend.observability import MetricsCollector, mask_sensitive
from backend.result_engine import format_tr_number


def test_tr_number_format() -> None:
    assert format_tr_number(1250000) == "1.250.000"
    assert format_tr_number(1250000.5) == "1.250.000,50"
    assert format_tr_number(Decimal("0.125")) == "0,13"


def test_masking() -> None:
    text = "tckn 12345678901 mail ali@ornek.com tel 0532 123 45 67 api_key=abc123 TR330006100519786457841326"
    masked = mask_sensitive(text)
    for secret in ("12345678901", "ali@ornek.com", "532 123", "abc123", "TR3300"):
        assert secret not in masked


def test_metrics_collector_and_optional_otel_bridge() -> None:
    class _FakeCounter:
        def __init__(self) -> None:
            self.calls: list[tuple[int | float, dict[str, str] | None]] = []

        def add(self, amount: int | float, attributes: dict[str, str] | None = None) -> None:
            self.calls.append((amount, attributes))

    class _FakeHistogram:
        def __init__(self) -> None:
            self.calls: list[tuple[int | float, dict[str, str] | None]] = []

        def record(self, amount: int | float, attributes: dict[str, str] | None = None) -> None:
            self.calls.append((amount, attributes))

    class _FakeMeter:
        def __init__(self) -> None:
            self.counters: dict[str, _FakeCounter] = {}
            self.histograms: dict[str, _FakeHistogram] = {}

        def create_counter(self, name: str, *, unit: str = "", description: str = "") -> _FakeCounter:
            del unit, description
            counter = _FakeCounter()
            self.counters[name] = counter
            return counter

        def create_histogram(self, name: str, *, unit: str = "", description: str = "") -> _FakeHistogram:
            del unit, description
            hist = _FakeHistogram()
            self.histograms[name] = hist
            return hist

    # Pure offline collector without OTel
    offline_metrics = MetricsCollector(enable_otel=False)
    offline_metrics.record_stage_latency("parse", 12.5)
    offline_metrics.record_stage_latency("parse", 7.5)
    offline_metrics.record_retry("validate")
    offline_metrics.record_security_violation("injection")
    offline_metrics.record_clarification()
    offline_metrics.record_template_bypass("kpi_net_sales_v1")
    offline_metrics.record_routing("direct", 1)
    offline_metrics.record_outcome(OutcomeStatus.ANSWERED)

    snap = offline_metrics.snapshot()
    assert snap.requests_total == 1
    assert snap.retries_total == 1
    assert snap.security_violations_total == 1
    assert snap.clarifications_total == 1
    assert snap.template_bypasses_total == 1
    assert snap.outcomes_by_status == {"answered": 1}
    assert snap.routing_modes == {"direct": 1}
    assert snap.stage_latencies_ms["parse"].count == 2
    assert snap.stage_latencies_ms["parse"].avg_ms == 10.0

    # Custom OTel meter bridge
    fake_meter = _FakeMeter()
    otel_metrics = MetricsCollector(enable_otel=True, otel_meter=fake_meter)
    assert otel_metrics.otel_enabled is True
    otel_metrics.record_stage_latency("execute", 4.2)
    otel_metrics.record_outcome(OutcomeStatus.REJECTED)
    assert fake_meter.histograms["trsql.stage.latency_ms"].calls == [(4.2, {"stage": "execute"})]
    assert fake_meter.counters["trsql.outcomes.total"].calls == [(1, {"status": "rejected"})]
