"""Statistical tests (McNemar, paired bootstrap CI) and Markdown comparison reports."""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class McNemarResult:
    """Result of McNemar's paired nominal significance test."""

    n_total: int
    n11: int
    n10: int
    n01: int
    n00: int
    statistic: float
    p_value: float
    exact: bool
    significant: bool


@dataclass(frozen=True)
class BootstrapCIResult:
    """Result of paired bootstrap confidence interval estimation."""

    observed_delta: float
    mean_delta: float
    std_error: float
    ci_low: float
    ci_high: float
    confidence: float
    p_value: float
    significant: bool
    n_resamples: int


@dataclass(frozen=True)
class ExperimentRecord:
    """Normalized summary of one experiment run for cross-stage comparison."""

    model: str
    stage: str
    dataset: str
    ex: float
    parseable_rate: float | None = None
    executable_rate: float | None = None
    p50_latency_ms: float | None = None
    p95_latency_ms: float | None = None
    peak_vram_mb: int | None = None
    generated_unsafe_rate: float | None = None
    db_reached_unsafe_rate: float | None = None
    attack_capture_rate: float | None = None
    per_example_correct: tuple[bool, ...] | None = None


def _exact_binomial_two_sided(b: int, c: int) -> float:
    n = b + c
    if n == 0:
        return 1.0
    k_max = min(b, c)
    log2_n = n * math.log(2.0)
    lgamma_n1 = math.lgamma(n + 1)
    tail = 0.0
    for k in range(k_max + 1):
        log_prob = lgamma_n1 - math.lgamma(k + 1) - math.lgamma(n - k + 1) - log2_n
        tail += math.exp(log_prob)
    return min(1.0, 2.0 * tail)


def mcnemar_test(
    baseline_correct: Sequence[bool],
    candidate_correct: Sequence[bool],
    *,
    exact: bool | None = None,
    continuity_correction: bool = True,
    alpha: float = 0.05,
) -> McNemarResult:
    """Run McNemar's test on paired binary outcomes."""
    if not baseline_correct:
        raise ValueError("McNemar testi için en az bir örnek gerekir.")
    if len(baseline_correct) != len(candidate_correct):
        raise ValueError("baseline_correct ve candidate_correct uzunlukları eşit olmalıdır.")

    n11 = n10 = n01 = n00 = 0
    for b_ok, c_ok in zip(baseline_correct, candidate_correct, strict=True):
        if b_ok and c_ok:
            n11 += 1
        elif b_ok and not c_ok:
            n10 += 1
        elif not b_ok and c_ok:
            n01 += 1
        else:
            n00 += 1

    n_disc = n10 + n01
    use_exact = (n_disc < 25) if exact is None else exact

    if n_disc == 0:
        stat = 0.0
        p_val = 1.0
    elif use_exact:
        stat = float(min(n10, n01))
        p_val = _exact_binomial_two_sided(n10, n01)
    else:
        diff = abs(n10 - n01)
        if continuity_correction:
            diff = max(0, diff - 1)
        stat = (diff * diff) / n_disc
        p_val = math.erfc(math.sqrt(stat / 2.0))

    return McNemarResult(
        n_total=len(baseline_correct),
        n11=n11,
        n10=n10,
        n01=n01,
        n00=n00,
        statistic=stat,
        p_value=p_val,
        exact=use_exact,
        significant=p_val < alpha,
    )


class _SplitMix64:
    """Fast deterministic 64-bit PRNG for statistical bootstrap resampling."""

    def __init__(self, seed: int) -> None:
        self._state = seed & 0xFFFFFFFFFFFFFFFF

    def next_u64(self) -> int:
        self._state = (self._state + 0x9E3779B97F4A7C15) & 0xFFFFFFFFFFFFFFFF
        z = self._state
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & 0xFFFFFFFFFFFFFFFF
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & 0xFFFFFFFFFFFFFFFF
        return z ^ (z >> 31)

    def randbelow(self, upper: int) -> int:
        return self.next_u64() % upper


def _quantile(sorted_vals: Sequence[float], q: float) -> float:
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    pos = q * (len(sorted_vals) - 1)
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return sorted_vals[lo]
    frac = pos - lo
    return sorted_vals[lo] + frac * (sorted_vals[hi] - sorted_vals[lo])


def paired_bootstrap_ci(
    baseline_scores: Sequence[float | bool],
    candidate_scores: Sequence[float | bool],
    *,
    n_resamples: int = 10_000,
    confidence: float = 0.95,
    seed: int = 42,
) -> BootstrapCIResult:
    """Compute a paired bootstrap confidence interval for ``candidate - baseline``."""
    if not baseline_scores:
        raise ValueError("Bootstrap CI için en az bir örnek gerekir.")
    if len(baseline_scores) != len(candidate_scores):
        raise ValueError("baseline_scores ve candidate_scores uzunlukları eşit olmalıdır.")
    if n_resamples < 1:
        raise ValueError("n_resamples en az 1 olmalıdır.")
    if not (0.0 < confidence < 1.0):
        raise ValueError("confidence 0 ile 1 arasında olmalıdır.")

    diffs = [float(c) - float(b) for b, c in zip(baseline_scores, candidate_scores, strict=True)]
    n = len(diffs)
    observed = sum(diffs) / n

    rng = _SplitMix64(seed)
    boot_deltas: list[float] = []
    for _ in range(n_resamples):
        total = 0.0
        for _ in range(n):
            total += diffs[rng.randbelow(n)]
        boot_deltas.append(total / n)

    boot_deltas.sort()
    mean_delta = sum(boot_deltas) / n_resamples
    variance = sum((d - mean_delta) ** 2 for d in boot_deltas) / max(1, n_resamples - 1)
    std_err = math.sqrt(variance)

    alpha = 1.0 - confidence
    ci_low = _quantile(boot_deltas, alpha / 2.0)
    ci_high = _quantile(boot_deltas, 1.0 - alpha / 2.0)

    le_zero = sum(1 for d in boot_deltas if d <= 0.0) / n_resamples
    ge_zero = sum(1 for d in boot_deltas if d >= 0.0) / n_resamples
    p_value = min(1.0, 2.0 * min(le_zero, ge_zero))

    return BootstrapCIResult(
        observed_delta=observed,
        mean_delta=mean_delta,
        std_error=std_err,
        ci_low=ci_low,
        ci_high=ci_high,
        confidence=confidence,
        p_value=p_value,
        significant=not (ci_low <= 0.0 <= ci_high),
        n_resamples=n_resamples,
    )


def _stage_sort_key(stage: str) -> tuple[int, str]:
    upper = stage.strip().upper()
    if upper.startswith("D") and upper[1:].isdigit():
        return (int(upper[1:]), upper)
    return (999, upper)


def load_experiment_record(exp_dir: str | Path) -> ExperimentRecord:
    """Load an :class:`ExperimentRecord` from a directory containing ``metrics.json``."""
    d = Path(exp_dir)
    metrics_path = d / "metrics.json"
    if not metrics_path.exists():
        raise FileNotFoundError(f"metrics.json bulunamadı: {metrics_path}")
    payload: dict[str, Any] = json.loads(metrics_path.read_text(encoding="utf-8"))

    exp = payload.get("experiment", {})
    summary = payload.get("summary", {})
    latency = summary.get("latency_ms", {})
    safety = summary.get("safety", {})
    hardware = payload.get("hardware", {})

    per_example: tuple[bool, ...] | None = None
    preds_path = d / "predictions.jsonl"
    if preds_path.exists():
        matches: list[bool] = []
        for raw in preds_path.read_text(encoding="utf-8").splitlines():
            stripped = raw.strip()
            if not stripped:
                continue
            item = json.loads(stripped)
            if item.get("ex_match") is not None:
                matches.append(bool(item["ex_match"]))
        if matches:
            per_example = tuple(matches)

    return ExperimentRecord(
        model=str(exp.get("model", "unknown")),
        stage=str(exp.get("stage", "D0")),
        dataset=str(exp.get("dataset", "unknown")),
        ex=float(summary.get("execution_accuracy", 0.0)),
        parseable_rate=(
            float(summary["parseable_rate"]) if summary.get("parseable_rate") is not None else None
        ),
        executable_rate=(
            float(summary["executable_rate"]) if summary.get("executable_rate") is not None else None
        ),
        p50_latency_ms=(float(latency["p50"]) if latency.get("p50") is not None else None),
        p95_latency_ms=(float(latency["p95"]) if latency.get("p95") is not None else None),
        peak_vram_mb=(
            int(hardware["peak_vram_used_mb"]) if hardware.get("peak_vram_used_mb") is not None else None
        ),
        generated_unsafe_rate=(
            float(safety["generated_unsafe_rate"])
            if safety.get("generated_unsafe_rate") is not None
            else None
        ),
        db_reached_unsafe_rate=(
            float(safety["db_reached_unsafe_rate"])
            if safety.get("db_reached_unsafe_rate") is not None
            else None
        ),
        attack_capture_rate=(
            float(safety["attack_capture_rate"]) if safety.get("attack_capture_rate") is not None else None
        ),
        per_example_correct=per_example,
    )


def load_experiment_records(exp_dirs: Sequence[str | Path]) -> list[ExperimentRecord]:
    """Load multiple experiment directories into :class:`ExperimentRecord` items."""
    return [load_experiment_record(d) for d in exp_dirs]


def _fmt_pct(val: float | None) -> str:
    if val is None:
        return "—"
    return f"{val * 100:.1f}%"


def _fmt_delta_pp(delta: float | None) -> str:
    if delta is None:
        return "—"
    return f"{delta * 100:+.1f} pp"


def format_comparison_markdown(
    records: Sequence[ExperimentRecord],
    *,
    baseline_stage: str | None = None,
    bootstrap_resamples: int = 2000,
    seed: int = 42,
) -> str:
    """Format a Markdown comparison report (model × stage × dataset) + Δ EX + stats."""
    if not records:
        return "# TRSQL Deney Karşılaştırma Raporu\n\nKayıt bulunamadı.\n"

    ordered = sorted(records, key=lambda r: (r.dataset, r.model, _stage_sort_key(r.stage)))
    grouped: dict[tuple[str, str], list[ExperimentRecord]] = defaultdict(list)
    for rec in ordered:
        grouped[(rec.model, rec.dataset)].append(rec)

    lines: list[str] = [
        "# TRSQL Deney Karşılaştırma Raporu",
        "",
        "## Model × Basamak × Veri Kümesi",
        "",
        "| Model | Basamak | Veri Kümesi | EX | Δ EX | Parseable | Executable | P95 (ms) | Tepe VRAM (MB) |",
        "|---|---|---|---|---|---|---|---|---|",
    ]

    stat_rows: list[str] = []

    for (_model, _dataset), group in grouped.items():
        base_rec: ExperimentRecord | None = None
        if baseline_stage is not None:
            base_rec = next((g for g in group if g.stage.upper() == baseline_stage.upper()), None)

        prev_rec: ExperimentRecord | None = None
        for rec in group:
            ref = base_rec if (baseline_stage is not None and base_rec is not rec) else prev_rec
            delta_ex = (rec.ex - ref.ex) if ref is not None else None
            p95_str = f"{rec.p95_latency_ms:.1f}" if rec.p95_latency_ms is not None else "—"
            vram_str = str(rec.peak_vram_mb) if rec.peak_vram_mb is not None else "—"
            lines.append(
                f"| {rec.model} | {rec.stage} | {rec.dataset} | {_fmt_pct(rec.ex)} | "
                f"{_fmt_delta_pp(delta_ex)} | {_fmt_pct(rec.parseable_rate)} | "
                f"{_fmt_pct(rec.executable_rate)} | {p95_str} | {vram_str} |"
            )

            if (
                prev_rec is not None
                and prev_rec.per_example_correct is not None
                and rec.per_example_correct is not None
                and len(prev_rec.per_example_correct) == len(rec.per_example_correct)
                and len(rec.per_example_correct) > 0
            ):
                mcn = mcnemar_test(prev_rec.per_example_correct, rec.per_example_correct)
                boot = paired_bootstrap_ci(
                    prev_rec.per_example_correct,
                    rec.per_example_correct,
                    n_resamples=bootstrap_resamples,
                    seed=seed,
                )
                sig_label = "Evet" if (mcn.significant or boot.significant) else "Hayır"
                stat_rows.append(
                    f"| {rec.model} | {rec.dataset} | {prev_rec.stage} → {rec.stage} | "
                    f"{_fmt_delta_pp(boot.observed_delta)} | "
                    f"[{boot.ci_low * 100:+.1f}, {boot.ci_high * 100:+.1f}] pp | "
                    f"{mcn.p_value:.4f} | {sig_label} |"
                )

            prev_rec = rec

    has_safety = any(
        r.attack_capture_rate is not None
        or r.generated_unsafe_rate is not None
        or r.db_reached_unsafe_rate is not None
        for r in ordered
    )
    if has_safety:
        safety_header = (
            "| Model | Basamak | Veri Kümesi | Saldırı Yakalama | "
            "Üretilen Tehlikeli | DB'ye Ulaşan Tehlikeli |"
        )
        lines.extend(
            [
                "",
                "## Güvenlik Özeti",
                "",
                safety_header,
                "|---|---|---|---|---|---|",
            ]
        )
        for rec in ordered:
            lines.append(
                f"| {rec.model} | {rec.stage} | {rec.dataset} | "
                f"{_fmt_pct(rec.attack_capture_rate)} | "
                f"{_fmt_pct(rec.generated_unsafe_rate)} | "
                f"{_fmt_pct(rec.db_reached_unsafe_rate)} |"
            )

    if stat_rows:
        stat_header = (
            "| Model | Veri Kümesi | Karşılaştırma | Δ EX | %95 Bootstrap Gİ | McNemar p | Anlamlı (α=0.05) |"
        )
        lines.extend(
            [
                "",
                "## İstatistiksel Anlamlılık (McNemar & %95 Eşli Bootstrap Gİ)",
                "",
                stat_header,
                "|---|---|---|---|---|---|---|",
                *stat_rows,
            ]
        )

    return "\n".join(lines) + "\n"


def generate_report(
    exp_dirs: Sequence[str | Path],
    output_path: str | Path | None = None,
    *,
    baseline_stage: str | None = None,
    bootstrap_resamples: int = 2000,
    seed: int = 42,
) -> str:
    """Load experiment directories, format Markdown comparison report, and optionally save."""
    records = load_experiment_records(exp_dirs)
    markdown = format_comparison_markdown(
        records,
        baseline_stage=baseline_stage,
        bootstrap_resamples=bootstrap_resamples,
        seed=seed,
    )
    if output_path is not None:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(markdown, encoding="utf-8")
    return markdown


def _main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="TRSQL karşılaştırmalı deney raporu")
    parser.add_argument("experiments", nargs="+", help="metrics.json içeren deney klasörleri")
    parser.add_argument("--output", default=None, help="Çıktı Markdown dosyası")
    parser.add_argument("--baseline-stage", default=None, help="Taban basamak (ör. D0)")
    args = parser.parse_args(list(argv) if argv is not None else None)
    md = generate_report(args.experiments, args.output, baseline_stage=args.baseline_stage)
    if args.output is None:
        print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())


__all__ = [
    "BootstrapCIResult",
    "ExperimentRecord",
    "McNemarResult",
    "format_comparison_markdown",
    "generate_report",
    "load_experiment_record",
    "load_experiment_records",
    "mcnemar_test",
    "paired_bootstrap_ci",
]
