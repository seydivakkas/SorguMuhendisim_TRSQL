"""FastAPI application factory (L1 — API & Security Gateway)."""

from __future__ import annotations

import os
from collections.abc import Collection, Mapping
from typing import Protocol

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from pydantic import BaseModel, Field

from backend.api.rate_limit import (
    RateLimiter,
    RequestTooLargeError,
    check_connection_ownership,
    validate_request_size,
)
from backend.auth import OIDCAuthProvider, OIDCConfig, load_auth_provider, load_role_policies
from backend.core.config import AuthSettings, load_settings
from backend.core.contracts import AuthContext, PipelineOutcome, QueryRequest
from backend.core.errors import AuthorizationError, ConfigError
from backend.observability import MetricsCollector
from backend.orchestration import Pipeline, PlanPreview, build_pipeline_from_env


class AuthProvider(Protocol):
    def authenticate(self, token: str | None) -> AuthContext: ...


_AUTH_FAILURES_PER_MINUTE = 10


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
    auth_provider: AuthProvider,
    *,
    auth_settings: AuthSettings | None = None,
    rate_limiter: RateLimiter | None = None,
    connection_owners: Mapping[str, str | Collection[str]] | None = None,
    max_payload_bytes: int = 16_384,
    metrics: MetricsCollector | None = None,
    auth_failure_limiter: RateLimiter | None = None,
) -> FastAPI:
    """Create the L1 FastAPI application with auth, rate limiting, ownership, and HITL plan routes.

    Authenticated requests are limited per ``tenant:user``. Failed authentication
    attempts are limited per client address *before* the token is checked, so
    bearer tokens cannot be brute-forced (``auth_failure_limiter``, default 10/min).
    """
    app = FastAPI(title="TRSQL", version="1.0.0")
    limiter = rate_limiter or RateLimiter(auth_settings)
    failures = auth_failure_limiter or RateLimiter(limit_per_minute=_AUTH_FAILURES_PER_MINUTE)

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

    def current_user(request: Request, authorization: str | None = Header(default=None)) -> AuthContext:
        client_key = f"auth-fail:{request.client.host if request.client else 'unknown'}"
        wait = failures.retry_after(client_key)
        if wait is not None:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Çok fazla başarısız kimlik doğrulama denemesi; lütfen daha sonra tekrar deneyin.",
                headers={"Retry-After": str(wait)},
            )
        token = _extract_bearer_token(authorization)
        try:
            return auth_provider.authenticate(token)
        except AuthorizationError as exc:
            failures.check(client_key)
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
    def get_metrics(auth: AuthContext = Depends(current_user)) -> dict[str, object]:
        # Security counters reveal attack activity; never serve them anonymously.
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


def create_default_app() -> FastAPI:
    """Zero-argument FastAPI factory wired from TOML configs and environment variables."""
    config_path = os.environ.get("TRSQL_CONFIG", "").strip() or "configs/default.toml"
    settings = load_settings(config_path)
    metrics = MetricsCollector()
    pipeline = build_pipeline_from_env(settings, metrics=metrics)
    policies_dir = os.environ.get("TRSQL_POLICIES_DIR", "").strip() or None

    oidc_jwks = os.environ.get("TRSQL_OIDC_JWKS", "").strip()
    auth_provider: AuthProvider
    if oidc_jwks:
        issuer = os.environ.get("TRSQL_OIDC_ISSUER", "").strip()
        audience = os.environ.get("TRSQL_OIDC_AUDIENCE", "").strip()
        if not issuer or not audience:
            raise ConfigError("OIDC için TRSQL_OIDC_ISSUER ve TRSQL_OIDC_AUDIENCE gereklidir.")
        policies = load_role_policies(policies_dir or "security_policies")
        auth_provider = OIDCAuthProvider(
            OIDCConfig(issuer=issuer, audience=audience, jwks_path=oidc_jwks),
            policies,
        )
    else:
        tokens_path = os.environ.get("TRSQL_TOKENS_FILE", "").strip() or None
        auth_provider = load_auth_provider(tokens_path=tokens_path, policies_dir=policies_dir)

    return create_app(
        pipeline,
        auth_provider,
        auth_settings=settings.auth,
        metrics=metrics,
    )
