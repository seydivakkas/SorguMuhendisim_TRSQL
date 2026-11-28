"""BIRDTurk JSON dataset loader (evaluation-only per ADR-0009)."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from benchmarks import BenchmarkExample, LoadedDataset, sha256_file

BIRDTURK_LICENSE = "cc-by-nc-sa-4.0"


def _ensure_eval_only(split: str, for_training: bool) -> str:
    normalized = split.strip().lower()
    if for_training:
        raise ValueError(
            "BIRDTurk cc-by-nc-sa-4.0 lisanslıdır ve ADR-0009 uyarınca eğitimde kullanılamaz "
            "(for_training=True yasaktır)."
        )
    if normalized == "train" or normalized.startswith("train_"):
        raise ValueError(
            "BIRDTurk cc-by-nc-sa-4.0 lisanslıdır ve ADR-0009 uyarınca 'train' bölümü "
            "yüklenemez; yalnızca değerlendirme (dev/test) izinli."
        )
    return normalized


def _read_birdturk_records(path: Path) -> list[dict[str, Any]]:
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
        raise ValueError(f"BIRDTurk veri kümesi JSON listesi olmalıdır: {path}")
    for idx, item in enumerate(payload):
        if not isinstance(item, dict):
            raise ValueError(f"Kayıt {idx} sözlük değil: {path}")
    return payload


def parse_birdturk_records(
    records: Sequence[Mapping[str, Any]],
    *,
    split: str = "dev",
    for_training: bool = False,
    source_path: str = "<memory>",
    sha256: str = "",
) -> LoadedDataset:
    """Parse BIRDTurk records while enforcing ADR-0009 eval-only constraints."""
    split_norm = _ensure_eval_only(split, for_training)
    examples: list[BenchmarkExample] = []

    for idx, item in enumerate(records):
        question_raw = item.get("question")
        sql_raw = item.get("SQL") if "SQL" in item else (item.get("sql") or item.get("query"))
        db_raw = item.get("db_id")

        question = str(question_raw).strip() if question_raw is not None else ""
        sql = str(sql_raw).strip() if sql_raw is not None else ""
        db_id = str(db_raw).strip() if db_raw is not None else ""

        if not question:
            raise ValueError(f"BIRDTurk kaydı {idx} için 'question' alanı eksik veya boş.")
        if not sql:
            raise ValueError(f"BIRDTurk kaydı {idx} için 'SQL' alanı eksik veya boş.")
        if not db_id:
            raise ValueError(f"BIRDTurk kaydı {idx} için 'db_id' alanı eksik veya boş.")

        evidence_raw = item.get("evidence")
        evidence = (
            str(evidence_raw).strip() if evidence_raw is not None and str(evidence_raw).strip() else None
        )

        diff_raw = item.get("difficulty")
        difficulty = str(diff_raw).strip().lower() if diff_raw else "unknown"

        ex_id_raw = item.get("question_id") if "question_id" in item else item.get("id")
        example_id = str(ex_id_raw).strip() if ex_id_raw is not None else f"birdturk-{split_norm}-{idx}"

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
                dataset="birdturk",
                split=split_norm,
                eval_only=True,
            )
        )

    return LoadedDataset(
        name="birdturk",
        split=split_norm,
        license=BIRDTURK_LICENSE,
        eval_only=True,
        source_path=source_path,
        sha256=sha256,
        examples=tuple(examples),
    )


def load_birdturk(
    path: str | Path,
    *,
    split: str = "dev",
    for_training: bool = False,
) -> LoadedDataset:
    """Load BIRDTurk JSON/JSONL dataset (strictly evaluation-only, cc-by-nc-sa-4.0)."""
    _ensure_eval_only(split, for_training)
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"BIRDTurk dosyası bulunamadı: {p}")
    records = _read_birdturk_records(p)
    return parse_birdturk_records(
        records,
        split=split,
        for_training=for_training,
        source_path=str(p),
        sha256=sha256_file(p),
    )


__all__ = ["BIRDTURK_LICENSE", "load_birdturk", "parse_birdturk_records"]
