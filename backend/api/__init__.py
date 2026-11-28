"""L1 — HTTP API (FastAPI) & offline MCP tool adapter.

The only module allowed to import ``fastapi``. FastAPI is an optional
dependency (``pip install -e .[api]``) so the core pipeline can be tested
without a web server.
"""

from backend.api.app import QueryBody, create_app
from backend.api.mcp_server import TRSQLMCPServer
from backend.api.rate_limit import (
    RateLimiter,
    RateLimitExceededError,
    RequestTooLargeError,
    check_connection_ownership,
    validate_request_size,
)

__all__ = [
    "QueryBody",
    "RateLimitExceededError",
    "RateLimiter",
    "RequestTooLargeError",
    "TRSQLMCPServer",
    "check_connection_ownership",
    "create_app",
    "validate_request_size",
]
