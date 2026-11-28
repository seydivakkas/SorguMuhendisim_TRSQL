"""L1 — Authentication & RBAC.

Public API:
- :class:`StaticAuthProvider` — test/dev provider that maps tokens to contexts.
- :class:`HashedTokenAuthProvider` — SHA-256 constant-time token provider.
- :class:`RolePolicy`, :class:`TokenRecord`, :func:`load_role_policies`,
  :func:`load_token_records`, :func:`load_auth_provider`, :func:`hash_token`,
  :data:`DEFAULT_PII_DENIED_COLUMNS` — role policy and hashed token loaders.
- :func:`scope_schema` — returns the subset of a schema the user may see.

``scope_schema`` runs **before** any other layer sees the schema (ADR-0004),
so the NLP, linking, RAG and model layers can never learn that an
unauthorized table or column exists.
"""

from __future__ import annotations

from backend.auth.oidc import OIDCAuthProvider, OIDCConfig
from backend.auth.policies import (
    DEFAULT_PII_DENIED_COLUMNS,
    HashedTokenAuthProvider,
    RolePolicy,
    TokenRecord,
    hash_token,
    load_auth_provider,
    load_role_policies,
    load_token_records,
)
from backend.auth.provider import StaticAuthProvider
from backend.auth.scoping import scope_schema

__all__ = [
    "DEFAULT_PII_DENIED_COLUMNS",
    "HashedTokenAuthProvider",
    "OIDCAuthProvider",
    "OIDCConfig",
    "RolePolicy",
    "StaticAuthProvider",
    "TokenRecord",
    "hash_token",
    "load_auth_provider",
    "load_role_policies",
    "load_token_records",
    "scope_schema",
]
