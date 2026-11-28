"""Offline OIDC / JWT bearer authenticator backed by a local JWKS file (T-19, ADR-0011)."""

from __future__ import annotations

import importlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pydantic import Field, field_validator

from backend.auth.policies import RolePolicy
from backend.core.contracts import AuthContext, Contract
from backend.core.errors import AuthorizationError, ConfigError


def _load_jwt() -> Any:
    try:
        return importlib.import_module("jwt")
    except ImportError as exc:
        raise ConfigError(
            "OIDC doğrulaması için 'pyjwt[crypto]' paketi gereklidir (pip install -e \".[oidc]\")."
        ) from exc


_ALLOWED_ASYMMETRIC_ALGS: frozenset[str] = frozenset(
    {
        "RS256",
        "RS384",
        "RS512",
        "ES256",
        "ES384",
        "ES512",
        "PS256",
        "PS384",
        "PS512",
        "EdDSA",
    }
)


class OIDCConfig(Contract):
    """Configuration for offline OIDC JWT verification against a local JWKS file."""

    issuer: str = Field(min_length=1)
    audience: str = Field(min_length=1)
    jwks_path: str = Field(min_length=1)
    algorithms: tuple[str, ...] = ("RS256", "ES256")
    role_claim: str = "roles"
    user_claim: str = "sub"
    tenant_claim: str = "tenant_id"
    default_tenant: str | None = None
    leeway_seconds: int = Field(default=30, ge=0, le=300)

    @field_validator("algorithms")
    @classmethod
    def _validate_algorithms(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value:
            raise ValueError("en az bir asimetrik JWT algoritması tanımlanmalıdır")
        for alg in value:
            if alg not in _ALLOWED_ASYMMETRIC_ALGS:
                raise ValueError(
                    f"güvensiz veya desteklenmeyen JWT algoritması: {alg!r}; "
                    f"yalnızca {sorted(_ALLOWED_ASYMMETRIC_ALGS)} izinli"
                )
        return value


def _extract_claim(payload: Mapping[str, Any], claim_path: str) -> Any:
    current: Any = payload
    for part in claim_path.split("."):
        if isinstance(current, Mapping) and part in current:
            current = current[part]
        else:
            return None
    return current


def _extract_roles(raw: Any) -> tuple[str, ...]:
    if raw is None:
        return ()
    if isinstance(raw, str):
        parts = [p.strip().lower() for p in raw.replace(",", " ").split() if p.strip()]
        return tuple(parts)
    if isinstance(raw, (list, tuple, set, frozenset)):
        out: list[str] = []
        for item in raw:
            if isinstance(item, str) and item.strip():
                out.append(item.strip().lower())
        return tuple(out)
    return ()


def _merge_contexts(contexts: list[AuthContext], roles: frozenset[str]) -> AuthContext:
    first = contexts[0]
    if len(contexts) == 1:
        return first.model_copy(update={"roles": roles})
    allowed = frozenset().union(*(c.allowed_tables for c in contexts))
    denied = frozenset().union(*(c.denied_columns for c in contexts))
    max_rows = min(c.max_rows for c in contexts)
    return AuthContext(
        user_id=first.user_id,
        tenant_id=first.tenant_id,
        roles=roles,
        allowed_tables=allowed,
        denied_columns=denied,
        max_rows=max_rows,
    )


class OIDCAuthProvider:
    """Offline OIDC/JWT token verifier using local JWKS + TOML role policies.

    Never makes runtime HTTP requests (ADR-0002). Implements the same
    ``authenticate(token) -> AuthContext`` interface as :class:`StaticAuthProvider`.
    """

    def __init__(
        self,
        config: OIDCConfig,
        policies: Mapping[str, RolePolicy],
    ) -> None:
        self._config = config
        self._policies = {k.strip().lower(): v for k, v in policies.items()}
        self._keys: tuple[Any, ...] = self._load_jwks(Path(config.jwks_path))

    @staticmethod
    def _load_jwks(path: Path) -> tuple[Any, ...]:
        jwt_mod = _load_jwt()
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ConfigError("yerel JWKS dosyası okunamadı") from exc
        if not isinstance(raw, dict) or not raw.get("keys"):
            raise ConfigError("JWKS dosyasında geçerli anahtar kümesi bulunamadı")
        try:
            key_set = jwt_mod.PyJWKSet.from_dict(raw)
        except Exception as exc:
            raise ConfigError("JWKS anahtarları ayrıştırılamadı") from exc
        if not key_set.keys:
            raise ConfigError("JWKS dosyası boş")
        return tuple(key_set.keys)

    def _select_signing_key(self, kid: str | None) -> Any:
        if kid:
            for key in self._keys:
                if key.key_id == kid:
                    return key
            raise AuthorizationError("bilinmeyen OIDC imza anahtarı")
        if len(self._keys) == 1:
            return self._keys[0]
        raise AuthorizationError("OIDC belirtecinde anahtar kimliği (kid) eksik")

    def authenticate(self, token: str | None) -> AuthContext:
        if not token or not token.strip():
            raise AuthorizationError("kimlik doğrulama gerekli")
        raw_token = token.strip()
        jwt_mod = _load_jwt()
        jwt_err: type[Exception] = jwt_mod.PyJWTError

        try:
            header = jwt_mod.get_unverified_header(raw_token)
        except jwt_err as exc:
            raise AuthorizationError("geçersiz OIDC belirteç başlığı") from exc

        alg = header.get("alg")
        if not isinstance(alg, str) or alg == "none" or alg not in self._config.algorithms:
            raise AuthorizationError("desteklenmeyen veya güvensiz OIDC imza algoritması")

        kid = header.get("kid")
        jwk = self._select_signing_key(kid if isinstance(kid, str) and kid else None)

        try:
            payload: dict[str, Any] = jwt_mod.decode(
                raw_token,
                key=jwk.key,
                algorithms=list(self._config.algorithms),
                audience=self._config.audience,
                issuer=self._config.issuer,
                leeway=self._config.leeway_seconds,
                options={
                    "require": ["exp", "iss", "aud", self._config.user_claim],
                    "verify_signature": True,
                    "verify_exp": True,
                    "verify_nbf": True,
                    "verify_iss": True,
                    "verify_aud": True,
                },
            )
        except jwt_err as exc:
            raise AuthorizationError("geçersiz veya süresi dolmuş OIDC belirteci") from exc

        raw_user = _extract_claim(payload, self._config.user_claim)
        if not isinstance(raw_user, str) or not raw_user.strip():
            raise AuthorizationError("OIDC belirtecinde kullanıcı kimliği eksik")
        user_id = raw_user.strip()

        raw_tenant = _extract_claim(payload, self._config.tenant_claim)
        tenant_id = (
            raw_tenant.strip()
            if isinstance(raw_tenant, str) and raw_tenant.strip()
            else self._config.default_tenant
        )
        if not tenant_id:
            raise AuthorizationError("OIDC belirtecinde kiracı kimliği eksik")

        raw_roles = _extract_claim(payload, self._config.role_claim)
        if not raw_roles and "realm_access" in payload:
            raw_roles = _extract_claim(payload, "realm_access.roles")
        role_names = _extract_roles(raw_roles)
        if not role_names:
            raise AuthorizationError("OIDC belirtecinde yetkili rol bulunamadı")

        matched_contexts: list[AuthContext] = []
        matched_roles: set[str] = set()
        for rname in role_names:
            policy = self._policies.get(rname)
            if policy is not None:
                matched_contexts.append(policy.to_auth_context(user_id=user_id, tenant_id=tenant_id))
                matched_roles.add(rname)

        if not matched_contexts:
            raise AuthorizationError("bilinmeyen veya tanımsız OIDC rolü")

        return _merge_contexts(matched_contexts, frozenset(matched_roles))
