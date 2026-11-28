from __future__ import annotations

import hmac
from collections.abc import Mapping

from backend.core.contracts import AuthContext
from backend.core.errors import AuthorizationError


class StaticAuthProvider:
    """Maps opaque bearer tokens to :class:`AuthContext` objects.

    For development and tests only. Production authentication (OIDC/LDAP)
    is decided in AR-07 and must implement the same ``authenticate`` method.
    """

    def __init__(self, tokens: Mapping[str, AuthContext]) -> None:
        self._tokens = dict(tokens)

    def authenticate(self, token: str | None) -> AuthContext:
        if not token:
            raise AuthorizationError("kimlik doğrulama gerekli")
        for known, ctx in self._tokens.items():
            if hmac.compare_digest(known.encode(), token.encode()):
                return ctx
        raise AuthorizationError("geçersiz kimlik bilgisi")
