from __future__ import annotations

import sqlglot
from sqlglot import exp

from backend.core.config import ExecutionSettings
from backend.core.contracts import ApprovedQuery, AuthContext, ValidationReport, Verdict
from backend.core.errors import SecurityViolation


class PolicyEngine:
    def __init__(self, settings: ExecutionSettings | None = None) -> None:
        self._settings = settings or ExecutionSettings()

    def approve(self, report: ValidationReport, auth: AuthContext) -> ApprovedQuery:
        if report.verdict is not Verdict.APPROVED:
            raise SecurityViolation("onaylanmamış sorgu yürütülemez")
        dialect = report.candidate.dialect
        cap = min(auth.max_rows, self._settings.max_rows)
        tree = sqlglot.parse_one(report.candidate.sql, read=dialect.value)
        if not isinstance(tree, exp.Query):  # defensive; L6 already enforced this
            raise SecurityViolation("yalnızca SELECT sorgularına izin verilir")
        tree = tree.limit(min(self._existing_limit(tree) or cap, cap))
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
        if isinstance(limit, exp.Limit) and isinstance(limit.expression, exp.Literal):
            try:
                return int(limit.expression.this)
            except ValueError:
                return None
        return None
