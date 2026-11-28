from __future__ import annotations

import pytest

from backend.core.contracts import Dialect, GenerationParams, PromptBundle
from backend.model_engine import FakeModelAdapter
from backend.sql_generator import SQLGenerator, extract_sql, extract_sql_and_reasoning

PROMPT = PromptBundle(template_id="mschema_v1", system="sys", user="usr")


def test_extract_sql_strips_think_block_before_searching_sql() -> None:
    raw = (
        "<think>\n"
        "Önce yanlış bir taslak düşünelim:\n"
        "```sql\nSELECT * FROM wrong_table\n```\n"
        "Asıl tablo dealers olmalı.\n"
        "</think>\n\n"
        "```sql\nSELECT name, city FROM dealers WHERE city = 'Trabzon'\n```"
    )
    sql, reasoning = extract_sql_and_reasoning(raw)
    assert sql == "SELECT name, city FROM dealers WHERE city = 'Trabzon'"
    assert reasoning is not None and "wrong_table" in reasoning
    assert extract_sql(raw) == sql


def test_extract_sql_handles_bare_select_with_and_cte_and_preserves_attacks() -> None:
    assert extract_sql("İşte sorgu:\nSELECT id, name FROM dealers;\nBu sorgu bayileri listeler.") == (
        "SELECT id, name FROM dealers;"
    )
    assert (
        extract_sql("<think>plan</think>\nWITH top_dealers AS (SELECT 1) SELECT * FROM top_dealers")
        == "WITH top_dealers AS (SELECT 1) SELECT * FROM top_dealers"
    )
    assert extract_sql("prefix</think>\n```\nSELECT COUNT(*) FROM sales\n```") == (
        "SELECT COUNT(*) FROM sales"
    )
    assert extract_sql("<think>truncated thinking") == ""
    # Dangerous SQL must pass through intact so L6 classifies it as SECURITY.
    assert extract_sql("DROP TABLE sales") == "DROP TABLE sales"
    assert extract_sql("SELECT 1; DROP TABLE sales") == "SELECT 1; DROP TABLE sales"


def test_sql_generator_populates_reasoning_and_single_candidate() -> None:
    model = FakeModelAdapter(
        [
            "<think>Satışları topluyorum.</think>\n```sql\nSELECT SUM(total_amount) FROM sales\n```",
        ]
    )
    gen = SQLGenerator(model, GenerationParams(temperature=0.0))
    cand = gen.generate(PROMPT, Dialect.SQLITE, attempt=1)
    assert cand.sql == "SELECT SUM(total_amount) FROM sales"
    assert cand.reasoning == "Satışları topluyorum."
    assert cand.attempt == 1
    assert cand.dialect is Dialect.SQLITE
    assert model.params[0].temperature == 0.0


def test_sql_generator_generate_candidates_for_self_consistency() -> None:
    model = FakeModelAdapter(
        [
            "```sql\nSELECT 1\n```",
            "<think>alternatif</think>\n```sql\nSELECT 2\n```",
            "SELECT 3",
            "SELECT 4",
        ]
    )
    gen = SQLGenerator(model, GenerationParams(temperature=0.0))

    single = gen.generate_candidates(PROMPT, Dialect.POSTGRES, attempt=1, n=1)
    assert len(single) == 1
    assert single[0].sql == "SELECT 1"
    assert model.params[0].temperature == 0.0

    model.params.clear()
    model.prompts.clear()
    multi = gen.generate_candidates(
        PromptBundle(template_id="mschema_v1", system="sys", user="usr"),
        Dialect.POSTGRES,
        attempt=2,
        n=4,
    )
    assert len(multi) == 4
    assert [c.sql for c in multi] == ["SELECT 1", "SELECT 2", "SELECT 3", "SELECT 4"]
    assert multi[1].reasoning == "alternatif"
    assert all(c.attempt == 2 for c in multi)
    temps = [p.temperature for p in model.params]
    assert temps[0] == 0.0
    assert all(t > 0.0 for t in temps[1:])
    assert len(set(temps)) == 4

    with pytest.raises(ValueError):
        gen.generate_candidates(PROMPT, Dialect.SQLITE, attempt=1, n=0)
