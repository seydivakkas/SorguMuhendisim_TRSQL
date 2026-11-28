"""Schema intelligence: a graph view of a (scoped) schema.

Builds an undirected PK/FK graph and finds join paths that connect a set of
tables. Pure Python for now; NetworkX / Steiner-tree variants are evaluated
in AR-03 (ablation tier D2).
"""

from backend.schema_intelligence.graph import SchemaGraph

__all__ = ["SchemaGraph"]
