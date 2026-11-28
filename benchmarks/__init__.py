"""Offline evaluation datasets, metrics, runner and reporting for TRSQL (AR-08)."""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from backend.core.contracts import Intent


def sha256_file(path: str | Path) -> str:
    """Compute the SHA-256 hex digest of a file."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as fh:
        while chunk := fh.read(65_536):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class BenchmarkExample:
    """Normalized benchmark item shared across TURSpider, BIRDTurk and enterprise sets."""

    example_id: str
    question: str
    gold_sql: str | None
    db_id: str
    difficulty: str = "unknown"
    category: str = "normal"
    expected_outcome: str = "answered"
    evidence: str | None = None
    dataset: str = ""
    split: str = "dev"
    eval_only: bool = False
    expected_intent: Intent | None = None
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class LoadedDataset:
    """A benchmark dataset split together with provenance and license metadata."""

    name: str
    split: str
    license: str
    eval_only: bool
    source_path: str
    sha256: str
    examples: tuple[BenchmarkExample, ...]

    def __len__(self) -> int:
        return len(self.examples)

    def __iter__(self) -> Iterator[BenchmarkExample]:
        return iter(self.examples)


__all__ = ["BenchmarkExample", "LoadedDataset", "sha256_file"]
