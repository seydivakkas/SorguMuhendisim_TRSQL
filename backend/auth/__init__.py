"""L1 — Authentication & RBAC.

Public API:
- :class:`StaticAuthProvider` — test/dev provider that maps tokens to contexts.
- :func:`scope_schema` — returns the subset of a schema the user may see.

``scope_schema`` runs **before** any other layer sees the schema (ADR-0004),
so the NLP, linking, RAG and model layers can never learn that an
unauthorized table or column exists.
"""

from backend.auth.provider import StaticAuthProvider
from backend.auth.scoping import scope_schema

__all__ = ["StaticAuthProvider", "scope_schema"]
