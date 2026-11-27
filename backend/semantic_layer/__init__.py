"""L4 — Semantic Layer: resolves metric words (``net satış``, ``ciro``) to
approved, versioned :class:`MetricDefinition` objects so the model never
invents how a business metric is computed.
"""

from backend.semantic_layer.resolver import SemanticLayer

__all__ = ["SemanticLayer"]
