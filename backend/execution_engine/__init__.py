"""L7 — Database Execution Engine.

The single gateway to the database. Accepts only :class:`ApprovedQuery`
(which cannot exist without an APPROVED validation report).
"""

from backend.execution_engine.engine import ExecutionEngine

__all__ = ["ExecutionEngine"]
