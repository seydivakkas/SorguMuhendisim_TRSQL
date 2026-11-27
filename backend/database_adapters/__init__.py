"""Dialect-specific database adapters behind the ``DatabaseAdapter`` port.

This is the **only** module allowed to import database drivers
(``sqlite3``, ``psycopg``, ``sqlalchemy``...). Only ``execution_engine``
(and connection registration in ``orchestration``) may use it.
"""

from backend.database_adapters.postgres import PostgresAdapter
from backend.database_adapters.sqlite import SQLiteAdapter

__all__ = ["PostgresAdapter", "SQLiteAdapter"]
