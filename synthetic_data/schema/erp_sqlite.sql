-- TRSQL Sentetik Kurumsal ERP / Satış / Finans / Stok / İK Şeması (SQLite 3)
-- PostgreSQL 16 (erp.sql) şemasının birebir aynı 28 tablo ve sütun yapısına sahip SQLite sürümüdür.
-- Tüm değerler ve varlıklar %100 sentetiktir; gerçek kişisel veri içermez.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS bolgeler (
    bolge_id   INTEGER PRIMARY KEY,
    bolge_kodu TEXT NOT NULL UNIQUE,
    bolge_adi  TEXT NOT NULL,
    ulke       TEXT NOT NULL DEFAULT 'Türkiye'
);

CREATE TABLE IF NOT EXISTS bayiler (
    bayi_id       INTEGER PRIMARY KEY,
    bolge_id      INTEGER NOT NULL REFERENCES bolgeler (bolge_id),
    bayi_kodu     TEXT NOT NULL UNIQUE,
    bayi_adi      TEXT NOT NULL,
    sehir         TEXT NOT NULL,
    ilce          TEXT NOT NULL,
    vergi_no      TEXT NOT NULL,
    telefon       TEXT NOT NULL,
    eposta        TEXT NOT NULL,
    aktif         INTEGER NOT NULL DEFAULT 1 CHECK (aktif IN (0, 1)),
    acilis_tarihi TEXT NOT NULL,
    tenant_id     TEXT NOT NULL DEFAULT 't-kurum'
);

CREATE TABLE IF NOT EXISTS musteri_segmentleri (
    segment_id    INTEGER PRIMARY KEY,
    segment_adi   TEXT NOT NULL UNIQUE,
    indirim_orani REAL NOT NULL DEFAULT 0,
    min_ciro      REAL NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS musteriler (
    musteri_id           INTEGER PRIMARY KEY,
    segment_id           INTEGER NOT NULL REFERENCES musteri_segmentleri (segment_id),
    bayi_id              INTEGER NOT NULL REFERENCES bayiler (bayi_id),
    ad_soyad             TEXT NOT NULL,
    unvan                TEXT NOT NULL,
    sehir                TEXT NOT NULL,
    tckn                 TEXT NOT NULL,
    telefon              TEXT NOT NULL,
    eposta               TEXT NOT NULL,
    kayit_tarihi         TEXT NOT NULL,
    son_alisveris_tarihi TEXT,
    aktif                INTEGER NOT NULL DEFAULT 1 CHECK (aktif IN (0, 1)),
    kredi_limiti         REAL NOT NULL DEFAULT 0,
    tenant_id            TEXT NOT NULL DEFAULT 't-kurum'
);

CREATE TABLE IF NOT EXISTS kategoriler (
    kategori_id     INTEGER PRIMARY KEY,
    ust_kategori_id INTEGER REFERENCES kategoriler (kategori_id),
    kategori_adi    TEXT NOT NULL UNIQUE,
    kdv_orani       REAL NOT NULL DEFAULT 20.0
);

CREATE TABLE IF NOT EXISTS urunler (
    urun_id        INTEGER PRIMARY KEY,
    kategori_id    INTEGER NOT NULL REFERENCES kategoriler (kategori_id),
    urun_kodu      TEXT NOT NULL UNIQUE,
    urun_adi       TEXT NOT NULL,
    birim          TEXT NOT NULL DEFAULT 'Adet',
    birim_fiyat    REAL NOT NULL,
    maliyet_fiyati REAL NOT NULL,
    kdv_orani      REAL NOT NULL DEFAULT 20.0,
    aktif          INTEGER NOT NULL DEFAULT 1 CHECK (aktif IN (0, 1))
);

CREATE TABLE IF NOT EXISTS depolar (
    depo_id   INTEGER PRIMARY KEY,
    bolge_id  INTEGER NOT NULL REFERENCES bolgeler (bolge_id),
    depo_kodu TEXT NOT NULL UNIQUE,
    depo_adi  TEXT NOT NULL,
    sehir     TEXT NOT NULL,
    kapasite  INTEGER NOT NULL CHECK (kapasite > 0),
    aktif     INTEGER NOT NULL DEFAULT 1 CHECK (aktif IN (0, 1))
);

CREATE TABLE IF NOT EXISTS stok_hareketleri (
    hareket_id     INTEGER PRIMARY KEY,
    depo_id        INTEGER NOT NULL REFERENCES depolar (depo_id),
    urun_id        INTEGER NOT NULL REFERENCES urunler (urun_id),
    hareket_turu   TEXT NOT NULL CHECK (hareket_turu IN ('giris', 'cikis', 'transfer', 'iade')),
    miktar         INTEGER NOT NULL,
    hareket_tarihi TEXT NOT NULL,
    aciklama       TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS kampanyalar (
    kampanya_id      INTEGER PRIMARY KEY,
    kampanya_adi     TEXT NOT NULL,
    baslangic_tarihi TEXT NOT NULL,
    bitis_tarihi     TEXT NOT NULL,
    indirim_yuzdesi  REAL NOT NULL DEFAULT 0,
    aktif            INTEGER NOT NULL DEFAULT 1 CHECK (aktif IN (0, 1))
);

CREATE TABLE IF NOT EXISTS departmanlar (
    departman_id  INTEGER PRIMARY KEY,
    departman_adi TEXT NOT NULL UNIQUE,
    butce         REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS calisanlar (
    calisan_id       INTEGER PRIMARY KEY,
    departman_id     INTEGER NOT NULL REFERENCES departmanlar (departman_id),
    bayi_id          INTEGER NOT NULL REFERENCES bayiler (bayi_id),
    ad_soyad         TEXT NOT NULL,
    unvan            TEXT NOT NULL,
    sehir            TEXT NOT NULL,
    tckn             TEXT NOT NULL,
    ise_giris_tarihi TEXT NOT NULL,
    aktif            INTEGER NOT NULL DEFAULT 1 CHECK (aktif IN (0, 1))
);

CREATE TABLE IF NOT EXISTS siparisler (
    siparis_id     INTEGER PRIMARY KEY,
    musteri_id     INTEGER NOT NULL REFERENCES musteriler (musteri_id),
    bayi_id        INTEGER NOT NULL REFERENCES bayiler (bayi_id),
    calisan_id     INTEGER NOT NULL REFERENCES calisanlar (calisan_id),
    kampanya_id    INTEGER REFERENCES kampanyalar (kampanya_id),
    siparis_no     TEXT NOT NULL UNIQUE,
    siparis_tarihi TEXT NOT NULL,
    durum          TEXT NOT NULL CHECK (durum IN ('tamamlandi', 'beklemede', 'kargoda', 'iptal')),
    odeme_yontemi  TEXT NOT NULL CHECK (odeme_yontemi IN ('Kredi Kartı', 'Havale', 'Vadeli')),
    brut_tutar     REAL NOT NULL,
    indirim_tutari REAL NOT NULL DEFAULT 0,
    kdv_tutari     REAL NOT NULL DEFAULT 0,
    toplam_tutar   REAL NOT NULL,
    iade_tutari    REAL NOT NULL DEFAULT 0,
    tenant_id      TEXT NOT NULL DEFAULT 't-kurum'
);

CREATE TABLE IF NOT EXISTS siparis_kalemleri (
    kalem_id       INTEGER PRIMARY KEY,
    siparis_id     INTEGER NOT NULL REFERENCES siparisler (siparis_id),
    urun_id        INTEGER NOT NULL REFERENCES urunler (urun_id),
    miktar         INTEGER NOT NULL CHECK (miktar > 0),
    birim_fiyat    REAL NOT NULL,
    indirim_tutari REAL NOT NULL DEFAULT 0,
    kdv_tutari     REAL NOT NULL DEFAULT 0,
    satir_tutari   REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS iadeler (
    iade_id            INTEGER PRIMARY KEY,
    siparis_id         INTEGER NOT NULL REFERENCES siparisler (siparis_id),
    musteri_id         INTEGER NOT NULL REFERENCES musteriler (musteri_id),
    iade_tarihi        TEXT NOT NULL,
    neden              TEXT NOT NULL,
    durum              TEXT NOT NULL CHECK (durum IN ('onaylandi', 'beklemede', 'reddedildi')),
    toplam_iade_tutari REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS iade_kalemleri (
    iade_kalem_id INTEGER PRIMARY KEY,
    iade_id       INTEGER NOT NULL REFERENCES iadeler (iade_id),
    urun_id       INTEGER NOT NULL REFERENCES urunler (urun_id),
    ret_qty       INTEGER NOT NULL CHECK (ret_qty > 0),
    iade_tutari   REAL NOT NULL,
    aciklama      TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS faturalar (
    fatura_id       INTEGER PRIMARY KEY,
    siparis_id      INTEGER NOT NULL REFERENCES siparisler (siparis_id),
    musteri_id      INTEGER NOT NULL REFERENCES musteriler (musteri_id),
    fatura_no       TEXT NOT NULL UNIQUE,
    fatura_tarihi   TEXT NOT NULL,
    vade_tarihi     TEXT NOT NULL,
    kdv_haric_tutar REAL NOT NULL,
    kdv_tutari      REAL NOT NULL,
    genel_toplam    REAL NOT NULL,
    odenen_tutar    REAL NOT NULL DEFAULT 0,
    durum           TEXT NOT NULL CHECK (durum IN ('odendi', 'kismi_odendi', 'odenmedi', 'vadesi_gecmis', 'iptal')),
    tenant_id       TEXT NOT NULL DEFAULT 't-kurum'
);

CREATE TABLE IF NOT EXISTS odemeler (
    odeme_id      INTEGER PRIMARY KEY,
    fatura_id     INTEGER NOT NULL REFERENCES faturalar (fatura_id),
    musteri_id    INTEGER NOT NULL REFERENCES musteriler (musteri_id),
    odeme_tarihi  TEXT NOT NULL,
    tutar         REAL NOT NULL,
    odeme_yontemi TEXT NOT NULL,
    iban          TEXT NOT NULL,
    durum         TEXT NOT NULL CHECK (durum IN ('basarili', 'beklemede', 'iptal'))
);

CREATE TABLE IF NOT EXISTS satis_hedefleri (
    hedef_id          INTEGER PRIMARY KEY,
    bayi_id           INTEGER NOT NULL REFERENCES bayiler (bayi_id),
    yil               INTEGER NOT NULL,
    ay                INTEGER NOT NULL CHECK (ay BETWEEN 1 AND 12),
    hedef_tutar       REAL NOT NULL,
    gerceklesen_tutar REAL NOT NULL
);

-- RBAC hassas tablo: standart analist rolüne kapalıdır.
CREATE TABLE IF NOT EXISTS maaslar (
    maas_id    INTEGER PRIMARY KEY,
    calisan_id INTEGER NOT NULL REFERENCES calisanlar (calisan_id),
    donem_yil  INTEGER NOT NULL,
    donem_ay   INTEGER NOT NULL CHECK (donem_ay BETWEEN 1 AND 12),
    brut_maas  REAL NOT NULL,
    net_maas   REAL NOT NULL,
    prim       REAL NOT NULL DEFAULT 0,
    iban       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS masraflar (
    masraf_id     INTEGER PRIMARY KEY,
    departman_id  INTEGER NOT NULL REFERENCES departmanlar (departman_id),
    bayi_id       INTEGER NOT NULL REFERENCES bayiler (bayi_id),
    masraf_tarihi TEXT NOT NULL,
    kategori      TEXT NOT NULL,
    tutar         REAL NOT NULL,
    aciklama      TEXT NOT NULL,
    onay_durumu   TEXT NOT NULL CHECK (onay_durumu IN ('onaylandi', 'beklemede', 'reddedildi'))
);

CREATE TABLE IF NOT EXISTS tedarikciler (
    tedarikci_id  INTEGER PRIMARY KEY,
    tedarikci_adi TEXT NOT NULL,
    sehir         TEXT NOT NULL,
    vergi_no      TEXT NOT NULL,
    telefon       TEXT NOT NULL,
    eposta        TEXT NOT NULL,
    vade_gun      INTEGER NOT NULL DEFAULT 30
);

CREATE TABLE IF NOT EXISTS satin_alma_siparisleri (
    satin_alma_id  INTEGER PRIMARY KEY,
    tedarikci_id   INTEGER NOT NULL REFERENCES tedarikciler (tedarikci_id),
    depo_id        INTEGER NOT NULL REFERENCES depolar (depo_id),
    urun_id        INTEGER NOT NULL REFERENCES urunler (urun_id),
    siparis_tarihi TEXT NOT NULL,
    teslim_tarihi  TEXT,
    miktar         INTEGER NOT NULL CHECK (miktar > 0),
    birim_maliyet  REAL NOT NULL,
    toplam_tutar   REAL NOT NULL,
    durum          TEXT NOT NULL CHECK (durum IN ('teslim_alindi', 'yolda', 'onay_bekliyor', 'iptal'))
);

CREATE TABLE IF NOT EXISTS sevkiyatlar (
    sevkiyat_id   INTEGER PRIMARY KEY,
    siparis_id    INTEGER NOT NULL REFERENCES siparisler (siparis_id),
    depo_id       INTEGER NOT NULL REFERENCES depolar (depo_id),
    kargo_firmasi TEXT NOT NULL,
    takip_no      TEXT NOT NULL UNIQUE,
    cikis_tarihi  TEXT NOT NULL,
    teslim_tarihi TEXT,
    durum         TEXT NOT NULL CHECK (durum IN ('teslim_edildi', 'dagitimda', 'hazirlaniyor', 'iade_dondu'))
);

CREATE TABLE IF NOT EXISTS destek_talepleri (
    talep_id       INTEGER PRIMARY KEY,
    musteri_id     INTEGER NOT NULL REFERENCES musteriler (musteri_id),
    siparis_id     INTEGER REFERENCES siparisler (siparis_id),
    calisan_id     INTEGER NOT NULL REFERENCES calisanlar (calisan_id),
    konu           TEXT NOT NULL,
    oncelik        TEXT NOT NULL CHECK (oncelik IN ('dusuk', 'orta', 'yuksek', 'kritik')),
    durum          TEXT NOT NULL CHECK (durum IN ('acik', 'inceleniyor', 'cozuldu', 'kapali')),
    acilis_tarihi  TEXT NOT NULL,
    kapanis_tarihi TEXT
);

-- Çapraz dilli şema eşleme tabloları (Cross-lingual English-abbreviated tables/columns)
CREATE TABLE IF NOT EXISTS cust_loyalty (
    loyalty_id  INTEGER PRIMARY KEY,
    cust_id     INTEGER NOT NULL UNIQUE REFERENCES musteriler (musteri_id),
    tier_code   TEXT NOT NULL CHECK (tier_code IN ('BRONZE', 'SILVER', 'GOLD', 'PLATINUM')),
    pts_bal     INTEGER NOT NULL DEFAULT 0,
    enrolled_dt TEXT NOT NULL,
    last_upd_dt TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS inv_ledger (
    ledger_id INTEGER PRIMARY KEY,
    cust_id   INTEGER NOT NULL REFERENCES musteriler (musteri_id),
    inv_id    INTEGER NOT NULL REFERENCES faturalar (fatura_id),
    prod_id   INTEGER NOT NULL REFERENCES urunler (urun_id),
    inv_amt   REAL NOT NULL,
    ret_qty   INTEGER NOT NULL DEFAULT 0,
    net_bal   REAL NOT NULL,
    tx_dt     TEXT NOT NULL,
    curr_code TEXT NOT NULL DEFAULT 'TRY'
);

CREATE TABLE IF NOT EXISTS prod_pricing_hist (
    hist_id    INTEGER PRIMARY KEY,
    prod_id    INTEGER NOT NULL REFERENCES urunler (urun_id),
    old_prc    REAL NOT NULL,
    new_prc    REAL NOT NULL,
    chg_dt     TEXT NOT NULL,
    chg_reason TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS wh_stock_snap (
    snap_id      INTEGER PRIMARY KEY,
    wh_id        INTEGER NOT NULL REFERENCES depolar (depo_id),
    prod_id      INTEGER NOT NULL REFERENCES urunler (urun_id),
    qty_on_hand  INTEGER NOT NULL,
    qty_reserved INTEGER NOT NULL DEFAULT 0,
    snap_dt      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_bayiler_sehir ON bayiler (sehir);
CREATE INDEX IF NOT EXISTS idx_musteriler_sehir ON musteriler (sehir);
CREATE INDEX IF NOT EXISTS idx_siparisler_tarih_durum ON siparisler (siparis_tarihi, durum);
CREATE INDEX IF NOT EXISTS idx_faturalar_vade_durum ON faturalar (vade_tarihi, durum);
CREATE INDEX IF NOT EXISTS idx_inv_ledger_cust_prod ON inv_ledger (cust_id, prod_id);
