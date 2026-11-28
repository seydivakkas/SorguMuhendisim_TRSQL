"""FastAPI application factory.

Rate limiting, session management and tenant isolation are L1 duties that
are designed in AR-07; the hooks are marked with TODO(AR-07).
"""

from __future__ import annotations

from fastapi import Depends, FastAPI, Header, HTTPException, status
from pydantic import BaseModel, Field

from backend.auth import StaticAuthProvider
from backend.core.contracts import AuthContext, PipelineOutcome, QueryRequest
from backend.core.errors import AuthorizationError
from backend.orchestration import Pipeline


class QueryBody(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    connection_id: str = Field(min_length=1)


def create_app(pipeline: Pipeline, auth_provider: StaticAuthProvider) -> FastAPI:
    app = FastAPI(title="TRSQL", version="0.2.0")

    def current_user(authorization: str | None = Header(default=None)) -> AuthContext:
        token = authorization.removeprefix("Bearer ").strip() if authorization else None
        try:
            return auth_provider.authenticate(token)
        except AuthorizationError as exc:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/v1/query", response_model=PipelineOutcome)
    def query(body: QueryBody, auth: AuthContext = Depends(current_user)) -> PipelineOutcome:
        # TODO(AR-07): rate limiting per user/tenant, connection ownership check.
        request = QueryRequest(question=body.question, connection_id=body.connection_id)
        return pipeline.run(request, auth)

    return app
