"""AST structural cost checks and PostgreSQL EXPLAIN (FORMAT JSON) evaluation (L6)."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from sqlglot import exp

from backend.core.contracts import CheckName, CheckResult, Severity


@dataclass(frozen=True)
class CostThresholds:
    """Configurable structural and EXPLAIN cost thresholds."""

    max_joins: int = 6
    max_subqueries: int = 5
    max_subquery_depth: int = 4
    max_generate_series_rows: int = 10_000
    max_recursive_limit: int = 10_000
    max_explain_cost: float = 1_000_000.0
    max_explain_rows: int = 10_000_000
    max_seq_scan_rows: int = 10_000


def _ok(message: str = "") -> CheckResult:
    return CheckResult(check=CheckName.COST, passed=True, message=message)


def _fail(message: str, severity: Severity = Severity.REPAIRABLE) -> CheckResult:
    return CheckResult(check=CheckName.COST, passed=False, severity=severity, message=message)


def _is_tautology(expr: exp.Expression | None) -> bool:
    if expr is None:
        return False
    if isinstance(expr, exp.Paren):
        return _is_tautology(expr.this)
    if isinstance(expr, exp.Boolean):
        return bool(expr.this)
    if (
        isinstance(expr, exp.EQ)
        and isinstance(expr.this, exp.Literal)
        and isinstance(expr.expression, exp.Literal)
    ):
        return expr.this.this == expr.expression.this and expr.this.is_string == expr.expression.is_string
    return False


def _extract_int_literal(node: exp.Expression | None) -> int | None:
    if node is None:
        return None
    if isinstance(node, exp.Paren):
        return _extract_int_literal(node.this)
    if isinstance(node, exp.Neg) and isinstance(node.this, exp.Literal) and not node.this.is_string:
        try:
            return -int(node.this.this)
        except ValueError:
            return None
    if isinstance(node, exp.Literal) and not node.is_string:
        try:
            return int(node.this)
        except ValueError:
            return None
    return None


def _extract_date_literal(node: exp.Expression | None) -> datetime | None:
    if node is None:
        return None
    if isinstance(node, exp.Cast):
        return _extract_date_literal(node.this)
    if isinstance(node, exp.Literal) and node.is_string:
        text = str(node.this).strip()
        for parser in (datetime.fromisoformat,):
            try:
                return parser(text)
            except ValueError:
                pass
        try:
            d = date.fromisoformat(text)
            return datetime(d.year, d.month, d.day)
        except ValueError:
            return None
    return None


def _select_safe_limit(select: exp.Select | None) -> int | None:
    """Return LIMIT only if the SELECT has no aggregation/sorting/distinct that forces full scan."""
    if select is None:
        return None
    if select.args.get("group") or select.args.get("order") or select.args.get("distinct"):
        return None
    if any(isinstance(n, exp.AggFunc) for n in select.expressions):
        return None
    limit = select.args.get("limit")
    if isinstance(limit, exp.Limit):
        return _extract_int_literal(limit.expression)
    if isinstance(limit, exp.Fetch):
        return _extract_int_literal(limit.args.get("count"))
    return None


def _has_bounded_upper_predicate(where: exp.Where | None, max_limit: int) -> bool:
    if where is None:
        return False
    for cmp_node in where.find_all(exp.LT, exp.LTE):
        bound = _extract_int_literal(cmp_node.expression)
        if bound is not None and 0 <= bound <= max_limit:
            return True
    return False


def _check_recursive_ctes(tree: exp.Expression, thresholds: CostThresholds) -> CheckResult | None:
    for with_node in tree.find_all(exp.With):
        if not with_node.args.get("recursive"):
            continue
        for cte in with_node.expressions:
            cte_name = cte.alias_or_name.lower()
            body = cte.this
            if not isinstance(body, exp.Expression):
                continue
            refs_self = any(tbl.name.lower() == cte_name and not tbl.db for tbl in body.find_all(exp.Table))
            if not refs_self:
                continue

            cte_limit = body.args.get("limit")
            limit_val = (
                _extract_int_literal(cte_limit.expression)
                if isinstance(cte_limit, exp.Limit)
                else _extract_int_literal(cte_limit.args.get("count"))
                if isinstance(cte_limit, exp.Fetch)
                else None
            )
            if limit_val is not None and 0 <= limit_val <= thresholds.max_recursive_limit:
                continue

            # Check recursive branch (right side of Union, or all Selects referencing self)
            recursive_selects = [
                sel
                for sel in body.find_all(exp.Select)
                if any(tbl.name.lower() == cte_name and not tbl.db for tbl in sel.find_all(exp.Table))
            ]
            if recursive_selects and all(
                _has_bounded_upper_predicate(sel.args.get("where"), thresholds.max_recursive_limit)
                for sel in recursive_selects
            ):
                continue

            return _fail(
                "Sınırsız özyinelemeli CTE (WITH RECURSIVE) kullanılamaz; "
                "CTE içine LIMIT veya açık üst sınır koşulu ekleyin."
            )
    return None


def _check_generate_series(tree: exp.Expression, thresholds: CostThresholds) -> CheckResult | None:
    series_nodes: list[exp.Expression] = list(tree.find_all(exp.ExplodingGenerateSeries))
    for cls_name in ("GenerateSeries",):
        gen_cls = getattr(exp, cls_name, None)
        if isinstance(gen_cls, type) and issubclass(gen_cls, exp.Expression):
            series_nodes.extend(tree.find_all(gen_cls))
    for anon in tree.find_all(exp.Anonymous):
        if anon.name.lower() == "generate_series":
            series_nodes.append(anon)

    for node in series_nodes:
        if isinstance(node, exp.ExplodingGenerateSeries):
            start_expr = node.args.get("start")
            end_expr = node.args.get("end")
            step_expr = node.args.get("step")
        else:
            args = node.expressions
            start_expr = args[0] if len(args) > 0 else None
            end_expr = args[1] if len(args) > 1 else None
            step_expr = args[2] if len(args) > 2 else None

        select = node.find_ancestor(exp.Select)
        safe_limit = _select_safe_limit(select)
        if safe_limit is not None and 0 <= safe_limit <= thresholds.max_generate_series_rows:
            continue

        start_num = _extract_int_literal(start_expr)
        end_num = _extract_int_literal(end_expr)
        if start_num is not None and end_num is not None:
            step_num = _extract_int_literal(step_expr) if step_expr is not None else 1
            if step_num is None or step_num == 0:
                return _fail("generate_series adım değeri geçersiz veya sıfır olamaz.")
            est_rows = abs(end_num - start_num) // abs(step_num) + 1
            if est_rows > thresholds.max_generate_series_rows:
                return _fail(
                    f"generate_series aralığı çok geniş ({est_rows} satır; "
                    f"en fazla {thresholds.max_generate_series_rows})."
                )
            continue

        start_dt = _extract_date_literal(start_expr)
        end_dt = _extract_date_literal(end_expr)
        if start_dt is not None and end_dt is not None:
            days = abs((end_dt - start_dt).days) + 1
            if days <= thresholds.max_generate_series_rows:
                continue
            return _fail(f"generate_series tarih aralığı çok geniş ({days} gün).")

        return _fail("Sınırsız generate_series kullanılamaz; sabit üst sınır veya LIMIT ekleyin.")
    return None


def _subquery_stats(tree: exp.Expression) -> tuple[int, int]:
    """Return (nested_select_count, max_select_nesting_depth)."""
    selects = list(tree.find_all(exp.Select))
    nested_count = max(0, len(selects) - 1)
    max_depth = 0
    for sel in selects:
        depth = 0
        cur = sel.parent
        while cur is not None:
            if isinstance(cur, exp.Select):
                depth += 1
            cur = cur.parent
        if depth > max_depth:
            max_depth = depth
    return nested_count, max_depth


def check_ast_cost(tree: exp.Expression, thresholds: CostThresholds | None = None) -> CheckResult:
    """Perform structural AST cost checks without running queries against a database."""
    cfg = thresholds or CostThresholds()

    joins = list(tree.find_all(exp.Join))
    if len(joins) > cfg.max_joins:
        return _fail(f"Çok fazla JOIN ({len(joins)}).")

    for join in joins:
        on = join.args.get("on")
        has_condition = bool(join.args.get("using")) or (on is not None and not _is_tautology(on))
        select = join.find_ancestor(exp.Select)
        where = select.args.get("where") if select is not None else None
        has_where = where is not None and not _is_tautology(
            where.this if isinstance(where, exp.Where) else where
        )
        if not has_condition and not has_where:
            return _fail("Koşulsuz JOIN (kartezyen çarpım).")

    rec_err = _check_recursive_ctes(tree, cfg)
    if rec_err is not None:
        return rec_err

    series_err = _check_generate_series(tree, cfg)
    if series_err is not None:
        return series_err

    nested_count, max_depth = _subquery_stats(tree)
    if nested_count > cfg.max_subqueries or max_depth > cfg.max_subquery_depth:
        return _fail(
            f"Çok fazla veya çok derin iç içe alt sorgu (alt sorgu={nested_count}, derinlik={max_depth})."
        )

    return _ok()


def _inner_has_join_index_access(node: Mapping[str, Any]) -> bool:
    """Return True if a Nested Loop inner branch uses a parameterized index/tid access."""
    if any(k in node for k in ("Index Cond", "Recheck Cond", "Tid Cond")):
        return True
    for child in node.get("Plans", ()):
        if isinstance(child, Mapping) and _inner_has_join_index_access(child):
            return True
    return False


def _walk_explain_node(
    node: Mapping[str, Any],
    parent_type: str | None,
    *,
    max_cost: float,
    max_rows: int,
    max_seq_scan_rows: int,
) -> CheckResult | None:
    node_type = str(node.get("Node Type", ""))
    total_cost_raw = node.get("Total Cost")
    plan_rows_raw = node.get("Plan Rows")

    if isinstance(total_cost_raw, (int, float)) and float(total_cost_raw) > max_cost:
        return _fail(f"Tahmini sorgu maliyeti sınırı aşıyor ({float(total_cost_raw):.1f} > {max_cost:.1f}).")
    if isinstance(plan_rows_raw, (int, float)) and int(plan_rows_raw) > max_rows:
        return _fail(f"Tahmini satır sayısı sınırı aşıyor ({int(plan_rows_raw)} > {max_rows}).")

    # Full-table scan detection: unfiltered Seq Scan over threshold not immediately capped by Limit
    if (
        node_type == "Seq Scan"
        and parent_type != "Limit"
        and not node.get("Filter")
        and isinstance(plan_rows_raw, (int, float))
        and int(plan_rows_raw) > max_seq_scan_rows
    ):
        return _fail(
            f"Tam tablo taraması (Seq Scan) sınırı aşıyor ({int(plan_rows_raw)} > {max_seq_scan_rows})."
        )

    # Cartesian join detection in EXPLAIN plan
    children = [c for c in node.get("Plans", ()) if isinstance(c, Mapping)]
    if node_type == "Nested Loop" and not node.get("Join Filter") and len(children) >= 2:
        join_type = str(node.get("Join Type", "Inner"))
        if join_type in ("Inner", "Cross", "") and not _inner_has_join_index_access(children[1]):
            return _fail("EXPLAIN planında koşulsuz kartezyen birleşim (Nested Loop) tespit edildi.")
    if node_type == "Hash Join" and not node.get("Hash Cond") and not node.get("Join Filter"):
        return _fail("EXPLAIN planında koşulsuz Hash Join tespit edildi.")
    if node_type == "Merge Join" and not node.get("Merge Cond") and not node.get("Join Filter"):
        return _fail("EXPLAIN planında koşulsuz Merge Join tespit edildi.")

    for child in children:
        failure = _walk_explain_node(
            child,
            node_type,
            max_cost=max_cost,
            max_rows=max_rows,
            max_seq_scan_rows=max_seq_scan_rows,
        )
        if failure is not None:
            return failure
    return None


def evaluate_explain_plan(
    plan_json: str | Sequence[Mapping[str, Any]] | Mapping[str, Any],
    *,
    max_cost: float = 1_000_000.0,
    max_rows: int = 10_000_000,
    max_seq_scan_rows: int = 10_000,
) -> CheckResult:
    """Evaluate a PostgreSQL ``EXPLAIN (FORMAT JSON)`` plan against cost/row/scan budgets.

    Never executes or accepts ``EXPLAIN ANALYZE`` plans with runtime modification side-effects.
    """
    parsed: Any = plan_json
    if isinstance(plan_json, str):
        try:
            parsed = json.loads(plan_json)
        except json.JSONDecodeError:
            return _fail("EXPLAIN (FORMAT JSON) çıktısı geçerli JSON değil.")

    root_plan: Mapping[str, Any] | None = None
    if isinstance(parsed, Sequence) and not isinstance(parsed, (str, bytes)) and parsed:
        first = parsed[0]
        if isinstance(first, Mapping):
            candidate = first.get("Plan", first)
            if isinstance(candidate, Mapping):
                root_plan = candidate
    elif isinstance(parsed, Mapping):
        candidate = parsed.get("Plan", parsed)
        if isinstance(candidate, Mapping):
            root_plan = candidate

    if root_plan is None or "Node Type" not in root_plan:
        return _fail("EXPLAIN planı çözümlenemedi.")

    failure = _walk_explain_node(
        root_plan,
        None,
        max_cost=max_cost,
        max_rows=max_rows,
        max_seq_scan_rows=max_seq_scan_rows,
    )
    if failure is not None:
        return failure
    return _ok()
