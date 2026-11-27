from __future__ import annotations

from typing import cast

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

from backend.core.config import ValidationSettings
from backend.core.contracts import (
    AuthContext,
    CheckName,
    CheckResult,
    SchemaSnapshot,
    Severity,
    SQLCandidate,
    ValidationReport,
)

# Statement types that must never appear anywhere in a candidate.
_FORBIDDEN_NODES: tuple[type[exp.Expression], ...] = tuple(
    getattr(exp, name)
    for name in (
        "Insert", "Update", "Delete", "Drop", "Create", "Alter", "Command",
        "Merge", "TruncateTable", "Into", "Pragma", "Grant", "Transaction",
        "Commit", "Rollback", "Set", "Use", "Copy", "LoadData", "Attach", "Detach",
    )
    if hasattr(exp, name)
)  # fmt: skip

_SYSTEM_PREFIXES = ("sqlite_", "pg_")
_SYSTEM_SCHEMAS = frozenset({"information_schema", "pg_catalog", "sqlite_temp_master"})

_NOT_YET = "AR-07 kapsamında uygulanacak; şimdilik kontrol edilmiyor."


def _ok(check: CheckName, message: str = "") -> CheckResult:
    return CheckResult(check=check, passed=True, message=message)


def _fail(check: CheckName, severity: Severity, message: str) -> CheckResult:
    return CheckResult(check=check, passed=False, severity=severity, message=message)


class SQLValidator:
    def __init__(self, settings: ValidationSettings | None = None) -> None:
        self._settings = settings or ValidationSettings()
        self._forbidden_funcs = frozenset(f.lower() for f in self._settings.forbidden_functions)

    def validate(
        self, candidate: SQLCandidate, schema: SchemaSnapshot, auth: AuthContext
    ) -> ValidationReport:
        checks = self._run(candidate, schema, auth)
        return ValidationReport(candidate=candidate, checks=tuple(checks))

    # ------------------------------------------------------------------ #

    def _run(self, candidate: SQLCandidate, schema: SchemaSnapshot, auth: AuthContext) -> list[CheckResult]:
        sql = candidate.sql.strip()
        if not sql:
            return [_fail(CheckName.SYNTAX, Severity.REPAIRABLE, "Boş SQL üretildi.")]

        try:
            statements = [s for s in sqlglot.parse(sql, read=candidate.dialect.value) if s is not None]
        except ParseError as exc:
            first = exc.errors[0]["description"] if exc.errors else str(exc)
            return [_fail(CheckName.SYNTAX, Severity.REPAIRABLE, f"Sözdizimi hatası: {first}")]

        checks: list[CheckResult] = [_ok(CheckName.SYNTAX)]

        # --- Injection: stacked statements are an attack signature ----------
        if len(statements) != 1:
            checks.append(_fail(CheckName.INJECTION, Severity.SECURITY, "Birden fazla SQL ifadesi."))
            return checks
        tree = cast(exp.Expression, statements[0])

        # --- AST: read-only query, no forbidden nodes / functions -----------
        ast_check = self._check_ast(tree)
        checks.append(ast_check)
        if not ast_check.passed:
            return checks
        checks.append(self._check_injection(sql, tree))

        # --- Schema & authorization ------------------------------------------
        schema_check, auth_check = self._check_schema_and_auth(tree, schema, auth)
        checks += [schema_check, auth_check]

        # --- Cost --------------------------------------------------------------
        checks.append(self._check_cost(tree))

        # --- Not yet implemented (explicitly visible in reports) -------------
        checks.append(_ok(CheckName.SEMANTIC, _NOT_YET))
        checks.append(_ok(CheckName.BUSINESS_RULE, _NOT_YET))
        return checks

    def _check_ast(self, tree: exp.Expression) -> CheckResult:
        if not isinstance(tree, exp.Query):
            return _fail(CheckName.AST, Severity.SECURITY, "Yalnızca SELECT sorgularına izin verilir.")
        for node in tree.walk():
            if isinstance(node, _FORBIDDEN_NODES):
                return _fail(
                    CheckName.AST, Severity.SECURITY, f"İzin verilmeyen ifade: {type(node).__name__}"
                )
        return _ok(CheckName.AST)

    def _check_injection(self, sql: str, tree: exp.Expression) -> CheckResult:
        for func in tree.find_all(exp.Func):
            name = (func.name if isinstance(func, exp.Anonymous) else func.sql_name()).lower()
            if name in self._forbidden_funcs:
                return _fail(CheckName.INJECTION, Severity.SECURITY, f"Yasaklı fonksiyon: {name}")
        if "--" in sql or "/*" in sql:
            return _fail(CheckName.INJECTION, Severity.REPAIRABLE, "SQL yorum satırı içermemeli.")
        return _ok(CheckName.INJECTION)

    def _check_schema_and_auth(
        self, tree: exp.Expression, schema: SchemaSnapshot, auth: AuthContext
    ) -> tuple[CheckResult, CheckResult]:
        allowed = {t.lower() for t in auth.allowed_tables}
        denied_cols = {c.lower() for c in auth.denied_columns}
        cte_names = {cte.alias_or_name.lower() for cte in tree.find_all(exp.CTE)}

        alias_to_table: dict[str, str] = {}
        real_tables: set[str] = set()
        for table in tree.find_all(exp.Table):
            name = table.name.lower()
            qualifier = (table.db or "").lower()
            if name in cte_names and not qualifier:
                continue
            if qualifier in _SYSTEM_SCHEMAS or name.startswith(_SYSTEM_PREFIXES) or name in _SYSTEM_SCHEMAS:
                return (_ok(CheckName.SCHEMA), _fail(
                    CheckName.AUTHORIZATION, Severity.SECURITY, "Sistem kataloğuna erişim yasak.",
                ))  # fmt: skip
            if schema.table(name) is not None and name not in allowed:
                return (_ok(CheckName.SCHEMA), _fail(
                    CheckName.AUTHORIZATION, Severity.SECURITY, "Yetkisiz veri erişimi.",
                ))  # fmt: skip
            if schema.table(name) is None:
                return (
                    _fail(CheckName.SCHEMA, Severity.REPAIRABLE, f"Tablo bulunamadı: {name}"),
                    _ok(CheckName.AUTHORIZATION),
                )
            real_tables.add(name)
            alias_to_table[table.alias_or_name.lower()] = name

        def denied_in(tables: set[str]) -> bool:
            return any(c.split(".", 1)[0] in tables for c in denied_cols)

        # SELECT * would expose denied columns.
        for star in tree.find_all(exp.Star):
            parent_col = star.parent if isinstance(star.parent, exp.Column) else None
            scope = (
                {alias_to_table.get(parent_col.table.lower(), "")}
                if parent_col and parent_col.table
                else real_tables
            )
            if denied_in(scope):
                return (_ok(CheckName.SCHEMA), _fail(
                    CheckName.AUTHORIZATION, Severity.SECURITY, "Yetkisiz sütun erişimi (*).",
                ))  # fmt: skip

        select_aliases = {a.alias.lower() for a in tree.find_all(exp.Alias)}
        for col in tree.find_all(exp.Column):
            if isinstance(col.this, exp.Star):
                continue
            cname = col.name.lower()
            qualifier = col.table.lower() if col.table else ""
            if qualifier:
                if qualifier in cte_names:
                    continue
                tname = alias_to_table.get(qualifier)
                if tname is None:
                    return (
                        _fail(
                            CheckName.SCHEMA, Severity.REPAIRABLE, f"Bilinmeyen tablo takma adı: {qualifier}"
                        ),
                        _ok(CheckName.AUTHORIZATION),
                    )
                candidates = {tname}
            else:
                candidates = real_tables
            if any(f"{t}.{cname}" in denied_cols for t in candidates):
                return (_ok(CheckName.SCHEMA), _fail(
                    CheckName.AUTHORIZATION, Severity.SECURITY, "Yetkisiz sütun erişimi.",
                ))  # fmt: skip
            exists = any((info := schema.table(t)) is not None and info.column(cname) for t in candidates)
            if not exists and not (not qualifier and (cname in select_aliases or cte_names)):
                return (
                    _fail(CheckName.SCHEMA, Severity.REPAIRABLE, f"Sütun bulunamadı: {cname}"),
                    _ok(CheckName.AUTHORIZATION),
                )
        return _ok(CheckName.SCHEMA), _ok(CheckName.AUTHORIZATION)

    def _check_cost(self, tree: exp.Expression) -> CheckResult:
        joins = list(tree.find_all(exp.Join))
        if len(joins) > self._settings.max_joins:
            return _fail(CheckName.COST, Severity.REPAIRABLE, f"Çok fazla JOIN ({len(joins)}).")
        for join in joins:
            on = join.args.get("on")
            has_condition = bool(join.args.get("using")) or (
                on is not None and not (isinstance(on, exp.Boolean) and on.this is True)
            )
            select = join.find_ancestor(exp.Select)
            # Comma / CROSS joins are accepted only when a WHERE clause can restrict them.
            if not has_condition and (select is None or not select.args.get("where")):
                return _fail(CheckName.COST, Severity.REPAIRABLE, "Koşulsuz JOIN (kartezyen çarpım).")
        return _ok(CheckName.COST)
