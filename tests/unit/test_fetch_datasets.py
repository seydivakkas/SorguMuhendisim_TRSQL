from __future__ import annotations

from pathlib import Path

import pytest

from benchmarks.loaders import load_birdturk, load_enterprise, load_turspider
from tools.fetch_datasets import (
    _download_hf_file,
    build_enterprise_bundle,
    convert_turspider_csv_to_json,
)


def test_convert_turspider_csv_and_load_offline(tmp_path: Path) -> None:
    csv_file = tmp_path / "dev.csv"
    csv_file.write_text(
        "db_id\tquestion\thardness\tquery\nconcert\tKaç şarkıcı var?\teasy\tSELECT count(*) FROM singer\n",
        encoding="utf-8",
    )
    json_file = tmp_path / "dev.json"
    count, digest = convert_turspider_csv_to_json(csv_file, json_file)
    assert count == 1
    assert len(digest) == 64

    loaded = load_turspider(json_file, split="dev")
    assert len(loaded) == 1
    assert loaded.examples[0].difficulty == "easy"
    assert loaded.examples[0].gold_sql == "SELECT count(*) FROM singer"


def test_build_enterprise_bundle_and_disjoint_verification(tmp_path: Path) -> None:
    info = build_enterprise_bundle(tmp_path)
    assert info["count"] == 190
    assert info["disjoint_verified"] is True
    assert len(info["jsonl_sha256"]) == 64
    loaded = load_enterprise(info["jsonl_path"])
    assert len(loaded) == 190


def test_fetch_refuses_birdturk_train_split(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="ADR-0009"):
        _download_hf_file(
            "metunlp/birdturk",
            "train_tr.json",
            revision="abc",
            dest_path=tmp_path / "train.json",
        )
    with pytest.raises(ValueError, match="ADR-0009"):
        load_birdturk(tmp_path / "missing.json", split="train")
