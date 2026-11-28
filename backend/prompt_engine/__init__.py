"""L5 — Prompt Engine: builds versioned prompts from a plan.

Supports ``sql-gen/v1`` (compact baseline), ``ddl_v1`` (D0 classic DDL), and
``mschema_v1`` (D1 XiYan-style M-Schema with non-PII sample values), plus GBNF
grammar generation for constrained decoding. Only the scoped schema is ever
rendered (ADR-0004). Template ids are logged so every experiment is reproducible.
"""

from backend.prompt_engine.builder import SUPPORTED_TEMPLATES, TEMPLATE_ID, PromptBuilder, render_schema
from backend.prompt_engine.ddl import TEMPLATE_ID as DDL_TEMPLATE_ID
from backend.prompt_engine.ddl import render_ddl
from backend.prompt_engine.gbnf import build_gbnf_grammar_for_mode, build_sql_gbnf
from backend.prompt_engine.mschema import TEMPLATE_ID as MSCHEMA_TEMPLATE_ID
from backend.prompt_engine.mschema import is_pii_column, lookup_sample_values, render_mschema

__all__ = [
    "DDL_TEMPLATE_ID",
    "MSCHEMA_TEMPLATE_ID",
    "SUPPORTED_TEMPLATES",
    "TEMPLATE_ID",
    "PromptBuilder",
    "build_gbnf_grammar_for_mode",
    "build_sql_gbnf",
    "is_pii_column",
    "lookup_sample_values",
    "render_ddl",
    "render_mschema",
    "render_schema",
]
