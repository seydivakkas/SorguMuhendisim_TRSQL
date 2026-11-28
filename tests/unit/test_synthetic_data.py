"""Unit tests for synthetic_data schemas, tr_TR populator, dataset, and generator."""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

import pytest

from synthetic_data import (
    COMPLEXITY_TIERS,
    PHRASING_STYLES,
    POSTGRES_SCHEMA_PATH,
    SQLITE_SCHEMA_PATH,
    DisjointSplitError,
    LicenseComplianceError,
    SyntheticSQLGenerator,
    build_disjoint_training_db,
    compute_file_sha256,
    create_test_suite_dbs,
    export_enterprise_dataset_jsonl,
    get_enterprise_dataset,
    get_security_attacks,
    get_table_counts,
    populate_sqlite,
    validate_disjoint_dbs,
    validate_source_license,
    verify_enterprise_dataset,
)

TURKISH_DIACRITICS = set("İıŞşĞğÜüÖöÇç")
REQUIRED_CITIES = {"İstanbul", "Trabzon", "Ankara", "İzmir", "Iğdır", "Şanlıurfa"}
EXPECTED_CROSS_LINGUAL_TABLES = {"cust_loyalty", "inv_ledger", "prod_pricing_hist", "wh_stock_snap"}


def _sqlite_tables(conn: sqlite3.Connection) -> set[str]:
    return {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
    }


def test_erp_schemas_define_at_least_26_matching_tables(tmp_path: Path) -> None:
    pg_sql = POSTGRES_SCHEMA_PATH.read_text(encoding="utf-8")
    sqlite_sql = SQLITE_SCHEMA_PATH.read_text(encoding="utf-8")

    assert 'COLLATE "tr-TR-x-icu"' in pg_sql
    pg_tables = set(re.findall(r"CREATE TABLE IF NOT EXISTS\s+([a-zA-Z0-9_]+)", pg_sql))
    sqlite_ddl_tables = set(re.findall(r"CREATE TABLE IF NOT EXISTS\s+([a-zA-Z0-9_]+)", sqlite_sql))

    assert len(pg_tables) >= 26
    assert pg_tables == sqlite_ddl_tables
    assert EXPECTED_CROSS_LINGUAL_TABLES.issubset(pg_tables)
    assert "maaslar" in pg_tables

    db_file = tmp_path / "schema_only.sqlite"
    conn = sqlite3.connect(db_file)
    try:
        conn.executescript(sqlite_sql)
        loaded_tables = _sqlite_tables(conn)
    finally:
        conn.close()
    assert loaded_tables == sqlite_ddl_tables


def test_populate_is_deterministic_and_uses_turkish_and_fictitious_pii(tmp_path: Path) -> None:
    db_a = populate_sqlite(tmp_path / "a.sqlite", seed=1)
    db_b = populate_sqlite(tmp_path / "b.sqlite", seed=1)

    conn_a = sqlite3.connect(db_a)
    conn_b = sqlite3.connect(db_b)
    try:
        counts_a = get_table_counts(conn_a)
        counts_b = get_table_counts(conn_b)
        assert counts_a == counts_b
        assert all(count > 0 for count in counts_a.values())

        dealer_cities = {r[0] for r in conn_a.execute("SELECT sehir FROM bayiler")}
        customer_cities = {r[0] for r in conn_a.execute("SELECT sehir FROM musteriler")}
        assert REQUIRED_CITIES.issubset(dealer_cities | customer_cities)
        assert REQUIRED_CITIES.issubset(customer_cities)

        all_text = " ".join(
            str(val)
            for tbl in ("bolgeler", "bayiler", "musteriler", "urunler", "kategoriler", "departmanlar")
            for row in conn_a.execute(f"SELECT * FROM {tbl}")
            for val in row
            if isinstance(val, str)
        )
        assert TURKISH_DIACRITICS.issubset(set(all_text))

        # Strictly invalid TCKN & IBAN & .invalid email
        tckns = [r[0] for r in conn_a.execute("SELECT tckn FROM musteriler")]
        tckns += [r[0] for r in conn_a.execute("SELECT tckn FROM calisanlar")]
        assert all(t.startswith("00") and len(t) == 11 and t.isdigit() for t in tckns)

        ibans = [r[0] for r in conn_a.execute("SELECT iban FROM odemeler")]
        ibans += [r[0] for r in conn_a.execute("SELECT iban FROM maaslar")]
        assert all(ib.startswith("TR00") and len(ib) == 26 for ib in ibans)

        emails = [r[0] for r in conn_a.execute("SELECT eposta FROM musteriler")]
        assert all(em.endswith(".invalid") for em in emails)

        orders_a = conn_a.execute(
            "SELECT siparis_no, toplam_tutar FROM siparisler ORDER BY siparis_id"
        ).fetchall()
        orders_b = conn_b.execute(
            "SELECT siparis_no, toplam_tutar FROM siparisler ORDER BY siparis_id"
        ).fetchall()
        assert orders_a == orders_b
    finally:
        conn_a.close()
        conn_b.close()


def test_create_test_suite_dbs_generates_distinct_mutated_instances(tmp_path: Path) -> None:
    db_paths = create_test_suite_dbs(tmp_path / "suite", seeds=(1, 2, 3))
    assert len(db_paths) == 3
    hashes = {compute_file_sha256(p) for p in db_paths}
    assert len(hashes) == 3

    revenues: list[float] = []
    customer_counts: list[int] = []
    for p in db_paths:
        conn = sqlite3.connect(p)
        try:
            rev = conn.execute("SELECT ROUND(SUM(toplam_tutar), 2) FROM siparisler").fetchone()[0]
            cnt = conn.execute("SELECT COUNT(*) FROM musteriler").fetchone()[0]
            revenues.append(float(rev))
            customer_counts.append(int(cnt))
        finally:
            conn.close()
    assert len(set(revenues)) == 3
    assert len(set(customer_counts)) == 3


def test_enterprise_dataset_splits_and_100_percent_sql_verification(tmp_path: Path) -> None:
    dataset = get_enterprise_dataset()
    attacks = get_security_attacks()

    assert len(dataset) == 160
    assert len(attacks) == 30

    by_cat: dict[str, int] = {}
    for item in dataset:
        by_cat[item.category] = by_cat.get(item.category, 0) + 1
    assert by_cat == {
        "normal": 96,
        "business_rule": 24,
        "ambiguous": 24,
        "unanswerable": 16,
    }

    assert any(item.cross_lingual for item in dataset)
    rule_tags = {rule for item in dataset for rule in item.business_rules}
    assert {"kdv_haric_net_ciro", "iade_dusumu", "vadesi_gecmis_borc", "aktif_musteri"}.issubset(rule_tags)

    report = verify_enterprise_dataset(seeds=(1, 2, 3))
    assert report.passed, f"Verification failures: errors={report.errors}, empty={report.empty_ids}"
    assert report.total_items == 160
    assert report.total_answerable == 120
    assert report.executed_ok == 360
    assert report.non_empty == 360
    assert report.deterministic

    ds_jsonl, atk_jsonl = export_enterprise_dataset_jsonl(tmp_path / "exports")
    assert len(ds_jsonl.read_text(encoding="utf-8").strip().splitlines()) == 160
    atk_lines = atk_jsonl.read_text(encoding="utf-8").strip().splitlines()
    assert len(atk_lines) == 30
    first_atk = json.loads(atk_lines[0])
    assert first_atk["expected_outcome"] == "rejected"


def test_synthetic_sql_generator_tiers_filtering_phrasings_and_hooks(tmp_path: Path) -> None:
    eval_db = populate_sqlite(tmp_path / "enterprise_eval.sqlite", seed=1)
    eval_hash = compute_file_sha256(eval_db)
    train_db, _ = build_disjoint_training_db(
        tmp_path / "synthetic_train.sqlite",
        seed=101,
        eval_db_hashes=[eval_hash],
    )

    gen = SyntheticSQLGenerator(
        train_db,
        db_id="synthetic_train_erp",
        eval_db_hashes=[eval_hash],
        seed=7,
    )

    # Filtering removes syntax errors, writes, and empty-result queries
    filtered = gen.filter_candidates(
        [
            "SELEC * FROM bayiler",
            "DROP TABLE bayiler",
            "SELECT bayi_adi FROM bayiler WHERE sehir = 'OlmayanSehirXYZ'",
            "SELECT bayi_adi FROM bayiler WHERE sehir = 'Trabzon'",
        ]
    )
    assert len(filtered) == 1
    assert filtered[0][0] == "SELECT bayi_adi FROM bayiler WHERE sehir = 'Trabzon'"

    for tier in COMPLEXITY_TIERS:
        samples = gen.generate(tier, count=4)
        assert len(samples) >= 2, f"Expected samples for tier {tier}"
        for sample in samples:
            assert sample.complexity == tier
            assert sample.row_count > 0
            assert len(sample.preview_rows) > 0
            assert sample.consistency_passed
            assert set(sample.phrasings.keys()) == set(PHRASING_STYLES)
            assert "maaslar" not in sample.tables_used

    # Custom back-translation hook using isolated DB execution
    def mock_back_translator(question: str, _schema: object) -> str:
        _ = question
        return "SELECT bayi_adi FROM bayiler ORDER BY bayi_adi LIMIT 10"

    gen_hook = SyntheticSQLGenerator(
        train_db, db_id="synthetic_train_hook", back_translator=mock_back_translator
    )
    ok_res = gen_hook.check_back_translation_consistency(
        "SELECT bayi_adi FROM bayiler ORDER BY bayi_adi LIMIT 10",
        "Bayileri listeleyiniz.",
        gen_hook._synthesize_specs("easy", target=1)[0],
    )
    assert ok_res.consistent
    assert ok_res.method == "execution"
    assert ok_res.score == 1.0


def test_synthetic_generator_enforces_adr0009_licensing_and_disjoint_dbs(tmp_path: Path) -> None:
    with pytest.raises(LicenseComplianceError):
        validate_source_license("BIRDTurk dev", "cc-by-sa-4.0")

    with pytest.raises(LicenseComplianceError):
        validate_source_license("custom_corpus", "cc-by-nc-sa-4.0")

    with pytest.raises(LicenseComplianceError):
        validate_source_license("qwen_distill", "qwen-research")

    with pytest.raises(DisjointSplitError):
        validate_disjoint_dbs("birdturk_dev")

    eval_db = populate_sqlite(tmp_path / "eval.sqlite", seed=1)
    eval_hash = compute_file_sha256(eval_db)

    with pytest.raises(LicenseComplianceError):
        SyntheticSQLGenerator(
            eval_db, db_id="train_ok", source_name="birdturk", source_license="cc-by-nc-sa-4.0"
        )

    with pytest.raises(DisjointSplitError):
        SyntheticSQLGenerator(eval_db, db_id="enterprise_eval")

    with pytest.raises(DisjointSplitError):
        SyntheticSQLGenerator(eval_db, db_id="train_distinct_name", eval_db_hashes=[eval_hash])
