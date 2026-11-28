"""TURSpider / Spider JSON and JSONL dataset loader."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from benchmarks import BenchmarkExample, LoadedDataset, sha256_file


def _read_json_records(path: Path) -> list[dict[str, Any]]:
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
        for key in ("data", "examples", "questions", "items"):
            if key in payload and isinstance(payload[key], list):
                payload = payload[key]
                break
    if not isinstance(payload, list):
        raise ValueError(f"TURSpider veri kümesi JSON listesi olmalıdır: {path}")
    for idx, item in enumerate(payload):
        if not isinstance(item, dict):
            raise ValueError(f"Kayıt {idx} sözlük değil: {path}")
    return payload


def parse_turspider_records(
    records: Sequence[Mapping[str, Any]],
    *,
    split: str = "dev",
    eval_only: bool = False,
    source_path: str = "<memory>",
    sha256: str = "",
) -> LoadedDataset:
    """Parse Spider/TURSpider records into a :class:`LoadedDataset`."""
    examples: list[BenchmarkExample] = []
    for idx, item in enumerate(records):
        question_raw = item.get("question") or item.get("question_tr") or item.get("tr_question")
        sql_raw = item.get("query") or item.get("sql") or item.get("SQL")
        db_raw = item.get("db_id")

        question = str(question_raw).strip() if question_raw is not None else ""
        sql = str(sql_raw).strip() if sql_raw is not None else ""
        db_id = str(db_raw).strip() if db_raw is not None else ""

        if not question:
            raise ValueError(f"TURSpider kaydı {idx} için 'question' alanı eksik veya boş.")
        if not sql:
            raise ValueError(f"TURSpider kaydı {idx} için 'query' alanı eksik veya boş.")
        if not db_id:
            raise ValueError(f"TURSpider kaydı {idx} için 'db_id' alanı eksik veya boş.")

        diff_raw = item.get("difficulty") or item.get("hardness")
        difficulty = str(diff_raw).strip().lower() if diff_raw else "unknown"
        ex_id_raw = item.get("question_id") or item.get("id")
        example_id = str(ex_id_raw).strip() if ex_id_raw is not None else f"turspider-{split}-{idx}"

        evidence_raw = item.get("evidence")
        evidence = str(evidence_raw).strip() if evidence_raw else None

        examples.append(
            BenchmarkExample(
                example_id=example_id,
                question=question,
                gold_sql=sql,
                db_id=db_id,
                difficulty=difficulty,
                category="normal",
                expected_outcome="answered",
                evidence=evidence,
                dataset="turspider",
                split=split,
                eval_only=eval_only,
            )
        )

    return LoadedDataset(
        name="turspider",
        split=split,
        license="unspecified",
        eval_only=eval_only,
        source_path=source_path,
        sha256=sha256,
        examples=tuple(examples),
    )


def load_turspider(
    path: str | Path,
    *,
    split: str = "dev",
    eval_only: bool = False,
) -> LoadedDataset:
    """Load a TURSpider / Spider JSON or JSONL file."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"TURSpider dosyası bulunamadı: {p}")
    records = _read_json_records(p)
    return parse_turspider_records(
        records,
        split=split,
        eval_only=eval_only,
        source_path=str(p),
        sha256=sha256_file(p),
    )


__all__ = ["load_turspider", "parse_turspider_records"]
