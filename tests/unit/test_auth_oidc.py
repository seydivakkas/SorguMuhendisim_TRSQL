from __future__ import annotations

import base64
import json
import time
from pathlib import Path
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from backend.auth import (
    DEFAULT_PII_DENIED_COLUMNS,
    OIDCAuthProvider,
    OIDCConfig,
    RolePolicy,
)
from backend.core.errors import AuthorizationError, ConfigError


def _b64uint(val: int) -> str:
    raw = val.to_bytes((val.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _generate_rsa_jwk(kid: str = "key-1") -> tuple[rsa.RSAPrivateKey, dict[str, Any]]:
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pub = priv.public_key().public_numbers()
    jwk = {
        "kty": "RSA",
        "kid": kid,
        "use": "sig",
        "alg": "RS256",
        "n": _b64uint(pub.n),
        "e": _b64uint(pub.e),
    }
    return priv, jwk


def _write_jwks(path: Path, keys: list[dict[str, Any]]) -> Path:
    path.write_text(json.dumps({"keys": keys}), encoding="utf-8")
    return path


def _policies() -> dict[str, RolePolicy]:
    return {
        "analyst": RolePolicy(
            role="analyst",
            allowed_tables=("dealers", "sales"),
            denied_columns=("dealers.tax_number",),
            max_rows=200,
        )
    }


def _sign(
    priv: rsa.RSAPrivateKey,
    payload: dict[str, Any],
    *,
    kid: str | None = "key-1",
    algorithm: str = "RS256",
) -> str:
    headers = {"kid": kid} if kid else None
    return jwt.encode(payload, priv, algorithm=algorithm, headers=headers)


def test_oidc_provider_authenticates_valid_rs256_token(tmp_path: Path) -> None:
    priv, jwk = _generate_rsa_jwk("key-1")
    jwks_path = _write_jwks(tmp_path / "jwks.json", [jwk])
    cfg = OIDCConfig(
        issuer="https://idp.example.local/realms/trsql",
        audience="trsql-api",
        jwks_path=str(jwks_path),
    )
    provider = OIDCAuthProvider(cfg, _policies())

    now = int(time.time())
    tok = _sign(
        priv,
        {
            "sub": "u-oidc-1",
            "tenant_id": "t-corp",
            "iss": cfg.issuer,
            "aud": cfg.audience,
            "iat": now,
            "nbf": now - 5,
            "exp": now + 300,
            "realm_access": {"roles": ["analyst"]},
        },
    )
    ctx = provider.authenticate(tok)
    assert ctx.user_id == "u-oidc-1"
    assert ctx.tenant_id == "t-corp"
    assert ctx.roles == frozenset({"analyst"})
    assert ctx.allowed_tables == frozenset({"dealers", "sales"})
    assert ctx.max_rows == 200
    assert "dealers.tax_number" in ctx.denied_columns
    for col in DEFAULT_PII_DENIED_COLUMNS:
        assert f"dealers.{col}" in ctx.denied_columns


def test_oidc_rejects_expired_nbf_aud_iss_and_unknown_role(tmp_path: Path) -> None:
    priv, jwk = _generate_rsa_jwk("key-1")
    jwks_path = _write_jwks(tmp_path / "jwks.json", [jwk])
    cfg = OIDCConfig(
        issuer="https://idp.example.local/realms/trsql",
        audience="trsql-api",
        jwks_path=str(jwks_path),
        leeway_seconds=0,
    )
    provider = OIDCAuthProvider(cfg, _policies())
    now = int(time.time())

    cases = [
        {  # expired
            "sub": "u1",
            "tenant_id": "t1",
            "iss": cfg.issuer,
            "aud": cfg.audience,
            "exp": now - 10,
            "roles": ["analyst"],
        },
        {  # future nbf
            "sub": "u1",
            "tenant_id": "t1",
            "iss": cfg.issuer,
            "aud": cfg.audience,
            "nbf": now + 120,
            "exp": now + 600,
            "roles": ["analyst"],
        },
        {  # wrong audience
            "sub": "u1",
            "tenant_id": "t1",
            "iss": cfg.issuer,
            "aud": "other-client",
            "exp": now + 300,
            "roles": ["analyst"],
        },
        {  # wrong issuer
            "sub": "u1",
            "tenant_id": "t1",
            "iss": "https://evil.example.local",
            "aud": cfg.audience,
            "exp": now + 300,
            "roles": ["analyst"],
        },
        {  # unknown role
            "sub": "u1",
            "tenant_id": "t1",
            "iss": cfg.issuer,
            "aud": cfg.audience,
            "exp": now + 300,
            "roles": ["superadmin_unknown"],
        },
    ]
    for payload in cases:
        with pytest.raises(AuthorizationError):
            provider.authenticate(_sign(priv, payload))


def test_oidc_config_and_jwks_fail_closed(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        OIDCConfig(
            issuer="https://idp.local",
            audience="trsql",
            jwks_path=str(tmp_path / "jwks.json"),
            algorithms=("none",),
        )
    with pytest.raises(ValueError):
        OIDCConfig(
            issuer="https://idp.local",
            audience="trsql",
            jwks_path=str(tmp_path / "jwks.json"),
            algorithms=("HS256",),
        )

    bad_jwks = tmp_path / "bad.json"
    bad_jwks.write_text("{not-json", encoding="utf-8")
    cfg = OIDCConfig(issuer="https://idp.local", audience="trsql", jwks_path=str(bad_jwks))
    with pytest.raises(ConfigError):
        OIDCAuthProvider(cfg, _policies())
