"""Enterprise synthetic benchmark JSON/JSONL loader."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from backend.core.contracts import Intent
from benchmarks import BenchmarkExample, LoadedDataset, sha256_file

ENTERPRISE_CATEGORIES = frozenset({"normal", "business_rule", "ambiguous", "unanswerable", "security_attack"})

_DEFAULT_EXPECTED_OUTCOME: dict[str, str] = {
    "normal": "answered",
    "business_rule": "answered",
    "ambiguous": "needs_clarification",
    "unanswerable": "rejected",
    "security_attack": "rejected",
}


def _read_enterprise_records(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".jsonl":
        records: list[dict[str, Any]] = []
        for line_no, raw in enumerate(text.splitlines(), start=1):
            stripped = raw.strip()
            if not stripped:
                continue
            item = json.loads(stripped)
            if not isinstance(item, dict):
                raise ValueError(f"Satır {line_no} geçerli bir JSON nesnesi değil: {path}")
            records.append(item)
        return records

    payload = json.loads(text)
    if isinstance(payload, dict):
        for key in ("items", "examples", "data", "questions"):
            if key in payload and isinstance(payload[key], list):
                payload = payload[key]
                break
    if not isinstance(payload, list):
        raise ValueError(f"Kurumsal veri kümesi JSON listesi veya JSONL olmalıdır: {path}")
    for idx, item in enumerate(payload):
        if not isinstance(item, dict):
            raise ValueError(f"Kayıt {idx} sözlük değil: {path}")
    return payload


def parse_enterprise_records(
    records: Sequence[Mapping[str, Any]],
    *,
    split: str = "eval",
    eval_only: bool = True,
    source_path: str = "<memory>",
    sha256: str = "",
) -> LoadedDataset:
    """Parse enterprise benchmark records across all 5 evaluation categories."""
    examples: list[BenchmarkExample] = []

    for idx, item in enumerate(records):
        question_raw = item.get("question")
        question = str(question_raw).strip() if question_raw is not None else ""
        if not question:
            raise ValueError(f"Kurumsal kayıt {idx} için 'question' alanı eksik veya boş.")

        category_raw = item.get("category", "normal")
        category = str(category_raw).strip().lower()
        if category not in ENTERPRISE_CATEGORIES:
            raise ValueError(
                f"Geçersiz kurumsal kategori {category!r} (kayıt {idx}). "
                f"Beklenen: {sorted(ENTERPRISE_CATEGORIES)}"
            )

        expected_outcome_raw = item.get("expected_outcome")
        expected_outcome = (
            str(expected_outcome_raw).strip().lower()
            if expected_outcome_raw
            else _DEFAULT_EXPECTED_OUTCOME[category]
        )

        sql_raw = (
            item.get("gold_sql")
            if "gold_sql" in item
            else (item.get("sql") or item.get("SQL") or item.get("query"))
        )
        gold_sql = str(sql_raw).strip() if sql_raw is not None and str(sql_raw).strip() else None
        if category in {"normal", "business_rule"} and expected_outcome == "answered" and not gold_sql:
            raise ValueError(f"Yanıtlanabilir kurumsal kayıt {idx} ('{category}') için gold_sql zorunludur.")

        db_raw = item.get("db_id", "erp")
        db_id = str(db_raw).strip() or "erp"

        diff_raw = item.get("difficulty")
        difficulty = str(diff_raw).strip().lower() if diff_raw else "unknown"

        ex_id_raw = item.get("example_id") or item.get("id") or item.get("question_id")
        example_id = str(ex_id_raw).strip() if ex_id_raw is not None else f"enterprise-{split}-{idx}"

        evidence_raw = item.get("evidence") or item.get("business_rule")
        evidence = str(evidence_raw).strip() if evidence_raw else None

        intent_raw = item.get("expected_intent") or item.get("intent")
        expected_intent = Intent(str(intent_raw).strip().lower()) if intent_raw else None

        tags_raw = item.get("tags", ())
        tags = tuple(str(t).strip() for t in tags_raw) if isinstance(tags_raw, (list, tuple)) else ()

        examples.append(
            BenchmarkExample(
                example_id=example_id,
                question=question,
                gold_sql=gold_sql,
                db_id=db_id,
                difficulty=difficulty,
                category=category,
                expected_outcome=expected_outcome,
                evidence=evidence,
                dataset="enterprise",
                split=split,
                eval_only=eval_only,
                expected_intent=expected_intent,
                tags=tags,
            )
        )

    return LoadedDataset(
        name="enterprise",
        split=split,
        license="proprietary-synthetic",
        eval_only=eval_only,
        source_path=source_path,
        sha256=sha256,
        examples=tuple(examples),
    )


def load_enterprise(
    path: str | Path,
    *,
    split: str = "eval",
    eval_only: bool = True,
) -> LoadedDataset:
    """Load an enterprise benchmark dataset from JSON or JSONL."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Kurumsal veri kümesi bulunamadı: {p}")
    records = _read_enterprise_records(p)
    return parse_enterprise_records(
        records,
        split=split,
        eval_only=eval_only,
        source_path=str(p),
        sha256=sha256_file(p),
    )


__all__ = [
    "ENTERPRISE_CATEGORIES",
    "load_enterprise",
    "parse_enterprise_records",
]
