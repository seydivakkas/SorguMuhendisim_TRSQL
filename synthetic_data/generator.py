"""OmniSQL-inspired Turkish synthetic SQL & question generator (F8 / AR-06).

Pipeline inspired by OmniSQL (SynSQL-2.5M):
1. Introspect schema & non-PII sample values from an isolated training SQLite DB.
2. Synthesize SQL candidates stratified by complexity tier
   (``easy``, ``medium``, ``hard``, ``nested``).
3. Execute candidates on an isolated read-only SQLite connection; discard any
   syntax error, runtime error, or empty result set.
4. Generate varied Turkish natural-language phrasings (``formal``,
   ``colloquial``, ``abbreviated``) with an optional local LLM hook.
5. Verify round-trip semantic consistency via a pluggable back-translation hook.

Strictly enforces ADR-0009:
- Refuses BIRDTurk and any NC / research-only licensed datasets.
- Enforces disjoint train vs. evaluation database IDs and file hashes.
"""

from __future__ import annotations

import hashlib
import random
import sqlite3
from collections import Counter, deque
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import sqlglot
from sqlglot import exp

from synthetic_data.populate import DEFAULT_REFERENCE_DATE, populate_sqlite

ComplexityTier = Literal["easy", "medium", "hard", "nested"]
PhrasingStyle = Literal["formal", "colloquial", "abbreviated"]

PHRASING_STYLES: tuple[PhrasingStyle, ...] = ("formal", "colloquial", "abbreviated")
COMPLEXITY_TIERS: tuple[ComplexityTier, ...] = ("easy", "medium", "hard", "nested")

FORBIDDEN_SOURCE_TOKENS: frozenset[str] = frozenset({"birdturk", "bird-turk", "qwen-research"})
FORBIDDEN_LICENSE_TOKENS: frozenset[str] = frozenset(
    {
        "cc-by-nc",
        "cc-by-nc-sa",
        "cc-by-nc-sa-4.0",
        "nc",
        "non-commercial",
        "qwen-research",
    }
)
DEFAULT_EVAL_DB_IDS: frozenset[str] = frozenset(
    {
        "birdturk",
        "birdturk_dev",
        "turspider",
        "turspider_dev",
        "enterprise_eval",
        "erp_eval",
    }
)

# Sensitive tables/columns excluded from synthetic training prompt generation (KVKK/RBAC)
_SENSITIVE_TABLES: frozenset[str] = frozenset({"maaslar"})
_SENSITIVE_COLUMNS: frozenset[str] = frozenset(
    {
        "tckn",
        "iban",
        "vergi_no",
        "telefon",
        "eposta",
        "brut_maas",
        "net_maas",
    }
)

_TABLE_TURKISH_LABELS: dict[str, str] = {
    "bolgeler": "bölgeler",
    "bayiler": "bayiler",
    "musteri_segmentleri": "müşteri segmentleri",
    "musteriler": "müşteriler",
    "kategoriler": "ürün kategorileri",
    "urunler": "ürünler",
    "depolar": "depolar",
    "stok_hareketleri": "stok hareketleri",
    "kampanyalar": "kampanyalar",
    "departmanlar": "departmanlar",
    "calisanlar": "çalışanlar",
    "siparisler": "siparişler",
    "siparis_kalemleri": "sipariş kalemleri",
    "iadeler": "iadeler",
    "iade_kalemleri": "iade kalemleri",
    "faturalar": "faturalar",
    "odemeler": "ödemeler",
    "satis_hedefleri": "satış hedefleri",
    "masraflar": "masraflar",
    "tedarikciler": "tedarikçiler",
    "satin_alma_siparisleri": "satın alma siparişleri",
    "sevkiyatlar": "sevkiyatlar",
    "destek_talepleri": "destek talepleri",
    "cust_loyalty": "müşteri sadakat programı",
    "inv_ledger": "fatura defteri",
    "prod_pricing_hist": "ürün fiyat geçmişi",
    "wh_stock_snap": "depo stok özeti",
}

_COLUMN_TURKISH_LABELS: dict[str, str] = {
    "bolge_adi": "bölge adı",
    "bayi_adi": "bayi adı",
    "sehir": "şehir",
    "ilce": "ilçe",
    "segment_adi": "segment adı",
    "ad_soyad": "ad soyad",
    "unvan": "ünvan",
    "kategori_adi": "kategori adı",
    "urun_adi": "ürün adı",
    "birim_fiyat": "birim fiyat",
    "maliyet_fiyati": "maliyet fiyatı",
    "depo_adi": "depo adı",
    "kapasite": "kapasite",
    "hareket_turu": "hareket türü",
    "miktar": "miktar",
    "kampanya_adi": "kampanya adı",
    "departman_adi": "departman adı",
    "butce": "bütçe",
    "durum": "durum",
    "odeme_yontemi": "ödeme yöntemi",
    "toplam_tutar": "toplam tutar",
    "brut_tutar": "brüt tutar",
    "indirim_tutari": "indirim tutarı",
    "kdv_tutari": "KDV tutarı",
    "iade_tutari": "iade tutarı",
    "satir_tutari": "satır tutarı",
    "toplam_iade_tutari": "toplam iade tutarı",
    "kdv_haric_tutar": "KDV hariç tutar",
    "genel_toplam": "genel toplam",
    "odenen_tutar": "ödenen tutar",
    "tutar": "tutar",
    "hedef_tutar": "hedef tutar",
    "gerceklesen_tutar": "gerçekleşen tutar",
    "kredi_limiti": "kredi limiti",
    "tier_code": "sadakat kademesi",
    "pts_bal": "sadakat puanı",
    "inv_amt": "fatura tutarı",
    "ret_qty": "iade adedi",
    "net_bal": "net bakiye",
    "old_prc": "eski fiyat",
    "new_prc": "yeni fiyat",
    "qty_on_hand": "mevcut stok",
    "qty_reserved": "rezerve stok",
    "kargo_firmasi": "kargo firması",
    "tedarikci_adi": "tedarikçi adı",
    "oncelik": "öncelik",
    "neden": "iade nedeni",
    "kategori": "masraf kategorisi",
}

_ALLOWED_SQLITE_ACTIONS = frozenset(
    {
        sqlite3.SQLITE_SELECT,
        sqlite3.SQLITE_READ,
        sqlite3.SQLITE_FUNCTION,
        sqlite3.SQLITE_RECURSIVE,
    }
)


class LicenseComplianceError(ValueError):
    """Raised when an input dataset or source violates ADR-0009 licensing rules."""


class DisjointSplitError(ValueError):
    """Raised when synthetic training data overlaps an evaluation database (ADR-0009)."""


@dataclass(frozen=True)
class IntrospectedColumn:
    """Column metadata and non-PII sample values."""

    name: str
    data_type: str
    is_primary_key: bool
    sample_values: tuple[str, ...] = ()

    @property
    def is_numeric(self) -> bool:
        upper = self.data_type.upper()
        return any(tok in upper for tok in ("INT", "REAL", "NUM", "DEC", "FLOAT", "DOUBLE"))


@dataclass(frozen=True)
class IntrospectedFK:
    """Foreign key relationship from child column to parent table/column."""

    column: str
    ref_table: str
    ref_column: str


@dataclass(frozen=True)
class IntrospectedTable:
    """Table schema representation for candidate synthesis."""

    name: str
    columns: tuple[IntrospectedColumn, ...]
    foreign_keys: tuple[IntrospectedFK, ...] = ()

    @property
    def pk_column(self) -> str:
        for col in self.columns:
            if col.is_primary_key:
                return col.name
        return self.columns[0].name

    def label_column(self) -> str:
        preferred = (
            "bayi_adi",
            "ad_soyad",
            "urun_adi",
            "kategori_adi",
            "bolge_adi",
            "depo_adi",
            "departman_adi",
            "segment_adi",
            "kampanya_adi",
            "tedarikci_adi",
            "kargo_firmasi",
            "konu",
            "neden",
            "tier_code",
            "sehir",
            "durum",
        )
        col_names = {c.name.lower(): c.name for c in self.columns}
        for p in preferred:
            if p in col_names:
                return col_names[p]
        for col in self.columns:
            if not col.is_primary_key and not col.is_numeric and col.name.lower() not in _SENSITIVE_COLUMNS:
                return col.name
        return self.pk_column

    def metric_column(self) -> str | None:
        preferred = (
            "toplam_tutar",
            "satir_tutari",
            "genel_toplam",
            "tutar",
            "birim_fiyat",
            "gerceklesen_tutar",
            "toplam_iade_tutari",
            "inv_amt",
            "net_bal",
            "pts_bal",
            "qty_on_hand",
            "miktar",
            "ret_qty",
            "kapasite",
            "kredi_limiti",
            "butce",
        )
        col_names = {c.name.lower(): c.name for c in self.columns}
        for p in preferred:
            if p in col_names:
                return col_names[p]
        for col in self.columns:
            if (
                col.is_numeric
                and not col.is_primary_key
                and not col.name.lower().endswith("_id")
                and col.name.lower() not in _SENSITIVE_COLUMNS
            ):
                return col.name
        return None


@dataclass(frozen=True)
class IntrospectedSchema:
    """Full SQLite schema snapshot used by :class:`SyntheticSQLGenerator`."""

    db_id: str
    tables: tuple[IntrospectedTable, ...]

    def table(self, name: str) -> IntrospectedTable | None:
        lowered = name.lower()
        return next((t for t in self.tables if t.name.lower() == lowered), None)


@dataclass(frozen=True)
class ConsistencyResult:
    """Result of the back-translation consistency check."""

    consistent: bool
    score: float
    method: Literal["structural", "execution"]
    back_sql: str | None = None
    reason: str = ""


@dataclass(frozen=True)
class SyntheticSQLSample:
    """Verified non-empty synthetic SQL + Turkish phrasing sample."""

    sample_id: str
    db_id: str
    complexity: ComplexityTier
    sql: str
    question: str
    phrasings: dict[PhrasingStyle, str]
    style: PhrasingStyle
    tables_used: tuple[str, ...]
    row_count: int
    preview_rows: tuple[tuple[Any, ...], ...]
    consistency_passed: bool
    consistency_score: float
    source_license: str = "synthetic-proprietary"
    split: str = "train"


@dataclass(frozen=True)
class _SqlSpec:
    complexity: ComplexityTier
    sql: str
    primary_table: str
    joined_tables: tuple[str, ...]
    target_column: str
    aggregate: str | None
    filter_col: str | None
    filter_val: str | None
    limit: int | None


def validate_source_license(source_name: str, license_id: str) -> None:
    """Enforce ADR-0009: forbid BIRDTurk and NC/research-only training sources."""
    src_norm = source_name.strip().lower()
    lic_norm = license_id.strip().lower()
    for token in FORBIDDEN_SOURCE_TOKENS:
        if token in src_norm:
            raise LicenseComplianceError(
                f"ADR-0009 ihlali: '{source_name}' eğitim verisi olarak kullanılamaz."
            )
    for token in FORBIDDEN_LICENSE_TOKENS:
        if token == lic_norm or (len(token) > 2 and token in lic_norm):
            raise LicenseComplianceError(
                f"ADR-0009 ihlali: '{license_id}' lisansı sentetik eğitim üretimi için yasaktır."
            )


def compute_file_sha256(path: str | Path) -> str:
    """Compute SHA-256 hex digest of a database file for split isolation checks."""
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while chunk := handle.read(65536):
            h.update(chunk)
    return h.hexdigest()


def validate_disjoint_dbs(
    train_db_id: str,
    eval_db_ids: Iterable[str] = DEFAULT_EVAL_DB_IDS,
    *,
    train_db_hash: str | None = None,
    eval_db_hashes: Iterable[str] = (),
) -> None:
    """Enforce ADR-0009: training DB must be strictly disjoint from evaluation DBs."""
    norm_train = train_db_id.strip().lower()
    eval_set = {e.strip().lower() for e in eval_db_ids}
    if norm_train in eval_set:
        raise DisjointSplitError(f"ADR-0009 ihlali: '{train_db_id}' değerlendirme veritabanı ile çakışıyor.")
    if train_db_hash is not None and train_db_hash in set(eval_db_hashes):
        raise DisjointSplitError(
            "ADR-0009 ihlali: eğitim veritabanı dosya özeti (SHA-256) değerlendirme DB'si ile aynı."
        )


def build_disjoint_training_db(
    output_path: str | Path,
    *,
    seed: int = 101,
    scale: int = 1,
    eval_db_hashes: Iterable[str] = (),
) -> tuple[Path, str]:
    """Build a dedicated SQLite training DB disjoint from evaluation DBs."""
    path = populate_sqlite(output_path, seed=seed, reference_date=DEFAULT_REFERENCE_DATE, scale=scale)
    digest = compute_file_sha256(path)
    if digest in set(eval_db_hashes):
        raise DisjointSplitError("Üretilen eğitim DB'si değerlendirme DB özeti ile çakıştı.")
    return path, digest


def _ro_authorizer(
    action: int, arg1: str | None, _arg2: str | None, _db: str | None, _src: str | None
) -> int:
    if action in _ALLOWED_SQLITE_ACTIONS:
        if action == sqlite3.SQLITE_READ and arg1 and arg1.lower().startswith("sqlite_"):
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK
    return sqlite3.SQLITE_DENY


def _open_readonly_sqlite(db_path: Path, *, use_authorizer: bool = True) -> sqlite3.Connection:
    conn = sqlite3.connect(f"{db_path.resolve().as_uri()}?mode=ro", uri=True)
    conn.execute("PRAGMA query_only = ON")
    if use_authorizer:
        conn.set_authorizer(_ro_authorizer)
    return conn


def introspect_sqlite_schema(
    db_path: str | Path,
    *,
    db_id: str = "synthetic_train_erp",
    exclude_tables: frozenset[str] = _SENSITIVE_TABLES,
) -> IntrospectedSchema:
    """Read schema metadata and non-PII sample values from an isolated SQLite DB."""
    path = Path(db_path)
    conn = _open_readonly_sqlite(path, use_authorizer=False)
    try:
        table_names = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        tables: list[IntrospectedTable] = []
        for tname in table_names:
            if tname.lower() in exclude_tables:
                continue
            quoted_t = '"' + tname.replace('"', '""') + '"'
            raw_cols = conn.execute(f"PRAGMA table_info({quoted_t})").fetchall()
            raw_fks = conn.execute(f"PRAGMA foreign_key_list({quoted_t})").fetchall()

            fks = tuple(
                IntrospectedFK(column=fk[3], ref_table=fk[2], ref_column=fk[4])
                for fk in raw_fks
                if fk[2].lower() not in exclude_tables
            )
            cols: list[IntrospectedColumn] = []
            for col_row in raw_cols:
                cname = str(col_row[1])
                ctype = str(col_row[2] or "TEXT")
                is_pk = bool(col_row[5])
                samples: tuple[str, ...] = ()
                if (
                    cname.lower() not in _SENSITIVE_COLUMNS
                    and not is_pk
                    and not cname.lower().endswith("_id")
                    and "TEXT" in ctype.upper()
                ):
                    quoted_c = '"' + cname.replace('"', '""') + '"'
                    sample_rows = conn.execute(
                        f"SELECT DISTINCT {quoted_c} FROM {quoted_t} "  # noqa: S608
                        f"WHERE {quoted_c} IS NOT NULL AND {quoted_c} <> '' LIMIT 5"
                    ).fetchall()
                    samples = tuple(str(r[0]) for r in sample_rows if r[0] is not None)
                cols.append(
                    IntrospectedColumn(
                        name=cname,
                        data_type=ctype,
                        is_primary_key=is_pk,
                        sample_values=samples,
                    )
                )
            tables.append(IntrospectedTable(name=tname, columns=tuple(cols), foreign_keys=fks))
        return IntrospectedSchema(db_id=db_id, tables=tuple(tables))
    finally:
        conn.close()


def _tr_table(name: str) -> str:
    return _TABLE_TURKISH_LABELS.get(name.lower(), name.replace("_", " "))


def _tr_col(name: str) -> str:
    return _COLUMN_TURKISH_LABELS.get(name.lower(), name.replace("_", " "))


def _quote_sql_literal(val: str) -> str:
    escaped = val.replace("'", "''")
    return f"'{escaped}'"


class SyntheticSQLGenerator:
    """OmniSQL-inspired synthetic Turkish SQL + question generator with ADR-0009 safety."""

    def __init__(
        self,
        db_path: str | Path,
        *,
        db_id: str = "synthetic_train_erp",
        source_name: str = "synthetic_erp_generator",
        source_license: str = "synthetic-proprietary",
        eval_db_ids: Iterable[str] = DEFAULT_EVAL_DB_IDS,
        eval_db_hashes: Iterable[str] = (),
        seed: int = 42,
        phrasing_fn: Callable[[str, PhrasingStyle, str], str] | None = None,
        back_translator: Callable[[str, IntrospectedSchema], str] | None = None,
    ) -> None:
        validate_source_license(source_name, source_license)
        self._db_path = Path(db_path)
        if not self._db_path.exists():
            raise FileNotFoundError(f"Veritabanı bulunamadı: {self._db_path}")
        self._db_hash = compute_file_sha256(self._db_path)
        validate_disjoint_dbs(
            db_id,
            eval_db_ids=eval_db_ids,
            train_db_hash=self._db_hash,
            eval_db_hashes=eval_db_hashes,
        )
        self._db_id = db_id
        self._source_license = source_license
        self._rng = random.Random(seed)  # noqa: S311
        self._phrasing_fn = phrasing_fn
        self._back_translator = back_translator
        self._schema = introspect_sqlite_schema(self._db_path, db_id=db_id)

    @property
    def schema(self) -> IntrospectedSchema:
        return self._schema

    @property
    def db_hash(self) -> str:
        return self._db_hash

    def execute_isolated(
        self, sql: str, *, max_rows: int = 200
    ) -> tuple[bool, tuple[tuple[Any, ...], ...], str | None]:
        """Execute ``sql`` on an isolated read-only SQLite connection.

        Returns ``(ok, rows, error_message)``. Rejects non-SELECT statements and
        syntax errors before touching SQLite.
        """
        try:
            parsed = sqlglot.parse(sql, read="sqlite")
        except Exception as exc:
            return False, (), f"Parse error: {exc}"
        if len(parsed) != 1 or not isinstance(parsed[0], exp.Query):
            return False, (), "Only single SELECT/WITH queries are allowed"

        conn = _open_readonly_sqlite(self._db_path)
        try:
            cur = conn.execute(sql)
            rows = tuple(tuple(r) for r in cur.fetchmany(max_rows))
            return True, rows, None
        except sqlite3.Error as exc:
            return False, (), str(exc)
        finally:
            conn.close()

    def filter_candidates(
        self, sql_candidates: Sequence[str]
    ) -> list[tuple[str, tuple[tuple[Any, ...], ...]]]:
        """Filter candidate SQLs by execution validity and non-empty result rows."""
        kept: list[tuple[str, tuple[tuple[Any, ...], ...]]] = []
        seen_sql: set[str] = set()
        for raw_sql in sql_candidates:
            normalized = " ".join(raw_sql.split())
            if normalized in seen_sql:
                continue
            ok, rows, _ = self.execute_isolated(raw_sql)
            if ok and rows:
                seen_sql.add(normalized)
                kept.append((raw_sql, rows))
        return kept

    def verbalize_turkish(
        self,
        spec: _SqlSpec,
    ) -> dict[PhrasingStyle, str]:
        """Produce formal, colloquial, and abbreviated Turkish phrasings for a SQL spec."""
        t_label = _tr_table(spec.primary_table)
        j_labels = [_tr_table(t) for t in spec.joined_tables]
        target_label = _tr_col(spec.target_column)

        filter_phrase_formal = ""
        filter_phrase_colloq = ""
        filter_phrase_abbr = ""
        if spec.filter_col and spec.filter_val:
            f_col_lbl = _tr_col(spec.filter_col)
            filter_phrase_formal = f" ({f_col_lbl}: '{spec.filter_val}' koşuluyla)"
            filter_phrase_colloq = f" {spec.filter_val} olanları"
            filter_phrase_abbr = f" [{f_col_lbl}={spec.filter_val}]"

        agg_map_formal = {
            "SUM": f"toplam {target_label} değerini",
            "AVG": f"ortalama {target_label} değerini",
            "COUNT": "kayıt sayısını",
            "MAX": f"en yüksek {target_label} değerini",
        }
        agg_map_colloq = {
            "SUM": f"toplam {target_label} ne kadar",
            "AVG": f"ortalama {target_label} kaç",
            "COUNT": "kaç tane var",
            "MAX": f"en fazla {target_label} kaç",
        }
        agg_map_abbr = {
            "SUM": f"top. {target_label}",
            "AVG": f"ort. {target_label}",
            "COUNT": "adet",
            "MAX": f"maks. {target_label}",
        }

        limit_formal = f" ilk {spec.limit} kaydı" if spec.limit else ""
        limit_colloq = f" ilk {spec.limit} tanesini" if spec.limit else ""
        limit_abbr = f" (ilk {spec.limit})" if spec.limit else ""

        if spec.complexity == "easy":
            if spec.aggregate:
                f_txt = (
                    f"{t_label} tablosundaki{filter_phrase_formal} "
                    f"{agg_map_formal[spec.aggregate]} hesaplayınız."
                )
                c_txt = f"{t_label}{filter_phrase_colloq} için {agg_map_colloq[spec.aggregate]}?"
                a_txt = f"{t_label}: {agg_map_abbr[spec.aggregate]}{filter_phrase_abbr}"
            else:
                f_txt = (
                    f"{t_label} arasından{filter_phrase_formal} "
                    f"{target_label} bilgisini{limit_formal} listeleyiniz."
                )
                c_txt = f"{t_label} içinden{filter_phrase_colloq}{limit_colloq} getirir misin?"
                a_txt = f"{t_label} / {target_label}{filter_phrase_abbr}{limit_abbr}"
        elif spec.complexity == "medium":
            grp_lbl = _tr_table(spec.joined_tables[0]) if spec.joined_tables else t_label
            agg_key = spec.aggregate or "SUM"
            f_txt = (
                f"{grp_lbl} bazında {t_label} kayıtlarının{filter_phrase_formal} "
                f"{agg_map_formal[agg_key]}{limit_formal} büyükten küçüğe sıralayınız."
            )
            c_txt = (
                f"Her bir {grp_lbl} için {t_label} tarafında{filter_phrase_colloq} "
                f"{agg_map_colloq[agg_key]},{limit_colloq} sıralayıp ver."
            )
            a_txt = f"{grp_lbl} x {t_label}: {agg_map_abbr[agg_key]}{filter_phrase_abbr}{limit_abbr}"
        elif spec.complexity == "hard":
            chain_txt = " ve ".join([t_label, *j_labels])
            agg_key = spec.aggregate or "SUM"
            f_txt = (
                f"{chain_txt} tablolarını birleştirerek{filter_phrase_formal} "
                f"{agg_map_formal[agg_key]}{limit_formal} raporlayınız."
            )
            c_txt = (
                f"{chain_txt} verilerini bağlayıp{filter_phrase_colloq} "
                f"{agg_map_colloq[agg_key]}{limit_colloq} çıkarır mısın?"
            )
            a_txt = f"{chain_txt} -> {agg_map_abbr[agg_key]}{filter_phrase_abbr}{limit_abbr}"
        else:  # nested
            grp_lbl = _tr_table(spec.joined_tables[0]) if spec.joined_tables else t_label
            f_txt = (
                f"Genel ortalamanın üzerinde kalan {grp_lbl} kayıtlarını {t_label} "
                f"üzerinden{limit_formal} alt sorgu ile listeleyiniz."
            )
            c_txt = f"Ortalamayı geçen {grp_lbl} hangileri, {t_label} verisine göre{limit_colloq} göster?"
            a_txt = f"ort. üstü {grp_lbl} ({t_label}){limit_abbr}"

        out: dict[PhrasingStyle, str] = {
            "formal": f_txt,
            "colloquial": c_txt,
            "abbreviated": a_txt,
        }
        if self._phrasing_fn is not None:
            for style in PHRASING_STYLES:
                out[style] = self._phrasing_fn(spec.sql, style, out[style])
        return out

    def check_back_translation_consistency(
        self,
        gold_sql: str,
        question: str,
        spec: _SqlSpec,
    ) -> ConsistencyResult:
        """Verify round-trip semantic consistency via hook or structural AST alignment."""
        if self._back_translator is not None:
            back_sql = self._back_translator(question, self._schema)
            ok_gold, gold_rows, _ = self.execute_isolated(gold_sql)
            ok_back, back_rows, err_back = self.execute_isolated(back_sql)
            if not ok_gold or not ok_back:
                return ConsistencyResult(
                    consistent=False,
                    score=0.0,
                    method="execution",
                    back_sql=back_sql,
                    reason=err_back or "Execution failed during back-translation check",
                )
            gold_counter = Counter(gold_rows)
            back_counter = Counter(back_rows)
            consistent = gold_counter == back_counter
            overlap = sum((gold_counter & back_counter).values())
            total = max(sum(gold_counter.values()), sum(back_counter.values()), 1)
            return ConsistencyResult(
                consistent=consistent,
                score=round(overlap / total, 4),
                method="execution",
                back_sql=back_sql,
                reason="Exact result multiset match" if consistent else "Result multiset mismatch",
            )

        # Structural fallback: verify SQL parses cleanly and question reflects tables/filter
        try:
            parsed = sqlglot.parse_one(gold_sql, read="sqlite")
        except Exception as exc:
            return ConsistencyResult(False, 0.0, "structural", reason=str(exc))

        cte_names = {c.alias_or_name.lower() for c in parsed.find_all(exp.CTE)}
        tables_in_sql = {
            t.name.lower() for t in parsed.find_all(exp.Table) if t.name and t.name.lower() not in cte_names
        }
        q_lower = question.lower()
        hits = 0
        checks = 0
        for tbl in tables_in_sql:
            checks += 1
            lbl = _tr_table(tbl).lower()
            if lbl in q_lower or tbl in q_lower or any(part in q_lower for part in lbl.split()):
                hits += 1
        if spec.filter_val:
            checks += 1
            if spec.filter_val.lower() in q_lower:
                hits += 1
        score = round(hits / max(checks, 1), 4)
        return ConsistencyResult(
            consistent=score >= 0.75,
            score=score,
            method="structural",
            back_sql=parsed.sql(dialect="sqlite"),
            reason="Structural SQLGlot + Turkish label alignment",
        )

    def generate(
        self,
        complexity: ComplexityTier,
        *,
        count: int = 10,
        style: PhrasingStyle | None = None,
    ) -> list[SyntheticSQLSample]:
        """Generate up to ``count`` verified, non-empty synthetic samples for ``complexity``."""
        if count <= 0:
            return []
        specs = self._synthesize_specs(complexity, target=max(count * 3, 12))
        samples: list[SyntheticSQLSample] = []
        seen_sql: set[str] = set()

        for spec in specs:
            norm_sql = " ".join(spec.sql.split())
            if norm_sql in seen_sql:
                continue
            ok, rows, _ = self.execute_isolated(spec.sql)
            if not ok or not rows:
                continue

            phrasings = self.verbalize_turkish(spec)
            chosen_style: PhrasingStyle = style or PHRASING_STYLES[len(samples) % len(PHRASING_STYLES)]
            question = phrasings[chosen_style]
            consistency = self.check_back_translation_consistency(spec.sql, question, spec)
            if not consistency.consistent:
                continue

            parsed = sqlglot.parse_one(spec.sql, read="sqlite")
            cte_names = {c.alias_or_name.lower() for c in parsed.find_all(exp.CTE)}
            tables_used = tuple(
                sorted(
                    {
                        t.name.lower()
                        for t in parsed.find_all(exp.Table)
                        if t.name and t.name.lower() not in cte_names
                    }
                )
            )
            seen_sql.add(norm_sql)
            samples.append(
                SyntheticSQLSample(
                    sample_id=f"SYN-{complexity.upper()}-{len(samples) + 1:03d}",
                    db_id=self._db_id,
                    complexity=complexity,
                    sql=spec.sql,
                    question=question,
                    phrasings=phrasings,
                    style=chosen_style,
                    tables_used=tables_used,
                    row_count=len(rows),
                    preview_rows=rows[:5],
                    consistency_passed=consistency.consistent,
                    consistency_score=consistency.score,
                    source_license=self._source_license,
                    split="train",
                )
            )
            if len(samples) >= count:
                break
        return samples

    # ------------------------------------------------------------------ #
    # Internal SQL candidate synthesizers per tier
    # ------------------------------------------------------------------ #

    def _fk_neighbors(self) -> dict[str, list[tuple[str, str, str]]]:
        """Undirected adjacency list: table -> [(neighbor_table, local_col, remote_col)]."""
        adj: dict[str, list[tuple[str, str, str]]] = {t.name: [] for t in self._schema.tables}
        for tbl in self._schema.tables:
            for fk in tbl.foreign_keys:
                if fk.ref_table in adj:
                    adj[tbl.name].append((fk.ref_table, fk.column, fk.ref_column))
                    adj[fk.ref_table].append((tbl.name, fk.ref_column, fk.column))
        return adj

    def _synthesize_specs(self, complexity: ComplexityTier, *, target: int) -> list[_SqlSpec]:
        if complexity == "easy":
            return self._specs_easy(target)
        if complexity == "medium":
            return self._specs_medium(target)
        if complexity == "hard":
            return self._specs_hard(target)
        return self._specs_nested(target)

    def _pick_filter(self, tbl: IntrospectedTable) -> tuple[str | None, str | None]:
        candidates = [
            (col.name, val)
            for col in tbl.columns
            if col.sample_values and col.name.lower() not in _SENSITIVE_COLUMNS
            for val in col.sample_values
        ]
        if not candidates:
            return None, None
        return self._rng.choice(candidates)

    def _specs_easy(self, target: int) -> list[_SqlSpec]:
        specs: list[_SqlSpec] = []
        tables = list(self._schema.tables)
        self._rng.shuffle(tables)
        for tbl in tables:
            label_col = tbl.label_column()
            metric_col = tbl.metric_column()
            fcol, fval = self._pick_filter(tbl)

            # Variant 1: filtered lookup
            where_sql = f" WHERE {fcol} = {_quote_sql_literal(fval)}" if fcol and fval else ""
            limit = 10
            sql_lookup = (
                f"SELECT {label_col} FROM {tbl.name}{where_sql} "  # noqa: S608
                f"ORDER BY {label_col} LIMIT {limit}"
            )
            specs.append(_SqlSpec("easy", sql_lookup, tbl.name, (), label_col, None, fcol, fval, limit))

            # Variant 2: count or sum
            if metric_col:
                agg = self._rng.choice(("SUM", "AVG", "MAX"))
                sql_agg = f"SELECT {agg}({metric_col}) AS sonuc FROM {tbl.name}{where_sql}"  # noqa: S608
                specs.append(_SqlSpec("easy", sql_agg, tbl.name, (), metric_col, agg, fcol, fval, None))
            else:
                sql_cnt = f"SELECT COUNT(*) AS adet FROM {tbl.name}{where_sql}"  # noqa: S608
                specs.append(
                    _SqlSpec("easy", sql_cnt, tbl.name, (), tbl.pk_column, "COUNT", fcol, fval, None)
                )

            if len(specs) >= target:
                break
        return specs

    def _specs_medium(self, target: int) -> list[_SqlSpec]:
        specs: list[_SqlSpec] = []
        tables = list(self._schema.tables)
        self._rng.shuffle(tables)
        for child in tables:
            if not child.foreign_keys:
                continue
            metric = child.metric_column()
            for fk in child.foreign_keys:
                parent = self._schema.table(fk.ref_table)
                if parent is None:
                    continue
                p_label = parent.label_column()
                fcol, fval = self._pick_filter(child)
                where_sql = f" WHERE c.{fcol} = {_quote_sql_literal(fval)}" if fcol and fval else ""
                if metric:
                    agg = "SUM" if len(specs) % 2 == 0 else "AVG"
                    sql = (
                        f"SELECT p.{p_label}, {agg}(c.{metric}) AS deger "  # noqa: S608
                        f"FROM {child.name} c "
                        f"JOIN {parent.name} p ON p.{fk.ref_column} = c.{fk.column}"
                        f"{where_sql} "
                        f"GROUP BY p.{parent.pk_column}, p.{p_label} "
                        f"ORDER BY deger DESC LIMIT 10"
                    )
                    target_col = metric
                else:
                    agg = "COUNT"
                    sql = (
                        f"SELECT p.{p_label}, COUNT(*) AS deger "  # noqa: S608
                        f"FROM {child.name} c "
                        f"JOIN {parent.name} p ON p.{fk.ref_column} = c.{fk.column}"
                        f"{where_sql} "
                        f"GROUP BY p.{parent.pk_column}, p.{p_label} "
                        f"ORDER BY deger DESC LIMIT 10"
                    )
                    target_col = child.pk_column
                specs.append(
                    _SqlSpec("medium", sql, child.name, (parent.name,), target_col, agg, fcol, fval, 10)
                )
                if len(specs) >= target:
                    return specs
        return specs

    def _specs_hard(self, target: int) -> list[_SqlSpec]:
        specs: list[_SqlSpec] = []
        adj = self._fk_neighbors()
        tables = list(self._schema.tables)
        self._rng.shuffle(tables)

        for start in tables:
            metric = start.metric_column()
            if not metric:
                continue
            # Find a 2-hop (3-table) path via BFS
            queue: deque[list[tuple[str, str | None, str | None]]] = deque([[(start.name, None, None)]])
            visited = {start.name}
            paths: list[list[tuple[str, str | None, str | None]]] = []
            while queue and len(paths) < 3:
                path = queue.popleft()
                if len(path) == 3:
                    paths.append(path)
                    continue
                curr = path[-1][0]
                for nbr, lcol, rcol in adj.get(curr, []):
                    if nbr not in visited:
                        visited.add(nbr)
                        queue.append([*path, (nbr, lcol, rcol)])

            for path in paths:
                t0 = start
                t1_name, c01_l, c01_r = path[1]
                t2_name, c12_l, c12_r = path[2]
                t2 = self._schema.table(t2_name)
                if t2 is None or not c01_l or not c01_r or not c12_l or not c12_r:
                    continue
                t2_label = t2.label_column()
                fcol, fval = self._pick_filter(t0)
                where_sql = f" WHERE t0.{fcol} = {_quote_sql_literal(fval)}" if fcol and fval else ""
                sql = (
                    f"SELECT t2.{t2_label}, SUM(t0.{metric}) AS toplam "  # noqa: S608
                    f"FROM {t0.name} t0 "
                    f"JOIN {t1_name} t1 ON t0.{c01_l} = t1.{c01_r} "
                    f"JOIN {t2_name} t2 ON t1.{c12_l} = t2.{c12_r}"
                    f"{where_sql} "
                    f"GROUP BY t2.{t2.pk_column}, t2.{t2_label} "
                    f"HAVING SUM(t0.{metric}) > 0 "
                    f"ORDER BY toplam DESC LIMIT 10"
                )
                specs.append(
                    _SqlSpec(
                        "hard",
                        sql,
                        t0.name,
                        (t1_name, t2_name),
                        metric,
                        "SUM",
                        fcol,
                        fval,
                        10,
                    )
                )
                if len(specs) >= target:
                    return specs
        return specs

    def _specs_nested(self, target: int) -> list[_SqlSpec]:
        specs: list[_SqlSpec] = []
        tables = list(self._schema.tables)
        self._rng.shuffle(tables)

        for child in tables:
            metric = child.metric_column()
            if not metric:
                continue
            for fk in child.foreign_keys:
                parent = self._schema.table(fk.ref_table)
                if parent is None:
                    continue
                p_label = parent.label_column()
                sql = (
                    f"WITH ozet AS ("  # noqa: S608
                    f"SELECT {fk.column} AS grp_id, SUM({metric}) AS toplam "
                    f"FROM {child.name} GROUP BY {fk.column}"
                    f") "
                    f"SELECT p.{p_label}, o.toplam "
                    f"FROM ozet o JOIN {parent.name} p ON p.{fk.ref_column} = o.grp_id "
                    f"WHERE o.toplam >= (SELECT AVG(toplam) FROM ozet) "
                    f"ORDER BY o.toplam DESC LIMIT 10"
                )
                specs.append(
                    _SqlSpec("nested", sql, child.name, (parent.name,), metric, "SUM", None, None, 10)
                )
                if len(specs) >= target:
                    return specs

            # Scalar subquery fallback
            label_col = child.label_column()
            sql_scalar = (
                f"SELECT {label_col}, {metric} "  # noqa: S608
                f"FROM {child.name} "
                f"WHERE {metric} > (SELECT AVG({metric}) FROM {child.name}) "
                f"ORDER BY {metric} DESC LIMIT 10"
            )
            specs.append(_SqlSpec("nested", sql_scalar, child.name, (), metric, None, None, None, 10))
            if len(specs) >= target:
                return specs
        return specs
