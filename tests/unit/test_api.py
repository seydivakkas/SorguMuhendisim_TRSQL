import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.auth import StaticAuthProvider


def test_requires_auth() -> None:
    app = create_app(pipeline=None, auth_provider=StaticAuthProvider({}))  # type: ignore[arg-type]
    client = TestClient(app)
    assert client.get("/health").json() == {"status": "ok"}
    r = client.post("/v1/query", json={"question": "kaç bayi var", "connection_id": "demo"})
    assert r.status_code == 401
