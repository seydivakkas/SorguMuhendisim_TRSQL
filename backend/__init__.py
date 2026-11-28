"""TRSQL backend — a modular monolith (ADR-0001).

Each sub-package is a module with a public API exposed in its
``__init__.py``. Cross-module imports must go through that public API and
are restricted by ``backend/boundaries.toml`` (checked in CI).
"""

__version__ = "0.2.0"
