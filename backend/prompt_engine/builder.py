from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence

from backend.core.contracts import (
    KnowledgeContext,
    ParsedQuestion,
    PromptBundle,
    QueryPlan,
    ReasoningMode,
    SchemaSnapshot,
)
from backend.core.errors import ConfigError
from backend.prompt_engine.ddl import TEMPLATE_ID as DDL_TEMPLATE_ID
from backend.prompt_engine.ddl import render_ddl
from backend.prompt_engine.mschema import TEMPLATE_ID as MSCHEMA_TEMPLATE_ID
from backend.prompt_engine.mschema import render_mschema

TEMPLATE_ID = "sql-gen/v1"
SUPPORTED_TEMPLATES: frozenset[str] = frozenset({TEMPLATE_ID, DDL_TEMPLATE_ID, MSCHEMA_TEMPLATE_ID})

_SYSTEM_DIRECT = (
    "Sen bir SQL üretim bileşenisin. Yalnızca tek bir SELECT sorgusu üret. "
    "Sadece verilen şemadaki tablo ve sütunları kullan. "
    "Veri değiştiren komut (INSERT, UPDATE, DELETE, DROP, ALTER...) yazma. "
    "Yanıtı yalnızca ```sql ... ``` bloğu içinde ver."
)

_SYSTEM_THINKING = (
    "Sen bir SQL üretim bileşenisin. Yalnızca tek bir SELECT sorgusu üret. "
    "Sadece verilen şemadaki tablo ve sütunları kullan. "
    "Veri değiştiren komut (INSERT, UPDATE, DELETE, DROP, ALTER...) yazma. "
    "Önce tabloları, JOIN yollarını, filtreleri ve iş kurallarını <think>...</think> bloğu içinde "
    "adım adım düşün; ardından son sorguyu yalnızca ```sql ... ``` bloğu içinde ver."
)


def render_schema(schema: SchemaSnapshot, tables: tuple[str, ...] = ()) -> str:
    """Compact baseline schema renderer preserved for ``sql-gen/v1``."""
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
    """Versioned prompt builder supporting ``sql-gen/v1``, ``ddl_v1``, and ``mschema_v1``."""

    def __init__(
        self,
        *,
        template_id: str = TEMPLATE_ID,
        reasoning_mode: ReasoningMode = ReasoningMode.DIRECT,
        sample_values: Mapping[str, Sequence[object]] | None = None,
        denied_columns: Collection[str] = (),
        pii_columns: Collection[str] = (),
    ) -> None:
        if template_id not in SUPPORTED_TEMPLATES:
            raise ConfigError(
                f"Desteklenmeyen istem şablonu: {template_id!r}. "
                f"Geçerli şablonlar: {sorted(SUPPORTED_TEMPLATES)}"
            )
        self._template_id = template_id
        self._reasoning_mode = reasoning_mode
        self._sample_values = sample_values
        self._denied_columns = tuple(denied_columns)
        self._pii_columns = tuple(pii_columns)

    @property
    def template_id(self) -> str:
        return self._template_id

    @property
    def reasoning_mode(self) -> ReasoningMode:
        return self._reasoning_mode

    def _render_schema_section(
        self,
        template_id: str,
        schema: SchemaSnapshot,
        tables: tuple[str, ...],
        *,
        sample_values: Mapping[str, Sequence[object]] | None,
        denied_columns: Collection[str],
        pii_columns: Collection[str],
    ) -> str:
        if template_id == TEMPLATE_ID:
            return render_schema(schema, tables)
        if template_id == DDL_TEMPLATE_ID:
            return render_ddl(
                schema,
                tables,
                denied_columns=denied_columns,
                pii_columns=pii_columns,
                sample_values=sample_values,
            )
        if template_id == MSCHEMA_TEMPLATE_ID:
            return render_mschema(
                schema,
                tables,
                sample_values=sample_values,
                denied_columns=denied_columns,
                pii_columns=pii_columns,
            )
        raise ConfigError(f"Desteklenmeyen istem şablonu: {template_id!r}")

    def build(
        self,
        plan: QueryPlan,
        schema: SchemaSnapshot,
        knowledge: KnowledgeContext,
        question: ParsedQuestion,
        feedback: tuple[str, ...] = (),
        *,
        template_id: str | None = None,
        reasoning_mode: ReasoningMode | None = None,
        sample_values: Mapping[str, Sequence[object]] | None = None,
        denied_columns: Collection[str] | None = None,
        pii_columns: Collection[str] | None = None,
    ) -> PromptBundle:
        active_template = template_id if template_id is not None else self._template_id
        if active_template not in SUPPORTED_TEMPLATES:
            raise ConfigError(f"Desteklenmeyen istem şablonu: {active_template!r}")
        active_mode = reasoning_mode if reasoning_mode is not None else self._reasoning_mode
        active_samples = sample_values if sample_values is not None else self._sample_values
        active_denied = denied_columns if denied_columns is not None else self._denied_columns
        active_pii = pii_columns if pii_columns is not None else self._pii_columns

        schema_block = self._render_schema_section(
            active_template,
            schema,
            plan.tables,
            sample_values=active_samples,
            denied_columns=active_denied,
            pii_columns=active_pii,
        )
        parts: list[str] = [schema_block]

        if knowledge.metrics:
            parts.append("【METRICS】")
            parts += [f"- {m.name}: {m.expression} (tablo: {m.base_table})" for m in knowledge.metrics]
        if knowledge.rules:
            parts.append("【BUSINESS_RULES】")
            for rule in knowledge.rules:
                sql_hint = f" (SQL: {rule.sql_fragment})" if rule.sql_fragment else ""
                parts.append(f"- {rule.term}: {rule.definition}{sql_hint}")
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
        if active_mode is ReasoningMode.THINKING:
            parts.append("【MODE】thinking (<think>...</think> ardından ```sql ... ```)")
        parts.append(f"【QUESTION】{question.original_text}")

        system_prompt = _SYSTEM_THINKING if active_mode is ReasoningMode.THINKING else _SYSTEM_DIRECT
        return PromptBundle(template_id=active_template, system=system_prompt, user="\n".join(parts))
