from __future__ import annotations

from pathlib import Path

import pytest

from backend.auth import scope_schema
from backend.core.config import RagSettings
from backend.core.contracts import (
    AuthContext,
    BusinessRule,
    ColumnInfo,
    Dialect,
    FewShotExample,
    Intent,
    Mention,
    MentionKind,
    ParsedQuestion,
    SchemaSnapshot,
    SortDirection,
    TableInfo,
)
from backend.core.ports import EmbeddingAdapter
from backend.knowledge_base import (
    InMemoryKnowledgeBase,
    MetadataEntry,
    load_knowledge_base,
    tr_casefold,
)
from backend.rag import (
    BM25Retriever,
    DenseRetriever,
    DeterministicHashEmbedder,
    HybridKnowledgeRetriever,
    KeywordRetriever,
    MinHashLSHIndex,
    OkapiBM25,
    ValueLinker,
    levenshtein_distance,
    mask_sql_literals_and_identifiers,
    reciprocal_rank_fusion,
    skeleton_similarity,
)


def _pq(
    text: str,
    *,
    intent: Intent = Intent.LOOKUP,
    mentions: tuple[Mention, ...] = (),
    sort: SortDirection | None = None,
    limit: int | None = None,
) -> ParsedQuestion:
    return ParsedQuestion(
        original_text=text,
        normalized_text=tr_casefold(text),
        intent=intent,
        mentions=mentions,
        sort=sort,
        limit=limit,
    )


def _sample_kb() -> InMemoryKnowledgeBase:
    return InMemoryKnowledgeBase(
        rules=(
            BusinessRule(
                rule_id="R-001",
                term="geçerli sipariş",
                definition="İptal edilmemiş satış kayıtları",
                sql_fragment="sales.status <> 'cancelled'",
                source="policy",
                approved=True,
            ),
            BusinessRule(
                rule_id="R-002",
                term="aktif müşteri",
                definition="Son 90 günde alışveriş yapan müşteri",
                sql_fragment="customers.last_purchase_date >= CURRENT_DATE - INTERVAL '90 days'",
                source="policy",
                approved=True,
            ),
            BusinessRule(
                rule_id="R-999",
                term="taslak gizli satış kuralı",
                definition="Onaysız taslak kural asla dönmemeli",
                sql_fragment="1 = 0",
                source="draft",
                approved=False,
            ),
        ),
        examples=(
            FewShotExample(
                question="Trabzon'daki bayiler hangileri?",
                sql="SELECT name FROM dealers WHERE city = 'Trabzon'",
                dialect=Dialect.SQLITE,
            ),
            FewShotExample(
                question="En çok satış yapan 5 bayi hangileri?",
                sql=(
                    "SELECT d.name, SUM(s.total_amount - s.return_amount) AS net_sales "
                    "FROM dealers d JOIN sales s ON s.dealer_id = d.dealer_id "
                    "GROUP BY d.name ORDER BY net_sales DESC LIMIT 5"
                ),
                dialect=Dialect.SQLITE,
            ),
            FewShotExample(
                question="Toplam bayi sayısı kaçtır?",
                sql="SELECT COUNT(*) FROM dealers",
                dialect=Dialect.POSTGRES,
            ),
        ),
        metadata=(
            MetadataEntry(
                entry_id="M-001",
                table="sales",
                column="status",
                description="Sipariş ve satış durum kodu",
                code_values=(("completed", "tamamlandı"), ("cancelled", "iptal")),
                synonyms=("durum", "statü"),
                approved=True,
            ),
            MetadataEntry(
                entry_id="M-002",
                table="sales",
                column="total_amount",
                description="Brüt satış tutarı",
                unit="TRY",
                synonyms=("tutar", "ciro"),
                approved=True,
            ),
            MetadataEntry(
                entry_id="M-003",
                table="salaries",
                column="amount",
                description="Çalışan maaş tutarı",
                unit="TRY",
                approved=True,
            ),
            MetadataEntry(
                entry_id="M-999",
                table="sales",
                column="internal_flag",
                description="Onaysız gizli durum",
                approved=False,
            ),
        ),
    )


def test_keyword_retriever_backward_compatible_and_excludes_unapproved() -> None:
    kb = _sample_kb()
    retriever = KeywordRetriever(kb)
    rules = retriever.rules(_pq("iptal satış taslak gizli kuralı"))
    assert [r.rule_id for r in rules] == ["R-001"]
    assert all(r.approved for r in rules)

    examples = retriever.examples(_pq("Trabzon bayiler"))
    assert len(examples) == 1
    assert "Trabzon" in examples[0].question


def test_bm25_excludes_unapproved_rules_and_matches_turkish_inflections() -> None:
    kb = _sample_kb()
    retriever = BM25Retriever(kb)

    rules = retriever.rules(_pq("Siparişlerin iptal durumu ve taslak gizli satış kuralı"))
    assert [r.rule_id for r in rules] == ["R-001"]
    assert all(r.approved for r in rules)

    bm25 = OkapiBM25(["Trabzon şehrindeki bayiler", "Ankara merkez depo"])
    scores = bm25.score("Trabzon'daki bayiler")
    assert scores[0] > scores[1]


def test_bm25_schema_elements_and_metadata_respect_rbac(schema: SchemaSnapshot, analyst: AuthContext) -> None:
    kb = _sample_kb()
    scoped = scope_schema(schema, analyst)
    retriever = BM25Retriever(kb, schema=scoped)

    elems = retriever.schema_elements(_pq("dealers city sales total_amount"), schema=scoped)
    names = {e.qualified_name for e in elems}
    assert any(n.startswith("dealers") or n.startswith("sales") for n in names)
    assert all(not n.startswith("salaries") for n in names)
    assert "dealers.tax_number" not in names

    described_schema = SchemaSnapshot(
        dialect=Dialect.SQLITE,
        tables=(
            TableInfo(
                name="dealers",
                description="Bayi ve şube bilgileri",
                columns=(
                    ColumnInfo(name="city", data_type="TEXT", description="Bayi şehir bilgisi"),
                    ColumnInfo(name="tax_number", data_type="TEXT", description="Vergi numarası"),
                ),
            ),
            TableInfo(
                name="sales",
                description="Satış hareketleri",
                columns=(ColumnInfo(name="total_amount", data_type="REAL", description="Brüt satış tutarı"),),
            ),
            TableInfo(
                name="salaries",
                description="Çalışan maaş tutarları",
                columns=(ColumnInfo(name="amount", data_type="REAL", description="Maaş tutarı"),),
            ),
        ),
    )
    scoped_desc = scope_schema(described_schema, analyst)
    tr_elems = retriever.schema_elements(_pq("bayi şehir satış tutarı ve maaş"), schema=scoped_desc)
    tr_names = {e.qualified_name for e in tr_elems}
    assert "dealers.city" in tr_names
    assert "sales.total_amount" in tr_names
    assert all(not n.startswith("salaries") for n in tr_names)
    assert "dealers.tax_number" not in tr_names

    meta = retriever.metadata(_pq("satış durum iptal veya maaş"), allowed_tables=scoped.table_names)
    meta_ids = [m.entry_id for m in meta]
    assert "M-001" in meta_ids
    assert "M-003" not in meta_ids
    assert "M-999" not in meta_ids


def test_load_knowledge_base_parses_metadata_toml(tmp_path: Path) -> None:
    toml_path = tmp_path / "kb.toml"
    toml_path.write_text(
        """
[[rules]]
rule_id = "R-1"
term = "geçerli"
definition = "iptal değil"
source = "test"
approved = true

[[metadata]]
entry_id = "M-1"
table = "sales"
column = "status"
description = "Durum kodu"
unit = "kod"
synonyms = ["statü"]
code_mappings = { "3" = "iptal", "1" = "onaylı" }
""",
        encoding="utf-8",
    )
    kb = load_knowledge_base(toml_path)
    assert len(kb.approved_rules()) == 1
    assert len(kb.approved_metadata()) == 1
    assert kb.metadata[0].code_map == {"3": "iptal", "1": "onaylı"}


def test_dail_sql_masked_skeleton_similarity() -> None:
    sql_a = "SELECT name FROM dealers WHERE city = 'Trabzon'"
    sql_b = "SELECT branch_name FROM branches WHERE region = 'Ankara'"
    sql_c = (
        "SELECT d.name, SUM(s.total_amount) AS total FROM dealers d "
        "JOIN sales s ON s.dealer_id = d.dealer_id GROUP BY d.name ORDER BY total DESC LIMIT 5"
    )
    skel_a = mask_sql_literals_and_identifiers(sql_a)
    skel_b = mask_sql_literals_and_identifiers(sql_b)
    assert skel_a == "SELECT <COL> FROM <TAB> WHERE <COL> = <VAL>"
    assert skel_a == skel_b
    assert skeleton_similarity(sql_a, sql_b) == 1.0
    assert skeleton_similarity(sql_a, sql_c) < 0.7

    kb = _sample_kb()
    retriever = BM25Retriever(kb)
    candidate = (
        "SELECT c.full_name, SUM(o.amount) AS rev FROM customers c "
        "JOIN orders o ON o.cid = c.cid GROUP BY c.full_name ORDER BY rev DESC LIMIT 10"
    )
    ranked = retriever.examples(_pq("müşteri listesi"), candidate_sql=candidate)
    assert ranked
    assert "LIMIT 5" in ranked[0].sql


def test_dense_retriever_with_injected_and_hash_embedder(
    schema: SchemaSnapshot, analyst: AuthContext
) -> None:
    kb = _sample_kb()
    hash_embedder = DeterministicHashEmbedder(dim=128)
    assert isinstance(hash_embedder, EmbeddingAdapter)

    dense = DenseRetriever(kb, hash_embedder, use_faiss=False)
    rules = dense.rules(_pq("son 90 günde alışveriş yapan aktif müşteri"))
    assert rules and rules[0].rule_id == "R-002"
    assert all(r.approved for r in rules)

    class KeywordVectorEmbedder:
        def embed(self, texts: list[str]) -> list[list[float]]:
            vecs: list[list[float]] = []
            for t in texts:
                low = t.lower()
                vecs.append(
                    [
                        1.0 if "müşteri" in low or "90" in low else 0.0,
                        1.0 if "iptal" in low or "durum" in low else 0.0,
                        1.0 if "trabzon" in low or "bayi" in low else 0.0,
                    ]
                )
            return vecs

    custom_dense = DenseRetriever(kb, KeywordVectorEmbedder(), use_faiss=False)
    scoped = scope_schema(schema, analyst)
    assert custom_dense.rules(_pq("aktif müşteri"))[0].rule_id == "R-002"
    assert custom_dense.examples(_pq("Trabzon bayileri"))[0].question == "Trabzon'daki bayiler hangileri?"
    meta = custom_dense.metadata(_pq("iptal durum"), allowed_tables=scoped.table_names)
    assert meta and meta[0].entry_id == "M-001"
    elems = custom_dense.schema_elements(_pq("bayi"), schema=scoped)
    assert all(not e.table.startswith("salaries") for e in elems)


def test_reciprocal_rank_fusion_and_hybrid_ablation_flags(
    schema: SchemaSnapshot, analyst: AuthContext
) -> None:
    fused = reciprocal_rank_fusion(
        [["doc_a", "doc_b", "doc_c"], ["doc_b", "doc_d", "doc_a"]],
        weights=[0.5, 0.5],
        k=60,
    )
    assert fused[0][0] in {"doc_a", "doc_b"}
    assert dict(fused)["doc_b"] > dict(fused)["doc_c"]

    with pytest.raises(ValueError):
        reciprocal_rank_fusion([["a"]], k=0)
    with pytest.raises(ValueError):
        reciprocal_rank_fusion([["a"], ["b"]], weights=[1.0])

    kb = _sample_kb()
    scoped = scope_schema(schema, analyst)
    linker = ValueLinker()
    linker.index_column("dealers", "city", ["Trabzon", "İstanbul", "Ankara"])

    q = _pq(
        "İstanbul'daki bayilerin iptal olmayan satışları",
        intent=Intent.RANKING,
        sort=SortDirection.DESC,
        limit=5,
        mentions=(Mention(text="İstanbul'daki", kind=MentionKind.LOCATION, lemma="istanbul"),),
    )

    full = HybridKnowledgeRetriever(
        kb,
        embedder=DeterministicHashEmbedder(),
        value_linker=linker,
        settings=RagSettings(),
        schema=scoped,
    )
    res_full = full.retrieve(q, schema=scoped, denied_columns=analyst.denied_columns)
    assert res_full.rules and all(r.approved for r in res_full.rules)
    assert res_full.examples
    assert res_full.schema_elements
    assert res_full.value_matches and res_full.value_matches[0].matched_value == "İstanbul"

    ctx = full.to_knowledge_context(q)
    assert ctx.rules == res_full.rules

    # D3 leave-one-out ablation flags
    no_rule = HybridKnowledgeRetriever(
        kb,
        embedder=DeterministicHashEmbedder(),
        value_linker=linker,
        settings=RagSettings(enable_rule_rag=False),
    )
    assert no_rule.retrieve(q, schema=scoped).rules == ()

    no_example = HybridKnowledgeRetriever(
        kb,
        embedder=DeterministicHashEmbedder(),
        value_linker=linker,
        settings=RagSettings(enable_example_rag=False),
    )
    assert no_example.retrieve(q, schema=scoped).examples == ()

    no_schema = HybridKnowledgeRetriever(
        kb,
        embedder=DeterministicHashEmbedder(),
        value_linker=linker,
        settings=RagSettings(enable_schema_rag=False),
    )
    assert no_schema.retrieve(q, schema=scoped).schema_elements == ()

    no_val = HybridKnowledgeRetriever(
        kb,
        embedder=DeterministicHashEmbedder(),
        value_linker=linker,
        settings=RagSettings(enable_value_linking=False),
    )
    assert no_val.retrieve(q, schema=scoped).value_matches == ()


def test_value_linker_turkish_inflections_typos_and_pii_exclusion() -> None:
    assert levenshtein_distance("istanbul", "istanbl") == 1

    lsh = MinHashLSHIndex(num_perm=64, bands=32)
    lsh.add(0, "istanbul")
    assert 0 in lsh.query("istanbl")

    linker = ValueLinker(min_similarity=0.72)
    added_cities = linker.index_column(
        "dealers",
        "city",
        ["İstanbul", "Trabzon", "Iğdır", "Şanlıurfa", "Mardin", "Burdur", "Isparta"],
    )
    assert added_cities == 7

    # Auto-detected PII columns must NEVER be indexed
    assert linker.index_column("dealers", "tax_number", ["1111111111", "2222222222"]) == 0
    assert linker.index_column("customers", "tckn", ["99999999999"]) == 0
    assert linker.index_column("employees", "salary", ["50000"]) == 0
    # Explicit denied_columns must also block indexing
    assert (
        linker.index_column(
            "dealers",
            "secret_code",
            ["OZEL123"],
            denied_columns=frozenset({"dealers.secret_code"}),
        )
        == 0
    )

    # Apostrophe inflection ("İstanbul'daki" -> "İstanbul")
    m1 = linker.link(_pq("İstanbul'daki bayiler hangileri?"))
    assert m1 and m1[0].matched_value == "İstanbul"
    assert m1[0].edit_distance == 0

    # Turkish capital I/ı ("Iğdır'dan" -> "Iğdır")
    m2 = linker.link(_pq("Iğdır'dan gelen siparişler"))
    assert m2 and m2[0].matched_value == "Iğdır"
    assert m2[0].edit_distance == 0

    # Non-apostrophe attached suffix + ASCII fallback + proper nouns ending in suffix-like letters
    m3 = linker.link(_pq("sanliurfadaki ve mardindeki şubeler"))
    matched_vals = {m.matched_value for m in m3}
    assert {"Şanlıurfa", "Mardin"}.issubset(matched_vals)

    # Typo tolerance via LSH + Levenshtein
    m4 = linker.link(_pq("İstanbl'daki satışlar"))
    assert m4 and m4[0].matched_value == "İstanbul"
    assert m4[0].edit_distance == 1

    # PII values never match; query-time denied_columns also blocks indexed columns
    assert linker.link(_pq("1111111111 vergi numaralı bayi")) == ()
    assert (
        linker.link(
            _pq("İstanbul'daki bayiler"),
            denied_columns=frozenset({"dealers.city"}),
        )
        == ()
    )
    assert (
        linker.link(
            _pq("İstanbul'daki bayiler"),
            allowed_tables=frozenset({"sales"}),
        )
        == ()
    )
