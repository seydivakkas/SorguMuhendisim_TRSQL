"""Offline-safe MCP tool adapter wrapping the full L1-L9 TRSQL pipeline.

Preserves ADR-0004: NEVER exposes ``execute_sql`` or raw database access to
external MCP clients or LLMs. All queries traverse ``Pipeline.run``.
"""

from __future__ import annotations

import json
from collections.abc import Collection, Mapping
from typing import Any

from backend.api.rate_limit import (
    RateLimiter,
    RateLimitExceededError,
    RequestTooLargeError,
    check_connection_ownership,
    validate_request_size,
)
from backend.auth import StaticAuthProvider
from backend.core.contracts import AuthContext, OutcomeStatus, QueryRequest
from backend.core.errors import AuthorizationError
from backend.orchestration import Pipeline

_TOOL_SPECS: tuple[dict[str, Any], ...] = (
    {
        "name": "trsql_query",
        "description": (
            "Türkçe doğal dil sorusunu tam L1-L9 TRSQL güvenlik, doğrulama ve "
            "yetkilendirme hattından geçirerek deterministik yanıt üretir."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "question": {"type": "string", "minLength": 1, "maxLength": 2000},
                "connection_id": {"type": "string", "minLength": 1},
                "token": {"type": "string"},
                "session_id": {"type": "string"},
            },
            "required": ["question", "connection_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "trsql_plan",
        "description": (
            "SQL yürütmeden RBAC kapsamlı tablo, JOIN, metrik ve yönlendirme "
            "planı önizlemesi döndürür (HITL onay adımı)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "question": {"type": "string", "minLength": 1, "maxLength": 2000},
                "connection_id": {"type": "string", "minLength": 1},
                "token": {"type": "string"},
                "session_id": {"type": "string"},
            },
            "required": ["question", "connection_id"],
            "additionalProperties": False,
        },
    },
)


class TRSQLMCPServer:
    """Offline JSON-RPC 2.0 / MCP tool server over ``Pipeline``."""

    def __init__(
        self,
        pipeline: Pipeline,
        auth_provider: StaticAuthProvider,
        *,
        rate_limiter: RateLimiter | None = None,
        connection_owners: Mapping[str, str | Collection[str]] | None = None,
        max_payload_bytes: int = 16_384,
    ) -> None:
        self._pipeline = pipeline
        self._auth_provider = auth_provider
        self._rate_limiter = rate_limiter
        self._connection_owners = connection_owners
        self._max_payload_bytes = max_payload_bytes

    def list_tools(self) -> list[dict[str, Any]]:
        """Return MCP tool descriptors. Never includes raw ``execute_sql``."""
        return [dict(spec) for spec in _TOOL_SPECS]

    def call_tool(
        self,
        name: str,
        arguments: Mapping[str, Any],
        *,
        token: str | None = None,
        auth: AuthContext | None = None,
    ) -> dict[str, Any]:
        """Execute a registered MCP tool through L1 auth/RBAC/rate-limit gates."""
        if name not in {"trsql_query", "trsql_plan"}:
            raise ValueError(f"Bilinmeyen veya izin verilmeyen MCP aracı: {name}")

        raw_token = token if token is not None else arguments.get("token")
        token_str = raw_token if isinstance(raw_token, str) else None
        resolved_auth = auth if auth is not None else self._auth_provider.authenticate(token_str)

        if self._rate_limiter is not None:
            self._rate_limiter.enforce(resolved_auth)

        question = arguments.get("question")
        connection_id = arguments.get("connection_id")
        session_id = arguments.get("session_id")
        if not isinstance(question, str) or not isinstance(connection_id, str) or not connection_id.strip():
            raise ValueError("Geçerli 'question' ve 'connection_id' alanları gereklidir.")

        validate_request_size(question, max_payload_bytes=self._max_payload_bytes)
        check_connection_ownership(connection_id, resolved_auth, self._connection_owners)

        req = QueryRequest(
            question=question,
            connection_id=connection_id,
            session_id=session_id if isinstance(session_id, str) else None,
        )

        if name == "trsql_plan":
            preview = self._pipeline.preview_plan(req, resolved_auth)
            payload = preview.model_dump(mode="json")
            return {
                "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}],
                "structuredContent": payload,
                "isError": False,
            }

        outcome = self._pipeline.run(req, resolved_auth)
        payload = outcome.model_dump(mode="json")
        is_error = outcome.status in {OutcomeStatus.REJECTED, OutcomeStatus.ERROR}
        return {
            "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}],
            "structuredContent": payload,
            "isError": is_error,
        }

    def handle_jsonrpc(
        self,
        request: Mapping[str, Any],
        *,
        token: str | None = None,
    ) -> dict[str, Any]:
        """Handle a single JSON-RPC 2.0 MCP message offline without network I/O."""
        req_id = request.get("id")
        method = request.get("method")
        params = request.get("params") or {}
        if not isinstance(params, Mapping):
            return self._rpc_error(req_id, -32602, "Geçersiz JSON-RPC params nesnesi.")

        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "serverInfo": {"name": "trsql-mcp", "version": "1.0.0"},
                    "capabilities": {"tools": {"listChanged": False}},
                },
            }
        if method == "ping":
            return {"jsonrpc": "2.0", "id": req_id, "result": {}}
        if method == "tools/list":
            return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": self.list_tools()}}
        if method == "tools/call":
            tool_name = params.get("name")
            arguments = params.get("arguments") or {}
            if not isinstance(tool_name, str) or not isinstance(arguments, Mapping):
                return self._rpc_error(req_id, -32602, "Geçersiz tools/call parametreleri.")
            try:
                result = self.call_tool(tool_name, arguments, token=token)
            except AuthorizationError as exc:
                return self._rpc_error(req_id, -32001, str(exc))
            except RateLimitExceededError as exc:
                return self._rpc_error(req_id, -32029, str(exc))
            except (RequestTooLargeError, ValueError) as exc:
                return self._rpc_error(req_id, -32602, str(exc))
            return {"jsonrpc": "2.0", "id": req_id, "result": result}

        return self._rpc_error(req_id, -32601, f"Bilinmeyen yöntem: {method!r}")

    @staticmethod
    def _rpc_error(req_id: Any, code: int, message: str) -> dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": code, "message": message},
        }
