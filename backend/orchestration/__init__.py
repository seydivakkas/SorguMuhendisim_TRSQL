"""Orchestration: runs the request lifecycle L1 → L9.

The only module that composes other modules. It depends on the stage
Protocols in ``backend.core.ports``; concrete modules are wired in
:func:`build_default_pipeline`. See ``docs/architecture/request-lifecycle.md``.
"""

from backend.orchestration.factory import build_default_pipeline
from backend.orchestration.knowledge import KnowledgeAssembler
from backend.orchestration.pipeline import Pipeline, PipelineStages

__all__ = ["KnowledgeAssembler", "Pipeline", "PipelineStages", "build_default_pipeline"]
