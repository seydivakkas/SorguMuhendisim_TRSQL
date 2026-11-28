"""Standalone SHA-256 and format verifier for local TRSQL model weights.

Runs outside ``backend/`` with zero third-party dependencies so air-gapped
deployments and startup checks can validate weight integrity (ADR-0002,
ADR-0007 / T12) before loading any model file.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import re
import sys
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

ALLOWED_MODEL_EXTENSIONS: frozenset[str] = frozenset({".gguf", ".safetensors"})
REJECTED_MODEL_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".bin",
        ".pt",
        ".pth",
        ".pkl",
        ".pickle",
        ".ckpt",
        ".joblib",
        ".dill",
        ".marshal",
    }
)
IGNORED_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".md",
        ".txt",
        ".py",
        ".json",
        ".toml",
        ".yaml",
        ".yml",
        ".sha256",
        ".gitkeep",
        ".example",
    }
)
IGNORED_FILENAMES: frozenset[str] = frozenset({".gitkeep", "manifest.json", "checksums.sha256"})
_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_CHECKSUM_LINE_RE = re.compile(r"^([0-9a-fA-F]{64})\s+\*?(.+)$")

VerificationStatus = Literal["verified", "mismatch", "rejected_format", "missing_checksum"]


class ModelVerificationError(RuntimeError):
    """Raised when the models directory or manifest cannot be inspected."""


@dataclass(frozen=True)
class ModelFileResult:
    """Verification outcome for a single candidate file in ``models/``."""

    path: str
    filename: str
    extension: str
    sha256: str | None
    expected_sha256: str | None
    status: VerificationStatus
    message: str


@dataclass(frozen=True)
class VerificationSummary:
    """Aggregate result of verifying a directory of model weights."""

    models_dir: str
    results: tuple[ModelFileResult, ...]
    passed: bool
    verified_count: int
    rejected_count: int
    failed_count: int
    message: str


def compute_sha256(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    """Compute the lowercase hexadecimal SHA-256 digest of ``path``."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest().lower()


def _validate_digest(raw: str, source: str) -> str:
    cleaned = raw.strip().lower()
    if not _SHA256_RE.match(cleaned):
        raise ModelVerificationError(f"Geçersiz SHA-256 özeti ({source}): {raw!r}")
    return cleaned


def load_checksum_manifest(manifest_path: Path) -> dict[str, str]:
    """Load expected SHA-256 digests from JSON, TOML, or ``.sha256`` text files."""
    if not manifest_path.is_file():
        raise ModelVerificationError(f"Manifest dosyası bulunamadı: {manifest_path}")

    suffix = manifest_path.suffix.lower()
    text = manifest_path.read_text(encoding="utf-8")

    if suffix == ".json":
        payload = json.loads(text)
        mapping: dict[str, str] = {}
        if isinstance(payload, dict):
            if "models" in payload and isinstance(payload["models"], list):
                for entry in payload["models"]:
                    if isinstance(entry, dict) and "filename" in entry and "sha256" in entry:
                        name = str(entry["filename"]).strip()
                        mapping[name] = _validate_digest(str(entry["sha256"]), name)
            else:
                for key, val in payload.items():
                    if isinstance(val, str):
                        mapping[str(key).strip()] = _validate_digest(val, str(key))
                    elif isinstance(val, dict) and "sha256" in val:
                        mapping[str(key).strip()] = _validate_digest(str(val["sha256"]), str(key))
        return mapping

    if suffix == ".toml":
        parsed = tomllib.loads(text)
        mapping = {}
        models_section = parsed.get("models")
        if isinstance(models_section, list):
            for entry in models_section:
                if isinstance(entry, dict) and "filename" in entry and "sha256" in entry:
                    name = str(entry["filename"]).strip()
                    mapping[name] = _validate_digest(str(entry["sha256"]), name)
        elif isinstance(models_section, dict):
            for key, val in models_section.items():
                if isinstance(val, str):
                    mapping[str(key).strip()] = _validate_digest(val, str(key))
        else:
            for key, val in parsed.items():
                if isinstance(val, str):
                    mapping[str(key).strip()] = _validate_digest(val, str(key))
        return mapping

    mapping = {}
    for line_no, raw_line in enumerate(text.splitlines(), start=1):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = _CHECKSUM_LINE_RE.match(stripped)
        if not match:
            raise ModelVerificationError(
                f"Geçersiz checksum satırı ({manifest_path}:{line_no}): {raw_line!r}"
            )
        digest_hex, filename = match.groups()
        mapping[filename.strip()] = digest_hex.lower()
    return mapping


def verify_model_file(
    path: Path,
    expected_sha256: str | None = None,
    *,
    require_checksum: bool = True,
) -> ModelFileResult:
    """Verify a single model weight file's extension and SHA-256 digest."""
    ext = path.suffix.lower()
    if ext in REJECTED_MODEL_EXTENSIONS:
        return ModelFileResult(
            path=str(path),
            filename=path.name,
            extension=ext,
            sha256=None,
            expected_sha256=expected_sha256.lower() if expected_sha256 else None,
            status="rejected_format",
            message=(
                f"Güvensiz model biçimi reddedildi ({ext}): pickle/ikili (.bin/.pt/.pkl) "
                "dosyalarına izin verilmez; yalnızca .gguf ve .safetensors kabul edilir."
            ),
        )

    if ext not in ALLOWED_MODEL_EXTENSIONS:
        return ModelFileResult(
            path=str(path),
            filename=path.name,
            extension=ext,
            sha256=None,
            expected_sha256=expected_sha256.lower() if expected_sha256 else None,
            status="rejected_format",
            message=(
                f"Desteklenmeyen ağırlık biçimi reddedildi ({ext or 'uzantısız'}): "
                "yalnızca .gguf ve .safetensors kabul edilir."
            ),
        )

    actual_sha = compute_sha256(path)
    if expected_sha256 is None:
        if require_checksum:
            return ModelFileResult(
                path=str(path),
                filename=path.name,
                extension=ext,
                sha256=actual_sha,
                expected_sha256=None,
                status="missing_checksum",
                message="Beklenen SHA-256 değeri manifest içinde tanımlı değil.",
            )
        return ModelFileResult(
            path=str(path),
            filename=path.name,
            extension=ext,
            sha256=actual_sha,
            expected_sha256=None,
            status="verified",
            message="Biçim geçerli ve SHA-256 hesaplandı (manifest kontrolü devre dışı).",
        )

    normalized_expected = _validate_digest(expected_sha256, path.name)
    if hmac.compare_digest(actual_sha, normalized_expected):
        return ModelFileResult(
            path=str(path),
            filename=path.name,
            extension=ext,
            sha256=actual_sha,
            expected_sha256=normalized_expected,
            status="verified",
            message="SHA-256 bütünlük doğrulaması başarılı.",
        )

    return ModelFileResult(
        path=str(path),
        filename=path.name,
        extension=ext,
        sha256=actual_sha,
        expected_sha256=normalized_expected,
        status="mismatch",
        message=(f"SHA-256 uyuşmazlığı: beklenen={normalized_expected}, hesaplanan={actual_sha}"),
    )


def _lookup_expected(rel_path: Path, expected_hashes: Mapping[str, str]) -> str | None:
    posix = rel_path.as_posix()
    if posix in expected_hashes:
        return expected_hashes[posix]
    if rel_path.name in expected_hashes:
        return expected_hashes[rel_path.name]
    return None


def verify_models_directory(
    models_dir: Path,
    expected_hashes: Mapping[str, str] | None = None,
    *,
    require_checksum: bool = True,
    allow_empty: bool = False,
) -> VerificationSummary:
    """Scan ``models_dir`` recursively, rejecting unsafe formats and verifying SHA-256 digests."""
    if not models_dir.exists() or not models_dir.is_dir():
        raise ModelVerificationError(f"Model dizini bulunamadı: {models_dir}")

    hashes = expected_hashes or {}
    results: list[ModelFileResult] = []

    for candidate in sorted(models_dir.rglob("*")):
        if not candidate.is_file():
            continue
        rel = candidate.relative_to(models_dir)
        if "__pycache__" in rel.parts:
            continue
        ext = candidate.suffix.lower()
        if ext in REJECTED_MODEL_EXTENSIONS:
            results.append(verify_model_file(candidate, _lookup_expected(rel, hashes)))
            continue
        if ext in IGNORED_EXTENSIONS or candidate.name in IGNORED_FILENAMES:
            continue
        results.append(
            verify_model_file(
                candidate,
                _lookup_expected(rel, hashes),
                require_checksum=require_checksum,
            )
        )

    verified_count = sum(1 for item in results if item.status == "verified")
    rejected_count = sum(1 for item in results if item.status == "rejected_format")
    failed_count = sum(1 for item in results if item.status in {"mismatch", "missing_checksum"})

    if not results:
        passed = allow_empty
        msg = (
            "Model ağırlık dosyası bulunamadı (--allow-empty ile geçildi)."
            if allow_empty
            else "Doğrulanacak .gguf veya .safetensors model dosyası bulunamadı."
        )
    elif rejected_count > 0 or failed_count > 0:
        passed = False
        msg = (
            f"Doğrulama başarısız: {verified_count} doğrulandı, "
            f"{rejected_count} güvensiz/desteklenmeyen biçim, {failed_count} özet hatası."
        )
    else:
        passed = True
        msg = f"{verified_count} model dosyası başarıyla doğrulandı."

    return VerificationSummary(
        models_dir=str(models_dir),
        results=tuple(results),
        passed=passed,
        verified_count=verified_count,
        rejected_count=rejected_count,
        failed_count=failed_count,
        message=msg,
    )


def _discover_manifest(models_dir: Path) -> Path | None:
    for name in ("manifest.json", "checksums.sha256", "manifest.toml"):
        candidate = models_dir / name
        if candidate.is_file():
            return candidate
    return None


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="TRSQL yerel model ağırlıkları (.gguf / .safetensors) SHA-256 doğrulayıcısı"
    )
    parser.add_argument(
        "--models-dir",
        type=Path,
        default=Path("models"),
        help="Model ağırlıklarının bulunduğu dizin (varsayılan: models)",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="SHA-256 manifest dosyası (.json, .toml veya .sha256)",
    )
    parser.add_argument(
        "--allow-empty",
        action="store_true",
        help="Henüz ağırlık indirilmemiş boş dizine izin ver (güvensiz .bin dosyaları yine reddedilir)",
    )
    parser.add_argument(
        "--allow-unlisted",
        action="store_true",
        help="Manifest içinde olmayan .gguf/.safetensors dosyalarının özetini hesaplayarak kabul et",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Çıktıyı JSON biçiminde yazdır",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point for standalone model verification."""
    args = _build_parser().parse_args(list(argv) if argv is not None else None)
    try:
        manifest_path = args.manifest or _discover_manifest(args.models_dir)
        expected = load_checksum_manifest(manifest_path) if manifest_path else {}
        summary = verify_models_directory(
            args.models_dir,
            expected_hashes=expected,
            require_checksum=not args.allow_unlisted,
            allow_empty=args.allow_empty,
        )
    except ModelVerificationError as exc:
        if args.json:
            print(json.dumps({"passed": False, "error": str(exc)}, ensure_ascii=False))
        else:
            print(f"[HATA] {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(asdict(summary), ensure_ascii=False, indent=2))
    else:
        for item in summary.results:
            tag = "OK" if item.status == "verified" else "RED"
            digest_info = f" sha256={item.sha256[:12]}..." if item.sha256 else ""
            print(f"[{tag}] {item.filename}{digest_info} — {item.message}")
        print(summary.message)

    return 0 if summary.passed else 1


if __name__ == "__main__":
    sys.exit(main())
