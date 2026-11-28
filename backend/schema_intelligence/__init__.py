"""Schema intelligence: a graph view of a (scoped) schema.

Builds an undirected PK/FK graph, finds multi-hop Steiner join paths that
connect a set of tables, and inspects k-hop FK neighborhoods (AR-03).
"""

from backend.schema_intelligence.graph import SchemaGraph

__all__ = ["SchemaGraph"]
