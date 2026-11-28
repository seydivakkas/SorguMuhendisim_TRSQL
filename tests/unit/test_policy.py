from collections.abc import Callable

from backend.core.config import ExecutionSettings
from backend.core.contracts import AuthContext, SchemaSnapshot, SQLCandidate
from backend.policy_engine import PolicyEngine
from backend.sql_validator import SQLValidator


def approve(sql: str, schema: SchemaSnapshot, auth: AuthContext, make: Callable[[str], SQLCandidate]) -> str:
    report = SQLValidator().validate(make(sql), schema, auth)
    return PolicyEngine(ExecutionSettings(max_rows=1000)).approve(report, auth).sql


def test_limit_added(
    schema: SchemaSnapshot, analyst: AuthContext, candidate: Callable[[str], SQLCandidate]
) -> None:
    assert approve("SELECT name FROM dealers", schema, analyst, candidate).endswith("LIMIT 100")


def test_limit_capped(
    schema: SchemaSnapshot, analyst: AuthContext, candidate: Callable[[str], SQLCandidate]
) -> None:
    assert approve("SELECT name FROM dealers LIMIT 5000", schema, analyst, candidate).endswith("LIMIT 100")


def test_smaller_limit_kept(
    schema: SchemaSnapshot, analyst: AuthContext, candidate: Callable[[str], SQLCandidate]
) -> None:
    assert approve("SELECT name FROM dealers LIMIT 5", schema, analyst, candidate).endswith("LIMIT 5")
