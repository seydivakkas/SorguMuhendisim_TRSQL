"""L5 — Prompt Engine: builds versioned prompts from a plan.

The schema is rendered in a compact M-Schema-like text format. Only the
scoped schema is ever rendered (ADR-0004). Template ids are logged so every
experiment is reproducible.
"""

from backend.prompt_engine.builder import PromptBuilder, render_schema

__all__ = ["PromptBuilder", "render_schema"]
