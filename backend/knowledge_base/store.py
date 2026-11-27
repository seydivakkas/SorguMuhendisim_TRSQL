from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from backend.core.contracts import BusinessRule, FewShotExample, MetricDefinition


@dataclass(frozen=True)
class InMemoryKnowledgeBase:
    rules: tuple[BusinessRule, ...] = ()
    metrics: tuple[MetricDefinition, ...] = ()
    examples: tuple[FewShotExample, ...] = field(default=())

    def approved_rules(self) -> tuple[BusinessRule, ...]:
        return tuple(r for r in self.rules if r.approved)


def load_knowledge_base(path: str | Path) -> InMemoryKnowledgeBase:
    data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    return InMemoryKnowledgeBase(
        rules=tuple(BusinessRule.model_validate(r) for r in data.get("rules", [])),
        metrics=tuple(MetricDefinition.model_validate(m) for m in data.get("metrics", [])),
        examples=tuple(FewShotExample.model_validate(e) for e in data.get("examples", [])),
    )
