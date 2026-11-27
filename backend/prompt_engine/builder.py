from __future__ import annotations

from backend.core.contracts import (
    KnowledgeContext,
    ParsedQuestion,
    PromptBundle,
    QueryPlan,
    SchemaSnapshot,
)

TEMPLATE_ID = "sql-gen/v1"

_SYSTEM = (
    "Sen bir SQL üretim bileşenisin. Yalnızca tek bir SELECT sorgusu üret. "
    "Sadece verilen şemadaki tablo ve sütunları kullan. "
    "Veri değiştiren komut (INSERT, UPDATE, DELETE, DROP, ALTER...) yazma. "
    "Yanıtı yalnızca ```sql ... ``` bloğu içinde ver."
)


def render_schema(schema: SchemaSnapshot, tables: tuple[str, ...] = ()) -> str:
    wanted = {t.lower() for t in tables}
    lines: list[str] = [f"【DB_DIALECT】{schema.dialect.value}"]
    for t in schema.tables:
        if wanted and t.name.lower() not in wanted:
            continue
        head = f"# Table: {t.name}"
        if t.description:
            head += f"  -- {t.description}"
        lines.append(head)
        for c in t.columns:
            pk = ", PK" if c.is_primary_key else ""
            desc = f", {c.description}" if c.description else ""
            lines.append(f"  ({c.name}: {c.data_type}{pk}{desc})")
        for fk in t.foreign_keys:
            lines.append(f"  FK {t.name}.{fk.column} -> {fk.ref_table}.{fk.ref_column}")
    return "\n".join(lines)


class PromptBuilder:
    def build(
        self,
        plan: QueryPlan,
        schema: SchemaSnapshot,
        knowledge: KnowledgeContext,
        question: ParsedQuestion,
        feedback: tuple[str, ...] = (),
    ) -> PromptBundle:
        parts: list[str] = [render_schema(schema, plan.tables)]
        if knowledge.metrics:
            parts.append("【METRICS】")
            parts += [f"- {m.name}: {m.expression} (tablo: {m.base_table})" for m in knowledge.metrics]
        if knowledge.rules:
            parts.append("【BUSINESS_RULES】")
            parts += [f"- {r.term}: {r.definition}" for r in knowledge.rules]
        for t in plan.temporal:
            parts.append(f"【TIME】{t.text}: {t.start} <= tarih < {t.end}")
        if plan.sort:
            parts.append(f"【SORT】{plan.sort.value}")
        if plan.limit:
            parts.append(f"【LIMIT】{plan.limit}")
        for ex in knowledge.examples:
            parts.append(f"【EXAMPLE】{ex.question}\n```sql\n{ex.sql}\n```")
        if feedback:
            parts.append("【PREVIOUS_ATTEMPT_ERRORS】")
            parts += [f"- {f}" for f in feedback]
        parts.append(f"【QUESTION】{question.original_text}")
        return PromptBundle(template_id=TEMPLATE_ID, system=_SYSTEM, user="\n".join(parts))
