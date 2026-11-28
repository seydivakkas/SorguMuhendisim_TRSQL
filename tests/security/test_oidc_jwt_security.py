"""Security tests for offline OIDC/JWT validation (T-19, ADR-0011).

Must never be skipped (AGENTS.md §1.8).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from pathlib import Path
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from backend.auth import OIDCAuthProvider, OIDCConfig, RolePolicy
from backend.core.errors import AuthorizationError

pytestmark = pytest.mark.security


def _b64json(data: dict[str, Any]) -> str:
    raw = json.dumps(data, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64uint(val: int) -> str:
    raw = val.to_bytes((val.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _provider(tmp_path: Path) -> tuple[OIDCAuthProvider, rsa.RSAPrivateKey, bytes]:
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pub_nums = priv.public_key().public_numbers()
    pub_pem = priv.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    jwks_path = tmp_path / "jwks.json"
    jwks_path.write_text(
        json.dumps(
            {
                "keys": [
                    {
                        "kty": "RSA",
                        "kid": "k1",
                        "use": "sig",
                        "alg": "RS256",
                        "n": _b64uint(pub_nums.n),
                        "e": _b64uint(pub_nums.e),
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    cfg = OIDCConfig(
        issuer="https://idp.internal/trsql",
        audience="trsql-api",
        jwks_path=str(jwks_path),
    )
    policies = {
        "analyst": RolePolicy(
            role="analyst",
            allowed_tables=("dealers",),
            denied_columns=("dealers.tax_number",),
        )
    }
    return OIDCAuthProvider(cfg, policies), priv, pub_pem


def test_oidc_rejects_alg_none_unsigned_tampered_and_key_confusion(tmp_path: Path) -> None:
    provider, priv, pub_pem = _provider(tmp_path)
    now = int(time.time())
    claims = {
        "sub": "u-sec",
        "tenant_id": "t-demo",
        "iss": "https://idp.internal/trsql",
        "aud": "trsql-api",
        "exp": now + 300,
        "roles": ["analyst"],
    }

    # 1. alg=none attack (no signature)
    alg_none = f"{_b64json({'alg': 'none', 'typ': 'JWT'})}.{_b64json(claims)}."
    with pytest.raises(AuthorizationError):
        provider.authenticate(alg_none)

    # 2. Unsigned token with RS256 header claim
    unsigned_rs256 = f"{_b64json({'alg': 'RS256', 'kid': 'k1', 'typ': 'JWT'})}.{_b64json(claims)}."
    with pytest.raises(AuthorizationError):
        provider.authenticate(unsigned_rs256)

    # 3. Signed by an untrusted attacker RSA key
    rogue_priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    forged_sig = jwt.encode(claims, rogue_priv, algorithm="RS256", headers={"kid": "k1"})
    with pytest.raises(AuthorizationError):
        provider.authenticate(forged_sig)

    # 4. Payload tampering after valid signature
    valid = jwt.encode(claims, priv, algorithm="RS256", headers={"kid": "k1"})
    hdr, _, sig = valid.split(".")
    tampered_claims = {**claims, "sub": "admin"}
    tampered = f"{hdr}.{_b64json(tampered_claims)}.{sig}"
    with pytest.raises(AuthorizationError):
        provider.authenticate(tampered)

    # 5. Symmetric HS256 key-confusion attempt using RSA public key bytes
    hs_header = _b64json({"alg": "HS256", "kid": "k1", "typ": "JWT"})
    hs_body = _b64json(claims)
    signing_input = f"{hs_header}.{hs_body}".encode("ascii")
    hs_sig = (
        base64.urlsafe_b64encode(hmac.new(pub_pem, signing_input, hashlib.sha256).digest())
        .rstrip(b"=")
        .decode("ascii")
    )
    hs256_confused = f"{hs_header}.{hs_body}.{hs_sig}"
    with pytest.raises(AuthorizationError):
        provider.authenticate(hs256_confused)
