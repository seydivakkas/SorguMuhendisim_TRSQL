"""L3 — Schema Linking Intelligence.

Maps Turkish mentions (``bayi``, ``satış``, ``şehir``) to real tables and
columns of the *scoped* schema and finds the join path between them.
Hybrid (lexical + embedding) linking is evaluated in AR-03.
"""

from backend.schema_linking.linker import LexiconSchemaLinker

__all__ = ["LexiconSchemaLinker"]
