from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path
from types import ModuleType

from backend.core.contracts import OutcomeStatus

REPO_ROOT = Path(__file__).resolve().parents[2]
DEPLOYMENT_DIR = REPO_ROOT / "deployment"
FRONTEND_DIR = REPO_ROOT / "frontend"


def _load_verify_models() -> ModuleType:
    module_path = DEPLOYMENT_DIR / "verify_models.py"
    spec = importlib.util.spec_from_file_location("trsql_verify_models", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_verify_models_passes_with_matching_gguf_and_safetensors(tmp_path: Path) -> None:
    vm = _load_verify_models()
    gguf_path = tmp_path / "hati-q4.gguf"
    safe_path = tmp_path / "embed.safetensors"
    gguf_bytes = b"GGUF-synthetic-weights-payload"
    safe_bytes = b"SAFETENSORS-synthetic-weights-payload"
    gguf_path.write_bytes(gguf_bytes)
    safe_path.write_bytes(safe_bytes)

    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "hati-q4.gguf": _sha256_bytes(gguf_bytes),
                "embed.safetensors": _sha256_bytes(safe_bytes),
            }
        ),
        encoding="utf-8",
    )

    loaded = vm.load_checksum_manifest(manifest_path)
    summary = vm.verify_models_directory(tmp_path, expected_hashes=loaded)
    assert summary.passed is True
    assert summary.verified_count == 2
    assert summary.rejected_count == 0
    assert summary.failed_count == 0
    assert vm.main(["--models-dir", str(tmp_path), "--manifest", str(manifest_path)]) == 0


def test_verify_models_fails_on_sha256_mismatch(tmp_path: Path) -> None:
    vm = _load_verify_models()
    gguf_path = tmp_path / "model.gguf"
    gguf_path.write_bytes(b"actual-contents")

    wrong_digest = "0" * 64
    summary = vm.verify_models_directory(tmp_path, expected_hashes={"model.gguf": wrong_digest})
    assert summary.passed is False
    assert summary.failed_count == 1
    assert summary.results[0].status == "mismatch"
    assert vm.main(["--models-dir", str(tmp_path), "--allow-empty"]) == 1


def test_verify_models_rejects_bin_and_pickle_files(tmp_path: Path) -> None:
    vm = _load_verify_models()
    for bad_name in ("pytorch_model.bin", "weights.pkl", "legacy.ckpt", "model.pt"):
        model_dir = tmp_path / bad_name.replace(".", "_")
        model_dir.mkdir()
        bad_file = model_dir / bad_name
        bad_file.write_bytes(b"unsafe-pickle-payload")

        result = vm.verify_model_file(bad_file, expected_sha256=_sha256_bytes(b"unsafe-pickle-payload"))
        assert result.status == "rejected_format"

        summary = vm.verify_models_directory(model_dir, allow_empty=True)
        assert summary.passed is False
        assert summary.rejected_count == 1
        assert vm.main(["--models-dir", str(model_dir), "--allow-empty"]) == 1


def test_verify_models_supports_sha256_text_and_toml_manifests(tmp_path: Path) -> None:
    vm = _load_verify_models()
    weights = tmp_path / "qwen3-4b.gguf"
    payload = b"qwen3-gguf-bytes"
    weights.write_bytes(payload)
    digest = _sha256_bytes(payload)

    sha_file = tmp_path / "checksums.sha256"
    sha_file.write_text(f"{digest}  qwen3-4b.gguf\n", encoding="utf-8")
    assert vm.load_checksum_manifest(sha_file) == {"qwen3-4b.gguf": digest}

    toml_file = tmp_path / "manifest.toml"
    toml_file.write_text(f'[models]\n"qwen3-4b.gguf" = "{digest}"\n', encoding="utf-8")
    assert vm.load_checksum_manifest(toml_file) == {"qwen3-4b.gguf": digest}


def test_docker_compose_invariants() -> None:
    compose_text = (DEPLOYMENT_DIR / "docker-compose.yml").read_text(encoding="utf-8")

    # Required services and PostgreSQL 16
    assert "postgres:" in compose_text
    assert "postgres:16" in compose_text
    assert "api:" in compose_text
    assert "frontend:" in compose_text

    # Read-only models mount and postgres initdb scripts mount
    assert "./models:/app/models:ro" in compose_text
    assert "./deployment/postgres:/docker-entrypoint-initdb.d:ro" in compose_text

    # Offline-first and KVKK retention env vars
    assert re.search(r'HF_HUB_OFFLINE:\s*"?1"?', compose_text) is not None
    assert re.search(r'TRSQL_OFFLINE:\s*"?1"?', compose_text) is not None
    assert "TRSQL_PG_DSN:" in compose_text
    assert "TRSQL_MODEL_PATH:" in compose_text
    assert "TRSQL_LOG_RETENTION_DAYS:" in compose_text

    # Ensure no hardcoded passwords or inline DSN credentials
    for line_no, line in enumerate(compose_text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if any(key in stripped for key in ("PASSWORD:", "SECRET:", "TOKEN:", "TRSQL_PG_DSN:")):
            _, _, value = stripped.partition(":")
            val = value.strip().strip("\"'")
            assert val.startswith("${"), (
                f"docker-compose.yml:{line_no} must use env interpolation for sensitive setting: {stripped}"
            )
            assert ":-" not in val or val.startswith("${TRSQL_"), (
                f"docker-compose.yml:{line_no} must not provide a hardcoded fallback password: {stripped}"
            )
        assert not re.search(r"postgres(?:ql)?://[^:]+:[^@${}]+@", stripped), (
            f"docker-compose.yml:{line_no} contains inline DSN password"
        )


def test_dockerfile_and_install_scripts_present_and_consistent() -> None:
    dockerfile = (DEPLOYMENT_DIR / "Dockerfile").read_text(encoding="utf-8")
    assert "FROM python:3.12-slim AS builder" in dockerfile
    assert "FROM python:3.12-slim AS runtime" in dockerfile
    assert 'HF_HUB_OFFLINE="1"' in dockerfile
    assert 'TRSQL_ASGI_APP="backend.api.app:create_default_app"' in dockerfile
    assert "verify_models.py" in dockerfile

    ps1 = (DEPLOYMENT_DIR / "install.ps1").read_text(encoding="utf-8")
    sh = (DEPLOYMENT_DIR / "install.sh").read_text(encoding="utf-8")
    for script in (ps1, sh):
        assert "HF_HUB_OFFLINE" in script
        assert "verify_models.py" in script
        assert "check_boundaries.py" in script
        assert "-m security" in script

    readme = (DEPLOYMENT_DIR / "README.md").read_text(encoding="utf-8")
    assert "KVKK" in readme
    assert "systemd" in readme
    assert "Windows Service" in readme


def test_frontend_contracts_match_backend_outcome_status() -> None:
    contracts_ts = (FRONTEND_DIR / "src" / "types" / "contracts.ts").read_text(encoding="utf-8")

    block_match = re.search(
        r"export const OutcomeStatus\s*=\s*\{(.*?)\}\s*as const;",
        contracts_ts,
        flags=re.DOTALL,
    )
    assert block_match is not None, "OutcomeStatus constant block missing in contracts.ts"

    ts_values = set(re.findall(r':\s*"([a-z_]+)"', block_match.group(1)))
    py_values = {status.value for status in OutcomeStatus}
    assert ts_values == py_values

    for chart_kind in ('"bar"', '"line"', '"pie"', '"table"'):
        assert chart_kind in contracts_ts

    for field in (
        "request_id",
        "status",
        "attempts",
        "report",
        "clarification",
        "reason",
        "title",
        "summary",
        "columns",
        "rows",
        "chart",
        "sql",
        "metrics_used",
        "truncated",
    ):
        assert field in contracts_ts
