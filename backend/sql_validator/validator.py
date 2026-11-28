from __future__ import annotations

from collections.abc import Sequence
from typing import cast

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

from backend.core.config import ValidationSettings
from backend.core.contracts import (
    AuthContext,
    CheckName,
    CheckResult,
    KnowledgeContext,
    SchemaSnapshot,
    Severity,
    SQLCandidate,
    ValidationReport,
)
from backend.sql_validator.business_rules import BusinessRuleSpec, validate_business_rules
from backend.sql_validator.cost import CostThresholds, check_ast_cost
from backend.sql_validator.semantic import validate_semantics

# Statement/clause types that must never appear anywhere in a candidate.
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

_ALWAYS_FORBIDDEN_FUNCTIONS = frozenset(
    {
        "pg_sleep",
        "pg_read_file",
        "pg_read_binary_file",
        "pg_stat_file",
        "pg_ls_dir",
        "pg_ls_logdir",
        "pg_ls_waldir",
        "pg_ls_tmpdir",
        "pg_ls_archive_statusdir",
        "pg_terminate_backend",
        "pg_cancel_backend",
        "pg_reload_conf",
        "pg_rotate_logfile",
        "pg_export_snapshot",
        "lo_import",
        "lo_export",
        "lo_create",
        "lo_unlink",
        "lo_put",
        "lo_get",
        "lo_from_bytea",
        "dblink",
        "dblink_exec",
        "dblink_connect",
        "dblink_send_query",
        "load_extension",
        "readfile",
        "writefile",
        "set_config",
        "current_setting",
        "query_to_xml",
        "table_to_xml",
    }
)

_SYSTEM_PREFIXES = ("sqlite_", "pg_")
_SYSTEM_SCHEMAS = frozenset({"information_schema", "pg_catalog", "pg_toast", "pg_temp", "sqlite_temp_master"})


def _ok(check: CheckName, message: str = "") -> CheckResult:
    return CheckResult(check=check, passed=True, message=message)


def _fail(check: CheckName, severity: Severity, message: str) -> CheckResult:
    return CheckResult(check=check, passed=False, severity=severity, message=message)


class SQLValidator:
    def __init__(
        self,
        settings: ValidationSettings | None = None,
        *,
        business_rules: Sequence[BusinessRuleSpec] | None = None,
    ) -> None:
        self._settings = settings or ValidationSettings()
        self._forbidden_funcs = _ALWAYS_FORBIDDEN_FUNCTIONS | frozenset(
            f.lower() for f in self._settings.forbidden_functions
        )
        self._business_rules = business_rules
        self._cost_thresholds = CostThresholds(
            max_joins=self._settings.max_joins,
            max_explain_cost=self._settings.max_explain_cost,
            max_explain_rows=self._settings.max_explain_rows,
        )

    def validate(
        self,
        candidate: SQLCandidate,
        schema: SchemaSnapshot,
        auth: AuthContext,
        *,
        knowledge: KnowledgeContext | None = None,
        question: str | None = None,
    ) -> ValidationReport:
        checks = self._run(candidate, schema, auth, knowledge=knowledge, question=question)
        return ValidationReport(candidate=candidate, checks=tuple(checks))

    # ------------------------------------------------------------------ #

    def _run(
        self,
        candidate: SQLCandidate,
        schema: SchemaSnapshot,
        auth: AuthContext,
        *,
        knowledge: KnowledgeContext | None = None,
        question: str | None = None,
    ) -> list[CheckResult]:
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

        # --- Schema & authorization -----------------------------------------
        schema_check, auth_check = self._check_schema_and_auth(tree, schema, auth)
        checks += [schema_check, auth_check]

        # --- Cost -----------------------------------------------------------
        checks.append(check_ast_cost(tree, self._cost_thresholds))

        # --- Semantic & business rules (only when schema & auth succeeded) --
        if schema_check.passed and auth_check.passed:
            checks.append(validate_semantics(tree))
            checks.append(
                validate_business_rules(
                    tree,
                    schema,
                    knowledge=knowledge,
                    question=question,
                    rule_specs=self._business_rules,
                )
            )
        else:
            checks.append(_ok(CheckName.SEMANTIC, "Şema veya yetki doğrulaması geçemediği için atlandı."))
            checks.append(
                _ok(CheckName.BUSINESS_RULE, "Şema veya yetki doğrulaması geçemediği için atlandı.")
            )
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
        tvf_aliases: set[str] = set()
        real_tables: set[str] = set()
        for table in tree.find_all(exp.Table):
            if not isinstance(table.this, (exp.Identifier, str)) and not table.name:
                if table.alias:
                    tvf_aliases.add(table.alias.lower())
                continue
            name = table.name.lower()
            qualifier = (table.db or "").lower()
            if name in cte_names and not qualifier:
                continue
            if (
                qualifier in _SYSTEM_SCHEMAS
                or qualifier.startswith(_SYSTEM_PREFIXES)
                or name.startswith(_SYSTEM_PREFIXES)
                or name in _SYSTEM_SCHEMAS
            ):
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
                if qualifier in cte_names or qualifier in tvf_aliases:
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
            if not exists and not (not qualifier and (cname in select_aliases or cte_names or tvf_aliases)):
                return (
                    _fail(CheckName.SCHEMA, Severity.REPAIRABLE, f"Sütun bulunamadı: {cname}"),
                    _ok(CheckName.AUTHORIZATION),
                )
        return _ok(CheckName.SCHEMA), _ok(CheckName.AUTHORIZATION)
