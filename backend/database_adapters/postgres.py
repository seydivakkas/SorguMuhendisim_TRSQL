from __future__ import annotations

import importlib
import json
import os
import time
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Protocol, cast

from backend.core.contracts import (
    ApprovedQuery,
    AuthContext,
    ColumnInfo,
    Dialect,
    ExecutionResult,
    ForeignKey,
    SchemaSnapshot,
    TableInfo,
)
from backend.core.errors import ExecutionError

_FORBIDDEN_SCHEMAS = frozenset({"pg_catalog", "information_schema", "pg_toast"})


class _PgCursor(Protocol):
    @property
    def description(self) -> Sequence[Any] | None: ...

    def execute(self, query: str, params: Sequence[Any] | None = None) -> Any: ...

    def fetchall(self) -> list[tuple[Any, ...]]: ...

    def fetchmany(self, size: int = ...) -> list[tuple[Any, ...]]: ...

    def close(self) -> None: ...


class _PgConnection(Protocol):
    def cursor(self) -> _PgCursor: ...

    def rollback(self) -> None: ...

    def close(self) -> None: ...


class _PgModule(Protocol):
    def connect(self, conninfo: str, **kwargs: Any) -> _PgConnection: ...


def _load_psycopg() -> _PgModule:
    try:
        mod = importlib.import_module("psycopg")
    except ImportError as exc:
        raise ExecutionError("PostgreSQL sürücüsü (psycopg) kurulu değil") from exc
    return cast(_PgModule, mod)


def _validate_schemas(schemas: tuple[str, ...]) -> tuple[str, ...]:
    cleaned: list[str] = []
    for raw in schemas:
        name = raw.strip()
        lowered = name.lower()
        if not name:
            continue
        if lowered in _FORBIDDEN_SCHEMAS or lowered.startswith("pg_"):
            raise ExecutionError(f"Sistem şeması içe aktarılamaz: {name}")
        if name not in cleaned:
            cleaned.append(name)
    if not cleaned:
        raise ExecutionError("En az bir izinli PostgreSQL şeması gereklidir")
    return tuple(cleaned)


def _inner_has_index_access(node: Mapping[str, Any]) -> bool:
    if any(k in node for k in ("Index Cond", "Recheck Cond", "Tid Cond")):
        return True
    for child in node.get("Plans", ()):
        if isinstance(child, Mapping) and _inner_has_index_access(child):
            return True
    return False


def _validate_explain_node(
    node: Mapping[str, Any],
    parent_type: str | None,
    *,
    max_cost: float,
    max_rows: int,
    max_seq_scan_rows: int,
) -> None:
    node_type = str(node.get("Node Type", ""))
    total_cost = node.get("Total Cost")
    plan_rows = node.get("Plan Rows")

    if isinstance(total_cost, (int, float)) and float(total_cost) > max_cost:
        raise ExecutionError(f"Sorgu maliyet eşiği aşıldı ({float(total_cost):.1f} > {max_cost:.1f})")
    if isinstance(plan_rows, (int, float)) and int(plan_rows) > max_rows:
        raise ExecutionError(f"Tahmini satır eşiği aşıldı ({int(plan_rows)} > {max_rows})")
    if (
        node_type == "Seq Scan"
        and parent_type != "Limit"
        and not node.get("Filter")
        and isinstance(plan_rows, (int, float))
        and int(plan_rows) > max_seq_scan_rows
    ):
        raise ExecutionError("Tam tablo taraması (Seq Scan) güvenlik maliyet eşiği nedeniyle engellendi")

    children = [c for c in node.get("Plans", ()) if isinstance(c, Mapping)]
    if node_type == "Nested Loop" and not node.get("Join Filter") and len(children) >= 2:
        join_type = str(node.get("Join Type", "Inner"))
        if join_type in ("Inner", "Cross", "") and not _inner_has_index_access(children[1]):
            raise ExecutionError("EXPLAIN planında koşulsuz kartezyen birleşim engellendi")
    if node_type == "Hash Join" and not node.get("Hash Cond") and not node.get("Join Filter"):
        raise ExecutionError("EXPLAIN planında koşulsuz Hash Join engellendi")
    if node_type == "Merge Join" and not node.get("Merge Cond") and not node.get("Join Filter"):
        raise ExecutionError("EXPLAIN planında koşulsuz Merge Join engellendi")

    for child in children:
        _validate_explain_node(
            child,
            node_type,
            max_cost=max_cost,
            max_rows=max_rows,
            max_seq_scan_rows=max_seq_scan_rows,
        )


def _check_explain_json(
    raw_value: Any,
    *,
    max_cost: float,
    max_rows: int,
    max_seq_scan_rows: int,
) -> None:
    parsed: Any = json.loads(raw_value) if isinstance(raw_value, str) else raw_value
    root_plan: Mapping[str, Any] | None = None
    if isinstance(parsed, Sequence) and not isinstance(parsed, (str, bytes)) and parsed:
        first = parsed[0]
        if isinstance(first, Mapping):
            cand = first.get("Plan", first)
            if isinstance(cand, Mapping):
                root_plan = cand
    elif isinstance(parsed, Mapping):
        cand = parsed.get("Plan", parsed)
        if isinstance(cand, Mapping):
            root_plan = cand

    if root_plan is None or "Node Type" not in root_plan:
        raise ExecutionError("EXPLAIN (FORMAT JSON) planı okunamadı")

    _validate_explain_node(
        root_plan,
        None,
        max_cost=max_cost,
        max_rows=max_rows,
        max_seq_scan_rows=max_seq_scan_rows,
    )


class PostgresAdapter:
    """PostgreSQL read-only database adapter with defense-in-depth session controls.

    Enforces per-transaction:
    - ``SET TRANSACTION READ ONLY``
    - ``SET LOCAL statement_timeout``
    - ``SET LOCAL lock_timeout``
    - ``SET LOCAL idle_in_transaction_session_timeout``
    - Optional parameterized ``app.user_id`` / ``app.tenant_id`` via ``set_config(..., true)`` for RLS
    - Row cap ``fetchmany(query.max_rows + 1)`` and optional ``EXPLAIN (FORMAT JSON)`` budget check
    """

    def __init__(
        self,
        dsn_env: str = "TRSQL_PG_DSN",
        *,
        allowed_schemas: tuple[str, ...] = ("public",),
        statement_timeout_ms: int = 5000,
        lock_timeout_ms: int = 2000,
        idle_in_tx_timeout_ms: int = 10_000,
        check_explain: bool = False,
        max_explain_cost: float = 1_000_000.0,
        max_explain_rows: int = 10_000_000,
        max_seq_scan_rows: int = 10_000,
        user_id: str | None = None,
        tenant_id: str | None = None,
        connect_fn: Callable[[str], _PgConnection] | None = None,
    ) -> None:
        self._dsn_env = dsn_env
        self._allowed_schemas = _validate_schemas(allowed_schemas)
        if statement_timeout_ms <= 0 or lock_timeout_ms <= 0 or idle_in_tx_timeout_ms <= 0:
            raise ExecutionError("Zaman aşımı değerleri pozitif olmalıdır")
        self._statement_timeout_ms = int(statement_timeout_ms)
        self._lock_timeout_ms = int(lock_timeout_ms)
        self._idle_in_tx_timeout_ms = int(idle_in_tx_timeout_ms)
        self._check_explain = check_explain
        self._max_explain_cost = float(max_explain_cost)
        self._max_explain_rows = int(max_explain_rows)
        self._max_seq_scan_rows = int(max_seq_scan_rows)
        self._user_id = user_id
        self._tenant_id = tenant_id
        self._connect_fn = connect_fn

    @property
    def dialect(self) -> Dialect:
        return Dialect.POSTGRES

    def with_auth(self, auth: AuthContext) -> PostgresAdapter:
        """Return a new adapter bound to *auth*'s user and tenant for PostgreSQL RLS."""
        return PostgresAdapter(
            self._dsn_env,
            allowed_schemas=self._allowed_schemas,
            statement_timeout_ms=self._statement_timeout_ms,
            lock_timeout_ms=self._lock_timeout_ms,
            idle_in_tx_timeout_ms=self._idle_in_tx_timeout_ms,
            check_explain=self._check_explain,
            max_explain_cost=self._max_explain_cost,
            max_explain_rows=self._max_explain_rows,
            max_seq_scan_rows=self._max_seq_scan_rows,
            user_id=auth.user_id,
            tenant_id=auth.tenant_id,
            connect_fn=self._connect_fn,
        )

    def _get_dsn(self) -> str:
        dsn = os.environ.get(self._dsn_env, "").strip()
        if not dsn:
            raise ExecutionError(f"PostgreSQL bağlantı ortam değişkeni tanımlı değil: {self._dsn_env}")
        return dsn

    def _connect(self) -> _PgConnection:
        dsn = self._get_dsn()
        if self._connect_fn is not None:
            return self._connect_fn(dsn)
        pg = _load_psycopg()
        return pg.connect(dsn, autocommit=False)

    def _configure_transaction(
        self,
        cur: _PgCursor,
        *,
        timeout_ms: int,
        user_id: str | None,
        tenant_id: str | None,
    ) -> None:
        safe_stmt_ms = int(timeout_ms)
        if safe_stmt_ms <= 0:
            raise ExecutionError("Geçersiz statement_timeout değeri")
        cur.execute("SET TRANSACTION READ ONLY")
        cur.execute(f"SET LOCAL statement_timeout = {safe_stmt_ms}")
        cur.execute(f"SET LOCAL lock_timeout = {self._lock_timeout_ms}")
        cur.execute(f"SET LOCAL idle_in_transaction_session_timeout = {self._idle_in_tx_timeout_ms}")
        # Pin name resolution to the allowed schemas so an unqualified table can never
        # resolve to a shadowing table in another schema (e.g. ``"$user"``).
        search_path = ", ".join('"' + name.replace('"', '""') + '"' for name in self._allowed_schemas)
        cur.execute("SELECT set_config('search_path', %s, true)", (search_path,))
        # Parameterized set_config avoids interpolating user/tenant strings into SET LOCAL SQL.
        if user_id:
            cur.execute("SELECT set_config('app.user_id', %s, true)", (user_id,))
        if tenant_id:
            cur.execute("SELECT set_config('app.tenant_id', %s, true)", (tenant_id,))

    def _format_table_name(self, schema_name: str, table_name: str) -> str:
        if len(self._allowed_schemas) == 1 or schema_name == "public":
            return table_name
        return f"{schema_name}.{table_name}"

    def introspect(self) -> SchemaSnapshot:
        conn = self._connect()
        placeholders = ", ".join(["%s"] * len(self._allowed_schemas))
        col_sql = (
            "SELECT c.table_schema, c.table_name, c.column_name, c.data_type, "
            "c.is_nullable, "
            "EXISTS ("
            "  SELECT 1 FROM information_schema.table_constraints tc "
            "  JOIN information_schema.key_column_usage kcu "
            "    ON tc.constraint_name = kcu.constraint_name "
            "   AND tc.table_schema = kcu.table_schema "
            "   AND tc.table_name = kcu.table_name "
            "  WHERE tc.constraint_type = 'PRIMARY KEY' "
            "    AND tc.table_schema = c.table_schema "
            "    AND tc.table_name = c.table_name "
            "    AND kcu.column_name = c.column_name"
            ") AS is_pk "
            "FROM information_schema.columns c "
            "JOIN information_schema.tables t "
            "  ON t.table_schema = c.table_schema AND t.table_name = c.table_name "
            "WHERE t.table_type IN ('BASE TABLE', 'VIEW') "
            "  AND c.table_schema NOT IN ('pg_catalog', 'information_schema') "
            f"  AND c.table_schema IN ({placeholders}) "
            "ORDER BY c.table_schema, c.table_name, c.ordinal_position"
        )
        fk_sql = (
            "SELECT kcu.table_schema, kcu.table_name, kcu.column_name, "
            "ccu.table_schema AS ref_schema, ccu.table_name AS ref_table, ccu.column_name AS ref_column "
            "FROM information_schema.table_constraints tc "
            "JOIN information_schema.key_column_usage kcu "
            "  ON tc.constraint_name = kcu.constraint_name "
            " AND tc.table_schema = kcu.table_schema "
            "JOIN information_schema.constraint_column_usage ccu "
            "  ON tc.constraint_name = ccu.constraint_name "
            " AND tc.constraint_schema = ccu.constraint_schema "
            "WHERE tc.constraint_type = 'FOREIGN KEY' "
            "  AND tc.table_schema NOT IN ('pg_catalog', 'information_schema') "
            f"  AND tc.table_schema IN ({placeholders}) "
            f"  AND ccu.table_schema IN ({placeholders}) "
            "ORDER BY kcu.table_schema, kcu.table_name, kcu.column_name"
        )
        try:
            cur = conn.cursor()
            self._configure_transaction(
                cur,
                timeout_ms=self._statement_timeout_ms,
                user_id=None,
                tenant_id=None,
            )
            cur.execute(col_sql, self._allowed_schemas)
            col_rows = cur.fetchall()
            cur.execute(fk_sql, self._allowed_schemas + self._allowed_schemas)
            fk_rows = cur.fetchall()

            cols_by_table: dict[str, list[ColumnInfo]] = {}
            schema_by_table: dict[str, str] = {}
            for schema_name, tbl_name, col_name, data_type, is_nullable, is_pk in col_rows:
                sname = str(schema_name)
                if sname.lower() in _FORBIDDEN_SCHEMAS or sname.lower().startswith("pg_"):
                    continue
                key = self._format_table_name(sname, str(tbl_name))
                schema_by_table.setdefault(key, sname.lower())
                nullable = (
                    str(is_nullable).upper() == "YES" if isinstance(is_nullable, str) else bool(is_nullable)
                )
                cols_by_table.setdefault(key, []).append(
                    ColumnInfo(
                        name=str(col_name),
                        data_type=str(data_type or ""),
                        nullable=nullable,
                        is_primary_key=bool(is_pk),
                    )
                )

            fks_by_table: dict[str, list[ForeignKey]] = {}
            for schema_name, tbl_name, col_name, ref_schema, ref_tbl, ref_col in fk_rows:
                sname = str(schema_name)
                rsname = str(ref_schema)
                if sname.lower() in _FORBIDDEN_SCHEMAS or rsname.lower() in _FORBIDDEN_SCHEMAS:
                    continue
                key = self._format_table_name(sname, str(tbl_name))
                ref_key = self._format_table_name(rsname, str(ref_tbl))
                fks_by_table.setdefault(key, []).append(
                    ForeignKey(
                        column=str(col_name),
                        ref_table=ref_key,
                        ref_column=str(ref_col),
                    )
                )

            tables = tuple(
                TableInfo(
                    name=tname,
                    schema_name=schema_by_table[tname],
                    columns=tuple(cols),
                    foreign_keys=tuple(fks_by_table.get(tname, ())),
                )
                for tname, cols in cols_by_table.items()
            )
            return SchemaSnapshot(dialect=Dialect.POSTGRES, tables=tables)
        except ExecutionError:
            raise
        except Exception as exc:
            raise ExecutionError("PostgreSQL şema bilgisi okunamadı") from exc
        finally:
            try:
                conn.rollback()
            finally:
                conn.close()

    def execute(
        self,
        query: ApprovedQuery,
        *,
        auth: AuthContext | None = None,
    ) -> ExecutionResult:
        if query.dialect is not Dialect.POSTGRES:
            raise ExecutionError("Sorgu diyalekti PostgreSQL değil")

        # RLS context: explicit argument, else the identity the query was approved for,
        # else the identity this adapter was bound to with :meth:`with_auth`.
        identity = auth if auth is not None else query.auth
        eff_user = identity.user_id if identity is not None else self._user_id
        eff_tenant = identity.tenant_id if identity is not None else self._tenant_id

        conn = self._connect()
        started = time.perf_counter()
        try:
            cur = conn.cursor()
            self._configure_transaction(
                cur,
                timeout_ms=query.timeout_ms,
                user_id=eff_user,
                tenant_id=eff_tenant,
            )
            if self._check_explain:
                # Never run EXPLAIN ANALYZE; FORMAT JSON estimates plan cost without executing writes.
                cur.execute(f"EXPLAIN (FORMAT JSON) {query.sql}")
                plan_rows = cur.fetchall()
                if not plan_rows:
                    raise ExecutionError("EXPLAIN (FORMAT JSON) sonucu boş döndü")
                _check_explain_json(
                    plan_rows[0][0],
                    max_cost=self._max_explain_cost,
                    max_rows=self._max_explain_rows,
                    max_seq_scan_rows=self._max_seq_scan_rows,
                )

            cur.execute(query.sql)
            rows = cur.fetchmany(query.max_rows + 1)
            desc = cur.description or ()
            columns = tuple(str(d.name if hasattr(d, "name") else d[0]) for d in desc)
        except ExecutionError:
            raise
        except Exception as exc:
            raise ExecutionError("PostgreSQL sorgusu yürütülemedi") from exc
        finally:
            try:
                conn.rollback()
            finally:
                conn.close()

        truncated = len(rows) > query.max_rows
        return ExecutionResult(
            columns=columns,
            rows=tuple(tuple(r) for r in rows[: query.max_rows]),
            truncated=truncated,
            elapsed_ms=(time.perf_counter() - started) * 1000,
        )
