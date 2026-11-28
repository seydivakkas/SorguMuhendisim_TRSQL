"""Deterministic Turkish (tr_TR) synthetic data populator for the ERP schema.

Generates 100% synthetic, culturally authentic Turkish business records containing
all Turkish diacritics (İ/ı, Ş/ş, Ğ/ğ, Ü/ü, Ö/ö, Ç/ç) while strictly ensuring
sensitive identifiers (TCKN, IBAN, tax numbers, phone numbers, emails) are
formally invalid and never correspond to real individuals or institutions.

Uses ``Faker('tr_TR')`` if installed, with a rich deterministic built-in
Turkish generator fallback so zero external dependencies are required.
"""

from __future__ import annotations

import importlib
import random
import sqlite3
from collections.abc import Sequence
from datetime import date, timedelta
from pathlib import Path
from typing import Any

DEFAULT_REFERENCE_DATE = date(2026, 11, 28)
SCHEMA_DIR = Path(__file__).resolve().parent / "schema"
SQLITE_SCHEMA_PATH = SCHEMA_DIR / "erp_sqlite.sql"
POSTGRES_SCHEMA_PATH = SCHEMA_DIR / "erp.sql"


def _load_faker_class() -> Any | None:
    try:
        mod = importlib.import_module("faker")
        return getattr(mod, "Faker", None)
    except ImportError:  # pragma: no cover - covered by fallback path in base venv
        return None


_FakerClass: Any | None = _load_faker_class()


_REGIONS: tuple[tuple[int, str, str], ...] = (
    (1, "BLG-MRM", "Marmara"),
    (2, "BLG-KRD", "Karadeniz"),
    (3, "BLG-ICA", "İç Anadolu"),
    (4, "BLG-EGE", "Ege"),
    (5, "BLG-DOA", "Doğu Anadolu"),
    (6, "BLG-GDA", "Güneydoğu Anadolu"),
    (7, "BLG-AKD", "Akdeniz"),
)

_CITIES: tuple[tuple[str, int, str], ...] = (
    ("İstanbul", 1, "Kadıköy"),
    ("İstanbul", 1, "Şişli"),
    ("Trabzon", 2, "Ortahisar"),
    ("Trabzon", 2, "Akçaabat"),
    ("Ankara", 3, "Çankaya"),
    ("Ankara", 3, "Yenimahalle"),
    ("İzmir", 4, "Konak"),
    ("İzmir", 4, "Bornova"),
    ("Iğdır", 5, "Merkez"),
    ("Şanlıurfa", 6, "Haliliye"),
    ("Bursa", 1, "Nilüfer"),
    ("Antalya", 7, "Muratpaşa"),
    ("Gaziantep", 6, "Şehitkamil"),
    ("Kayseri", 3, "Melikgazi"),
    ("Eskişehir", 3, "Odunpazarı"),
    ("Muğla", 4, "Menteşe"),
    ("Çanakkale", 1, "Merkez"),
    ("Ağrı", 5, "Merkez"),
)

_FIRST_NAMES: tuple[str, ...] = (
    "Ahmet",
    "Ayşe",
    "Mehmet",
    "Fatma",
    "Mustafa",
    "Zeynep",
    "İbrahim",
    "Elif",
    "Ömer",
    "Şeyma",
    "Çağlar",
    "Gülşah",
    "Ümit",
    "İrem",
    "Yusuf",
    "Büşra",
    "Doğan",
    "Pınar",
    "Kürşat",
    "Özge",
    "Hüseyin",
    "Deniz",
    "Selim",
    "Yağmur",
    "Burak",
    "Ceren",
    "Tuğba",
    "Serkan",
)

_LAST_NAMES: tuple[str, ...] = (
    "Yılmaz",
    "Kaya",
    "Demir",
    "Şahin",
    "Çelik",
    "Yıldız",
    "Öztürk",
    "Aydın",
    "Özdemir",
    "Arslan",
    "Doğan",
    "Kılıç",
    "Çetin",
    "Işık",
    "Güneş",
    "Koç",
    "Ünal",
    "Erdoğan",
    "Şimşek",
    "Aktaş",
    "Karahan",
    "Turan",
    "Güler",
    "Sarı",
)

_COMPANY_PREFIXES: tuple[str, ...] = (
    "Anadolu",
    "Boğaziçi",
    "Karadeniz",
    "Güneş",
    "Yıldız",
    "Çağdaş",
    "Işık",
    "Özgür",
    "Ümit",
    "Şahin",
    "Doğu",
    "Ege",
    "Çınar",
    "Başkent",
    "Fırat",
    "Marmara",
)

_COMPANY_SUFFIXES: tuple[str, ...] = (
    "Ticaret A.Ş.",
    "Lojistik Ltd. Şti.",
    "Yapı Malzemeleri A.Ş.",
    "Elektronik San. Tic.",
    "Gıda Pazarlama Ltd.",
    "Endüstriyel Tedarik A.Ş.",
    "Dağıtım ve Pazarlama",
    "Teknoloji Çözümleri",
)

_DEALERS: tuple[tuple[int, str, str, str, str], ...] = (
    (1, "Marmara Merkez Bayi", "İstanbul", "Şişli", "BY-IST-01"),
    (1, "Kadıköy Anadolu Bayi", "İstanbul", "Kadıköy", "BY-IST-02"),
    (2, "Karadeniz Doğu Bayi", "Trabzon", "Ortahisar", "BY-TRB-01"),
    (2, "Akçaabat Sahil Bayi", "Trabzon", "Akçaabat", "BY-TRB-02"),
    (3, "Başkent Çankaya Bayi", "Ankara", "Çankaya", "BY-ANK-01"),
    (3, "Ostim Sanayi Bayi", "Ankara", "Yenimahalle", "BY-ANK-02"),
    (4, "Ege Körfez Bayi", "İzmir", "Konak", "BY-IZM-01"),
    (4, "Bornova Lojistik Bayi", "İzmir", "Bornova", "BY-IZM-02"),
    (5, "Aras DOĞU Bayi", "Iğdır", "Merkez", "BY-IGD-01"),
    (6, "Fırat Güneydoğu Bayi", "Şanlıurfa", "Haliliye", "BY-URF-01"),
    (1, "Uludağ Bursa Bayi", "Bursa", "Nilüfer", "BY-BRS-01"),
    (7, "Akdeniz Turizm Bayi", "Antalya", "Muratpaşa", "BY-ANT-01"),
    (6, "İpekyolu Gaziantep Bayi", "Gaziantep", "Şehitkamil", "BY-GZT-01"),
    (3, "Erciyes Kayseri Bayi", "Kayseri", "Melikgazi", "BY-KYS-01"),
)

_CATEGORIES: tuple[tuple[int, int | None, str, float], ...] = (
    (1, None, "Elektronik", 20.0),
    (2, None, "Ev & Yaşam", 20.0),
    (3, None, "Ofis Malzemeleri", 20.0),
    (4, None, "Yapı Market", 20.0),
    (5, None, "Gıda & İçecek", 10.0),
    (6, None, "Tekstil", 10.0),
    (7, None, "Lojistik Ekipman", 20.0),
    (8, None, "Endüstriyel Ürünler", 20.0),
    (9, 1, "Bilgisayar & Çevre Birimleri", 20.0),
    (10, 2, "Küçük Ev Aletleri", 20.0),
    (11, 3, "Kırtasiye & Kağıt", 10.0),
    (12, 4, "El Aletleri", 20.0),
)

_PRODUCTS: tuple[tuple[int, str, str, str, float, float, float], ...] = (
    (9, "URN-001", "Işıklı Mekanik Klavye", "Adet", 1850.0, 1120.0, 20.0),
    (9, "URN-002", "Kablosuz Ergonomik Fare", "Adet", 920.0, 540.0, 20.0),
    (9, "URN-003", "27 İnç IPS Monitör", "Adet", 8400.0, 5600.0, 20.0),
    (1, "URN-004", "Taşınabilir Güç Kaynağı 20000mAh", "Adet", 1450.0, 880.0, 20.0),
    (10, "URN-005", "Öğütücülü Türk Kahve Makinesi", "Adet", 4250.0, 2650.0, 20.0),
    (2, "URN-006", "Çelik Termos 1.2L", "Adet", 780.0, 410.0, 20.0),
    (2, "URN-007", "Gümüş İşlemeli Şamdan Seti", "Set", 1650.0, 920.0, 20.0),
    (10, "URN-008", "Buharlı Dikey Ütü", "Adet", 3100.0, 1890.0, 20.0),
    (11, "URN-009", "A4 Fotokopi Kağıdı (5'li Koli)", "Koli", 680.0, 440.0, 10.0),
    (3, "URN-010", "Ergonomik Yönetici Koltuğu", "Adet", 6900.0, 4200.0, 20.0),
    (11, "URN-011", "Tükenmez Kalem 50'li Kutu", "Kutu", 340.0, 175.0, 10.0),
    (3, "URN-012", "Çift Çekmeceli Evrak Dolabı", "Adet", 4800.0, 2950.0, 20.0),
    (12, "URN-013", "Şarjlı Darbeli Matkap Seti", "Set", 5300.0, 3300.0, 20.0),
    (4, "URN-014", "Su Geçirmez Yağmur İzolasyon Boyası", "Kova", 2150.0, 1320.0, 20.0),
    (12, "URN-015", "Çelik Lokma Anahtar Takımı", "Takım", 2750.0, 1680.0, 20.0),
    (5, "URN-016", "Rize Siyah Çay 5 Kg Kurumsal Paket", "Paket", 1120.0, 740.0, 10.0),
    (5, "URN-017", "Soğuk Sıkım Zeytinyağı 5L Teneke", "Teneke", 1980.0, 1310.0, 10.0),
    (5, "URN-018", "Kavrulmuş Giresun Fındık 2 Kg", "Paket", 960.0, 620.0, 10.0),
    (6, "URN-019", "İpek Dokuma Şal Koleksiyonu", "Adet", 1250.0, 680.0, 10.0),
    (6, "URN-020", "Su İtici İş Güvenliği Yağmurluk", "Adet", 1480.0, 860.0, 10.0),
    (7, "URN-021", "Euro Palet Taşıma Transpaleti", "Adet", 14500.0, 9800.0, 20.0),
    (7, "URN-022", "Ağır Hizmet Streç Film 6'lı Rulo", "Koli", 1320.0, 810.0, 20.0),
    (8, "URN-023", "Üç Fazlı Endüstriyel Kompresör", "Adet", 28900.0, 19500.0, 20.0),
    (8, "URN-024", "Dijital Barkod Okuyucu Terminal", "Adet", 5600.0, 3550.0, 20.0),
)

_DEPARTMENTS: tuple[tuple[int, str, float], ...] = (
    (1, "Satış ve Pazarlama", 1_850_000.0),
    (2, "Finans ve Muhasebe", 920_000.0),
    (3, "Lojistik ve Depo", 1_450_000.0),
    (4, "Müşteri Hizmetleri", 680_000.0),
    (5, "İnsan Kaynakları", 540_000.0),
    (6, "Bilgi Teknolojileri", 1_250_000.0),
)

_TITLES: tuple[str, ...] = (
    "Bölge Satış Müdürü",
    "Kurumsal Müşteri Temsilcisi",
    "Finans Uzmanı",
    "Depo ve Sevkiyat Sorumlusu",
    "Müşteri Destek Uzmanı",
    "İK İş Ortağı",
    "Veri Analisti",
    "Satın Alma Uzmanı",
)

_RETURN_REASONS: tuple[str, ...] = (
    "Kargo sırasında ambalaj hasarı",
    "Yanlış ürün sevkiyatı",
    "Teknik arıza / çalışmama sorunu",
    "Müşteri vazgeçme bildirimi",
    "Eksik parça teslimatı",
)

_EXPENSE_CATEGORIES: tuple[str, ...] = (
    "Lojistik ve Nakliye",
    "Pazarlama ve Fuar",
    "Ofis ve Kırtasiye",
    "Seyahat ve Konaklama",
    "Yazılım ve Lisans",
)

_CARGO_COMPANIES: tuple[str, ...] = (
    "Yurtiçi Kargo",
    "Aras Kargo",
    "MNG Kargo",
    "Sürat Kargo",
    "UPS Türkiye",
)

_TICKET_SUBJECTS: tuple[str, ...] = (
    "Fatura KDV oranı düzeltme talebi",
    "Kargo takip numarası güncellenmedi",
    "İade onay sürecinin hızlandırılması",
    "Toplu sipariş indirim tanımlaması",
    "Eksik ürün teslimat bildirimi",
    "Cari hesap mutabakat ekstre talebi",
)

_PRICE_CHANGE_REASONS: tuple[str, ...] = (
    "Üretici maliyet güncellemesi",
    "Döviz kuru uyarlaması",
    "Dönemsel kampanya indirimi",
    "Yıllık liste fiyatı revizyonu",
)


def make_fictitious_tckn(index: int, seed: int) -> str:
    """Return a strictly invalid 11-digit TCKN starting with ``00``."""
    suffix = (seed * 7919 + index * 104729) % 1_000_000_000
    return f"00{suffix:09d}"


def make_fictitious_iban(index: int, seed: int) -> str:
    """Return a strictly invalid 26-char IBAN starting with ``TR00``."""
    body = (seed * 131 + index * 997) % 10**12
    return f"TR0000061000{index:02d}{body:012d}"


def make_fictitious_tax_no(index: int, seed: int) -> str:
    """Return a strictly fictitious 10-digit tax number starting with ``000``."""
    suffix = (seed * 313 + index * 773) % 10_000_000
    return f"000{suffix:07d}"


def make_fictitious_phone(index: int, seed: int) -> str:
    """Return a non-routable synthetic phone number with area code ``000``."""
    mid = 100 + ((index * 37 + seed * 13) % 900)
    p1 = 10 + ((index * 19 + seed * 7) % 90)
    p2 = 10 + ((index * 23 + seed * 11) % 90)
    return f"+90 000 {mid:03d} {p1:02d} {p2:02d}"


def make_fictitious_email(prefix: str, index: int, seed: int) -> str:
    """Return a synthetic RFC 2606 ``.invalid`` email address."""
    return f"{prefix}.{seed}.{index}@trsql-sentetik.invalid"


class _TurkishTextSampler:
    """Uses ``Faker('tr_TR')`` when available, falling back to deterministic Turkish pools."""

    def __init__(self, seed: int) -> None:
        self._rng = random.Random(seed)  # noqa: S311
        self._faker: Any = None
        if _FakerClass is not None:  # pragma: no cover - optional dependency
            try:
                faker_inst = _FakerClass("tr_TR")
                faker_inst.seed_instance(seed)
                self._faker = faker_inst
            except Exception:
                self._faker = None

    def full_name(self, idx: int) -> str:
        if self._faker is not None and idx % 2 == 1:  # pragma: no cover
            return str(self._faker.name())
        first = _FIRST_NAMES[(idx * 3 + self._rng.randint(0, len(_FIRST_NAMES) - 1)) % len(_FIRST_NAMES)]
        last = _LAST_NAMES[(idx * 5 + self._rng.randint(0, len(_LAST_NAMES) - 1)) % len(_LAST_NAMES)]
        return f"{first} {last}"

    def company_name(self, idx: int) -> str:
        prefix = _COMPANY_PREFIXES[(idx + self._rng.randint(0, 5)) % len(_COMPANY_PREFIXES)]
        suffix = _COMPANY_SUFFIXES[(idx * 3 + self._rng.randint(0, 3)) % len(_COMPANY_SUFFIXES)]
        return f"{prefix} {suffix}"


def _dstr(d: date) -> str:
    return d.isoformat()


def get_table_counts(conn: sqlite3.Connection) -> dict[str, int]:
    """Return row counts for every user table in the connected SQLite database."""
    tables = [
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
    ]
    counts: dict[str, int] = {}
    for table in tables:
        quoted = '"' + table.replace('"', '""') + '"'
        count_row = conn.execute(f"SELECT COUNT(*) FROM {quoted}").fetchone()  # noqa: S608
        counts[table] = int(count_row[0]) if count_row else 0
    return counts


def populate_connection(
    conn: sqlite3.Connection,
    *,
    seed: int = 1,
    reference_date: date = DEFAULT_REFERENCE_DATE,
    scale: int = 1,
) -> dict[str, int]:
    """Populate an already-initialized SQLite ERP connection deterministically.

    Different ``seed`` values produce distinct mutated database states (different
    row counts, amounts, entity assignments, and dates) while keeping all core
    entities, statuses, and business-rule scenarios populated for Test Suite
    Accuracy.
    """
    if scale < 1:
        raise ValueError("scale must be >= 1")

    rng = random.Random(seed * 1009 + 17)  # noqa: S311
    sampler = _TurkishTextSampler(seed)
    conn.execute("PRAGMA foreign_keys = ON")

    # 1. Regions (bolgeler)
    conn.executemany(
        "INSERT INTO bolgeler (bolge_id, bolge_kodu, bolge_adi, ulke) VALUES (?, ?, ?, ?)",
        [(bid, code, name, "Türkiye") for bid, code, name in _REGIONS],
    )

    # 2. Dealers (bayiler) — keep all 14 core dealers + extra seed-mutated dealers
    dealer_rows: list[tuple[Any, ...]] = []
    for idx, (bolge_id, base_name, sehir, ilce, kod) in enumerate(_DEALERS, start=1):
        open_date = reference_date - timedelta(days=365 * 3 + idx * 45 + (seed % 5) * 15)
        tenant = "t-kurum" if idx <= 12 else "t-anadolu"
        dealer_rows.append(
            (
                idx,
                bolge_id,
                kod,
                f"{base_name}" if seed == 1 else f"{base_name} #{seed}",
                sehir,
                ilce,
                make_fictitious_tax_no(idx, seed),
                make_fictitious_phone(idx, seed),
                make_fictitious_email("bayi", idx, seed),
                1,
                _dstr(open_date),
                tenant,
            )
        )
    extra_dealers = seed % 3
    for extra_idx in range(extra_dealers):
        did = len(_DEALERS) + extra_idx + 1
        city, bolge_id, ilce = _CITIES[(did + seed) % len(_CITIES)]
        dealer_rows.append(
            (
                did,
                bolge_id,
                f"BY-EK-{seed}-{did}",
                f"{city} Şube Bayi {did}",
                city,
                ilce,
                make_fictitious_tax_no(did, seed),
                make_fictitious_phone(did, seed),
                make_fictitious_email("bayi", did, seed),
                1 if extra_idx == 0 else 0,
                _dstr(reference_date - timedelta(days=200 + extra_idx * 30)),
                "t-kurum",
            )
        )
    conn.executemany(
        """
        INSERT INTO bayiler (
            bayi_id, bolge_id, bayi_kodu, bayi_adi, sehir, ilce,
            vergi_no, telefon, eposta, aktif, acilis_tarihi, tenant_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        dealer_rows,
    )
    num_dealers = len(dealer_rows)

    # 3. Customer segments (musteri_segmentleri)
    segments = [
        (1, "Kurumsal", round(10.0 + (seed % 3), 2), 100_000.0 + seed * 5_000.0),
        (2, "VIP", round(15.0 + (seed % 4), 2), 250_000.0 + seed * 10_000.0),
        (3, "KOBİ", round(5.0 + (seed % 2), 2), 25_000.0 + seed * 2_000.0),
        (4, "Bireysel", 0.0, 0.0),
    ]
    conn.executemany(
        "INSERT INTO musteri_segmentleri (segment_id, segment_adi, indirim_orani, min_ciro) "
        "VALUES (?, ?, ?, ?)",
        segments,
    )

    # 4. Customers (musteriler)
    num_customers = (32 + (seed % 5)) * scale
    customer_rows: list[tuple[Any, ...]] = []
    customer_cities: list[str] = []
    customer_active_flags: list[int] = []
    for cid in range(1, num_customers + 1):
        city, _, _ = _CITIES[(cid - 1 + seed) % len(_CITIES)]
        # Guarantee required target cities appear early
        if cid <= 6:
            city = ("İstanbul", "Trabzon", "Ankara", "İzmir", "Iğdır", "Şanlıurfa")[cid - 1]
        customer_cities.append(city)
        seg_id = ((cid + seed) % 4) + 1
        dealer_id = ((cid + seed) % min(num_dealers, 12)) + 1
        reg_date = reference_date - timedelta(days=120 + cid * 12 + rng.randint(0, 60))
        # Ensure active recent (<90d), older active (>90d), and inactive customers all exist
        if cid % 6 == 0:
            aktif = 0
            last_buy = reference_date - timedelta(days=150 + rng.randint(10, 120))
        elif cid % 5 == 0:
            aktif = 1
            last_buy = reference_date - timedelta(days=110 + rng.randint(5, 90))
        else:
            aktif = 1
            last_buy = reference_date - timedelta(days=rng.randint(2, 75))
        customer_active_flags.append(aktif)
        credit_limit = round(
            (25_000 + seg_id * 35_000 + rng.randint(1, 20) * 2_500) * (1 + (seed % 3) * 0.1), 2
        )
        tenant = "t-kurum" if cid % 7 != 0 else "t-anadolu"
        customer_rows.append(
            (
                cid,
                seg_id,
                dealer_id,
                sampler.full_name(cid),
                sampler.company_name(cid),
                city,
                make_fictitious_tckn(cid, seed),
                make_fictitious_phone(cid + 100, seed),
                make_fictitious_email("musteri", cid, seed),
                _dstr(reg_date),
                _dstr(last_buy),
                aktif,
                credit_limit,
                tenant,
            )
        )
    conn.executemany(
        """
        INSERT INTO musteriler (
            musteri_id, segment_id, bayi_id, ad_soyad, unvan, sehir, tckn,
            telefon, eposta, kayit_tarihi, son_alisveris_tarihi, aktif, kredi_limiti, tenant_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        customer_rows,
    )

    # 5. Categories (kategoriler)
    conn.executemany(
        "INSERT INTO kategoriler (kategori_id, ust_kategori_id, kategori_adi, kdv_orani) VALUES (?, ?, ?, ?)",
        _CATEGORIES,
    )

    # 6. Products (urunler)
    price_scale = 1.0 + (seed - 1) * 0.08
    product_rows: list[tuple[Any, ...]] = []
    product_prices: dict[int, tuple[float, float]] = {}
    for pid, (kat_id, kod, ad, birim, fiyat, maliyet, kdv) in enumerate(_PRODUCTS, start=1):
        jitter = 1.0 + rng.uniform(-0.04, 0.06)
        adj_price = round(fiyat * price_scale * jitter, 2)
        adj_cost = round(maliyet * price_scale * jitter, 2)
        product_prices[pid] = (adj_price, kdv)
        product_rows.append(
            (
                pid,
                kat_id,
                kod,
                ad,
                birim,
                adj_price,
                adj_cost,
                kdv,
                0 if pid == len(_PRODUCTS) and seed % 2 == 0 else 1,
            )
        )
    conn.executemany(
        """
        INSERT INTO urunler (
            urun_id, kategori_id, urun_kodu, urun_adi, birim,
            birim_fiyat, maliyet_fiyati, kdv_orani, aktif
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        product_rows,
    )
    num_products = len(product_rows)

    # 7. Warehouses (depolar)
    warehouse_specs = (
        (1, "DP-IST", "İstanbul Ana Lojistik Deposu", "İstanbul", 50_000),
        (2, "DP-TRB", "Trabzon Karadeniz Deposu", "Trabzon", 22_000),
        (3, "DP-ANK", "Ankara İç Anadolu Deposu", "Ankara", 35_000),
        (4, "DP-IZM", "İzmir Ege Dağıtım Merkezi", "İzmir", 30_000),
        (5, "DP-IGD", "Iğdır Doğu Sınır Deposu", "Iğdır", 12_000),
        (6, "DP-URF", "Şanlıurfa Güneydoğu Deposu", "Şanlıurfa", 18_000),
        (7, "DP-ANT", "Antalya Akdeniz Deposu", "Antalya", 20_000),
    )
    conn.executemany(
        "INSERT INTO depolar (depo_id, bolge_id, depo_kodu, depo_adi, sehir, kapasite, aktif) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            (wid, bid, kod, ad, sehir, kap + seed * 500, 1)
            for wid, (bid, kod, ad, sehir, kap) in enumerate(warehouse_specs, start=1)
        ],
    )
    num_warehouses = len(warehouse_specs)

    # 8. Stock movements (stok_hareketleri)
    movement_types = ("giris", "cikis", "transfer", "iade")
    stock_moves: list[tuple[Any, ...]] = []
    for mid in range(1, 64 * scale + 1):
        wid = ((mid + seed) % num_warehouses) + 1
        pid = ((mid * 3 + seed) % num_products) + 1
        mtype = movement_types[(mid + seed) % len(movement_types)]
        qty = rng.randint(5, 180)
        mdate = reference_date - timedelta(days=rng.randint(1, 180))
        stock_moves.append(
            (
                mid,
                wid,
                pid,
                mtype,
                qty,
                _dstr(mdate),
                f"{mtype.capitalize()} stok hareketi #{mid}",
            )
        )
    conn.executemany(
        """
        INSERT INTO stok_hareketleri (
            hareket_id, depo_id, urun_id, hareket_turu, miktar, hareket_tarihi, aciklama
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        stock_moves,
    )

    # 9. Campaigns (kampanyalar)
    campaigns = (
        (
            1,
            "Kış Kurumsal İndirimi",
            reference_date - timedelta(days=330),
            reference_date - timedelta(days=270),
            10.0,
            0,
        ),
        (
            2,
            "Bahar Anadolu Fırsatı",
            reference_date - timedelta(days=240),
            reference_date - timedelta(days=180),
            12.5,
            0,
        ),
        (
            3,
            "Yaz Lojistik Kampanyası",
            reference_date - timedelta(days=150),
            reference_date - timedelta(days=90),
            8.0,
            0,
        ),
        (
            4,
            "Sonbahar Teknoloji Haftası",
            reference_date - timedelta(days=60),
            reference_date - timedelta(days=25),
            15.0,
            1,
        ),
        (
            5,
            "Kasım Büyük B2B İndirimi",
            reference_date - timedelta(days=25),
            reference_date + timedelta(days=5),
            18.0,
            1,
        ),
        (
            6,
            "Yıl Sonu Hedef Desteği",
            reference_date - timedelta(days=10),
            reference_date + timedelta(days=30),
            10.0,
            1,
        ),
    )
    conn.executemany(
        """
        INSERT INTO kampanyalar (
            kampanya_id, kampanya_adi, baslangic_tarihi, bitis_tarihi, indirim_yuzdesi, aktif
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        [(cid, name, _dstr(s), _dstr(e), disc, act) for cid, name, s, e, disc, act in campaigns],
    )

    # 10. Departments (departmanlar)
    conn.executemany(
        "INSERT INTO departmanlar (departman_id, departman_adi, butce) VALUES (?, ?, ?)",
        [(did, name, round(budget * (1 + (seed % 3) * 0.05), 2)) for did, name, budget in _DEPARTMENTS],
    )

    # 11. Employees (calisanlar)
    num_employees = 18 + (seed % 4)
    employee_rows: list[tuple[Any, ...]] = []
    for eid in range(1, num_employees + 1):
        dept_id = ((eid - 1) % len(_DEPARTMENTS)) + 1
        dealer_id = ((eid + seed) % min(num_dealers, 12)) + 1
        city = _DEALERS[(dealer_id - 1) % len(_DEALERS)][2]
        hire_date = reference_date - timedelta(days=365 + eid * 60 + rng.randint(0, 90))
        employee_rows.append(
            (
                eid,
                dept_id,
                dealer_id,
                sampler.full_name(eid + 200),
                _TITLES[(eid - 1) % len(_TITLES)],
                city,
                make_fictitious_tckn(eid + 500, seed),
                _dstr(hire_date),
                1 if eid < num_employees or seed % 2 == 1 else 0,
            )
        )
    conn.executemany(
        """
        INSERT INTO calisanlar (
            calisan_id, departman_id, bayi_id, ad_soyad, unvan, sehir,
            tckn, ise_giris_tarihi, aktif
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        employee_rows,
    )

    # 12. Salaries (maaslar — RBAC sensitive)
    salary_rows: list[tuple[Any, ...]] = []
    sal_id = 1
    for month_offset in (1, 0):
        target_month = reference_date.month - month_offset
        target_year = reference_date.year
        if target_month <= 0:
            target_month += 12
            target_year -= 1
        for eid in range(1, num_employees + 1):
            gross = round(42_000.0 + (eid % 6) * 8_500.0 + seed * 750.0, 2)
            net = round(gross * 0.72, 2)
            bonus = round((eid % 3) * 3_500.0 + (seed % 4) * 500.0, 2)
            salary_rows.append(
                (
                    sal_id,
                    eid,
                    target_year,
                    target_month,
                    gross,
                    net,
                    bonus,
                    make_fictitious_iban(eid + 20, seed),
                )
            )
            sal_id += 1
    conn.executemany(
        """
        INSERT INTO maaslar (
            maas_id, calisan_id, donem_yil, donem_ay, brut_maas, net_maas, prim, iban
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        salary_rows,
    )

    # 13. Orders (siparisler) + Order items (siparis_kalemleri)
    num_orders = (96 + (seed % 5) * 4) * scale
    order_items_rows: list[tuple[Any, ...]] = []
    order_meta: list[dict[str, Any]] = []
    item_id = 1

    # Ensure deterministic coverage across date buckets (2025, 2026 Q1-Q4, last 90d, last 30d)
    date_offsets = (
        400,
        380,
        350,
        310,
        280,
        250,
        220,
        190,
        160,
        130,
        105,
        85,
        65,
        45,
        35,
        25,
        18,
        10,
        5,
        2,
    )
    payment_methods = ("Kredi Kartı", "Havale", "Vadeli")

    for oid in range(1, num_orders + 1):
        # First 32 orders map cleanly to active/all customers so recent customers have recent orders
        cid = ((oid - 1) % num_customers) + 1
        dealer_id = ((cid + oid + seed) % min(num_dealers, 12)) + 1
        emp_id = ((oid + seed) % num_employees) + 1
        camp_id = ((oid % 6) + 1) if oid % 3 == 0 else None

        if customer_active_flags[cid - 1] == 1 and oid <= num_customers:
            days_ago = rng.randint(2, 75)
        else:
            base_off = date_offsets[(oid - 1) % len(date_offsets)]
            days_ago = max(1, base_off + rng.randint(-5, 12))
        order_date = reference_date - timedelta(days=days_ago)

        if oid % 11 == 0:
            status = "iptal"
        elif oid % 13 == 0:
            status = "beklemede"
        elif oid % 9 == 0:
            status = "kargoda"
        else:
            status = "tamamlandi"

        pay_method = payment_methods[(oid + seed) % len(payment_methods)]
        tenant = "t-kurum" if cid % 7 != 0 else "t-anadolu"

        line_count = 1 + (oid % 3)
        gross_sum = 0.0
        disc_sum = 0.0
        kdv_sum = 0.0
        first_prod_id = 1
        for line_idx in range(line_count):
            pid = ((oid * 3 + line_idx * 5 + seed) % num_products) + 1
            if line_idx == 0:
                first_prod_id = pid
            unit_price, kdv_rate = product_prices[pid]
            qty = 1 + ((oid + line_idx + seed) % 6)
            line_gross = round(unit_price * qty, 2)
            disc_pct = 0.10 if camp_id is not None else (0.05 if line_idx == 0 and oid % 4 == 0 else 0.0)
            line_disc = round(line_gross * disc_pct, 2)
            taxable = line_gross - line_disc
            line_kdv = round(taxable * (kdv_rate / 100.0), 2)
            line_total = round(taxable + line_kdv, 2)
            gross_sum += line_gross
            disc_sum += line_disc
            kdv_sum += line_kdv
            order_items_rows.append(
                (
                    item_id,
                    oid,
                    pid,
                    qty,
                    unit_price,
                    line_disc,
                    line_kdv,
                    line_total,
                )
            )
            item_id += 1

        gross_sum = round(gross_sum, 2)
        disc_sum = round(disc_sum, 2)
        kdv_sum = round(kdv_sum, 2)
        total_sum = round(gross_sum - disc_sum + kdv_sum, 2)
        order_meta.append(
            {
                "siparis_id": oid,
                "musteri_id": cid,
                "bayi_id": dealer_id,
                "calisan_id": emp_id,
                "kampanya_id": camp_id,
                "siparis_no": f"SIP-2026-{oid:05d}",
                "siparis_tarihi": order_date,
                "durum": status,
                "odeme_yontemi": pay_method,
                "brut_tutar": gross_sum,
                "indirim_tutari": disc_sum,
                "kdv_tutari": kdv_sum,
                "toplam_tutar": total_sum,
                "iade_tutari": 0.0,
                "tenant_id": tenant,
                "first_prod_id": first_prod_id,
            }
        )

    # 14. Returns (iadeler) & Return items (iade_kalemleri) — update order iade_tutari first
    returns_rows: list[tuple[Any, ...]] = []
    return_items_rows: list[tuple[Any, ...]] = []
    ret_id = 1
    ret_item_id = 1
    completed_orders = [m for m in order_meta if m["durum"] == "tamamlandi"]
    order_return_map: dict[int, tuple[int, float]] = {}

    for idx, om in enumerate(completed_orders):
        if idx % 4 != 0:
            continue
        oid = om["siparis_id"]
        ret_date = min(reference_date, om["siparis_tarihi"] + timedelta(days=rng.randint(3, 20)))
        if ret_id % 7 == 0:
            ret_status = "beklemede"
        elif ret_id % 11 == 0:
            ret_status = "reddedildi"
        else:
            ret_status = "onaylandi"
        ret_amt = round(om["toplam_tutar"] * rng.uniform(0.15, 0.45), 2)
        ret_qty = 1 + (ret_id % 3)
        if ret_status == "onaylandi":
            om["iade_tutari"] = ret_amt
            order_return_map[oid] = (ret_qty, ret_amt)
        returns_rows.append(
            (
                ret_id,
                oid,
                om["musteri_id"],
                _dstr(ret_date),
                _RETURN_REASONS[(ret_id + seed) % len(_RETURN_REASONS)],
                ret_status,
                ret_amt,
            )
        )
        return_items_rows.append(
            (
                ret_item_id,
                ret_id,
                om["first_prod_id"],
                ret_qty,
                ret_amt,
                f"İade kalemi #{ret_item_id}",
            )
        )
        ret_id += 1
        ret_item_id += 1

    conn.executemany(
        """
        INSERT INTO siparisler (
            siparis_id, musteri_id, bayi_id, calisan_id, kampanya_id, siparis_no,
            siparis_tarihi, durum, odeme_yontemi, brut_tutar, indirim_tutari,
            kdv_tutari, toplam_tutar, iade_tutari, tenant_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                m["siparis_id"],
                m["musteri_id"],
                m["bayi_id"],
                m["calisan_id"],
                m["kampanya_id"],
                m["siparis_no"],
                _dstr(m["siparis_tarihi"]),
                m["durum"],
                m["odeme_yontemi"],
                m["brut_tutar"],
                m["indirim_tutari"],
                m["kdv_tutari"],
                m["toplam_tutar"],
                m["iade_tutari"],
                m["tenant_id"],
            )
            for m in order_meta
        ],
    )
    conn.executemany(
        """
        INSERT INTO siparis_kalemleri (
            kalem_id, siparis_id, urun_id, miktar, birim_fiyat,
            indirim_tutari, kdv_tutari, satir_tutari
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        order_items_rows,
    )
    conn.executemany(
        """
        INSERT INTO iadeler (
            iade_id, siparis_id, musteri_id, iade_tarihi, neden, durum, toplam_iade_tutari
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        returns_rows,
    )
    conn.executemany(
        """
        INSERT INTO iade_kalemleri (
            iade_kalem_id, iade_id, urun_id, ret_qty, iade_tutari, aciklama
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        return_items_rows,
    )

    # 15. Invoices (faturalar), Payments (odemeler), and Inv Ledger (inv_ledger)
    invoice_rows: list[tuple[Any, ...]] = []
    payment_rows: list[tuple[Any, ...]] = []
    ledger_rows: list[tuple[Any, ...]] = []
    inv_id = 1
    pay_id = 1
    ledger_id = 1

    for m in order_meta:
        if m["durum"] == "beklemede" and m["siparis_id"] % 2 == 0:
            continue
        inv_date = m["siparis_tarihi"]
        due_date = inv_date + timedelta(days=30)
        kdv_haric = round(m["brut_tutar"] - m["indirim_tutari"], 2)
        kdv = m["kdv_tutari"]
        grand = m["toplam_tutar"]

        if m["durum"] == "iptal":
            inv_status = "iptal"
            paid = 0.0
        elif inv_id % 6 == 0:
            # Force guaranteed overdue unpaid/partial invoices
            due_date = min(due_date, reference_date - timedelta(days=10 + (inv_id % 25)))
            inv_status = "vadesi_gecmis"
            paid = round(grand * 0.25, 2) if inv_id % 12 == 0 else 0.0
        elif inv_id % 5 == 0 and due_date < reference_date:
            inv_status = "kismi_odendi"
            paid = round(grand * 0.5, 2)
        elif inv_id % 7 == 0:
            inv_status = "odenmedi"
            due_date = reference_date + timedelta(days=14)
            paid = 0.0
        else:
            inv_status = "odendi"
            paid = grand

        invoice_rows.append(
            (
                inv_id,
                m["siparis_id"],
                m["musteri_id"],
                f"FAT-2026-{inv_id:05d}",
                _dstr(inv_date),
                _dstr(due_date),
                kdv_haric,
                kdv,
                grand,
                paid,
                inv_status,
                m["tenant_id"],
            )
        )

        if paid > 0:
            pay_date = min(reference_date, inv_date + timedelta(days=rng.randint(1, 15)))
            payment_rows.append(
                (
                    pay_id,
                    inv_id,
                    m["musteri_id"],
                    _dstr(pay_date),
                    paid,
                    m["odeme_yontemi"],
                    make_fictitious_iban(m["musteri_id"], seed),
                    "basarili",
                )
            )
            pay_id += 1

        ret_qty, ret_credit = order_return_map.get(m["siparis_id"], (0, 0.0))
        net_bal = round(max(0.0, grand - ret_credit), 2)
        ledger_rows.append(
            (
                ledger_id,
                m["musteri_id"],
                inv_id,
                m["first_prod_id"],
                grand,
                ret_qty,
                net_bal,
                _dstr(inv_date),
                "TRY",
            )
        )
        ledger_id += 1
        inv_id += 1

    conn.executemany(
        """
        INSERT INTO faturalar (
            fatura_id, siparis_id, musteri_id, fatura_no, fatura_tarihi, vade_tarihi,
            kdv_haric_tutar, kdv_tutari, genel_toplam, odenen_tutar, durum, tenant_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        invoice_rows,
    )
    conn.executemany(
        """
        INSERT INTO odemeler (
            odeme_id, fatura_id, musteri_id, odeme_tarihi, tutar, odeme_yontemi, iban, durum
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        payment_rows,
    )

    # 16. Sales Targets (satis_hedefleri)
    target_rows: list[tuple[Any, ...]] = []
    tid = 1
    for month_offset in (2, 1, 0):
        t_month = reference_date.month - month_offset
        t_year = reference_date.year
        if t_month <= 0:
            t_month += 12
            t_year -= 1
        for did in range(1, min(num_dealers, 14) + 1):
            target_amt = round(250_000.0 + (did % 5) * 75_000.0 + seed * 12_000.0, 2)
            # Ensure some dealers exceed 100% ("basarili bayi") and some fall below
            ratio = (
                1.08 + rng.uniform(0.0, 0.25) if (did + month_offset) % 2 == 0 else rng.uniform(0.65, 0.94)
            )
            actual_amt = round(target_amt * ratio, 2)
            target_rows.append((tid, did, t_year, t_month, target_amt, actual_amt))
            tid += 1
    conn.executemany(
        """
        INSERT INTO satis_hedefleri (
            hedef_id, bayi_id, yil, ay, hedef_tutar, gerceklesen_tutar
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        target_rows,
    )

    # 17. Expenses (masraflar)
    expense_rows: list[tuple[Any, ...]] = []
    for eid in range(1, 32 * scale + 1):
        dept_id = ((eid - 1) % len(_DEPARTMENTS)) + 1
        dealer_id = ((eid + seed) % min(num_dealers, 12)) + 1
        exp_date = reference_date - timedelta(days=rng.randint(2, 160))
        cat = _EXPENSE_CATEGORIES[(eid + seed) % len(_EXPENSE_CATEGORIES)]
        amt = round(rng.uniform(1_800.0, 42_000.0) * (1 + (seed % 3) * 0.08), 2)
        status = "beklemede" if eid % 8 == 0 else ("reddedildi" if eid % 13 == 0 else "onaylandi")
        expense_rows.append(
            (
                eid,
                dept_id,
                dealer_id,
                _dstr(exp_date),
                cat,
                amt,
                f"{cat} gider kaydı #{eid}",
                status,
            )
        )
    conn.executemany(
        """
        INSERT INTO masraflar (
            masraf_id, departman_id, bayi_id, masraf_tarihi, kategori, tutar, aciklama, onay_durumu
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        expense_rows,
    )

    # 18. Suppliers (tedarikciler) & Purchase Orders (satin_alma_siparisleri)
    supplier_rows: list[tuple[Any, ...]] = []
    supplier_cities = ("İstanbul", "Ankara", "İzmir", "Trabzon", "Bursa", "Gaziantep", "Kayseri", "Şanlıurfa")
    for sid in range(1, 9):
        city = supplier_cities[(sid - 1) % len(supplier_cities)]
        supplier_rows.append(
            (
                sid,
                f"{_COMPANY_PREFIXES[(sid + seed) % len(_COMPANY_PREFIXES)]} Üretim ve Tedarik A.Ş.",
                city,
                make_fictitious_tax_no(sid + 100, seed),
                make_fictitious_phone(sid + 300, seed),
                make_fictitious_email("tedarikci", sid, seed),
                15 * ((sid % 4) + 1),
            )
        )
    conn.executemany(
        """
        INSERT INTO tedarikciler (
            tedarikci_id, tedarikci_adi, sehir, vergi_no, telefon, eposta, vade_gun
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        supplier_rows,
    )

    po_statuses = ("teslim_alindi", "yolda", "onay_bekliyor", "iptal")
    po_rows: list[tuple[Any, ...]] = []
    for poid in range(1, 24 * scale + 1):
        sup_id = ((poid - 1) % 8) + 1
        wid = ((poid + seed) % num_warehouses) + 1
        pid = ((poid * 2 + seed) % num_products) + 1
        po_date = reference_date - timedelta(days=rng.randint(5, 140))
        status = po_statuses[(poid - 1) % len(po_statuses)]
        deliv = (
            _dstr(min(reference_date, po_date + timedelta(days=rng.randint(4, 15))))
            if status == "teslim_alindi"
            else None
        )
        qty = rng.randint(15, 120)
        unit_cost = round(product_prices[pid][0] * 0.62, 2)
        po_rows.append(
            (
                poid,
                sup_id,
                wid,
                pid,
                _dstr(po_date),
                deliv,
                qty,
                unit_cost,
                round(qty * unit_cost, 2),
                status,
            )
        )
    conn.executemany(
        """
        INSERT INTO satin_alma_siparisleri (
            satin_alma_id, tedarikci_id, depo_id, urun_id, siparis_tarihi,
            teslim_tarihi, miktar, birim_maliyet, toplam_tutar, durum
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        po_rows,
    )

    # 19. Shipments (sevkiyatlar)
    ship_rows: list[tuple[Any, ...]] = []
    ship_id = 1
    for m in order_meta:
        if m["durum"] == "iptal":
            continue
        wid = ((m["bayi_id"] + seed) % num_warehouses) + 1
        ship_out = m["siparis_tarihi"] + timedelta(days=1)
        if m["siparis_id"] in order_return_map:
            s_status = "iade_dondu"
            ship_deliv = _dstr(min(reference_date, ship_out + timedelta(days=3)))
        elif m["durum"] == "tamamlandi":
            s_status = "teslim_edildi"
            ship_deliv = _dstr(min(reference_date, ship_out + timedelta(days=rng.randint(1, 5))))
        elif m["durum"] == "kargoda":
            s_status = "dagitimda"
            ship_deliv = None
        else:
            s_status = "hazirlaniyor"
            ship_deliv = None
        ship_rows.append(
            (
                ship_id,
                m["siparis_id"],
                wid,
                _CARGO_COMPANIES[(ship_id + seed) % len(_CARGO_COMPANIES)],
                f"TRK-{seed}-{ship_id:06d}",
                _dstr(ship_out),
                ship_deliv,
                s_status,
            )
        )
        ship_id += 1
    conn.executemany(
        """
        INSERT INTO sevkiyatlar (
            sevkiyat_id, siparis_id, depo_id, kargo_firmasi, takip_no,
            cikis_tarihi, teslim_tarihi, durum
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ship_rows,
    )

    # 20. Support tickets (destek_talepleri)
    priorities = ("dusuk", "orta", "yuksek", "kritik")
    ticket_statuses = ("acik", "inceleniyor", "cozuldu", "kapali")
    ticket_rows: list[tuple[Any, ...]] = []
    for tid in range(1, 24 * scale + 1):
        om = order_meta[(tid * 3) % len(order_meta)]
        emp_id = ((tid + seed) % num_employees) + 1
        opened = min(reference_date, om["siparis_tarihi"] + timedelta(days=rng.randint(1, 10)))
        t_status = ticket_statuses[(tid - 1) % len(ticket_statuses)]
        closed = (
            _dstr(min(reference_date, opened + timedelta(days=rng.randint(1, 7))))
            if t_status in ("cozuldu", "kapali")
            else None
        )
        ticket_rows.append(
            (
                tid,
                om["musteri_id"],
                om["siparis_id"],
                emp_id,
                _TICKET_SUBJECTS[(tid - 1) % len(_TICKET_SUBJECTS)],
                priorities[(tid + seed) % len(priorities)],
                t_status,
                _dstr(opened),
                closed,
            )
        )
    conn.executemany(
        """
        INSERT INTO destek_talepleri (
            talep_id, musteri_id, siparis_id, calisan_id, konu,
            oncelik, durum, acilis_tarihi, kapanis_tarihi
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ticket_rows,
    )

    # 21. Cross-lingual tables: cust_loyalty, inv_ledger, prod_pricing_hist, wh_stock_snap
    tiers = ("BRONZE", "SILVER", "GOLD", "PLATINUM")
    loyalty_rows: list[tuple[Any, ...]] = []
    for lid in range(1, min(num_customers, 28 * scale) + 1):
        tier = tiers[(lid - 1 + seed) % len(tiers)]
        pts = (lid * 450 + seed * 310) % 18_500 + 250
        enrolled = reference_date - timedelta(days=120 + lid * 8)
        updated = reference_date - timedelta(days=rng.randint(1, 45))
        loyalty_rows.append((lid, lid, tier, pts, _dstr(enrolled), _dstr(updated)))
    conn.executemany(
        """
        INSERT INTO cust_loyalty (
            loyalty_id, cust_id, tier_code, pts_bal, enrolled_dt, last_upd_dt
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        loyalty_rows,
    )

    conn.executemany(
        """
        INSERT INTO inv_ledger (
            ledger_id, cust_id, inv_id, prod_id, inv_amt, ret_qty, net_bal, tx_dt, curr_code
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ledger_rows,
    )

    price_hist_rows: list[tuple[Any, ...]] = []
    for hid in range(1, min(num_products, 20) + 1):
        cur_price = product_prices[hid][0]
        old_price = round(cur_price * rng.uniform(0.82, 0.94), 2)
        chg_date = reference_date - timedelta(days=20 + hid * 10)
        price_hist_rows.append(
            (
                hid,
                hid,
                old_price,
                cur_price,
                _dstr(chg_date),
                _PRICE_CHANGE_REASONS[(hid + seed) % len(_PRICE_CHANGE_REASONS)],
            )
        )
    conn.executemany(
        """
        INSERT INTO prod_pricing_hist (
            hist_id, prod_id, old_prc, new_prc, chg_dt, chg_reason
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        price_hist_rows,
    )

    snap_rows: list[tuple[Any, ...]] = []
    snap_id = 1
    for wid in range(1, num_warehouses + 1):
        for pid in range(1, 9):
            # Force some rows to have qty_on_hand <= qty_reserved or low stock (< 15)
            if snap_id % 7 == 0:
                on_hand = 8 + (snap_id % 6)
                reserved = on_hand + 4
            else:
                on_hand = 30 + ((snap_id * 17 + seed * 9) % 240)
                reserved = rng.randint(2, 25)
            snap_rows.append(
                (
                    snap_id,
                    wid,
                    ((pid + wid) % num_products) + 1,
                    on_hand,
                    reserved,
                    _dstr(reference_date - timedelta(days=1)),
                )
            )
            snap_id += 1
    conn.executemany(
        """
        INSERT INTO wh_stock_snap (
            snap_id, wh_id, prod_id, qty_on_hand, qty_reserved, snap_dt
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        snap_rows,
    )

    conn.commit()
    return get_table_counts(conn)


def populate_sqlite(
    db_path: str | Path,
    *,
    seed: int = 1,
    reference_date: date = DEFAULT_REFERENCE_DATE,
    scale: int = 1,
    overwrite: bool = True,
) -> Path:
    """Create and populate a SQLite ERP database at ``db_path``."""
    target = Path(db_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if not overwrite:
            raise FileExistsError(f"Veritabanı dosyası zaten mevcut: {target}")
        target.unlink()

    schema_sql = SQLITE_SCHEMA_PATH.read_text(encoding="utf-8")
    conn = sqlite3.connect(target)
    try:
        conn.executescript(schema_sql)
        populate_connection(conn, seed=seed, reference_date=reference_date, scale=scale)
    finally:
        conn.close()
    return target


def create_test_suite_dbs(
    output_dir: str | Path,
    *,
    seeds: Sequence[int] = (1, 2, 3),
    reference_date: date = DEFAULT_REFERENCE_DATE,
    scale: int = 1,
) -> list[Path]:
    """Generate multiple mutated SQLite database instances for Test Suite Accuracy."""
    base = Path(output_dir)
    base.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for seed in seeds:
        path = base / f"erp_seed_{seed}.sqlite"
        populate_sqlite(path, seed=seed, reference_date=reference_date, scale=scale, overwrite=True)
        paths.append(path)
    return paths
