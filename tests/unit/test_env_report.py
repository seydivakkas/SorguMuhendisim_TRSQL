from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from benchmarks.hardware import HardwareSnapshot
from tools.env_report import collect_env_report, main


def test_collect_env_report_reuses_hardware_snapshot_offline(tmp_path: Path) -> None:
    fake_hw = HardwareSnapshot(
        os_name="Windows",
        os_release="11",
        os_version="10.0",
        machine="AMD64",
        python_version="3.12.0",
        cpu_count=16,
        ram_total_mb=32768,
        gpu_available=False,
        gpus=(),
        peak_vram_used_mb=None,
        cuda_version=None,
        llama_cpp_version=None,
        git_commit="abc123",
        git_dirty=False,
        captured_at="2026-11-28T00:00:00+00:00",
    )
    out_file = tmp_path / "hardware.json"
    with (
        patch("tools.env_report.collect_hardware_info", return_value=fake_hw),
        patch(
            "tools.env_report._probe_llama_cpp",
            return_value={"installed": False, "version": None, "gpu_offload": False},
        ),
    ):
        report = collect_env_report(tmp_path)
        assert report["python_version"] == "3.12.0"
        assert "packages" in report
        assert report["llama_cpp"]["gpu_offload"] is False

        rc = main(["--json", "--output", str(out_file)])
        assert rc == 0

    written = json.loads(out_file.read_text(encoding="utf-8"))
    assert written["git_commit"] == "abc123"
    assert "packages" in written
