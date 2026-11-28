"""L1 rate limiting, request size validation, and tenant/connection ownership checks."""

from __future__ import annotations

import math
import threading
import time
from collections import deque
from collections.abc import Callable, Collection, Mapping

from backend.core.config import AuthSettings
from backend.core.contracts import AuthContext
from backend.core.errors import AuthorizationError, TRSQLError


class RateLimitExceededError(TRSQLError):
    """Raised when a user/tenant exceeds their sliding-window request quota."""

    def __init__(self, retry_after_seconds: int = 60) -> None:
        self.retry_after_seconds = max(1, retry_after_seconds)
        super().__init__("İstek limiti aşıldı; lütfen daha sonra tekrar deneyin.")


class RequestTooLargeError(TRSQLError):
    """Raised when an incoming request payload or question exceeds size bounds."""


class RateLimiter:
    """Thread-safe sliding-window rate limiter keyed by ``tenant_id:user_id``."""

    def __init__(
        self,
        settings: AuthSettings | None = None,
        *,
        limit_per_minute: int | None = None,
        window_seconds: float = 60.0,
        clock: Callable[[], float] | None = None,
    ) -> None:
        effective = (
            limit_per_minute
            if limit_per_minute is not None
            else (settings or AuthSettings()).rate_limit_per_minute
        )
        if effective <= 0:
            raise ValueError("limit_per_minute must be positive")
        if window_seconds <= 0.0:
            raise ValueError("window_seconds must be positive")
        self._limit = effective
        self._window = window_seconds
        self._clock = clock or time.monotonic
        self._lock = threading.Lock()
        self._buckets: dict[str, deque[float]] = {}

    @property
    def limit_per_minute(self) -> int:
        return self._limit

    @staticmethod
    def key_for(auth: AuthContext) -> str:
        return f"{auth.tenant_id}:{auth.user_id}"

    def check(self, key: str) -> tuple[bool, int]:
        """Check and consume one slot for ``key``.

        Returns ``(allowed, value)`` where ``value`` is remaining quota when
        ``allowed=True`` or ``retry_after_seconds`` when ``allowed=False``.
        """
        now = self._clock()
        cutoff = now - self._window
        with self._lock:
            bucket = self._buckets.setdefault(key, deque())
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) >= self._limit:
                oldest = bucket[0]
                retry_after = max(1, math.ceil((oldest + self._window) - now))
                return False, retry_after
            bucket.append(now)
            return True, self._limit - len(bucket)

    def check_auth(self, auth: AuthContext) -> tuple[bool, int]:
        """Apply sliding-window rate limiting per ``(tenant_id, user_id)``."""
        return self.check(self.key_for(auth))

    def enforce(self, auth: AuthContext) -> int:
        """Consume one request slot or raise :class:`RateLimitExceededError`."""
        allowed, value = self.check_auth(auth)
        if not allowed:
            raise RateLimitExceededError(retry_after_seconds=value)
        return value


def validate_request_size(
    question: str,
    *,
    max_question_chars: int = 2000,
    max_payload_bytes: int = 16_384,
    payload_bytes: int | None = None,
) -> None:
    """Validate incoming request byte size and question length."""
    if payload_bytes is not None and payload_bytes > max_payload_bytes:
        raise RequestTooLargeError("İstek boyutu izin verilen sınırı aşıyor.")
    stripped = question.strip()
    if not stripped:
        raise ValueError("Soru metni boş olamaz.")
    if len(question) > max_question_chars:
        raise RequestTooLargeError("Soru uzunluğu izin verilen sınırı aşıyor.")


def check_connection_ownership(
    connection_id: str,
    auth: AuthContext,
    connection_owners: Mapping[str, str | Collection[str]] | None,
) -> None:
    """Ensure ``auth.tenant_id`` owns or is authorized for ``connection_id``.

    When ``connection_owners`` is ``None``, ownership checks are treated as
    unconfigured (backward-compatible dev/test mode).
    """
    if connection_owners is None:
        return
    owner = connection_owners.get(connection_id)
    if owner is None:
        raise AuthorizationError("Bu veritabanı bağlantısına erişim yetkiniz yok.")
    if isinstance(owner, str):
        if owner != auth.tenant_id:
            raise AuthorizationError("Bu veritabanı bağlantısına erişim yetkiniz yok.")
        return
    if auth.tenant_id not in owner:
        raise AuthorizationError("Bu veritabanı bağlantısına erişim yetkiniz yok.")
