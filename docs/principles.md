# TRSQL Mimari Tasarım İlkeleri

Her tasarım kararı ve kod incelemesi bu on ilkeye göre değerlendirilir. Bir PR bir ilkeyi
zayıflatıyorsa bunu açıkça belirtmeli ve ADR ile gerekçelendirmelidir.

| # | İlke | Anlamı | Pratikte | Nasıl denetlenir |
|---|---|---|---|---|
| 01 | **Turkish-first** | Türkçe dil özelliklerine öncelik. | `.lower()` yerine `tr_casefold()`; ekler, göreli zaman, sayı sözcükleri L2'de çözülür; kullanıcı mesajları Türkçe. | `tests/unit/test_turkish_nlp.py`; TURSpider/BIRDTurk sonuçları |
| 02 | **Offline-first** | Çevrimdışı ve yerel çalışma. | Çalışma zamanında dış ağ çağrısı yok; model ve gömme dosyaları yerelden okunur; veri kurum dışına çıkmaz (KVKK). | `boundaries.toml` HTTP istemcilerini yasaklar; ADR-0002 |
| 03 | **Small Model-first** | Büyük model yerine küçük ve desteklenmiş model. | 3B–9B, 4-bit; ≈6,8 GB VRAM bütçesi. Model zayıflığı L2/L3/L4 ile desteklenir. | VRAM/RAM ölçümü her deneyde zorunlu |
| 04 | **Schema-aware** | Veritabanı yapısını anlayarak sorgu üretme. | PK/FK grafiği, JOIN yolu, sütun açıklamaları isteme girer. | Schema Linking Accuracy |
| 05 | **Knowledge-grounded** | Kurumun gerçek bilgisine ve iş kurallarına dayanma. | Yalnız onaylı kurallar ve sürümlü metrikler kullanılır; model iş kuralı uydurmaz. | `test_happy_path` (onaysız kural isteme girmez) |
| 06 | **Security-by-design** | Güvenlik başlangıçta tasarlanır. | RBAC şemadan önce; 8 aşamalı L6; salt okunur yürütme; güvenlik ihlali tekrar denenmez. | `pytest -m security` (CI gate G4) |
| 07 | **Model-agnostic** | Tek bir modele bağımlı olmama. | Her model `ModelAdapter` arkasında; model değişimi başka modüle dokunmaz. | ADR-0003; sınır denetimi |
| 08 | **Database-agnostic** | Adaptörlerle farklı SQL dialect'lerini destekleme. | `DatabaseAdapter` portu; SQLGlot dialect parametresi. | SQLite + PostgreSQL testleri |
| 09 | **Explainable** | SQL, veri kaynakları ve kararlar açıklanabilir. | Rapor SQL'i, metrik sürümünü ve kaynağı gösterir; sayılar yalnız sonuçtan gelir; her aşama audit'lenir. | ADR-0008; `ResultReport.metrics_used` |
| 10 | **Benchmark-driven** | Teknoloji kararları ölçülebilir deneylere dayanır. | Her aday (model, retriever, NLP) D0–D8 ablasyonunda ölçülür; karar AR-09'da verilir. | `docs/evaluation/evaluation-plan.md` |

## İlke çatışmalarında öncelik sırası

1. **Security-by-design** (06) — her zaman önce gelir.
2. **Offline-first** (02) — KVKK gereği pazarlık konusu değildir.
3. **Explainable** (09)
4. **Benchmark-driven** (10)
5. Diğerleri

Örnek: Daha yüksek doğruluk veren bir bulut modeli Offline-first ilkesini ihlal ettiği
için üretim adayı olamaz; yalnızca karşılaştırma tabanı (upper bound) olarak, kurumsal veri
içermeyen açık benchmark'larda kullanılabilir.
