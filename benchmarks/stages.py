"""Cumulative ablation stage profiles D0-D8 (evaluation-plan §3)."""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from dataclasses import asdict, dataclass, fields, replace
from pathlib import Path
from typing import Any, Literal

from backend.core.config import Settings
from backend.core.contracts import MentionKind
from backend.core.errors import ConfigError, ExecutionError
from backend.core.ports import AuditSink, DatabaseAdapter, EmbeddingAdapter, ModelAdapter
from backend.knowledge_base import InMemoryKnowledgeBase
from backend.model_engine import create_embedding_adapter
from backend.orchestration import Pipeline, build_default_pipeline, build_hybrid_pipeline
from backend.rag import DeterministicHashEmbedder

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StageProfile:
    """Cumulative configuration bundle for a single ablation stage (D0..D8)."""

    stage: str
    pipeline: Literal["default", "hybrid"]
    prompt_template_id: str
    linker: Literal["lexicon", "hybrid"]
    rag: Literal["off", "rules", "rules_examples", "full"]
    turkish_nlp: Literal["basic", "morphology_ambiguity"]
    fail_closed_full: bool
    routing_enabled: bool
    vote_candidates: int
    max_attempts: int
    use_kpi_templates: bool
    grammar_constrained: bool = False
    fine_tuned_adapter: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


STAGE_PROFILES: dict[str, StageProfile] = {
    "D0": StageProfile(
        stage="D0",
        pipeline="default",
        prompt_template_id="ddl_v1",
        linker="lexicon",
        rag="off",
        turkish_nlp="basic",
        fail_closed_full=False,
        routing_enabled=False,
        vote_candidates=1,
        max_attempts=1,
        use_kpi_templates=False,
    ),
    "D1": StageProfile(
        stage="D1",
        pipeline="default",
        prompt_template_id="mschema_v1",
        linker="lexicon",
        rag="off",
        turkish_nlp="basic",
        fail_closed_full=False,
        routing_enabled=False,
        vote_candidates=1,
        max_attempts=1,
        use_kpi_templates=False,
    ),
    "D2": StageProfile(
        stage="D2",
        pipeline="hybrid",
        prompt_template_id="mschema_v1",
        linker="hybrid",
        rag="off",
        turkish_nlp="basic",
        fail_closed_full=False,
        routing_enabled=False,
        vote_candidates=1,
        max_attempts=1,
        use_kpi_templates=False,
    ),
    "D3": StageProfile(
        stage="D3",
        pipeline="hybrid",
        prompt_template_id="mschema_v1",
        linker="hybrid",
        rag="full",
        turkish_nlp="basic",
        fail_closed_full=False,
        routing_enabled=False,
        vote_candidates=1,
        max_attempts=1,
        use_kpi_templates=False,
    ),
    "D4": StageProfile(
        stage="D4",
        pipeline="hybrid",
        prompt_template_id="mschema_v1",
        linker="hybrid",
        rag="full",
        turkish_nlp="morphology_ambiguity",
        fail_closed_full=False,
        routing_enabled=False,
        vote_candidates=1,
        max_attempts=1,
        use_kpi_templates=False,
    ),
    "D5": StageProfile(
        stage="D5",
        pipeline="hybrid",
        prompt_template_id="mschema_v1",
        linker="hybrid",
        rag="full",
        turkish_nlp="morphology_ambiguity",
        fail_closed_full=True,
        routing_enabled=False,
        vote_candidates=1,
        max_attempts=1,
        use_kpi_templates=False,
    ),
    "D6": StageProfile(
        stage="D6",
        pipeline="hybrid",
        prompt_template_id="mschema_v1",
        linker="hybrid",
        rag="full",
        turkish_nlp="morphology_ambiguity",
        fail_closed_full=True,
        routing_enabled=True,
        vote_candidates=4,
        max_attempts=3,
        use_kpi_templates=False,
    ),
    "D7": StageProfile(
        stage="D7",
        pipeline="hybrid",
        prompt_template_id="mschema_v1",
        linker="hybrid",
        rag="full",
        turkish_nlp="morphology_ambiguity",
        fail_closed_full=True,
        routing_enabled=True,
        vote_candidates=4,
        max_attempts=3,
        use_kpi_templates=False,
        fine_tuned_adapter=True,
    ),
    "D8": StageProfile(
        stage="D8",
        pipeline="hybrid",
        prompt_template_id="mschema_v1",
        linker="hybrid",
        rag="full",
        turkish_nlp="morphology_ambiguity",
        fail_closed_full=True,
        routing_enabled=True,
        vote_candidates=4,
        max_attempts=3,
        use_kpi_templates=True,
    ),
}

_VALID_PROFILE_FIELDS = {f.name for f in fields(StageProfile) if f.name != "stage"}


def resolve_stage_profile(
    stage: str,
    overrides: Mapping[str, Any] | None = None,
) -> StageProfile:
    """Resolve cumulative D0..D8 stage profile with validated single-flag overrides."""
    key = stage.strip().upper()
    base = STAGE_PROFILES.get(key)
    if base is None:
        raise ConfigError(f"Bilinmeyen ablasyon basamağı: {stage!r} (beklenen: {sorted(STAGE_PROFILES)})")
    if not overrides:
        return base

    unknown = sorted(set(overrides) - _VALID_PROFILE_FIELDS)
    if unknown:
        raise ConfigError(f"Geçersiz stage_overrides anahtarları: {unknown}")

    updated = replace(base, **dict(overrides))
    if not 1 <= updated.max_attempts <= 5:
        raise ConfigError(
            f"max_attempts 1 ile 5 arasında olmalıdır (ADR-0006), gelen: {updated.max_attempts}"
        )
    if updated.vote_candidates < 1:
        raise ConfigError(f"vote_candidates >= 1 olmalıdır, gelen: {updated.vote_candidates}")
    if updated.pipeline not in ("default", "hybrid"):
        raise ConfigError(f"Geçersiz pipeline değeri: {updated.pipeline!r}")
    if updated.rag not in ("off", "rules", "rules_examples", "full"):
        raise ConfigError(f"Geçersiz rag değeri: {updated.rag!r}")
    return updated


def apply_profile_to_settings(settings: Settings, profile: StageProfile) -> Settings:
    """Return a copy of *settings* aligned with *profile* without lowering security invariants."""
    if profile.rag == "off":
        rag = settings.rag.model_copy(
            update={
                "enable_schema_rag": False,
                "enable_rule_rag": False,
                "enable_example_rag": False,
                "enable_value_linking": False,
            }
        )
    elif profile.rag == "rules":
        rag = settings.rag.model_copy(
            update={
                "enable_schema_rag": False,
                "enable_rule_rag": True,
                "enable_example_rag": False,
                "enable_value_linking": False,
            }
        )
    elif profile.rag == "rules_examples":
        rag = settings.rag.model_copy(
            update={
                "enable_schema_rag": False,
                "enable_rule_rag": True,
                "enable_example_rag": True,
                "enable_value_linking": False,
            }
        )
    else:
        rag = settings.rag

    retry = settings.retry.model_copy(update={"max_attempts": profile.max_attempts})
    routing = settings.routing.model_copy(
        update={
            "enabled": profile.routing_enabled,
            "vote_candidates": profile.vote_candidates,
        }
    )
    return settings.model_copy(update={"retry": retry, "rag": rag, "routing": routing})


def resolve_embedder_for_settings(
    settings: Settings,
    profile: StageProfile,
    *,
    environ: Mapping[str, str] | None = None,
) -> tuple[EmbeddingAdapter | None, str]:
    """Select real embedding adapter when configured or explicitly fall back to hash embedder."""
    if profile.pipeline == "default" or profile.rag == "off":
        return None, "none"

    env = os.environ if environ is None else environ
    emb_env = settings.model.embedding_model_path_env.strip()
    emb_path = env.get(emb_env, "").strip() if emb_env else ""
    if emb_path and (settings.model.adapter == "fake" or Path(emb_path).is_file()):
        try:
            adapter = create_embedding_adapter(settings.model)
            return adapter, f"adapter:{settings.model.adapter}"
        except (ConfigError, ExecutionError, OSError) as exc:
            _logger.warning(
                "Gömme adaptörü başlatılamadı (%s); DeterministicHashEmbedder yedeğine düşülüyor.",
                type(exc).__name__,
            )
            return DeterministicHashEmbedder(), "hash-fallback"

    _logger.warning(
        "Gömme modeli ortam değişkeni (%s) tanımlı değil; DeterministicHashEmbedder (hash-fallback) aktif.",
        emb_env or "<boş>",
    )
    return DeterministicHashEmbedder(), "hash-fallback"


def build_pipeline_for_profile(
    profile: StageProfile,
    *,
    settings: Settings,
    database: DatabaseAdapter,
    model: ModelAdapter,
    knowledge: InMemoryKnowledgeBase,
    nlp_lexicon: Mapping[str, MentionKind],
    schema_lexicon: Mapping[str, str],
    locations: frozenset[str],
    audit_sink: AuditSink,
    embedder: EmbeddingAdapter | None = None,
) -> Pipeline:
    """Build either default or hybrid :class:`Pipeline` for *profile* keeping L6 security intact."""
    if profile.pipeline == "default":
        return build_default_pipeline(
            settings=settings,
            database=database,
            model=model,
            knowledge=knowledge,
            nlp_lexicon=nlp_lexicon,
            schema_lexicon=schema_lexicon,
            locations=locations,
            audit_sink=audit_sink,
            prompt_template_id=profile.prompt_template_id,
        )

    return build_hybrid_pipeline(
        settings=settings,
        database=database,
        model=model,
        knowledge=knowledge,
        nlp_lexicon=nlp_lexicon,
        schema_lexicon=schema_lexicon,
        locations=locations,
        audit_sink=audit_sink,
        embedder=embedder,
        prompt_template_id=profile.prompt_template_id,
        use_kpi_templates=profile.use_kpi_templates,
    )


__all__ = [
    "STAGE_PROFILES",
    "StageProfile",
    "apply_profile_to_settings",
    "build_pipeline_for_profile",
    "resolve_embedder_for_settings",
    "resolve_stage_profile",
]
