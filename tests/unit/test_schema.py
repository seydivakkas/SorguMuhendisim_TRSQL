from __future__ import annotations

from datetime import date

from backend.auth import scope_schema
from backend.core.contracts import (
    AuthContext,
    ColumnInfo,
    Dialect,
    ForeignKey,
    Intent,
    Mention,
    MentionKind,
    ParsedQuestion,
    SchemaSnapshot,
    TableInfo,
)
from backend.schema_intelligence import SchemaGraph
from backend.schema_linking import (
    HybridSchemaLinker,
    estimate_schema_tokens,
    select_schema_within_budget,
)
from backend.turkish_nlp import RuleBasedTurkishParser
from tests.conftest import LOCATIONS, NLP_LEXICON, SCHEMA_LEXICON


def _build_5hop_erp_schema() -> SchemaSnapshot:
    return SchemaSnapshot(
        dialect=Dialect.SQLITE,
        tables=(
            TableInfo(
                name="regions",
                description="coğrafi bölgeler",
                columns=(
                    ColumnInfo(name="region_id", data_type="INTEGER", is_primary_key=True),
                    ColumnInfo(name="region_name", data_type="TEXT", description="bölge adı"),
                    ColumnInfo(name="internal_code", data_type="TEXT", description="dahili kod"),
                ),
            ),
            TableInfo(
                name="dealers",
                description="bayiler",
                columns=(
                    ColumnInfo(name="dealer_id", data_type="INTEGER", is_primary_key=True),
                    ColumnInfo(name="region_id", data_type="INTEGER", nullable=False),
                    ColumnInfo(name="dealer_name", data_type="TEXT", description="bayi adı"),
                    ColumnInfo(name="city", data_type="TEXT", description="şehir"),
                    ColumnInfo(name="tax_number", data_type="TEXT", description="vergi no"),
                ),
                foreign_keys=(ForeignKey(column="region_id", ref_table="regions", ref_column="region_id"),),
            ),
            TableInfo(
                name="orders",
                description="siparişler",
                columns=(
                    ColumnInfo(name="order_id", data_type="INTEGER", is_primary_key=True),
                    ColumnInfo(name="dealer_id", data_type="INTEGER", nullable=False),
                    ColumnInfo(name="order_date", data_type="TEXT", description="sipariş tarihi"),
                    ColumnInfo(name="notes", data_type="TEXT", description="açıklama notu"),
                ),
                foreign_keys=(ForeignKey(column="dealer_id", ref_table="dealers", ref_column="dealer_id"),),
            ),
            TableInfo(
                name="order_items",
                description="sipariş kalemleri",
                columns=(
                    ColumnInfo(name="item_id", data_type="INTEGER", is_primary_key=True),
                    ColumnInfo(name="order_id", data_type="INTEGER", nullable=False),
                    ColumnInfo(name="product_id", data_type="INTEGER", nullable=False),
                    ColumnInfo(name="quantity", data_type="INTEGER", description="miktar adet"),
                    ColumnInfo(name="line_total", data_type="REAL", description="satış tutarı"),
                ),
                foreign_keys=(
                    ForeignKey(column="order_id", ref_table="orders", ref_column="order_id"),
                    ForeignKey(column="product_id", ref_table="products", ref_column="product_id"),
                ),
            ),
            TableInfo(
                name="products",
                description="ürünler",
                columns=(
                    ColumnInfo(name="product_id", data_type="INTEGER", is_primary_key=True),
                    ColumnInfo(name="category_id", data_type="INTEGER", nullable=False),
                    ColumnInfo(name="product_name", data_type="TEXT", description="ürün adı"),
                    ColumnInfo(name="barcode", data_type="TEXT", description="barkod"),
                ),
                foreign_keys=(
                    ForeignKey(column="category_id", ref_table="categories", ref_column="category_id"),
                ),
            ),
            TableInfo(
                name="categories",
                description="kategoriler",
                columns=(
                    ColumnInfo(name="category_id", data_type="INTEGER", is_primary_key=True),
                    ColumnInfo(name="category_name", data_type="TEXT", description="kategori adı"),
                ),
            ),
            TableInfo(
                name="cust_loyalty",
                description="müşteri sadakat puanı",
                columns=(
                    ColumnInfo(name="cust_id", data_type="INTEGER", is_primary_key=True),
                    ColumnInfo(name="points", data_type="INTEGER", description="puan"),
                ),
            ),
            TableInfo(
                name="salaries",
                description="maaşlar",
                columns=(
                    ColumnInfo(name="employee_id", data_type="INTEGER", is_primary_key=True),
                    ColumnInfo(name="amount", data_type="REAL"),
                ),
            ),
        ),
    )


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


def test_three_plus_hop_steiner_join_and_neighborhood() -> None:
    erp = _build_5hop_erp_schema()
    graph = SchemaGraph(erp)

    # 4-hop chain: regions <-> dealers <-> orders <-> order_items <-> products
    path = graph.connect(("regions", "products"))
    assert path is not None and len(path) == 4
    touched = {step.left_table for step in path} | {step.right_table for step in path}
    assert touched == {"regions", "dealers", "orders", "order_items", "products"}

    # Multi-terminal Steiner tree across 5 hops
    multi = graph.connect(("regions", "order_items", "categories"))
    assert multi is not None and len(multi) == 5
    assert graph.connected_tables(("regions", "categories")) == (
        "regions",
        "categories",
        "dealers",
        "orders",
        "order_items",
        "products",
    )

    assert graph.neighborhood(("orders",), hops=0) == ("orders",)
    assert set(graph.neighborhood(("orders",), hops=1)) == {"orders", "dealers", "order_items"}
    assert set(graph.neighborhood(("orders",), hops=2)) == {
        "orders",
        "dealers",
        "order_items",
        "regions",
        "products",
    }

    # Hiding an intermediate bridge table breaks connectivity
    auth_no_orders = AuthContext(
        user_id="u",
        tenant_id="t",
        allowed_tables=frozenset({"regions", "dealers", "order_items", "products"}),
    )
    scoped = scope_schema(erp, auth_no_orders)
    assert SchemaGraph(scoped).connect(("regions", "products")) is None


def test_hybrid_linker_morphology_fuzzy_and_steiner_repair() -> None:
    erp = _build_5hop_erp_schema()
    auth = AuthContext(
        user_id="u-analyst",
        tenant_id="t-demo",
        allowed_tables=frozenset(
            {"regions", "dealers", "orders", "order_items", "products", "categories", "cust_loyalty"}
        ),
        denied_columns=frozenset({"dealers.tax_number"}),
    )
    scoped = scope_schema(erp, auth)

    parsed = ParsedQuestion(
        original_text="Bölgelere göre ürünlerimizin satış tutarı nedir?",
        normalized_text="bölgelere göre ürünlerimizin satış tutarı nedir",
        intent=Intent.AGGREGATE,
        mentions=(
            Mention(text="bölgelere", kind=MentionKind.ENTITY, lemma="bölge"),
            Mention(text="ürünlerimizin", kind=MentionKind.ENTITY, lemma="ürün"),
        ),
    )
    linker = HybridSchemaLinker(top_k_tables=3)
    linked = linker.link(parsed, scoped)

    assert "regions" in linked.tables
    assert "products" in linked.tables
    # Intermediate Steiner bridge tables must be added automatically
    assert {"dealers", "orders", "order_items"}.issubset(set(linked.tables))
    assert len(linked.join_path) >= 4
    # RBAC strictly respected
    assert "salaries" not in linked.tables
    assert all(lnk.column != "tax_number" for lnk in linked.links)

    # Cross-lingual & fuzzy typo match ("müsteri" -> cust_loyalty.cust_id)
    cust_q = ParsedQuestion(
        original_text="Müsteri sadakat puanı",
        normalized_text="müsteri sadakat puanı",
        intent=Intent.LOOKUP,
    )
    cust_linked = linker.link(cust_q, scoped)
    assert "cust_loyalty" in cust_linked.tables


def test_hybrid_linker_with_embedder_and_bidirectional_mode(
    schema: SchemaSnapshot,
    analyst: AuthContext,
) -> None:
    scoped = scope_schema(schema, analyst)

    class _FakeEmbedder:
        def embed(self, texts: list[str]) -> list[list[float]]:
            vecs: list[list[float]] = []
            for t in texts:
                low = t.lower()
                vecs.append(
                    [
                        1.0
                        if ("bayi" in low or "dealer" in low or "trabzon" in low or "city" in low)
                        else 0.1,
                        1.0 if ("sat" in low or "sale" in low or "ciro" in low or "amount" in low) else 0.1,
                        1.0 if "salar" in low else 0.0,
                    ]
                )
            return vecs

    parser = RuleBasedTurkishParser(NLP_LEXICON, LOCATIONS, today=lambda: date(2026, 11, 27))
    parsed = parser.parse("Geçen ay Trabzon'daki en çok satış yapan beş bayimiz hangileri?")
    linker = HybridSchemaLinker(
        {**SCHEMA_LEXICON, "gizli_maas": "salaries.amount"},
        embedder=_FakeEmbedder(),
    )
    bi = linker.link_bidirectional(parsed, scoped)

    assert set(bi.merged.tables) == {"dealers", "sales"}
    assert "salaries" not in bi.merged.tables
    assert len(bi.merged.join_path) == 1
    assert bi.agreement > 0.0

    # Even when embedder knows "salaries", RBAC-scoped schema never leaks it
    salary_q = ParsedQuestion(
        original_text="Çalışan maaşları toplamı",
        normalized_text="çalışan maaşları toplamı",
        intent=Intent.AGGREGATE,
    )
    salary_linked = linker.link(salary_q, scoped)
    assert "salaries" not in salary_linked.tables


def test_kasla_budget_pruning_preserves_join_keys() -> None:
    erp = _build_5hop_erp_schema()
    scoped = scope_schema(
        erp,
        AuthContext(
            user_id="u",
            tenant_id="t",
            allowed_tables=frozenset(
                {"regions", "dealers", "orders", "order_items", "products", "categories", "cust_loyalty"}
            ),
        ),
    )
    parsed = ParsedQuestion(
        original_text="Bölgelere göre ürün satış tutarı",
        normalized_text="bölgelere göre ürün satış tutarı",
        intent=Intent.AGGREGATE,
        mentions=(
            Mention(text="bölgelere", kind=MentionKind.ENTITY, lemma="bölge"),
            Mention(text="ürün", kind=MentionKind.ENTITY, lemma="ürün"),
            Mention(text="satış", kind=MentionKind.METRIC, lemma="satış"),
        ),
    )
    linked = HybridSchemaLinker(top_k_tables=4).link(parsed, scoped)
    full_tokens = estimate_schema_tokens(scoped)
    # Tight budget smaller than the full 7-table schema
    budget = max(180, int(full_tokens * 0.65))
    pruned = select_schema_within_budget(scoped, linked, max_tokens=budget)

    assert estimate_schema_tokens(pruned) <= budget
    assert pruned.table("cust_loyalty") is None  # unrelated table pruned
    for req_table in ("regions", "dealers", "orders", "order_items", "products"):
        t = pruned.table(req_table)
        assert t is not None
        # Primary keys preserved
        assert any(c.is_primary_key for c in t.columns)
    # Foreign keys needed for join_path preserved and no dangling FKs remain
    orders_tbl = pruned.table("orders")
    assert orders_tbl is not None and orders_tbl.column("dealer_id") is not None
    kept_names = pruned.table_names
    for tbl in pruned.tables:
        for fk in tbl.foreign_keys:
            assert fk.ref_table.lower() in kept_names
            assert tbl.column(fk.column) is not None
