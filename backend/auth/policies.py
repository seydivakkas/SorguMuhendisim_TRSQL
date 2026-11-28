"""Role policy TOML loader and constant-time hashed bearer token provider."""

from __future__ import annotations

import hashlib
import hmac
import re
import tomllib
from collections.abc import Mapping
from pathlib import Path

from pydantic import Field, ValidationError, field_validator

from backend.auth.provider import StaticAuthProvider
from backend.core.contracts import AuthContext, Contract
from backend.core.errors import AuthorizationError, ConfigError

DEFAULT_PII_DENIED_COLUMNS: frozenset[str] = frozenset(
    {
        "tc_kimlik_no",
        "telefon",
        "eposta",
        "iban",
    }
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def hash_token(token: str) -> str:
    """Return the lowercase SHA-256 hex digest of a bearer token."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class RolePolicy(Contract):
    """Access policy parsed from a ``security_policies/*.toml`` file."""

    role: str = Field(min_length=1)
    allowed_tables: tuple[str, ...] = ()
    denied_columns: tuple[str, ...] = ()
    max_rows: int = Field(default=1000, gt=0, le=100_000)
    tenant: str | None = None
    rls: dict[str, str] = Field(default_factory=dict)

    @field_validator("role", mode="before")
    @classmethod
    def _norm_role(cls, value: object) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("role must be a non-empty string")
        return value.strip().lower()

    @field_validator("allowed_tables", "denied_columns", mode="before")
    @classmethod
    def _norm_identifiers(cls, value: object) -> tuple[str, ...]:
        if value is None:
            return ()
        if not isinstance(value, (list, tuple)):
            raise ValueError("identifier list must be an array")
        items: list[str] = []
        for entry in value:
            if not isinstance(entry, str) or not entry.strip():
                raise ValueError("identifier entries must be non-empty strings")
            items.append(entry.strip().lower())
        return tuple(items)

    def to_auth_context(self, user_id: str, tenant_id: str | None = None) -> AuthContext:
        """Materialize an :class:`AuthContext` for a user carrying this role."""
        clean_user = user_id.strip()
        if not clean_user:
            raise AuthorizationError("kullanıcı kimliği gerekli")
        clean_tenant = tenant_id.strip() if tenant_id else None
        if self.tenant is not None and clean_tenant is not None and clean_tenant != self.tenant:
            raise AuthorizationError("kiracı eşleşmedi")
        effective_tenant = clean_tenant or self.tenant
        if not effective_tenant:
            raise AuthorizationError("kiracı kimliği gerekli")

        allowed = frozenset(self.allowed_tables)
        denied: set[str] = set(self.denied_columns)
        bare_denied = {col for col in self.denied_columns if "." not in col} | set(DEFAULT_PII_DENIED_COLUMNS)
        denied.update(bare_denied)
        for table in allowed:
            for col in bare_denied:
                denied.add(f"{table}.{col}")

        return AuthContext(
            user_id=clean_user,
            tenant_id=effective_tenant,
            roles=frozenset({self.role}),
            allowed_tables=allowed,
            denied_columns=frozenset(denied),
            max_rows=self.max_rows,
        )


class TokenRecord(Contract):
    """Single entry parsed from ``TRSQL_TOKENS_FILE`` (no plaintext tokens)."""

    token_hash: str
    user_id: str = Field(min_length=1)
    role: str = Field(min_length=1)
    tenant: str = Field(min_length=1)

    @field_validator("token_hash", mode="before")
    @classmethod
    def _validate_digest(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("token hash must be a string")
        clean = value.strip().lower()
        if not _SHA256_RE.fullmatch(clean):
            raise ValueError("token dosyası yalnızca 64 karakterli SHA-256 özeti içermelidir")
        return clean

    @field_validator("role", mode="before")
    @classmethod
    def _norm_role(cls, value: object) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("role must be non-empty")
        return value.strip().lower()


def load_role_policies(
    directory: str | Path,
    *,
    include_examples: bool = False,
) -> dict[str, RolePolicy]:
    """Load role policy TOML files from ``directory``.

    By default ``*.example.toml`` templates are ignored so copying an example
    to ``<role>.toml`` never causes duplicate role collisions.
    """
    base = Path(directory)
    if not base.is_dir():
        raise ConfigError("rol politikası dizini bulunamadı")

    policies: dict[str, RolePolicy] = {}
    for path in sorted(base.glob("*.toml")):
        if not include_examples and path.name.endswith(".example.toml"):
            continue
        try:
            raw = tomllib.loads(path.read_text(encoding="utf-8"))
            policy = RolePolicy.model_validate(raw)
        except (OSError, tomllib.TOMLDecodeError, ValidationError) as exc:
            raise ConfigError(f"geçersiz rol politikası dosyası: {path.name}") from exc
        if policy.role in policies:
            raise ConfigError(f"tekrarlanan rol politikası: {policy.role}")
        policies[policy.role] = policy
    return policies


def load_token_records(path: str | Path) -> tuple[TokenRecord, ...]:
    """Parse ``TRSQL_TOKENS_FILE`` lines of ``sha256:user_id:role:tenant``."""
    token_path = Path(path)
    try:
        content = token_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError("token dosyası okunamadı") from exc

    records: list[TokenRecord] = []
    seen_hashes: set[str] = set()
    for line_no, raw_line in enumerate(content.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split(":")] if ":" in line else line.split()
        if len(parts) != 4 or any(not part for part in parts):
            raise ConfigError(f"token dosyası satır biçimi geçersiz: satır {line_no}")
        try:
            record = TokenRecord(
                token_hash=parts[0],
                user_id=parts[1],
                role=parts[2],
                tenant=parts[3],
            )
        except ValidationError as exc:
            raise ConfigError(f"token dosyası satırı geçersiz: satır {line_no}") from exc
        if record.token_hash in seen_hashes:
            raise ConfigError("token dosyasında tekrarlanan token özeti")
        seen_hashes.add(record.token_hash)
        records.append(record)
    return tuple(records)


class HashedTokenAuthProvider(StaticAuthProvider):
    """Bearer token authenticator comparing SHA-256 digests in constant time.

    Plaintext bearer tokens are never stored in memory or on disk.
    """

    def __init__(self, hashed_tokens: Mapping[str, AuthContext]) -> None:
        normalized: dict[str, AuthContext] = {}
        for digest, ctx in hashed_tokens.items():
            clean = digest.strip().lower()
            if not _SHA256_RE.fullmatch(clean):
                raise ConfigError("geçersiz token özeti biçimi")
            if clean in normalized:
                raise ConfigError("tekrarlanan token özeti")
            normalized[clean] = ctx
        super().__init__(normalized)

    def authenticate(self, token: str | None) -> AuthContext:
        if not token:
            raise AuthorizationError("kimlik doğrulama gerekli")
        candidate_digest = hash_token(token).encode("ascii")
        for known_digest, ctx in self._tokens.items():
            if hmac.compare_digest(known_digest.encode("ascii"), candidate_digest):
                return ctx
        raise AuthorizationError("geçersiz kimlik bilgisi")

    @classmethod
    def from_files(
        cls,
        tokens_path: str | Path,
        policies: Mapping[str, RolePolicy],
    ) -> HashedTokenAuthProvider:
        records = load_token_records(tokens_path)
        contexts: dict[str, AuthContext] = {}
        for rec in records:
            policy = policies.get(rec.role)
            if policy is None:
                raise AuthorizationError(f"bilinmeyen rol: {rec.role}")
            contexts[rec.token_hash] = policy.to_auth_context(
                user_id=rec.user_id,
                tenant_id=rec.tenant,
            )
        return cls(contexts)


def load_auth_provider(
    tokens_path: str | Path | None = None,
    policies_dir: str | Path | None = None,
    *,
    include_examples: bool = False,
) -> HashedTokenAuthProvider:
    """Build a fail-closed :class:`HashedTokenAuthProvider` from files.

    When ``tokens_path`` is ``None``, returns an empty provider that rejects
    every token. When ``policies_dir`` is also provided, its TOML files are
    still validated on startup so broken configs fail fast.
    """
    policies: dict[str, RolePolicy] = {}
    if policies_dir is not None:
        policies = load_role_policies(policies_dir, include_examples=include_examples)
    if tokens_path is None:
        return HashedTokenAuthProvider({})
    resolved_dir = policies_dir if policies_dir is not None else Path("security_policies")
    if policies_dir is None:
        policies = load_role_policies(resolved_dir, include_examples=include_examples)
    return HashedTokenAuthProvider.from_files(tokens_path, policies)
