"""L6 — Policy Engine: the only producer of :class:`ApprovedQuery`.

Takes an APPROVED validation report, applies row limits and timeouts from
the user's context and settings, and returns the immutable query object
that the execution engine accepts.
"""

from backend.policy_engine.engine import PolicyEngine

__all__ = ["PolicyEngine"]
