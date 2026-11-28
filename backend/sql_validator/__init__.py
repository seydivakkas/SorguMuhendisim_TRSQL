"""L6 — Multi-stage SQL verification.

Every candidate goes through syntax, AST, schema, authorization, injection,
cost, semantic and business-rule checks. Each failed check carries a
severity:

- ``REPAIRABLE`` → the orchestrator may regenerate with feedback
  (bounded by the retry budget, ADR-0006).
- ``SECURITY``  → hard reject, never retried (ADR-0005).

SQLGlot is used for parsing and AST analysis. It is *not* a security
guarantee on its own: the database layer still enforces read-only roles,
timeouts and row limits (defense in depth, see docs/security).
"""

from backend.sql_validator.business_rules import BusinessRuleSpec, validate_business_rules
from backend.sql_validator.cost import CostThresholds, check_ast_cost, evaluate_explain_plan
from backend.sql_validator.semantic import validate_semantics
from backend.sql_validator.validator import SQLValidator

__all__ = [
    "BusinessRuleSpec",
    "CostThresholds",
    "SQLValidator",
    "check_ast_cost",
    "evaluate_explain_plan",
    "validate_business_rules",
    "validate_semantics",
]
