from __future__ import annotations

from backend.core.contracts import ApprovedQuery, ExecutionResult
from backend.core.errors import ExecutionError
from backend.core.ports import DatabaseAdapter


class ExecutionEngine:
    def __init__(self, adapter: DatabaseAdapter) -> None:
        self._adapter = adapter

    def run(self, query: ApprovedQuery) -> ExecutionResult:
        if query.dialect is not self._adapter.dialect:
            raise ExecutionError("sorgu diyalekti bağlantı ile uyuşmuyor")
        return self._adapter.execute(query)
