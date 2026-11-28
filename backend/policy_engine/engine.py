from __future__ import annotations

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

from backend.core.config import ExecutionSettings
from backend.core.contracts import ApprovedQuery, AuthContext, ValidationReport, Verdict
from backend.core.errors import SecurityViolation

_FORBIDDEN_NODES: tuple[type[exp.Expression], ...] = tuple(
    getattr(exp, name)
    for name in (
        "Insert", "Update", "Delete", "Drop", "Create", "Alter", "Command",
        "Merge", "TruncateTable", "Into", "Pragma", "Grant", "Transaction",
        "Commit", "Rollback", "Set", "Use", "Copy", "LoadData", "Attach",
        "Detach", "Lock",
    )
    if hasattr(exp, name)
)  # fmt: skip


class PolicyEngine:
    """Enforces row caps, timeouts, and read-only query invariants before execution."""

    def __init__(self, settings: ExecutionSettings | None = None) -> None:
        self._settings = settings or ExecutionSettings()

    def approve(self, report: ValidationReport, auth: AuthContext) -> ApprovedQuery:
        if report.verdict is not Verdict.APPROVED:
            raise SecurityViolation("onaylanmamış sorgu yürütülemez")

        dialect = report.candidate.dialect
        cap = min(auth.max_rows, self._settings.max_rows)
        try:
            statements = [s for s in sqlglot.parse(report.candidate.sql, read=dialect.value) if s is not None]
        except ParseError as exc:
            raise SecurityViolation("onaylanan sorgu ayrıştırılamadı") from exc

        if len(statements) != 1:
            raise SecurityViolation("yalnızca tek bir SELECT sorgusuna izin verilir")

        tree = statements[0]
        outer_limit = self._existing_limit(tree) if isinstance(tree, exp.Query) else None
        while isinstance(tree, exp.Subquery) and tree.this is not None:
            tree = tree.this
            if outer_limit is None and isinstance(tree, exp.Query):
                outer_limit = self._existing_limit(tree)

        if not isinstance(tree, exp.Query):
            raise SecurityViolation("yalnızca SELECT sorgularına izin verilir")

        for node in tree.walk():
            if isinstance(node, _FORBIDDEN_NODES):
                raise SecurityViolation("izin verilmeyen SQL düğümü")

        inner_limit = self._existing_limit(tree)
        candidates = [x for x in (outer_limit, inner_limit) if x is not None and x >= 0]
        target_limit = min([cap, *candidates]) if candidates else cap
        tree = tree.limit(target_limit)

        return ApprovedQuery(
            sql=tree.sql(dialect=dialect.value),
            dialect=dialect,
            report=report,
            max_rows=cap,
            timeout_ms=self._settings.timeout_ms,
        )

    @staticmethod
    def _existing_limit(tree: exp.Query) -> int | None:
        limit = tree.args.get("limit")
        if (
            isinstance(limit, exp.Limit)
            and isinstance(limit.expression, exp.Literal)
            and not limit.expression.is_string
        ):
            try:
                return int(limit.expression.this)
            except ValueError:
                return None
        if isinstance(limit, exp.Fetch):
            count = limit.args.get("count")
            if isinstance(count, exp.Literal) and not count.is_string:
                try:
                    return int(count.this)
                except ValueError:
                    return None
        return None
