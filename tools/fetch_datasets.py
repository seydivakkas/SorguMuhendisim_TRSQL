"""Dataset fetcher and synthetic corpus builder (T-10, runs outside backend/).

Enforces ADR-0009 license boundaries:
- TURSpider (CC BY 4.0): downloads ``dev`` only.
- BIRDTurk (CC BY-NC-SA 4.0): downloads ``dev`` only; refuses ``train``.
- Enterprise synthetic set: generates eval DB + JSONL and verifies zero overlap
  with any disjoint training split DB.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import urllib.request
from collections.abc import Sequence
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from benchmarks import sha256_file  # noqa: E402
from benchmarks.loaders import load_birdturk, load_enterprise, load_turspider  # noqa: E402
from synthetic_data import (  # noqa: E402
    build_disjoint_training_db,
    export_enterprise_dataset_jsonl,
    get_enterprise_dataset,
    get_security_attacks,
    populate_sqlite,
    validate_disjoint_dbs,
)

TURSPIDER_REPO = "AliBugra/TURSpider"
TURSPIDER_REVISION = "b01f5fc8608604aa2f96c1332110b7217bebe7ac"
TURSPIDER_LICENSE = "cc-by-4.0"

BIRDTURK_REPO = "metunlp/birdturk"
BIRDTURK_REVISION = "bb1c95577395223a8f893693b164bd8384089c7a"
BIRDTURK_LICENSE = "cc-by-nc-sa-4.0"


def _download_hf_file(
    repo_id: str,
    filename: str,
    *,
    revision: str,
    dest_path: Path,
) -> Path:
    if "train" in filename.lower():
        raise ValueError(f"ADR-0009: eğitim dosyası indirilemez: {filename}")
    url = f"https://huggingface.co/datasets/{repo_id}/resolve/{revision}/{filename}"
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    part = dest_path.with_suffix(dest_path.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "trsql-dataset-fetcher/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp, part.open("wb") as out:  # noqa: S310
            while chunk := resp.read(1024 * 1024):
                out.write(chunk)
        part.replace(dest_path)
    except Exception:
        part.unlink(missing_ok=True)
        raise
    return dest_path


def convert_turspider_csv_to_json(csv_path: Path, json_path: Path) -> tuple[int, str]:
    """Convert TURSpider tab/comma CSV ``dev.csv`` to standard JSON records for ``load_turspider``."""
    text = csv_path.read_text(encoding="utf-8")
    first_line = text.splitlines()[0] if text.splitlines() else ""
    delimiter = "\t" if "\t" in first_line else ","
    reader = csv.DictReader(text.splitlines(), delimiter=delimiter)
    records: list[dict[str, Any]] = []
    for idx, row in enumerate(reader, start=1):
        records.append(
            {
                "id": f"turspider-dev-{idx:04d}",
                "db_id": (row.get("db_id") or "").strip(),
                "question": (row.get("question") or "").strip(),
                "query": (row.get("query") or "").strip(),
                "difficulty": (row.get("hardness") or row.get("difficulty") or "unknown").strip(),
            }
        )
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return len(records), sha256_file(json_path)


def build_enterprise_bundle(
    dest_dir: Path,
    *,
    eval_seed: int = 42,
    train_seed: int = 999,
) -> dict[str, Any]:
    """Generate synthetic enterprise eval SQLite DB, eval JSONL, and disjoint train DB."""
    ent_dir = dest_dir / "enterprise"
    ent_dir.mkdir(parents=True, exist_ok=True)

    eval_db = ent_dir / "erp_eval.sqlite"
    populate_sqlite(eval_db, seed=eval_seed)
    eval_db_hash = sha256_file(eval_db)

    export_enterprise_dataset_jsonl(ent_dir)

    lines: list[str] = []
    for item in get_enterprise_dataset():
        lines.append(
            json.dumps(
                {
                    "id": item.example_id,
                    "question": item.question,
                    "gold_sql": item.gold_sql,
                    "db_id": "erp_eval",
                    "category": item.category,
                    "difficulty": item.difficulty,
                    "expected_outcome": item.expected_outcome,
                    "evidence": "; ".join(item.business_rules) if item.business_rules else None,
                },
                ensure_ascii=False,
            )
        )
    for atk in get_security_attacks():
        lines.append(
            json.dumps(
                {
                    "id": atk.attack_id,
                    "question": atk.prompt,
                    "db_id": "erp_eval",
                    "category": "security_attack",
                    "difficulty": "hard",
                    "expected_outcome": "rejected",
                },
                ensure_ascii=False,
            )
        )

    eval_jsonl = ent_dir / "eval.jsonl"
    eval_jsonl.write_text("\n".join(lines) + "\n", encoding="utf-8")

    train_db, train_db_hash = build_disjoint_training_db(
        ent_dir / "erp_train_disjoint.sqlite",
        seed=train_seed,
        eval_db_hashes=(eval_db_hash,),
    )
    validate_disjoint_dbs(
        "synthetic_train_erp",
        train_db_hash=train_db_hash,
        eval_db_hashes=(eval_db_hash,),
    )

    loaded = load_enterprise(eval_jsonl)
    return {
        "dataset": "enterprise",
        "license": "proprietary-all-rights-reserved",
        "eval_only": False,
        "count": len(loaded),
        "jsonl_path": str(eval_jsonl),
        "jsonl_sha256": loaded.sha256,
        "eval_db_path": str(eval_db),
        "eval_db_sha256": eval_db_hash,
        "disjoint_train_db_path": str(train_db),
        "disjoint_train_db_sha256": train_db_hash,
        "disjoint_verified": True,
    }


def fetch_turspider_dev(
    dest_dir: Path,
    *,
    revision: str = TURSPIDER_REVISION,
) -> dict[str, Any]:
    """Fetch TURSpider dev split and verify with :func:`load_turspider`."""
    out_dir = dest_dir / "turspider"
    csv_path = _download_hf_file(
        TURSPIDER_REPO,
        "dev.csv",
        revision=revision,
        dest_path=out_dir / "dev.csv",
    )
    json_path = out_dir / "dev.json"
    count, json_sha = convert_turspider_csv_to_json(csv_path, json_path)
    loaded = load_turspider(json_path, split="dev")
    return {
        "dataset": "turspider",
        "repo_id": TURSPIDER_REPO,
        "revision": revision,
        "license": TURSPIDER_LICENSE,
        "split": "dev",
        "count": count,
        "csv_sha256": sha256_file(csv_path),
        "json_sha256": json_sha,
        "json_path": str(json_path),
        "verified_count": len(loaded),
    }


def fetch_birdturk_dev(
    dest_dir: Path,
    *,
    revision: str = BIRDTURK_REVISION,
) -> dict[str, Any]:
    """Fetch BIRDTurk dev split ONLY (strictly refuses train per ADR-0009)."""
    out_dir = dest_dir / "birdturk"
    dev_json = _download_hf_file(
        BIRDTURK_REPO,
        "dev/dev_tr.json",
        revision=revision,
        dest_path=out_dir / "dev.json",
    )
    dev_tables = _download_hf_file(
        BIRDTURK_REPO,
        "dev/dev_tables_tr.json",
        revision=revision,
        dest_path=out_dir / "dev_tables_tr.json",
    )
    loaded = load_birdturk(dev_json, split="dev")
    return {
        "dataset": "birdturk",
        "repo_id": BIRDTURK_REPO,
        "revision": revision,
        "license": BIRDTURK_LICENSE,
        "eval_only": True,
        "split": "dev",
        "count": len(loaded),
        "dev_sha256": loaded.sha256,
        "tables_sha256": sha256_file(dev_tables),
        "json_path": str(dev_json),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="TRSQL veri kümesi indirme ve doğrulama aracı (ADR-0009)")
    parser.add_argument("--dest", type=Path, default=REPO_ROOT / "datasets" / "external")
    parser.add_argument(
        "--datasets",
        nargs="+",
        choices=["enterprise", "turspider", "birdturk"],
        default=["enterprise", "turspider", "birdturk"],
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    manifest: dict[str, Any] = {}
    if "enterprise" in args.datasets:
        manifest["enterprise"] = build_enterprise_bundle(args.dest)
    if "turspider" in args.datasets:
        manifest["turspider"] = fetch_turspider_dev(args.dest)
    if "birdturk" in args.datasets:
        manifest["birdturk"] = fetch_birdturk_dev(args.dest)

    manifest_path = args.dest / "manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
