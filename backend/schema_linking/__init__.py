"""L3 — Schema Linking Intelligence.

Maps Turkish mentions (``bayi``, ``satış``, ``şehir``) to real tables and
columns of the *scoped* schema, repairs multi-hop join paths, and selects
columns within a token budget (AR-03).
"""

from backend.schema_linking.budget import (
    default_token_counter,
    estimate_schema_tokens,
    estimate_table_tokens,
    select_schema_within_budget,
)
from backend.schema_linking.hybrid import (
    BidirectionalLinkResult,
    EmbeddingPort,
    HybridSchemaLinker,
)
from backend.schema_linking.linker import LexiconSchemaLinker

__all__ = [
    "BidirectionalLinkResult",
    "EmbeddingPort",
    "HybridSchemaLinker",
    "LexiconSchemaLinker",
    "default_token_counter",
    "estimate_schema_tokens",
    "estimate_table_tokens",
    "select_schema_within_budget",
]
