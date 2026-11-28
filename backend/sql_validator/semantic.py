"""AST-level semantic checks for generated SQL queries (L6)."""

from __future__ import annotations

import unicodedata
from collections.abc import Iterator

from sqlglot import exp

from backend.core.contracts import CheckName, CheckResult, Severity

_TR_UPPER_MAP = str.maketrans({"I": "ı", "İ": "i"})


def _tr_casefold(text: str) -> str:
    return unicodedata.normalize("NFC", text).translate(_TR_UPPER_MAP).lower()


def _ok(message: str = "") -> CheckResult:
    return CheckResult(check=CheckName.SEMANTIC, passed=True, message=message)


def _fail(message: str) -> CheckResult:
    return CheckResult(check=CheckName.SEMANTIC, passed=False, severity=Severity.REPAIRABLE, message=message)


def _iter_in_select_scope(node: exp.Expression, owner_select: exp.Select) -> Iterator[exp.Expression]:
    """Yield *node* and descendants belonging to *owner_select*, stopping at nested Select/CTE."""
    stack: list[exp.Expression] = [node]
    while stack:
        cur = stack.pop()
        if cur is not owner_select and isinstance(cur, (exp.Select, exp.CTE)):
            continue
        yield cur
        for child in cur.iter_expressions():
            stack.append(child)


def _is_window_agg(node: exp.Expression) -> bool:
    return isinstance(node, exp.AggFunc) and isinstance(node.parent, exp.Window)


def _extract_group_expressions(group: exp.Group) -> list[exp.Expression]:
    """Extract all expressions referenced in a GROUP BY clause (including ROLLUP/CUBE/GROUPING SETS)."""
    extracted: list[exp.Expression] = []
    for item in group.expressions:
        if isinstance(item, (exp.Rollup, exp.Cube, exp.GroupingSets)):
            for sub in item.expressions:
                if isinstance(sub, exp.Tuple):
                    extracted.extend(sub.expressions)
                else:
                    extracted.append(sub)
        else:
            extracted.append(item)
    return extracted


def _resolve_grouped_items(select: exp.Select, group: exp.Group) -> tuple[set[str], set[tuple[str, str]]]:
    """Return normalized SQL expressions and (table, column) pairs covered by GROUP BY."""
    alias_map: dict[str, exp.Expression] = {}
    for proj in select.expressions:
        if isinstance(proj, exp.Alias):
            alias_map[_tr_casefold(proj.alias)] = proj.this

    grouped_sqls: set[str] = set()
    grouped_cols: set[tuple[str, str]] = set()

    def record(expr: exp.Expression) -> None:
        unwrapped = expr.this if isinstance(expr, exp.Paren) else expr
        grouped_sqls.add(unwrapped.sql().lower())
        if isinstance(unwrapped, exp.Column) and not isinstance(unwrapped.this, exp.Star):
            grouped_cols.add((unwrapped.table.lower(), unwrapped.name.lower()))

    for item in _extract_group_expressions(group):
        if isinstance(item, exp.Literal) and not item.is_string:
            try:
                pos = int(item.this)
            except ValueError:
                pos = -1
            if 1 <= pos <= len(select.expressions):
                proj = select.expressions[pos - 1]
                if isinstance(proj, exp.Alias):
                    grouped_cols.add(("", proj.alias.lower()))
                    record(proj.this)
                else:
                    record(proj)
            continue

        record(item)
        if isinstance(item, exp.Column) and not item.table:
            target = alias_map.get(_tr_casefold(item.name))
            if target is not None:
                record(target)

    return grouped_sqls, grouped_cols


def _find_ungrouped_reference(
    node: exp.Expression,
    owner_select: exp.Select,
    grouped_sqls: set[str],
    grouped_cols: set[tuple[str, str]],
) -> str | None:
    """Return a violating column/star display name if *node* uses ungrouped columns."""
    unwrapped = node.this if isinstance(node, exp.Paren) else node
    if unwrapped.sql().lower() in grouped_sqls:
        return None
    if isinstance(node, exp.AggFunc) and not _is_window_agg(node):
        return None
    if node is not owner_select and isinstance(node, (exp.Select, exp.CTE)):
        return None
    if isinstance(node, exp.Star):
        return "*"
    if isinstance(node, exp.Column):
        if isinstance(node.this, exp.Star):
            return node.sql()
        tname = node.table.lower()
        cname = node.name.lower()
        if (tname, cname) in grouped_cols or ("", cname) in grouped_cols:
            return None
        if not tname and any(c == cname for _, c in grouped_cols):
            return None
        return node.sql()

    for child in node.iter_expressions():
        violation = _find_ungrouped_reference(child, owner_select, grouped_sqls, grouped_cols)
        if violation is not None:
            return violation
    return None


def _check_select_semantics(select: exp.Select) -> CheckResult | None:
    # 1. Duplicate output aliases in SELECT projections
    seen_aliases: set[str] = set()
    unaliased_cols: set[str] = set()
    for proj in select.expressions:
        if isinstance(proj, exp.Alias):
            raw = proj.alias
            key = _tr_casefold(raw)
            if key in seen_aliases or key in unaliased_cols:
                return _fail(f"SELECT listesinde yinelenen sütun takma adı: {raw}")
            seen_aliases.add(key)
        elif isinstance(proj, exp.Column) and not isinstance(proj.this, exp.Star):
            key = _tr_casefold(proj.name)
            if key in seen_aliases:
                return _fail(f"SELECT listesinde yinelenen sütun takma adı: {proj.name}")
            unaliased_cols.add(key)

    # 2. Aggregates inside WHERE (invalid SQL) & nested aggregate functions
    where = select.args.get("where")
    if isinstance(where, exp.Expression):
        for node in _iter_in_select_scope(where, select):
            if isinstance(node, exp.AggFunc) and not _is_window_agg(node):
                return _fail("WHERE yan tümcesinde toplama (aggregate) fonksiyonu kullanılamaz.")

    having = select.args.get("having")
    order = select.args.get("order")
    clauses = [c for c in [*select.expressions, having, order] if isinstance(c, exp.Expression)]

    non_window_aggs: list[exp.AggFunc] = []
    for clause in clauses:
        for node in _iter_in_select_scope(clause, select):
            if isinstance(node, exp.AggFunc) and not _is_window_agg(node):
                non_window_aggs.append(node)
                for child in node.iter_expressions():
                    for desc in _iter_in_select_scope(child, select):
                        if (isinstance(desc, exp.AggFunc) and not _is_window_agg(desc)) or isinstance(
                            desc, exp.Window
                        ):
                            return _fail("İç içe toplama (aggregate) fonksiyonları kullanılamaz.")

    # 3. HAVING without GROUP BY or aggregation
    group = select.args.get("group")
    has_group_by = isinstance(group, exp.Group)
    has_agg = bool(non_window_aggs)
    if having is not None and not has_group_by and not has_agg:
        return _fail("HAVING yan tümcesi GROUP BY veya toplama fonksiyonu olmadan kullanılamaz.")

    # 4. GROUP BY consistency across SELECT projections and HAVING
    if has_group_by or has_agg:
        grouped_sqls, grouped_cols = (
            _resolve_grouped_items(select, group) if isinstance(group, exp.Group) else (set(), set())
        )
        for proj in select.expressions:
            target = proj.this if isinstance(proj, exp.Alias) else proj
            violation = _find_ungrouped_reference(target, select, grouped_sqls, grouped_cols)
            if violation is not None:
                if violation == "*" or violation.endswith(".*"):
                    return _fail("Toplama veya GROUP BY içeren sorguda '*' seçilemez.")
                return _fail(
                    f"GROUP BY tutarlılığı hatası: '{violation}' sütunu GROUP BY içinde "
                    "yer almalı veya bir toplama fonksiyonuyla sarılmalıdır."
                )
        if isinstance(having, exp.Expression):
            violation = _find_ungrouped_reference(having, select, grouped_sqls, grouped_cols)
            if violation is not None:
                return _fail(
                    f"HAVING tutarlılığı hatası: '{violation}' sütunu GROUP BY içinde "
                    "yer almalı veya bir toplama fonksiyonuyla sarılmalıdır."
                )

    return None


def validate_semantics(tree: exp.Expression) -> CheckResult:
    """Validate SQL AST semantic consistency across all SELECT scopes."""
    for select in tree.find_all(exp.Select):
        failure = _check_select_semantics(select)
        if failure is not None:
            return failure
    return _ok()
