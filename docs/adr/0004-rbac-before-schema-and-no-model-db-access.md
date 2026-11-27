# ADR-0004: RBAC şemadan önce; model veritabanına erişemez

- **Durum:** Kabul edildi
- **Tarih:** 2026-11-27
- **İlgili AR paketi:** AR-07
- **İlgili ilkeler:** 06, 09

## Bağlam
v0.1'de yetkilendirme şema analizinden sonra konumlanıyordu. Bu durumda model,
kullanıcının göremeyeceği tablo ve sütunların adlarını isteminde görür; bu hem bilgi
sızıntısıdır (ör. `salaries`, `tc_kimlik_no` sütununun varlığı) hem de modeli yetkisiz
sorgu üretmeye iter. Ayrıca LLM çıktısı güvenilmeyen girdidir; istem enjeksiyonuyla
yönlendirilebilir.

## Karar
1. **Yetkilendirme, şema bilgisine erişilmeden önce yapılır.** L1, `AuthContext`'i üretir ve
   `auth.scope_schema()` kullanıcının görmeye yetkili olmadığı tablo, sütun ve FK
   ilişkilerini şemadan çıkarır. L2–L5 yalnızca bu **kapsamlı şemayı** görür.
2. **Model veritabanına hiçbir yoldan erişemez.**
   - `model_engine` yalnızca `core`'u içe aktarabilir; veritabanı sürücüleri yalnızca
     `database_adapters` içinde kullanılabilir (`boundaries.toml`).
   - `DatabaseAdapter.execute()` yalnızca `ApprovedQuery` kabul eder;
     `ApprovedQuery` onaylanmamış bir `ValidationReport` ile oluşturulamaz.
   - Veritabanına giden tek yol: `SQLCandidate → L6 → PolicyEngine → ApprovedQuery → L7`.
3. L6 doğrulayıcısı **tam şemayı** ve `AuthContext`'i görür; böylece yetkisiz bir tabloya
   erişim denemesini "tablo yok" (düzeltilebilir) ile karıştırmaz ve **güvenlik ihlali**
   olarak sınıflandırır. Ret mesajları gizli nesnelerin adını içermez.

## Sonuçlar
**Olumlu:** Sızıntı yüzeyi küçülür; model yetkisiz nesneleri "bilmediği" için onlara
yönelik sorgu üretme olasılığı düşer; kalan denemeler L6'da yakalanır.
**Olumsuz:** Her kullanıcı için ayrı kapsamlı şema → isteme özgü önbellek gerekir
(AR-07'de rol bazlı önbellek).

## Doğrulama
`tests/unit/test_schema.py`, `test_happy_path` (istemde `salaries`/`tax_number` yok),
`tests/security/*`, sınır denetimi.
