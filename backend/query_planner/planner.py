from __future__ import annotations

from backend.core.contracts import KnowledgeContext, LinkedSchema, ParsedQuestion, QueryPlan


class RuleBasedPlanner:
    def plan(self, question: ParsedQuestion, linked: LinkedSchema, knowledge: KnowledgeContext) -> QueryPlan:
        filters = tuple(r.sql_fragment for r in knowledge.rules if r.sql_fragment)
        return QueryPlan(
            intent=question.intent,
            tables=linked.tables,
            metrics=knowledge.metrics,
            filters=filters,
            temporal=question.temporal,
            sort=question.sort,
            limit=question.limit,
        )
