# Mimari Karar Kayıtları (ADR)

Her önemli mimari karar burada kayıt altına alınır. Bir kararı değiştirmek için eski ADR
silinmez; yeni bir ADR yazılır ve eskisi `Yerini aldı: ADR-XXXX` olarak işaretlenir.

| No | Başlık | Durum |
|---|---|---|
| [0001](0001-modular-monolith.md) | Modular Monolith | Kabul edildi |
| [0002](0002-offline-first-on-prem.md) | Offline-first ve on-prem çalışma (KVKK) | Kabul edildi |
| [0003](0003-model-agnostic-model-adapter.md) | Modelden bağımsızlık: `ModelAdapter` | Kabul edildi |
| [0004](0004-rbac-before-schema-and-no-model-db-access.md) | RBAC şemadan önce; model veritabanına erişemez | Kabul edildi |
| [0005](0005-reject-security-violations.md) | Güvenlik ihlalleri reddedilir, yeniden denenmez | Kabul edildi |
| [0006](0006-bounded-retry-budget.md) | Sınırlı yeniden deneme bütçesi | Kabul edildi |
| [0007](0007-defense-in-depth-sql-security.md) | SQL güvenliğinde derinlemesine savunma (SQLGlot yetmez) | Kabul edildi |
| [0008](0008-deterministic-numbers-in-results.md) | Sonuç sayıları deterministik; model sayı üretmez | Kabul edildi |
| [0009](0009-dataset-licensing.md) | Veri kümesi lisansları; BIRDTurk yalnız değerlendirme | Kabul edildi |
| [0010](0010-technology-candidates-decided-by-benchmarks.md) | Teknoloji yığını aday; karar AR-09'da ölçümle | Kabul edildi |
| [0011](0011-offline-oidc-jwt-auth.md) | Çevrimdışı OIDC / JWT doğrulaması (`PyJWT[crypto]`) | Kabul edildi |

Yeni ADR için [şablon](template.md) kullanılır. ADR'ler Türkçe yazılır.
