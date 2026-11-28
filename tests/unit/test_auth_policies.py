from __future__ import annotations

from pathlib import Path

import pytest

from backend.auth import (
    DEFAULT_PII_DENIED_COLUMNS,
    HashedTokenAuthProvider,
    RolePolicy,
    hash_token,
    load_auth_provider,
    load_role_policies,
    load_token_records,
    scope_schema,
)
from backend.core.contracts import SchemaSnapshot
from backend.core.errors import AuthorizationError, ConfigError


def _write_policy(directory: Path, name: str, body: str) -> Path:
    path = directory / name
    path.write_text(body, encoding="utf-8")
    return path


def test_load_role_policies_parses_toml_and_enforces_default_pii(tmp_path: Path) -> None:
    _write_policy(
        tmp_path,
        "analyst.toml",
        """
role = "Analyst"
allowed_tables = ["Dealers", "Sales"]
denied_columns = ["dealers.tax_number"]
max_rows = 250
tenant = "t-demo"
""",
    )
    policies = load_role_policies(tmp_path)
    assert set(policies) == {"analyst"}
    policy = policies["analyst"]
    assert isinstance(policy, RolePolicy)
    ctx = policy.to_auth_context(user_id="u-1")
    assert ctx.user_id == "u-1"
    assert ctx.tenant_id == "t-demo"
    assert ctx.allowed_tables == frozenset({"dealers", "sales"})
    assert ctx.max_rows == 250
    assert "dealers.tax_number" in ctx.denied_columns
    for pii_col in DEFAULT_PII_DENIED_COLUMNS:
        assert pii_col in ctx.denied_columns
        assert f"dealers.{pii_col}" in ctx.denied_columns
        assert f"sales.{pii_col}" in ctx.denied_columns


def test_load_role_policies_skips_examples_by_default(tmp_path: Path) -> None:
    _write_policy(
        tmp_path,
        "analyst.example.toml",
        'role = "analyst"\nallowed_tables = ["dealers"]\n',
    )
    assert load_role_policies(tmp_path) == {}
    assert set(load_role_policies(tmp_path, include_examples=True)) == {"analyst"}


def test_empty_allowed_tables_results_in_empty_scoped_schema(tmp_path: Path, schema: SchemaSnapshot) -> None:
    _write_policy(
        tmp_path,
        "empty.toml",
        """
role = "guest"
allowed_tables = []
tenant = "t-demo"
""",
    )
    policy = load_role_policies(tmp_path)["guest"]
    ctx = policy.to_auth_context(user_id="u-guest")
    scoped = scope_schema(schema, ctx)
    assert scoped.tables == ()


def test_malformed_toml_and_duplicate_roles_raise_config_error(tmp_path: Path) -> None:
    _write_policy(tmp_path, "broken.toml", "role = [unclosed")
    with pytest.raises(ConfigError):
        load_role_policies(tmp_path)

    (tmp_path / "broken.toml").unlink()
    _write_policy(tmp_path, "a.toml", 'role = "analyst"\nallowed_tables = ["dealers"]\n')
    _write_policy(tmp_path, "b.toml", 'role = "analyst"\nallowed_tables = ["sales"]\n')
    with pytest.raises(ConfigError):
        load_role_policies(tmp_path)


def test_hashed_token_provider_authenticates_and_rejects_bad_tokens(tmp_path: Path) -> None:
    _write_policy(
        tmp_path,
        "analyst.toml",
        'role = "analyst"\nallowed_tables = ["dealers"]\nmax_rows = 500\n',
    )
    tokens_file = tmp_path / "tokens.txt"
    bearer_value = "trsql-demo-bearer-01"
    tokens_file.write_text(
        f"# sha256:user_id:role:tenant\n{hash_token(bearer_value)}:u-1:analyst:t-demo\n",
        encoding="utf-8",
    )

    provider = load_auth_provider(tokens_path=tokens_file, policies_dir=tmp_path)
    assert isinstance(provider, HashedTokenAuthProvider)
    ctx = provider.authenticate(bearer_value)
    assert ctx.user_id == "u-1"
    assert ctx.tenant_id == "t-demo"
    assert ctx.allowed_tables == frozenset({"dealers"})

    with pytest.raises(AuthorizationError):
        provider.authenticate("wrong-value")
    with pytest.raises(AuthorizationError):
        provider.authenticate(None)
    # Must never authenticate with the SHA-256 hex digest itself as the bearer token.
    with pytest.raises(AuthorizationError):
        provider.authenticate(hash_token(bearer_value))


def test_unknown_role_in_tokens_file_raises_authorization_error(tmp_path: Path) -> None:
    _write_policy(tmp_path, "analyst.toml", 'role = "analyst"\nallowed_tables = ["dealers"]\n')
    tokens_file = tmp_path / "tokens.txt"
    tokens_file.write_text(
        f"{hash_token('t1')}:u-1:nonexistent_role:t-demo\n",
        encoding="utf-8",
    )
    with pytest.raises(AuthorizationError):
        load_auth_provider(tokens_path=tokens_file, policies_dir=tmp_path)


def test_duplicate_or_plaintext_tokens_raise_config_error(tmp_path: Path) -> None:
    digest = hash_token("dup-token")
    dup_file = tmp_path / "dup.txt"
    dup_file.write_text(
        f"{digest}:u-1:analyst:t-demo\n{digest}:u-2:analyst:t-demo\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError):
        load_token_records(dup_file)

    plain_file = tmp_path / "plain.txt"
    plain_file.write_text("my-plaintext-token:u-1:analyst:t-demo\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_token_records(plain_file)


def test_load_auth_provider_without_tokens_file_is_fail_closed(tmp_path: Path) -> None:
    provider = load_auth_provider(tokens_path=None, policies_dir=tmp_path)
    with pytest.raises(AuthorizationError):
        provider.authenticate("any-token")
