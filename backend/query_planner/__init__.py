"""L5 — Query Planner: turns the parsed question, linked schema and
knowledge into a model-independent :class:`QueryPlan`."""

from backend.query_planner.planner import RuleBasedPlanner

__all__ = ["RuleBasedPlanner"]
