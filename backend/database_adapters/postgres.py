from __future__ import annotations

from backend.core.contracts import ApprovedQuery, Dialect, ExecutionResult, SchemaSnapshot


class PostgresAdapter:
    """PostgreSQL adapter — placeholder until AR-07.

    Required behaviour when implemented:
    - Connect with a dedicated **read-only role** (``GRANT SELECT`` only on
      allowed schemas; no ``pg_read_server_files`` etc.). The DSN comes from
      an environment variable, never from config files.
    - Per transaction: ``SET TRANSACTION READ ONLY``,
      ``SET LOCAL statement_timeout = <query.timeout_ms>``,
      ``SET LOCAL idle_in_transaction_session_timeout``.
    - Row-level security (RLS) policies per tenant where applicable.
    - Fetch at most ``query.max_rows + 1`` rows (server-side cursor).
    """

    def __init__(self, dsn_env: str = "TRSQL_PG_DSN") -> None:
        self._dsn_env = dsn_env

    @property
    def dialect(self) -> Dialect:
        return Dialect.POSTGRES

    def introspect(self) -> SchemaSnapshot:
        raise NotImplementedError("PostgresAdapter is implemented in AR-07")

    def execute(self, query: ApprovedQuery) -> ExecutionResult:
        raise NotImplementedError("PostgresAdapter is implemented in AR-07")
