from backend.auth import scope_schema
from backend.core.contracts import AuthContext, SchemaSnapshot
from backend.schema_intelligence import SchemaGraph


def test_scope_hides_tables_and_columns(schema: SchemaSnapshot, analyst: AuthContext) -> None:
    scoped = scope_schema(schema, analyst)
    assert scoped.table_names == {"dealers", "sales"}
    dealers = scoped.table("dealers")
    assert dealers is not None and dealers.column("tax_number") is None


def test_scope_drops_fks_to_hidden_tables(schema: SchemaSnapshot) -> None:
    only_sales = AuthContext(user_id="u", tenant_id="t", allowed_tables=frozenset({"sales"}))
    sales = scope_schema(schema, only_sales).table("sales")
    assert sales is not None and sales.foreign_keys == ()


def test_empty_permissions_see_nothing(schema: SchemaSnapshot) -> None:
    nobody = AuthContext(user_id="u", tenant_id="t", allowed_tables=frozenset())
    assert scope_schema(schema, nobody).tables == ()


def test_join_path(schema: SchemaSnapshot) -> None:
    path = SchemaGraph(schema).connect(("dealers", "sales"))
    assert path is not None and len(path) == 1
    assert {path[0].left_table, path[0].right_table} == {"dealers", "sales"}
    assert SchemaGraph(schema).connect(("dealers", "salaries")) is None
