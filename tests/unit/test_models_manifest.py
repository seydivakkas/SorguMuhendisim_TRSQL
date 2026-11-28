from __future__ import annotations

import re
from pathlib import Path

from models.download import (
    CANDIDATE_MODELS,
    RESTRICTED_MODEL_WARNINGS,
    check_license_compliance,
    validate_download_url,
    validate_weight_filename,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
_HEX40_RE = re.compile(r"^[0-9a-f]{40}$")
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")


def test_candidate_manifest_pins_revisions_filenames_and_licenses() -> None:
    assert len(CANDIDATE_MODELS) == 5
    # qwen-research models must stay excluded from CANDIDATE_MODELS.
    for restricted in RESTRICTED_MODEL_WARNINGS:
        assert restricted not in CANDIDATE_MODELS

    for key, spec in CANDIDATE_MODELS.items():
        assert spec.key == key
        assert spec.commercial_allowed is True
        check_license_compliance(spec.license, model_key=spec.key)
        validate_weight_filename(spec.filename)
        url = validate_download_url(spec.url)

        assert _HEX40_RE.fullmatch(spec.revision), f"{key} must pin a 40-hex commit revision"
        assert "/resolve/main/" not in url, f"{key} URL must not use mutable 'main' branch"
        assert f"/resolve/{spec.revision}/{spec.filename}" in url
        assert spec.source_repo_id, f"{key} should document its upstream official repo"
        if spec.sha256 is not None:
            assert _HEX64_RE.fullmatch(spec.sha256), f"{key} sha256 must be 64-char lowercase hex or None"

        card = REPO_ROOT / spec.card_path
        assert card.is_file(), f"Missing model card: {card}"
        card_text = card.read_text(encoding="utf-8")
        assert spec.repo_id in card_text
        assert spec.revision in card_text
        assert spec.filename in card_text
        assert spec.quantization in card_text
