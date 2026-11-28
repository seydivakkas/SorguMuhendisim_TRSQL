"""L4 — Semantic Layer: resolves metric words (``net satış``, ``ciro``) to
approved, versioned :class:`MetricDefinition` objects and deterministic KPI
SQL templates so the model never invents how a business metric is computed.
"""

from __future__ import annotations

from backend.semantic_layer.resolver import SemanticLayer
from backend.semantic_layer.templates import (
    MetricTemplate,
    MetricTemplateRegistry,
    TemplateMatch,
    default_metric_templates,
)

__all__ = [
    "MetricTemplate",
    "MetricTemplateRegistry",
    "SemanticLayer",
    "TemplateMatch",
    "default_metric_templates",
]
