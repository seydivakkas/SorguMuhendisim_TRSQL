"""Hardware, runtime and Git metadata collection for reproducible experiments."""

from __future__ import annotations

import ctypes
import importlib.metadata
import os
import platform
import re
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_CUDA_PATTERN = re.compile(r"CUDA Version:\s*([0-9]+(?:\.[0-9]+)*)")


@dataclass(frozen=True)
class GpuInfo:
    """Single GPU snapshot parsed from ``nvidia-smi``."""

    name: str
    driver_version: str
    cuda_version: str | None = None
    memory_total_mb: int | None = None
    memory_used_mb: int | None = None
    memory_free_mb: int | None = None
    power_draw_w: float | None = None
    power_limit_w: float | None = None


@dataclass(frozen=True)
class HardwareSnapshot:
    """Hardware, OS, Python, runtime and Git state captured around a run."""

    os_name: str
    os_release: str
    os_version: str
    machine: str
    python_version: str
    cpu_count: int
    ram_total_mb: int | None
    gpu_available: bool
    gpus: tuple[GpuInfo, ...]
    peak_vram_used_mb: int | None
    cuda_version: str | None
    llama_cpp_version: str | None
    git_commit: str | None
    git_dirty: bool | None
    captured_at: str

    def to_dict(self) -> dict[str, Any]:
        """Serialize snapshot to a JSON-compatible dictionary."""
        return asdict(self)


def _parse_optional_int(raw: str) -> int | None:
    cleaned = raw.strip()
    if not cleaned or cleaned.startswith("["):
        return None
    try:
        return int(float(cleaned))
    except ValueError:
        return None


def _parse_optional_float(raw: str) -> float | None:
    cleaned = raw.strip()
    if not cleaned or cleaned.startswith("["):
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _run_command(args: list[str], *, cwd: Path | None = None, timeout_s: float = 5.0) -> tuple[int, str]:
    try:
        proc = subprocess.run(  # noqa: S603
            args,
            cwd=str(cwd) if cwd is not None else None,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_s,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return -1, ""
    return proc.returncode, proc.stdout


def parse_nvidia_smi_csv(csv_output: str, cuda_version: str | None = None) -> tuple[GpuInfo, ...]:
    """Parse ``nvidia-smi --query-gpu=... --format=csv,noheader,nounits`` lines."""
    gpus: list[GpuInfo] = []
    for line in csv_output.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        parts = [part.strip() for part in stripped.split(",")]
        if len(parts) < 5:
            continue
        gpus.append(
            GpuInfo(
                name=parts[0],
                driver_version=parts[1],
                cuda_version=cuda_version,
                memory_total_mb=_parse_optional_int(parts[2]),
                memory_used_mb=_parse_optional_int(parts[3]),
                memory_free_mb=_parse_optional_int(parts[4]),
                power_draw_w=_parse_optional_float(parts[5]) if len(parts) > 5 else None,
                power_limit_w=_parse_optional_float(parts[6]) if len(parts) > 6 else None,
            )
        )
    return tuple(gpus)


def query_nvidia_smi() -> tuple[tuple[GpuInfo, ...], str | None]:
    """Query GPU, driver, CUDA and VRAM info via ``nvidia-smi`` if installed."""
    exe = shutil.which("nvidia-smi")
    if exe is None:
        return (), None

    cuda_version: str | None = None
    banner_rc, banner_out = _run_command([exe])
    if banner_rc == 0:
        match = _CUDA_PATTERN.search(banner_out)
        if match:
            cuda_version = match.group(1)

    query_fields = "name,driver_version,memory.total,memory.used,memory.free,power.draw,power.limit"
    rc, csv_out = _run_command([exe, f"--query-gpu={query_fields}", "--format=csv,noheader,nounits"])
    if rc != 0:
        return (), cuda_version
    return parse_nvidia_smi_csv(csv_out, cuda_version=cuda_version), cuda_version


def sample_vram_mb() -> int | None:
    """Return current peak VRAM usage across GPUs in MB, or None if unavailable."""
    gpus, _ = query_nvidia_smi()
    used = [g.memory_used_mb for g in gpus if g.memory_used_mb is not None]
    return max(used) if used else None


def _get_ram_total_mb() -> int | None:
    system = platform.system()
    if system == "Windows":
        try:

            class _MemoryStatusEx(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            stat = _MemoryStatusEx()
            stat.dwLength = ctypes.sizeof(_MemoryStatusEx)
            windll = getattr(ctypes, "windll", None)
            if windll is not None and windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
                return int(stat.ullTotalPhys // (1024 * 1024))
        except (OSError, AttributeError, ValueError):
            return None
    meminfo = Path("/proc/meminfo")
    if meminfo.exists():
        try:
            for line in meminfo.read_text(encoding="utf-8").splitlines():
                if line.startswith("MemTotal:"):
                    kb = int(line.split()[1])
                    return kb // 1024
        except (OSError, ValueError, IndexError):
            return None
    return None


def _package_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def get_git_commit(repo_root: str | Path | None = None) -> str | None:
    """Return the current HEAD commit hash, or None outside a git repository."""
    exe = shutil.which("git")
    if exe is None:
        return None
    cwd = Path(repo_root) if repo_root is not None else None
    rc, out = _run_command([exe, "rev-parse", "HEAD"], cwd=cwd)
    if rc != 0:
        return None
    commit = out.strip()
    return commit or None


def is_git_dirty(repo_root: str | Path | None = None, *, default_if_unavailable: bool = True) -> bool:
    """Return True if the Git working tree has uncommitted changes (fail-closed by default)."""
    exe = shutil.which("git")
    if exe is None:
        return default_if_unavailable
    cwd = Path(repo_root) if repo_root is not None else None
    rc, out = _run_command([exe, "status", "--porcelain"], cwd=cwd)
    if rc != 0:
        return default_if_unavailable
    return bool(out.strip())


def collect_hardware_info(
    repo_root: str | Path | None = None,
    *,
    now: Callable[[], datetime] | None = None,
) -> HardwareSnapshot:
    """Collect GPU, driver, CUDA, VRAM, OS, Python, runtime and Git metadata."""
    gpus, cuda_version = query_nvidia_smi()
    used_values = [g.memory_used_mb for g in gpus if g.memory_used_mb is not None]
    timestamp = (now() if now is not None else datetime.now(UTC)).isoformat()
    git_commit = get_git_commit(repo_root)
    git_dirty = is_git_dirty(repo_root) if git_commit is not None else None

    return HardwareSnapshot(
        os_name=platform.system(),
        os_release=platform.release(),
        os_version=platform.version(),
        machine=platform.machine(),
        python_version=platform.python_version(),
        cpu_count=os.cpu_count() or 1,
        ram_total_mb=_get_ram_total_mb(),
        gpu_available=bool(gpus),
        gpus=gpus,
        peak_vram_used_mb=max(used_values) if used_values else None,
        cuda_version=cuda_version,
        llama_cpp_version=_package_version("llama-cpp-python"),
        git_commit=git_commit,
        git_dirty=git_dirty,
        captured_at=timestamp,
    )


__all__ = [
    "GpuInfo",
    "HardwareSnapshot",
    "collect_hardware_info",
    "get_git_commit",
    "is_git_dirty",
    "parse_nvidia_smi_csv",
    "query_nvidia_smi",
    "sample_vram_mb",
]
