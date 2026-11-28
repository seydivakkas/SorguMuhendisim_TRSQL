"""Orchestration: runs the request lifecycle L1 → L9.

The only module that composes other modules. It depends on the stage
Protocols in ``backend.core.ports``; concrete modules are wired in
:func:`build_default_pipeline` and :func:`build_hybrid_pipeline`.
See ``docs/architecture/request-lifecycle.md``.
"""

from backend.orchestration.factory import build_default_pipeline, build_hybrid_pipeline
from backend.orchestration.knowledge import KnowledgeAssembler
from backend.orchestration.pipeline import Pipeline, PipelineStages, PlanPreview
from backend.orchestration.routing import ComplexityRouter
from backend.orchestration.voting import (
    VotingOutcome,
    normalize_execution_result,
    select_consistent_candidate,
    vote_candidates,
)

__all__ = [
    "ComplexityRouter",
    "KnowledgeAssembler",
    "Pipeline",
    "PipelineStages",
    "PlanPreview",
    "VotingOutcome",
    "build_default_pipeline",
    "build_hybrid_pipeline",
    "normalize_execution_result",
    "select_consistent_candidate",
    "vote_candidates",
]
