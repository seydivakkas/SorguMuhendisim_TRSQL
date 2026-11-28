"""Offline-first end-to-end test proving zero outbound network calls (ADR-0002, T-20)."""

from __future__ import annotations

import socket
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient

from backend.api import create_default_app
from backend.auth import hash_token


@pytest.fixture
def block_outbound_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail immediately if any code opens an outbound network socket.

    On Windows, ``asyncio.ProactorEventLoop`` calls ``socket.socketpair()`` once
    internally for its self-pipe using loopback ``_fallback_socketpair``. That
    internal pipe setup is allowed while every other ``socket.connect`` fails.
    """
    orig_socketpair = socket.socketpair
    in_self_pipe = False

    def _guarded_socketpair(*args: object, **kwargs: object) -> tuple[socket.socket, socket.socket]:
        nonlocal in_self_pipe
        in_self_pipe = True
        try:
            return orig_socketpair(*args, **kwargs)  # type: ignore[arg-type]
        finally:
            in_self_pipe = False

    def _blocked_connect(self: socket.socket, address: object) -> None:
        if in_self_pipe:
            # Delegate solely for Python asyncio's internal Windows self-pipe.
            return socket._orig_trsql_connect(self, address)  # type: ignore[attr-defined]
        raise AssertionError(f"Çevrimdışı ihlali (ADR-0002): dış ağ bağlantısı engellendi -> {address!r}")

    monkeypatch.setattr(socket, "_orig_trsql_connect", socket.socket.connect, raising=False)
    monkeypatch.setattr(socket, "socketpair", _guarded_socketpair)
    monkeypatch.setattr(socket.socket, "connect", _blocked_connect)


def test_offline_e2e_create_default_app_forbids_network(
    db_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    block_outbound_network: None,
) -> None:
    policies_dir = tmp_path / "policies"
    policies_dir.mkdir()
    (policies_dir / "analyst.toml").write_text(
        'role = "analyst"\nallowed_tables = ["dealers", "sales"]\n'
        'denied_columns = ["dealers.tax_number"]\nmax_rows = 100\n',
        encoding="utf-8",
    )
    tokens_file = tmp_path / "tokens.txt"
    bearer = "offline-e2e-bearer-01"
    tokens_file.write_text(f"{hash_token(bearer)}:u-offline:analyst:t-demo\n", encoding="utf-8")

    monkeypatch.setenv("TRSQL_DB_DIALECT", "sqlite")
    monkeypatch.setenv("TRSQL_SQLITE_PATH", str(db_path))
    monkeypatch.setenv("TRSQL_MODEL_ADAPTER", "fake")
    monkeypatch.setenv("TRSQL_POLICIES_DIR", str(policies_dir))
    monkeypatch.setenv("TRSQL_TOKENS_FILE", str(tokens_file))

    app = create_default_app()
    client = TestClient(app)

    assert client.get("/health").status_code == 200

    plan_resp = client.post(
        "/v1/plan",
        json={"question": "Kaç bayi var?", "connection_id": "demo"},
        headers={"Authorization": f"Bearer {bearer}"},
    )
    assert plan_resp.status_code == 200
    assert "salaries" not in plan_resp.json()["tables"]

    query_resp = client.post(
        "/v1/query",
        json={"question": "Kaç bayi var?", "connection_id": "demo"},
        headers={"Authorization": f"Bearer {bearer}"},
    )
    assert query_resp.status_code == 200
    assert query_resp.json()["status"] == "answered"
