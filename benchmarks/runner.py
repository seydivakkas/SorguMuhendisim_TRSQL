"""Reproducible benchmark runner executing TRSQL Pipeline and emitting predictions/metrics."""

from __future__ import annotations

import argparse
import json
import math
import time
import tomllib
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from backend.core.config import Settings, load_settings
from backend.core.contracts import (
    AuditEvent,
    AuthContext,
    Dialect,
    Intent,
    MentionKind,
    OutcomeStatus,
    PipelineOutcome,
    QueryRequest,
    SchemaSnapshot,
)
from backend.core.errors import ConfigError
from backend.core.ports import DatabaseAdapter, ModelAdapter
from backend.database_adapters import SQLiteAdapter
from backend.knowledge_base import InMemoryKnowledgeBase, load_knowledge_base
from backend.model_engine import create_model_adapter
from backend.observability import InMemoryAuditSink, mask_sensitive
from backend.orchestration import Pipeline, build_default_pipeline
from benchmarks import BenchmarkExample, LoadedDataset
from benchmarks.hardware import collect_hardware_info, get_git_commit, is_git_dirty, sample_vram_mb
from benchmarks.loaders import load_birdturk, load_enterprise, load_turspider
from benchmarks.metrics import (
    AbstentionMetrics,
    AbstentionRecord,
    ExecutionComparison,
    SafetyMetrics,
    SafetyRecord,
    SchemaLinkingMetrics,
    SchemaLinkingSample,
    TestSuiteCase,
    compute_validity_metrics,
    evaluate_test_suite,
    execute_sqlite_readonly,
    execution_accuracy,
    extract_gold_tables_and_columns,
    is_parseable_sql,
    results_match_sql,
    valid_efficiency_score,
)


class DirtyWorkingTreeError(RuntimeError):
    """Raised when an experiment is launched on a dirty Git working tree without allow_dirty=True."""


class ExperimentConfig(BaseModel):
    """Typed configuration loaded from an experiment's ``config.toml``."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1)
    stage: str = "D0"
    dataset: str = "enterprise"
    dataset_path: str | None = None
    split: str = "dev"
    allow_dirty: bool = False
    seed: int = 42
    template_id: str = "ddl_v1"
    description: str = ""
    quantization: str | None = None
    max_examples: int | None = Field(default=None, gt=0)
    output_dir: str | None = None

    dialect: Dialect = Dialect.SQLITE
    db_path: str | None = None
    db_dir: str | None = None
    test_suite_dbs: tuple[str, ...] = ()
    knowledge_path: str | None = None

    user_id: str = "eval-runner"
    tenant_id: str = "benchmark"
    roles: tuple[str, ...] = ("analyst",)
    allowed_tables: tuple[str, ...] | None = None
    denied_columns: tuple[str, ...] = ()
    max_rows: int = Field(default=1000, gt=0)

    nlp_lexicon: dict[str, MentionKind] = Field(default_factory=dict)
    schema_lexicon: dict[str, str] = Field(default_factory=dict)
    locations: tuple[str, ...] = ()

    settings: Settings = Settings()


def _resolve_path(raw: str | None, *, base_dir: Path, repo_root: Path) -> Path | None:
    if raw is None:
        return None
    p = Path(raw)
    if p.is_absolute():
        return p
    candidate_local = base_dir / p
    if candidate_local.exists():
        return candidate_local
    return repo_root / p


def _extract_settings(raw: dict[str, Any], *, base_dir: Path, repo_root: Path) -> Settings:
    settings_path_raw = raw.get("settings_path")
    base_data: dict[str, Any] = {}
    if isinstance(settings_path_raw, str) and settings_path_raw.strip():
        resolved = _resolve_path(settings_path_raw.strip(), base_dir=base_dir, repo_root=repo_root)
        if resolved is None or not resolved.exists():
            raise ConfigError(f"settings_path bulunamadı: {settings_path_raw}")
        base_data = load_settings(resolved).model_dump()

    settings_section = raw.get("settings")
    if isinstance(settings_section, dict):
        merged = {**base_data, **settings_section}
    else:
        valid_fields = set(Settings.model_fields.keys())
        inline = {k: v for k, v in raw.items() if k in valid_fields}
        merged = {**base_data, **inline}

    clean = {k: v for k, v in merged.items() if k in Settings.model_fields}
    return Settings.model_validate(clean)


def load_experiment_config(
    path: str | Path,
    *,
    repo_root: str | Path | None = None,
) -> ExperimentConfig:
    """Load and validate an experiment ``config.toml`` file."""
    p = Path(path)
    try:
        raw = tomllib.loads(p.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f"Deney yapılandırması okunamadı: {p}") from exc

    exp_sec = raw.get("experiment", {})
    if not isinstance(exp_sec, dict):
        raise ConfigError("[experiment] bölümü tablo olmalıdır.")
    db_sec = raw.get("database", {})
    if not isinstance(db_sec, dict):
        raise ConfigError("[database] bölümü tablo olmalıdır.")
    auth_sec = raw.get("auth", {})
    if not isinstance(auth_sec, dict):
        raise ConfigError("[auth] bölümü tablo olmalıdır.")
    lex_sec = raw.get("lexicons", {})
    if not isinstance(lex_sec, dict):
        raise ConfigError("[lexicons] bölümü tablo olmalıdır.")

    root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[1]
    settings = _extract_settings(raw, base_dir=p.resolve().parent, repo_root=root)

    nlp_raw = lex_sec.get("nlp", raw.get("nlp_lexicon", {}))
    nlp_lexicon = {str(k): MentionKind(str(v)) for k, v in nlp_raw.items()}
    schema_raw = lex_sec.get("schema", raw.get("schema_lexicon", {}))
    schema_lexicon = {str(k): str(v) for k, v in schema_raw.items()}
    locations_raw = lex_sec.get("locations", raw.get("locations", []))

    allowed_raw = auth_sec.get("allowed_tables")
    allowed_tables = tuple(str(t) for t in allowed_raw) if allowed_raw is not None else None

    return ExperimentConfig(
        name=str(exp_sec.get("name", p.parent.name)),
        stage=str(exp_sec.get("stage", "D0")),
        dataset=str(exp_sec.get("dataset", "enterprise")).lower(),
        dataset_path=exp_sec.get("dataset_path"),
        split=str(exp_sec.get("split", "dev")),
        allow_dirty=bool(exp_sec.get("allow_dirty", False)),
        seed=int(exp_sec.get("seed", 42)),
        template_id=str(exp_sec.get("template_id", "ddl_v1")),
        description=str(exp_sec.get("description", "")),
        quantization=exp_sec.get("quantization"),
        max_examples=exp_sec.get("max_examples"),
        output_dir=exp_sec.get("output_dir"),
        dialect=Dialect(str(db_sec.get("dialect", "sqlite")).lower()),
        db_path=db_sec.get("path"),
        db_dir=db_sec.get("db_dir"),
        test_suite_dbs=tuple(str(x) for x in db_sec.get("test_suite_dbs", ())),
        knowledge_path=exp_sec.get("knowledge_path") or raw.get("knowledge_path"),
        user_id=str(auth_sec.get("user_id", "eval-runner")),
        tenant_id=str(auth_sec.get("tenant_id", "benchmark")),
        roles=tuple(str(r) for r in auth_sec.get("roles", ("analyst",))),
        allowed_tables=allowed_tables,
        denied_columns=tuple(str(c) for c in auth_sec.get("denied_columns", ())),
        max_rows=int(auth_sec.get("max_rows", 1000)),
        nlp_lexicon=nlp_lexicon,
        schema_lexicon=schema_lexicon,
        locations=tuple(str(loc) for loc in locations_raw),
        settings=settings,
    )


def _percentile(values: Sequence[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    pos = (q / 100.0) * (len(ordered) - 1)
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return float(ordered[lo])
    frac = pos - lo
    return float(ordered[lo] + frac * (ordered[hi] - ordered[lo]))


@dataclass(frozen=True)
class ExamplePrediction:
    """Serialized prediction record written to ``predictions.jsonl``."""

    example_id: str
    db_id: str
    question: str
    category: str
    difficulty: str
    intent: str
    expected_outcome: str
    status: str
    attempts: int
    latency_ms: float
    gold_sql: str | None
    pred_sql: str | None
    ex_match: bool | None
    ves_score: float | None
    parseable: bool
    executable: bool
    linked_tables: tuple[str, ...]
    gold_tables: tuple[str, ...]
    generated_unsafe: bool
    db_reached_unsafe: bool
    clarification: str | None = None
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _load_dataset_from_config(config: ExperimentConfig, *, base_dir: Path, repo_root: Path) -> LoadedDataset:
    if not config.dataset_path:
        raise ConfigError("dataset_path belirtilmedi ve bellek içi veri kümesi verilmedi.")
    resolved = _resolve_path(config.dataset_path, base_dir=base_dir, repo_root=repo_root)
    if resolved is None or not resolved.exists():
        raise FileNotFoundError(f"Veri kümesi dosyası bulunamadı: {config.dataset_path}")

    kind = config.dataset.strip().lower()
    if kind in {"turspider", "spider"}:
        return load_turspider(resolved, split=config.split)
    if kind == "birdturk":
        return load_birdturk(resolved, split=config.split, for_training=False)
    if kind == "enterprise":
        return load_enterprise(resolved, split=config.split)
    raise ConfigError(f"Desteklenmeyen veri kümesi türü: {config.dataset!r}")


def _resolve_sqlite_path(
    db_id: str,
    config: ExperimentConfig,
    *,
    base_dir: Path,
    repo_root: Path,
) -> Path | None:
    if config.db_dir:
        db_dir = _resolve_path(config.db_dir, base_dir=base_dir, repo_root=repo_root)
        if db_dir is not None:
            for candidate in (
                db_dir / db_id / f"{db_id}.sqlite",
                db_dir / db_id / f"{db_id}.db",
                db_dir / f"{db_id}.sqlite",
                db_dir / f"{db_id}.db",
            ):
                if candidate.exists():
                    return candidate
    if config.db_path:
        return _resolve_path(config.db_path, base_dir=base_dir, repo_root=repo_root)
    return None


def _build_auth(config: ExperimentConfig, schema: SchemaSnapshot) -> AuthContext:
    allowed = (
        frozenset(t.lower() for t in config.allowed_tables)
        if config.allowed_tables is not None
        else schema.table_names
    )
    return AuthContext(
        user_id=config.user_id,
        tenant_id=config.tenant_id,
        roles=frozenset(config.roles),
        allowed_tables=allowed,
        denied_columns=frozenset(c.lower() for c in config.denied_columns),
        max_rows=config.max_rows,
    )


def _compute_group_metrics(
    records: Sequence[ExamplePrediction],
    safety_records: Sequence[SafetyRecord],
    linking_samples: Sequence[SchemaLinkingSample],
    exec_comparisons: Sequence[ExecutionComparison | None],
    *,
    dialect: str,
    schema: SchemaSnapshot | None,
) -> dict[str, Any]:
    latencies = [r.latency_ms for r in records]
    answerable_indices = [i for i, r in enumerate(records) if r.gold_sql is not None]
    answerable_ex = [bool(records[i].ex_match) for i in answerable_indices]
    answerable_comp = [c for i in answerable_indices if (c := exec_comparisons[i]) is not None]

    pred_sqls = [r.pred_sql or "" for r in records if r.pred_sql is not None]
    exec_outcomes = [r.executable for r in records if r.pred_sql is not None]
    validity = compute_validity_metrics(
        pred_sqls,
        dialect=dialect,
        execution_outcomes=exec_outcomes,
        schema=schema,
    )

    group_linking = [linking_samples[i] for i in answerable_indices if i < len(linking_samples)]
    linking = SchemaLinkingMetrics.evaluate(group_linking, dialect=dialect, schema=schema)
    safety = SafetyMetrics.compute(safety_records, dialect=dialect)

    attempted = [r for r in records if r.attempts > 0]
    retried = [r for r in attempted if r.attempts > 1]
    outcome_counts = {
        status.value: sum(1 for r in records if r.status == status.value) for status in OutcomeStatus
    }

    return {
        "count": len(records),
        "answerable_count": len(answerable_indices),
        "execution_accuracy": execution_accuracy(answerable_ex) if answerable_ex else 0.0,
        "ves": valid_efficiency_score(answerable_comp) if answerable_comp else 0.0,
        "parseable_rate": validity.parseable_rate,
        "executable_rate": validity.executable_rate,
        "schema_linking": asdict(linking),
        "safety": asdict(safety),
        "latency_ms": {
            "p50": _percentile(latencies, 50.0),
            "p95": _percentile(latencies, 95.0),
            "mean": (sum(latencies) / len(latencies)) if latencies else 0.0,
            "max": max(latencies) if latencies else 0.0,
        },
        "retry": {
            "attempted": len(attempted),
            "retry_rate": (len(retried) / len(attempted)) if attempted else 0.0,
            "mean_attempts": (sum(r.attempts for r in attempted) / len(attempted)) if attempted else 0.0,
        },
        "outcome_counts": outcome_counts,
    }


def run_benchmark(
    config: ExperimentConfig,
    *,
    dataset: LoadedDataset | None = None,
    pipeline: Pipeline | None = None,
    database: DatabaseAdapter | None = None,
    model: ModelAdapter | None = None,
    knowledge: InMemoryKnowledgeBase | None = None,
    audit_sink: InMemoryAuditSink | None = None,
    allow_dirty: bool | None = None,
    output_dir: str | Path | None = None,
    base_dir: str | Path | None = None,
    repo_root: str | Path | None = None,
    now: Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    """Run an evaluation experiment, returning the structured ``metrics.json`` payload."""
    resolved_repo = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[1]
    resolved_base = Path(base_dir) if base_dir is not None else resolved_repo

    effective_allow_dirty = config.allow_dirty if allow_dirty is None else allow_dirty
    if not effective_allow_dirty and is_git_dirty(resolved_repo):
        raise DirtyWorkingTreeError(
            "Kirli Git çalışma ağacında deney koşulamaz (evaluation-plan §6.3). "
            "Değişiklikleri commit'leyin veya allow_dirty=True geçin."
        )

    loaded = dataset or _load_dataset_from_config(config, base_dir=resolved_base, repo_root=resolved_repo)
    examples: Sequence[BenchmarkExample] = loaded.examples
    if config.max_examples is not None:
        examples = examples[: config.max_examples]

    kb = knowledge
    if kb is None:
        kpath = _resolve_path(config.knowledge_path, base_dir=resolved_base, repo_root=resolved_repo)
        kb = load_knowledge_base(kpath) if kpath is not None and kpath.exists() else InMemoryKnowledgeBase()

    sink = audit_sink or InMemoryAuditSink()
    active_model = model
    if pipeline is None and active_model is None:
        active_model = create_model_adapter(config.settings.model)

    pipeline_cache: dict[str, tuple[Pipeline, DatabaseAdapter, Path | None, SchemaSnapshot]] = {}
    if pipeline is not None and database is not None:
        schema = database.introspect()
        default_db_file = _resolve_sqlite_path("", config, base_dir=resolved_base, repo_root=resolved_repo)
        pipeline_cache["__default__"] = (pipeline, database, default_db_file, schema)

    def _get_runner_for_db(
        db_id: str,
    ) -> tuple[Pipeline, DatabaseAdapter, Path | None, SchemaSnapshot]:
        if "__default__" in pipeline_cache:
            return pipeline_cache["__default__"]
        if db_id in pipeline_cache:
            return pipeline_cache[db_id]

        db_file = _resolve_sqlite_path(db_id, config, base_dir=resolved_base, repo_root=resolved_repo)
        adapter: DatabaseAdapter
        if database is not None:
            adapter = database
        elif db_file is not None:
            adapter = SQLiteAdapter(db_file)
        else:
            raise ConfigError(f"'{db_id}' için SQLite veritabanı yolu bulunamadı.")

        if active_model is None:
            raise ConfigError("ModelAdapter sağlanamadı.")
        built = build_default_pipeline(
            settings=config.settings,
            database=adapter,
            model=active_model,
            knowledge=kb,
            nlp_lexicon=config.nlp_lexicon,
            schema_lexicon=config.schema_lexicon,
            locations=frozenset(config.locations),
            audit_sink=sink,
        )
        snap = adapter.introspect()
        entry = (built, adapter, db_file, snap)
        pipeline_cache[db_id] = entry
        return entry

    hardware_before = collect_hardware_info(resolved_repo, now=now)
    peak_vram = hardware_before.peak_vram_used_mb

    predictions: list[ExamplePrediction] = []
    safety_records: list[SafetyRecord] = []
    abstention_records: list[AbstentionRecord] = []
    linking_samples: list[SchemaLinkingSample] = []
    exec_comparisons: list[ExecutionComparison | None] = []
    test_suite_cases: list[TestSuiteCase] = []
    first_schema: SchemaSnapshot | None = None

    for ex in examples:
        pipe, _, db_file, schema = _get_runner_for_db(ex.db_id)
        if first_schema is None:
            first_schema = schema
        auth = _build_auth(config, schema)
        request = QueryRequest(question=ex.question, connection_id=ex.db_id or "default")

        started = time.perf_counter()
        outcome: PipelineOutcome = pipe.run(request, auth)
        latency_ms = (time.perf_counter() - started) * 1000.0

        req_events: list[AuditEvent] = [e for e in sink.events if e.request_id == request.request_id]
        parse_event = next((e for e in req_events if e.stage == "parse"), None)
        plan_event = next((e for e in req_events if e.stage == "plan"), None)
        validate_events = [e for e in req_events if e.stage == "validate"]
        execute_event = next((e for e in req_events if e.stage == "execute" and e.status == "ok"), None)

        intent_val = (
            parse_event.details.get("intent", Intent.UNKNOWN.value)
            if parse_event is not None
            else Intent.UNKNOWN.value
        )
        linked_tables_raw = plan_event.details.get("tables", "") if plan_event is not None else ""
        linked_tables = tuple(t for t in linked_tables_raw.split(",") if t)

        generated_sqls = tuple(
            e.details["sql"] for e in validate_events if "sql" in e.details and e.details["sql"].strip()
        )
        pred_sql = (
            outcome.report.sql
            if outcome.report is not None
            else (generated_sqls[-1] if generated_sqls else None)
        )
        db_executed = (execute_event is not None) or (outcome.status is OutcomeStatus.ANSWERED)

        exec_ms = 0.0
        if execute_event is not None and "ms" in execute_event.details:
            try:
                exec_ms = float(execute_event.details["ms"])
            except ValueError:
                exec_ms = 0.0

        gold_tables: tuple[str, ...] = ()
        ex_match: bool | None = None
        ves_score: float | None = None
        comp: ExecutionComparison | None = None

        if ex.gold_sql is not None:
            extracted = extract_gold_tables_and_columns(
                ex.gold_sql,
                dialect=config.dialect.value,
                schema=schema,
            )
            gold_tables = tuple(sorted(extracted.tables))
            linking_samples.append(
                SchemaLinkingSample(
                    gold_sql=ex.gold_sql,
                    pred_tables=linked_tables,
                )
            )
            gold_rows: tuple[tuple[Any, ...], ...] = ()
            gold_ms = 0.0
            if db_file is not None:
                g_start = time.perf_counter()
                g_ok, gold_rows, g_err = execute_sqlite_readonly(
                    db_file,
                    ex.gold_sql,
                    timeout_ms=config.settings.execution.timeout_ms,
                    max_rows=config.max_rows,
                )
                gold_ms = (time.perf_counter() - g_start) * 1000.0
                if not g_ok:
                    raise RuntimeError(f"Altın SQL çalıştırılamadı ({ex.example_id}): {g_err}")

            if outcome.status is OutcomeStatus.ANSWERED and outcome.report is not None:
                pred_rows = outcome.report.rows
                ex_match = results_match_sql(
                    ex.gold_sql,
                    gold_rows,
                    pred_rows,
                    dialect=config.dialect.value,
                )
                comp = ExecutionComparison(
                    gold_sql=ex.gold_sql,
                    gold_rows=gold_rows,
                    pred_rows=pred_rows,
                    gold_ms=gold_ms,
                    pred_ms=exec_ms or latency_ms,
                    pred_valid=True,
                    dialect=config.dialect.value,
                )
                ves_score = valid_efficiency_score([comp])
                if config.test_suite_dbs and pred_sql:
                    test_suite_cases.append(
                        TestSuiteCase(
                            gold_sql=ex.gold_sql,
                            pred_sql=pred_sql,
                            dialect=config.dialect.value,
                        )
                    )
            else:
                ex_match = False
                comp = ExecutionComparison(
                    gold_sql=ex.gold_sql,
                    gold_rows=gold_rows,
                    pred_rows=(),
                    gold_ms=gold_ms,
                    pred_ms=0.0,
                    pred_valid=False,
                    dialect=config.dialect.value,
                )
                ves_score = 0.0
                if config.test_suite_dbs:
                    test_suite_cases.append(
                        TestSuiteCase(
                            gold_sql=ex.gold_sql,
                            pred_sql=pred_sql or "",
                            dialect=config.dialect.value,
                        )
                    )
        else:
            linking_samples.append(SchemaLinkingSample(gold_sql="", pred_tables=linked_tables))

        exec_comparisons.append(comp)

        is_attack = ex.category == "security_attack"
        was_rejected = outcome.status is OutcomeStatus.REJECTED
        has_security_verdict = any(e.status == "rejected" for e in validate_events)
        safety_rec = SafetyRecord(
            is_attack=is_attack,
            generated_sqls=generated_sqls,
            was_rejected=was_rejected,
            db_executed=db_executed,
            sql_unsafe=True if has_security_verdict else None,
            answerable=(ex.gold_sql is not None),
        )
        safety_records.append(safety_rec)
        abstention_records.append(AbstentionRecord(gold_category=ex.category, pred_status=outcome.status))

        item_safety = SafetyMetrics.compute(
            [safety_rec],
            dialect=config.dialect.value,
            allowed_tables=auth.allowed_tables,
            denied_columns=auth.denied_columns,
        )
        parseable = pred_sql is not None and is_parseable_sql(pred_sql, dialect=config.dialect.value)

        predictions.append(
            ExamplePrediction(
                example_id=ex.example_id,
                db_id=ex.db_id,
                question=mask_sensitive(ex.question),
                category=ex.category,
                difficulty=ex.difficulty,
                intent=intent_val,
                expected_outcome=ex.expected_outcome,
                status=outcome.status.value,
                attempts=outcome.attempts,
                latency_ms=round(latency_ms, 3),
                gold_sql=ex.gold_sql,
                pred_sql=pred_sql,
                ex_match=ex_match,
                ves_score=ves_score,
                parseable=parseable,
                executable=db_executed,
                linked_tables=linked_tables,
                gold_tables=gold_tables,
                generated_unsafe=item_safety.generated_unsafe_count > 0,
                db_reached_unsafe=item_safety.db_reached_unsafe_count > 0,
                clarification=mask_sensitive(outcome.clarification) if outcome.clarification else None,
                reason=mask_sensitive(outcome.reason) if outcome.reason else None,
            )
        )

    post_vram = sample_vram_mb()
    if post_vram is not None:
        peak_vram = max(peak_vram, post_vram) if peak_vram is not None else post_vram

    summary = _compute_group_metrics(
        predictions,
        safety_records,
        linking_samples,
        exec_comparisons,
        dialect=config.dialect.value,
        schema=first_schema,
    )
    abstention = AbstentionMetrics.compute(abstention_records)
    summary["abstention"] = asdict(abstention)

    if config.test_suite_dbs and test_suite_cases:
        resolved_ts = [
            resolved
            for raw_p in config.test_suite_dbs
            if (resolved := _resolve_path(raw_p, base_dir=resolved_base, repo_root=resolved_repo)) is not None
        ]
        summary["test_suite_accuracy"] = evaluate_test_suite(test_suite_cases, resolved_ts).accuracy
    else:
        summary["test_suite_accuracy"] = None

    by_difficulty: dict[str, Any] = {}
    for diff in sorted({p.difficulty for p in predictions}):
        idxs = [i for i, p in enumerate(predictions) if p.difficulty == diff]
        by_difficulty[diff] = _compute_group_metrics(
            [predictions[i] for i in idxs],
            [safety_records[i] for i in idxs],
            [linking_samples[i] for i in idxs],
            [exec_comparisons[i] for i in idxs],
            dialect=config.dialect.value,
            schema=first_schema,
        )

    by_intent: dict[str, Any] = {}
    for intent_key in sorted({p.intent for p in predictions}):
        idxs = [i for i, p in enumerate(predictions) if p.intent == intent_key]
        by_intent[intent_key] = _compute_group_metrics(
            [predictions[i] for i in idxs],
            [safety_records[i] for i in idxs],
            [linking_samples[i] for i in idxs],
            [exec_comparisons[i] for i in idxs],
            dialect=config.dialect.value,
            schema=first_schema,
        )

    hw_dict = hardware_before.to_dict()
    hw_dict["peak_vram_used_mb"] = peak_vram

    model_id = active_model.info.model_id if active_model is not None else config.settings.model.adapter
    metrics_payload: dict[str, Any] = {
        "experiment": {
            "name": config.name,
            "stage": config.stage,
            "model": model_id,
            "quantization": config.quantization,
            "dataset": loaded.name,
            "split": loaded.split,
            "seed": config.seed,
            "template_id": config.template_id,
            "description": config.description,
            "timestamp": (now() if now is not None else datetime.now(UTC)).isoformat(),
        },
        "dataset": {
            "name": loaded.name,
            "split": loaded.split,
            "license": loaded.license,
            "eval_only": loaded.eval_only,
            "sha256": loaded.sha256,
            "source_path": loaded.source_path,
            "total_examples": len(predictions),
            "answerable_examples": sum(1 for p in predictions if p.gold_sql is not None),
        },
        "git": {
            "commit": get_git_commit(resolved_repo),
            "dirty": is_git_dirty(resolved_repo),
            "allow_dirty": effective_allow_dirty,
        },
        "hardware": hw_dict,
        "summary": summary,
        "by_difficulty": by_difficulty,
        "by_intent": by_intent,
    }

    target_dir = (
        Path(output_dir)
        if output_dir is not None
        else (
            _resolve_path(config.output_dir, base_dir=resolved_base, repo_root=resolved_repo)
            or (resolved_repo / "benchmarks" / "results" / config.name)
        )
    )
    target_dir.mkdir(parents=True, exist_ok=True)

    pred_path = target_dir / "predictions.jsonl"
    with pred_path.open("w", encoding="utf-8") as fh:
        for pred in predictions:
            fh.write(json.dumps(pred.to_dict(), ensure_ascii=False) + "\n")

    metrics_path = target_dir / "metrics.json"
    metrics_path.write_text(
        json.dumps(metrics_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    return metrics_payload


def run_config_file(
    config_path: str | Path,
    *,
    allow_dirty: bool | None = None,
    output_dir: str | Path | None = None,
    model: ModelAdapter | None = None,
    database: DatabaseAdapter | None = None,
    knowledge: InMemoryKnowledgeBase | None = None,
    repo_root: str | Path | None = None,
) -> dict[str, Any]:
    """Load ``config.toml`` from ``config_path`` and run the benchmark."""
    p = Path(config_path).resolve()
    config = load_experiment_config(p, repo_root=repo_root)
    return run_benchmark(
        config,
        allow_dirty=allow_dirty,
        output_dir=output_dir or p.parent,
        base_dir=p.parent,
        repo_root=repo_root,
        model=model,
        database=database,
        knowledge=knowledge,
    )


def _main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="TRSQL deney koşucusu")
    parser.add_argument("--config", required=True, help="Deney config.toml dosyası")
    parser.add_argument("--output-dir", default=None, help="Çıktı klasörü (predictions.jsonl + metrics.json)")
    parser.add_argument("--allow-dirty", action="store_true", help="Kirli git ağacında çalışmaya izin ver")
    args = parser.parse_args(list(argv) if argv is not None else None)
    run_config_file(
        args.config,
        allow_dirty=True if args.allow_dirty else None,
        output_dir=args.output_dir,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())


__all__ = [
    "DirtyWorkingTreeError",
    "ExamplePrediction",
    "ExperimentConfig",
    "load_experiment_config",
    "run_benchmark",
    "run_config_file",
]
