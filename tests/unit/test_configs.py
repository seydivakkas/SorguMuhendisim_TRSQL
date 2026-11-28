from pathlib import Path

from backend.core.config import load_settings
from backend.knowledge_base import load_knowledge_base

ROOT = Path(__file__).resolve().parents[2]


def test_default_settings_load() -> None:
    s = load_settings(ROOT / "configs" / "default.toml")
    assert s.offline is True
    assert 1 <= s.retry.max_attempts <= 5


def test_example_rules_are_not_approved() -> None:
    kb = load_knowledge_base(ROOT / "configs" / "knowledge.example.toml")
    assert kb.rules and kb.approved_rules() == ()
