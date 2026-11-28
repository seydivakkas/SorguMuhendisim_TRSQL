"""L5 — SQL Generator: calls a ``ModelAdapter`` and extracts a single SQL
candidate from its text output. The candidate is untrusted until L6."""

from backend.sql_generator.generator import SQLGenerator, extract_sql

__all__ = ["SQLGenerator", "extract_sql"]
