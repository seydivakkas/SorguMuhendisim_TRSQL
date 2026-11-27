#!/usr/bin/env python3
"""Enforce the module boundaries declared in backend/boundaries.toml.

Usage:  python tools/check_boundaries.py [repo_root]
Exit code 0 = clean, 1 = violations (printed one per line).
"""

from __future__ import annotations

import ast
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

PKG = "backend"


@dataclass(frozen=True)
class Violation:
    path: Path
    line: int
    message: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.message}"


def _imports(tree: ast.AST) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found += [(node.lineno, alias.name) for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # relative import → resolved by caller as intra-module
                found.append((node.lineno, "." * node.level + (node.module or "")))
            elif node.module:
                found.append((node.lineno, node.module))
    return found


def check(root: Path) -> list[Violation]:
    config = tomllib.loads((root / PKG / "boundaries.toml").read_text(encoding="utf-8"))
    modules: dict[str, list[str]] = config["modules"]
    external: dict[str, list[str]] = config.get("external", {})
    violations: list[Violation] = []

    pkg_dir = root / PKG
    actual = {p.name for p in pkg_dir.iterdir() if p.is_dir() and (p / "__init__.py").exists()}
    for missing in sorted(actual - modules.keys()):
        violations.append(
            Violation(pkg_dir / missing, 0, f"module '{missing}' is not declared in boundaries.toml")
        )

    for path in sorted(pkg_dir.rglob("*.py")):
        rel = path.relative_to(pkg_dir)
        if len(rel.parts) < 2:
            continue  # backend/__init__.py
        owner = rel.parts[0]
        allowed = set(modules.get(owner, [])) | {"core", owner}
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for line, name in _imports(tree):
            if name.startswith("."):
                depth = len(name) - len(name.lstrip("."))
                if depth >= len(rel.parts):
                    violations.append(Violation(path, line, "relative import escapes its module"))
                continue
            parts = name.split(".")
            if parts[0] == PKG:
                if len(parts) == 1:
                    violations.append(Violation(path, line, "import the module, not the 'backend' root"))
                    continue
                target = parts[1]
                if target not in modules:
                    violations.append(Violation(path, line, f"unknown module '{target}'"))
                elif target not in allowed:
                    violations.append(Violation(path, line, f"'{owner}' may not import '{target}'"))
                elif target not in {owner, "core"} and len(parts) > 2:
                    violations.append(Violation(
                        path, line, f"use the public API 'backend.{target}', not '{name}'"
                    ))  # fmt: skip
                if owner == "core" and target != "core":
                    violations.append(Violation(path, line, "core must not import other modules"))
                continue
            top = parts[0]
            if top in external and owner not in external[top]:
                violations.append(
                    Violation(path, line, f"'{top}' may only be imported by {external[top] or 'nobody'}")
                )
    return violations


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
    violations = check(root)
    for v in violations:
        print(v)
    if violations:
        print(f"\n{len(violations)} boundary violation(s).", file=sys.stderr)
        return 1
    print("Module boundaries OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
