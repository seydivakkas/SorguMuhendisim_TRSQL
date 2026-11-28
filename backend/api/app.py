"""FastAPI application factory (L1 — API & Security Gateway)."""

from __future__ import annotations

from collections.abc import Collection, Mapping

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from pydantic import BaseModel, Field

from backend.api.rate_limit import (
    RateLimiter,
    RequestTooLargeError,
    check_connection_ownership,
    validate_request_size,
)
from backend.auth import StaticAuthProvider
from backend.core.config import AuthSettings
from backend.core.contracts import AuthContext, PipelineOutcome, QueryRequest
from backend.core.errors import AuthorizationError
from backend.observability import MetricsCollector
from backend.orchestration import Pipeline, PlanPreview


class QueryBody(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    connection_id: str = Field(min_length=1)
    session_id: str | None = None


def _extract_bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    if authorization[:7].lower() == "bearer ":
        return authorization[7:].strip() or None
    return None


def create_app(
    pipeline: Pipeline,
    auth_provider: StaticAuthProvider,
    *,
    auth_settings: AuthSettings | None = None,
    rate_limiter: RateLimiter | None = None,
    connection_owners: Mapping[str, str | Collection[str]] | None = None,
    max_payload_bytes: int = 16_384,
    metrics: MetricsCollector | None = None,
) -> FastAPI:
    """Create the L1 FastAPI application with auth, rate limiting, ownership, and HITL plan routes."""
    app = FastAPI(title="TRSQL", version="1.0.0")
    limiter = rate_limiter or RateLimiter(auth_settings)

    async def enforce_payload_size(request: Request) -> None:
        raw_len = request.headers.get("content-length")
        if raw_len is not None:
            try:
                if int(raw_len) > max_payload_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail="İstek boyutu izin verilen sınırı aşıyor.",
                    )
            except ValueError:
                pass
        raw_body = await request.body()
        if len(raw_body) > max_payload_bytes:
            raise HTTPException(
                status_code=413,
                detail="İstek boyutu izin verilen sınırı aşıyor.",
            )

    def current_user(authorization: str | None = Header(default=None)) -> AuthContext:
        token = _extract_bearer_token(authorization)
        try:
            return auth_provider.authenticate(token)
        except AuthorizationError as exc:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    def authorize_request(body: QueryBody, auth: AuthContext) -> QueryRequest:
        allowed, value = limiter.check_auth(auth)
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="İstek limiti aşıldı; lütfen daha sonra tekrar deneyin.",
                headers={"Retry-After": str(value)},
            )
        try:
            validate_request_size(body.question, max_payload_bytes=max_payload_bytes)
        except RequestTooLargeError as exc:
            raise HTTPException(status_code=413, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
        try:
            check_connection_ownership(body.connection_id, auth, connection_owners)
        except AuthorizationError as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
        return QueryRequest(
            question=body.question,
            connection_id=body.connection_id,
            session_id=body.session_id,
        )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/metrics")
    def get_metrics() -> dict[str, object]:
        if metrics is None:
            return {"enabled": False}
        snap = metrics.snapshot()
        return {
            "enabled": True,
            "requests_total": snap.requests_total,
            "retries_total": snap.retries_total,
            "security_violations_total": snap.security_violations_total,
            "clarifications_total": snap.clarifications_total,
            "template_bypasses_total": snap.template_bypasses_total,
            "outcomes_by_status": snap.outcomes_by_status,
            "routing_modes": snap.routing_modes,
            "otel_enabled": snap.otel_enabled,
        }

    @app.post("/v1/plan", response_model=PlanPreview, dependencies=[Depends(enforce_payload_size)])
    def plan(body: QueryBody, auth: AuthContext = Depends(current_user)) -> PlanPreview:
        request = authorize_request(body, auth)
        return pipeline.preview_plan(request, auth)

    @app.post("/v1/query", response_model=PipelineOutcome, dependencies=[Depends(enforce_payload_size)])
    def query(body: QueryBody, auth: AuthContext = Depends(current_user)) -> PipelineOutcome:
        request = authorize_request(body, auth)
        return pipeline.run(request, auth)

    return app
