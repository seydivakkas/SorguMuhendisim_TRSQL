from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient

from backend.api import RateLimiter, TRSQLMCPServer, create_app
from backend.auth import StaticAuthProvider
from backend.core.config import AuthSettings, RetrySettings, Settings
from backend.core.contracts import AuthContext, OutcomeStatus
from backend.database_adapters import SQLiteAdapter
from backend.knowledge_base import InMemoryKnowledgeBase
from backend.model_engine import FakeModelAdapter
from backend.observability import InMemoryAuditSink
from backend.orchestration import Pipeline, build_hybrid_pipeline
from tests.conftest import LOCATIONS, NLP_LEXICON, SCHEMA_LEXICON, TODAY

GOOD_SQL = """```sql
SELECT d.name, SUM(s.total_amount - s.return_amount) AS net_sales
FROM dealers d JOIN sales s ON s.dealer_id = d.dealer_id
WHERE d.city = 'Trabzon' AND s.sale_date >= '2026-10-01' AND s.sale_date < '2026-11-01'
  AND s.status <> 'cancelled'
GROUP BY d.name ORDER BY net_sales DESC LIMIT 5
```"""


def _build_pipeline(
    adapter: SQLiteAdapter,
    knowledge: InMemoryKnowledgeBase,
    responses: list[str] | None = None,
) -> tuple[Pipeline, FakeModelAdapter]:
    model = FakeModelAdapter(responses or [GOOD_SQL])
    sink = InMemoryAuditSink()
    pipeline = build_hybrid_pipeline(
        settings=Settings(retry=RetrySettings(max_attempts=3)),
        database=adapter,
        model=model,
        knowledge=knowledge,
        nlp_lexicon=NLP_LEXICON,
        schema_lexicon=SCHEMA_LEXICON,
        locations=LOCATIONS,
        audit_sink=sink,
        today=lambda: TODAY,
    )
    return pipeline, model


def test_requires_auth() -> None:
    app = create_app(pipeline=None, auth_provider=StaticAuthProvider({}))  # type: ignore[arg-type]
    client = TestClient(app)
    assert client.get("/health").json() == {"status": "ok"}
    r = client.post("/v1/query", json={"question": "kaç bayi var", "connection_id": "demo"})
    assert r.status_code == 401
    # Security counters must not be readable anonymously.
    assert client.get("/metrics").status_code == 401


def test_plan_preview_hitl_without_sql_execution(
    adapter: SQLiteAdapter,
    knowledge: InMemoryKnowledgeBase,
    analyst: AuthContext,
) -> None:
    pipeline, model = _build_pipeline(adapter, knowledge)
    app = create_app(
        pipeline,
        StaticAuthProvider({"tok-analyst": analyst}),
        connection_owners={"demo": "t-demo"},
    )
    client = TestClient(app)

    resp = client.post(
        "/v1/plan",
        json={
            "question": "Geçen ay Trabzon'daki en çok satış yapan beş bayimiz hangileri?",
            "connection_id": "demo",
        },
        headers={"Authorization": "Bearer tok-analyst"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "answered"
    assert "dealers" in body["tables"]
    assert "salaries" not in body["tables"]
    assert all("tax_number" not in c for c in body["columns"])
    assert model.prompts == []


def test_rate_limit_429_and_connection_ownership_403_and_size_413(
    adapter: SQLiteAdapter,
    knowledge: InMemoryKnowledgeBase,
    analyst: AuthContext,
) -> None:
    pipeline, _ = _build_pipeline(adapter, knowledge)
    other_user = analyst.model_copy(update={"user_id": "u-other", "tenant_id": "t-other"})

    now = [100.0]
    limiter = RateLimiter(AuthSettings(rate_limit_per_minute=2), clock=lambda: now[0])
    app = create_app(
        pipeline,
        StaticAuthProvider({"tok-1": analyst, "tok-2": other_user}),
        rate_limiter=limiter,
        connection_owners={"demo": "t-demo"},
        max_payload_bytes=512,
    )
    client = TestClient(app)

    # Connection ownership check -> 403 for wrong tenant
    r_forbidden = client.post(
        "/v1/query",
        json={"question": "Net satış nedir?", "connection_id": "demo"},
        headers={"Authorization": "Bearer tok-2"},
    )
    assert r_forbidden.status_code == 403

    # Size validation -> 413 for oversized payload
    r_big = client.post(
        "/v1/query",
        json={"question": "x" * 600, "connection_id": "demo"},
        headers={"Authorization": "Bearer tok-1"},
    )
    assert r_big.status_code == 413

    # Sliding-window rate limit -> 200, 200, then 429
    for _ in range(2):
        ok_resp = client.post(
            "/v1/query",
            json={"question": "Net satış tutarı nedir?", "connection_id": "demo"},
            headers={"Authorization": "Bearer tok-1"},
        )
        assert ok_resp.status_code == 200
        assert ok_resp.json()["status"] == OutcomeStatus.ANSWERED.value

    limited = client.post(
        "/v1/query",
        json={"question": "Net satış tutarı nedir?", "connection_id": "demo"},
        headers={"Authorization": "Bearer tok-1"},
    )
    assert limited.status_code == 429
    assert int(limited.headers["Retry-After"]) >= 1

    # Window expires -> allowed again
    now[0] += 61.0
    recovered = client.post(
        "/v1/query",
        json={"question": "Net satış tutarı nedir?", "connection_id": "demo"},
        headers={"Authorization": "Bearer tok-1"},
    )
    assert recovered.status_code == 200


def test_mcp_server_exposes_pipeline_tools_never_execute_sql(
    adapter: SQLiteAdapter,
    knowledge: InMemoryKnowledgeBase,
    analyst: AuthContext,
) -> None:
    pipeline, _ = _build_pipeline(adapter, knowledge, ["DROP TABLE sales"])
    analyst_tok = "tok-analyst"
    mcp = TRSQLMCPServer(
        pipeline,
        StaticAuthProvider({analyst_tok: analyst}),
        rate_limiter=RateLimiter(AuthSettings(rate_limit_per_minute=5)),
        connection_owners={"demo": "t-demo"},
    )

    tools = mcp.list_tools()
    tool_names = {t["name"] for t in tools}
    assert "trsql_query" in tool_names
    assert "execute_sql" not in tool_names

    # Unlisted execute_sql call must fail
    bad_rpc = mcp.handle_jsonrpc(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "execute_sql", "arguments": {"sql": "SELECT 1"}},
        },
        token=analyst_tok,
    )
    assert "error" in bad_rpc

    # End-to-end trsql_query via JSON-RPC using KPI template
    ok_rpc = mcp.handle_jsonrpc(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "trsql_query",
                "arguments": {"question": "Net satış tutarı nedir?", "connection_id": "demo"},
            },
        },
        token=analyst_tok,
    )
    assert "result" in ok_rpc
    assert ok_rpc["result"]["isError"] is False
    assert ok_rpc["result"]["structuredContent"]["status"] == "answered"
    assert ok_rpc["result"]["structuredContent"]["report"]["rows"] == [[5459999.0]]

    # Security violation through MCP trsql_query is still blocked by L6
    sec_rpc = mcp.handle_jsonrpc(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "trsql_query",
                "arguments": {"question": "Trabzon'daki bayiler", "connection_id": "demo"},
            },
        },
        token=analyst_tok,
    )
    assert sec_rpc["result"]["isError"] is True
    assert sec_rpc["result"]["structuredContent"]["status"] == "rejected"
