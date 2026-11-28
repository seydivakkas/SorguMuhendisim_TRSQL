import shutil
from pathlib import Path

from tools.check_boundaries import check

ROOT = Path(__file__).resolve().parents[2]


def test_repository_respects_module_boundaries() -> None:
    assert [str(v) for v in check(ROOT)] == []


def _mini_repo(tmp_path: Path, module: str, source: str) -> Path:
    pkg = tmp_path / "backend"
    pkg.mkdir()
    shutil.copy(ROOT / "backend" / "boundaries.toml", pkg / "boundaries.toml")
    (pkg / "__init__.py").write_text("")
    for name in ("core", "model_engine", "database_adapters", "rag", "knowledge_base"):
        (pkg / name).mkdir()
        (pkg / name / "__init__.py").write_text("")
    (pkg / module / "impl.py").write_text(source)
    return tmp_path


def _messages(root: Path) -> list[str]:
    return [v.message for v in check(root) if "not declared" not in v.message]


def test_model_engine_cannot_reach_database(tmp_path: Path) -> None:
    root = _mini_repo(tmp_path, "model_engine", "from backend.database_adapters import X\nimport sqlite3\n")
    msgs = _messages(root)
    assert any("may not import 'database_adapters'" in m for m in msgs)
    assert any("'sqlite3' may only be imported" in m for m in msgs)


def test_internal_imports_are_rejected(tmp_path: Path) -> None:
    root = _mini_repo(tmp_path, "rag", "from backend.knowledge_base.store import X\n")
    assert any("public API" in m for m in _messages(root))


def test_core_is_a_leaf(tmp_path: Path) -> None:
    root = _mini_repo(tmp_path, "core", "from backend.rag import X\n")
    assert _messages(root)
