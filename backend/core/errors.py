"""Error hierarchy. Messages shown to end users must be Turkish and must not
leak schema details the user is not authorized to see."""

from __future__ import annotations


class TRSQLError(Exception):
    """Base class for all TRSQL errors."""


class ConfigError(TRSQLError):
    pass


class AuthorizationError(TRSQLError):
    """The user may not access the requested resource."""


class SecurityViolation(TRSQLError):
    """A candidate query violated a security rule. Never retried (ADR-0005)."""


class ExecutionError(TRSQLError):
    """The database rejected or aborted an approved query (timeout, etc.)."""
