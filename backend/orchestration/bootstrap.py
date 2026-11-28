"""Composition root building a live :class:`Pipeline` from environment settings."""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from pathlib import Path

from backend.core.config import Settings, load_settings
from backend.core.contracts import Dialect, MentionKind
from backend.core.errors import ConfigError, ExecutionError
from backend.core.ports import AuditSink, DatabaseAdapter, EmbeddingAdapter, ModelAdapter
from backend.database_adapters import PostgresAdapter, SQLiteAdapter
from backend.knowledge_base import InMemoryKnowledgeBase, load_knowledge_base
from backend.model_engine import create_embedding_adapter, create_model_adapter
from backend.observability import InMemoryAuditSink, JsonlAuditSink, MetricsCollector
from backend.orchestration.factory import build_default_pipeline, build_hybrid_pipeline
from backend.orchestration.pipeline import Pipeline
from backend.rag import DeterministicHashEmbedder

_logger = logging.getLogger(__name__)


def _has_pg_dsn_syntax(dsn: str) -> bool:
    stripped = dsn.strip()
    if not stripped:
        return False
    if stripped.startswith(("postgresql://", "postgres://")):
        return "@" in stripped or "localhost" in stripped or "127.0.0.1" in stripped or "/" in stripped[13:]
    return "host=" in stripped or "dbname=" in stripped


def build_database_adapter_from_env(
    settings: Settings,
    environ: Mapping[str, str] | None = None,
) -> DatabaseAdapter:
    """Create the configured :class:`DatabaseAdapter` without logging secret DSNs."""
    env = os.environ if environ is None else environ
    raw_dialect = env.get("TRSQL_DB_DIALECT", "").strip().lower()
    pg_dsn_set = bool(env.get("TRSQL_PG_DSN", "").strip())
    sqlite_path = env.get("TRSQL_SQLITE_PATH", "").strip()

    if not raw_dialect:
        if pg_dsn_set:
            raw_dialect = Dialect.POSTGRES.value
        elif sqlite_path:
            raw_dialect = Dialect.SQLITE.value
        else:
            raise ConfigError(
                "Veritabanı yapılandırması eksik: TRSQL_DB_DIALECT ('sqlite' veya 'postgres') ayarlanmalıdır."
            )

    if raw_dialect == Dialect.SQLITE.value:
        if not sqlite_path or not Path(sqlite_path).is_file():
            raise ConfigError("SQLite veritabanı dosyası bulunamadı (TRSQL_SQLITE_PATH).")
        return SQLiteAdapter(Path(sqlite_path))

    if raw_dialect == Dialect.POSTGRES.value:
        dsn_val = env.get("TRSQL_PG_DSN", "").strip()
        if not dsn_val:
            raise ConfigError("PostgreSQL bağlantı değişkeni tanımlı değil (TRSQL_PG_DSN).")
        if not _has_pg_dsn_syntax(dsn_val):
            raise ConfigError("PostgreSQL bağlantı dizesi geçersiz biçimde (TRSQL_PG_DSN).")
        raw_schemas = env.get("TRSQL_PG_SCHEMAS", "public")
        schemas = tuple(s.strip() for s in raw_schemas.split(",") if s.strip()) or ("public",)
        return PostgresAdapter(
            "TRSQL_PG_DSN",
            allowed_schemas=schemas,
            statement_timeout_ms=settings.execution.timeout_ms,
            max_explain_cost=settings.validation.max_explain_cost,
            max_explain_rows=settings.validation.max_explain_rows,
        )

    raise ConfigError(f"Desteklenmeyen veritabanı lehçesi: {raw_dialect!r}")


def build_embedder_from_env(
    settings: Settings,
    environ: Mapping[str, str] | None = None,
) -> tuple[EmbeddingAdapter, bool]:
    """Build the configured :class:`EmbeddingAdapter` or fall back with an explicit warning.

    Returns ``(adapter, is_hash_fallback)``.
    """
    env = os.environ if environ is None else environ
    if settings.model.adapter == "fake":
        return create_embedding_adapter(settings.model), False

    emb_env = settings.model.embedding_model_path_env
    emb_path = env.get(emb_env, "").strip()
    if not emb_path or not Path(emb_path).is_file():
        _logger.warning(
            "Gömme modeli dosyası bulunamadı (%s); DeterministicHashEmbedder yedeğine düşülüyor.",
            emb_env,
        )
        return DeterministicHashEmbedder(), True

    try:
        return create_embedding_adapter(settings.model), False
    except (ConfigError, ExecutionError, OSError) as exc:
        _logger.warning(
            "Gömme modeli yüklenemedi (%s: %s); DeterministicHashEmbedder yedeğine düşülüyor.",
            emb_env,
            type(exc).__name__,
        )
        return DeterministicHashEmbedder(), True


def build_pipeline_from_env(
    settings: Settings | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    database: DatabaseAdapter | None = None,
    model: ModelAdapter | None = None,
    audit_sink: AuditSink | None = None,
    metrics: MetricsCollector | None = None,
    nlp_lexicon: Mapping[str, MentionKind] | None = None,
    schema_lexicon: Mapping[str, str] | None = None,
    locations: frozenset[str] | None = None,
) -> Pipeline:
    """Compose the full TRSQL :class:`Pipeline` from TOML settings and environment variables.

    Never connects to external networks when ``settings.offline`` is ``True``
    (ADR-0002), and never includes connection strings or passwords in raised
    :class:`ConfigError` messages.
    """
    env = os.environ if environ is None else environ
    active_settings = settings
    if active_settings is None:
        config_path = env.get("TRSQL_CONFIG", "").strip() or "configs/default.toml"
        active_settings = load_settings(config_path)

    adapter_override = env.get("TRSQL_MODEL_ADAPTER", "").strip()
    if adapter_override:
        active_settings = active_settings.model_copy(
            update={"model": active_settings.model.model_copy(update={"adapter": adapter_override})}
        )

    pipeline_mode = env.get("TRSQL_PIPELINE", "hybrid").strip().lower() or "hybrid"
    if pipeline_mode not in {"default", "hybrid"}:
        raise ConfigError("Geçersiz hat türü: TRSQL_PIPELINE ('default' veya 'hybrid' olmalıdır).")

    active_db = database or build_database_adapter_from_env(active_settings, env)
    try:
        active_db.introspect()
    except Exception as exc:
        raise ConfigError("Veritabanı şeması okunamadı; bağlantı ayarlarını kontrol edin.") from exc

    knowledge_path = env.get("TRSQL_KNOWLEDGE", "").strip()
    if knowledge_path:
        try:
            knowledge = load_knowledge_base(knowledge_path)
        except (OSError, ValueError) as exc:
            raise ConfigError("Bilgi tabanı dosyası yüklenemedi (TRSQL_KNOWLEDGE).") from exc
    else:
        knowledge = InMemoryKnowledgeBase()

    try:
        active_model = model or create_model_adapter(active_settings.model)
    except ConfigError:
        raise
    except Exception as exc:
        raise ConfigError("Model adaptörü başlatılamadı; model yapılandırmasını kontrol edin.") from exc

    active_audit = audit_sink
    if active_audit is None:
        log_dir = env.get("TRSQL_AUDIT_LOG_DIR", "").strip()
        active_audit = JsonlAuditSink(Path(log_dir) / "audit.jsonl") if log_dir else InMemoryAuditSink()

    active_nlp: Mapping[str, MentionKind] = nlp_lexicon or {}
    active_schema_lex: Mapping[str, str] = schema_lexicon or {}
    active_locations: frozenset[str] = locations or frozenset()

    if pipeline_mode == "default":
        return build_default_pipeline(
            settings=active_settings,
            database=active_db,
            model=active_model,
            knowledge=knowledge,
            nlp_lexicon=active_nlp,
            schema_lexicon=active_schema_lex,
            locations=active_locations,
            audit_sink=active_audit,
        )

    embedder, _ = build_embedder_from_env(active_settings, env)
    return build_hybrid_pipeline(
        settings=active_settings,
        database=active_db,
        model=active_model,
        knowledge=knowledge,
        nlp_lexicon=active_nlp,
        schema_lexicon=active_schema_lex,
        locations=active_locations,
        audit_sink=active_audit,
        embedder=embedder,
        metrics=metrics,
    )
