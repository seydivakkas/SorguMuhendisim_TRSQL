"""Offline hardware and runtime environment report (T-07).

Reuses :func:`benchmarks.hardware.collect_hardware_info` (never duplicates
``nvidia-smi``/RAM/Git probing) and checks local Python package availability
and ``llama.cpp`` CUDA GPU offload support with zero network calls.
"""

from __future__ import annotations

import argparse
import importlib
import importlib.metadata
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from benchmarks.hardware import collect_hardware_info  # noqa: E402


def _pkg_version(dist_name: str) -> str | None:
    try:
        return importlib.metadata.version(dist_name)
    except importlib.metadata.PackageNotFoundError:
        return None


def _probe_llama_cpp() -> dict[str, Any]:
    version = _pkg_version("llama-cpp-python")
    if version is None:
        return {"installed": False, "version": None, "gpu_offload": False}
    try:
        mod = importlib.import_module("llama_cpp")
        fn = getattr(mod, "llama_supports_gpu_offload", None)
        gpu_offload = bool(fn()) if callable(fn) else False
        return {"installed": True, "version": version, "gpu_offload": gpu_offload}
    except Exception as exc:  # pragma: no cover - broken native DLL load
        return {
            "installed": True,
            "version": version,
            "gpu_offload": False,
            "error": type(exc).__name__,
        }


def collect_env_report(repo_root: str | Path | None = None) -> dict[str, Any]:
    """Build JSON-serializable hardware + package report without network I/O."""
    root = Path(repo_root) if repo_root is not None else REPO_ROOT
    hw = collect_hardware_info(root)
    payload = hw.to_dict()
    payload["packages"] = {
        "psycopg": _pkg_version("psycopg"),
        "huggingface_hub": _pkg_version("huggingface-hub"),
        "faker": _pkg_version("faker"),
        "fastapi": _pkg_version("fastapi"),
        "pydantic": _pkg_version("pydantic"),
        "sqlglot": _pkg_version("sqlglot"),
    }
    payload["llama_cpp"] = _probe_llama_cpp()
    return payload


def _format_human(report: dict[str, Any]) -> str:
    gpus = report.get("gpus") or []
    gpu_line = (
        f"{gpus[0]['name']} (driver={gpus[0]['driver_version']}, vram={gpus[0].get('memory_total_mb')} MB)"
        if gpus
        else "GPU bulunamadı"
    )
    llama = report["llama_cpp"]
    pkgs = report["packages"]
    lines = [
        f"OS          : {report['os_name']} {report['os_release']} ({report['machine']})",
        f"Python      : {report['python_version']}",
        f"RAM (MB)    : {report['ram_total_mb']}",
        f"GPU         : {gpu_line}",
        f"CUDA        : {report.get('cuda_version') or 'yok'}",
        (
            f"llama-cpp   : installed={llama['installed']} "
            f"version={llama['version']} gpu_offload={llama['gpu_offload']}"
        ),
        f"psycopg     : {pkgs['psycopg'] or 'kurulu değil'}",
        f"hf-hub      : {pkgs['huggingface_hub'] or 'kurulu değil'}",
        f"faker       : {pkgs['faker'] or 'kurulu değil'}",
    ]
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="TRSQL çevrimdışı donanım ve ortam raporu")
    parser.add_argument("--json", action="store_true", help="JSON biçiminde yazdır")
    parser.add_argument(
        "--output", type=Path, default=None, help="JSON raporunu dosyaya yaz (ör. hardware.json)"
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    report = collect_env_report()
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(_format_human(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
