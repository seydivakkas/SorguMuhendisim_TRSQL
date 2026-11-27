# ADR-0007: SQL güvenliğinde derinlemesine savunma

- **Durum:** Kabul edildi
- **Tarih:** 2026-11-27
- **İlgili AR paketi:** AR-07
- **İlgili ilkeler:** 06, 08

## Bağlam
SQLGlot, SQL'i birçok dialect'te ayrıştırıp AST üzerinde analiz yapmayı sağlar. Ancak
ayrıştırıcı ile veritabanının ayrıştırıcısı arasında fark olabilir (dialect uç durumları,
yeni sözdizimi). Tek bir kontrol katmanına güvenmek tek hata noktasıdır.

## Karar
Güvenlik en az üç bağımsız katmanda uygulanır; her katman diğerleri başarısız olsa da
tek başına zararı engellemeyi hedefler:

| Katman | Mekanizma |
|---|---|
| L1 | Şema kapsamlama (yetkisiz nesneler modele görünmez) |
| L6 | SQLGlot ile 8 kontrol: yalnız tek `SELECT`/`WITH`, yasaklı düğüm ve fonksiyon listesi, sistem kataloğu yasağı, tablo/sütun yetkisi, `*` ile yasaklı sütun, maliyet |
| L6 | `PolicyEngine`: zorunlu `LIMIT` (kullanıcı ve sistem sınırının küçüğü), zaman aşımı |
| L7 | Veritabanı: salt okunur bağlantı/rol, `statement_timeout`, satır sınırı; SQLite'ta `mode=ro` + `query_only` + authorizer; PostgreSQL'de salt okunur rol + RLS (AR-07) |

Kullanıcı girdisi SQL'e **asla string birleştirme ile** eklenmez; değer gerektiren
deterministik sorgularda parametre bağlama kullanılır.

## Sonuçlar
**Olumlu:** Doğrulayıcıdaki bir hata tek başına veri kaybına yol açmaz
(`tests/security/test_sqlite_adapter.py` bu senaryoyu sahte onaylı raporla test eder).
**Olumsuz:** Bazı meşru sorgular (ör. `pragma` gerektiren) desteklenmez.

## Doğrulama
CI gate **G4** (`pytest -m security`).
