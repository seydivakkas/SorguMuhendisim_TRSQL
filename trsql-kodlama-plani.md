# TRSQL — Genel Kodlama Planı

28 Kasım 2026 · Seydi için · Dayanak: `trsql-birlesik-arastirma-raporu.md` ve `SorguMuhendisim_TRSQL` PR #1 iskeleti (commit `3ab4966`)

Bu plan, TRSQL'i kendi bilgisayarında (RTX 4070 Laptop 8 GB, 32 GB RAM, Windows) adım adım kodlaman için yazıldı. PR #1'deki mimariyi değiştirmez, onun üzerine kurulur: Modular Monolith, L0–L9 katmanları, ADR-0001..0010, `boundaries.toml`, G1–G5 kapıları, D0–D8 deney planı ve AR-01..AR-10 paketleri.

**Temel ilke:** Önce ölçmeyi kur, sonra bileşen ekle. Her faz bir D-kademesi üretir. Bir bileşen, önceki kademeye göre EX'i düşürmeden (ya da düşüşü güvenlik kazancıyla gerekçelendirerek) birleştirilir (E1 kapısı).

---

## 0. Ön koşullar

- [ ] PR #1'i incele ve `main`'e birleştir. Bu plandaki dosya yolları o iskelete göre.
- [ ] `AGENTS.md`'yi oku. Özellikle §1'deki değişmez kurallar bu planın her adımında geçerli:
  - model veritabanına dokunmaz (ADR-0004)
  - RBAC şemadan önce gelir
  - güvenlik ihlali yeniden denenmez (ADR-0005)
  - yeniden deneme bütçesi en fazla 5 (ADR-0006)
  - `backend/` içinde ağ çağrısı yapılmaz (ADR-0002)
  - kullanıcıya gösterilen sayılar modelden gelmez (ADR-0008)
  - BIRDTurk eğitim verisine girmez (ADR-0009)
- [ ] Her iş tek bir AR paketine ve mümkünse tek bir modüle bağlanır. Her iş için `.github/ISSUE_TEMPLATE/work-package.md` ile bir issue açılır.

---

## 1. Teknoloji yığını

| Katman / ihtiyaç | Seçim | Nerede (modül) | Not |
| --- | --- | --- | --- |
| Dil ve sözleşmeler | Python 3.12, Pydantic v2 | `core` | Mevcut |
| SQL ayrıştırma ve doğrulama | SQLGlot | `sql_validator`, `policy_engine` | Mevcut; `boundaries.toml` başka modüle izin vermiyor |
| API | FastAPI + Uvicorn | `api` | Mevcut iskelet |
| LLM çıkarımı | llama.cpp: `llama-cpp-python` (CUDA wheel) veya ayrı `llama-server` süreci | `model_engine` | Öneri: `llama-cpp-python` (aşağıda F2 notu) |
| Model biçimi | GGUF Q4_K_M / Q5_K_M (7–9B), Q5_K_M / Q6_K (3–4B) | `models/` (git dışı) | SHA256 doğrulamalı indirme betiği |
| Gömme (embedding) | BGE-M3 GGUF, llama.cpp embedding modunda, **CPU** | `model_engine` (yeni `EmbeddingAdapter` portu) | `rag` modülü `torch` veya `llama_cpp` içe aktaramaz; port ile çözülür |
| Anahtar kelime arama | `rank-bm25` (saf Python) | `rag` | |
| Vektör arama | `faiss-cpu` | `rag` | Kısıtlı paket değil |
| Değer arama | MinHash-LSH (`datasketch`) + karakter n-gram | `rag` | Türkçe ekli biçimler için önce lemma |
| Türkçe morfoloji | Kural tabanlı (mevcut) → opsiyonel `zemberek-python` | `turkish_nlp` | Zemberek JVM ister; D4'te ölçülerek karar verilir |
| Veritabanı | SQLite (mevcut), PostgreSQL 16 (salt okunur rol + RLS) | `database_adapters` | `psycopg` 3 |
| Lehçe çevirisi (testler) | SQLGlot transpile, DuckDB (opsiyonel) | `benchmarks/` | Değerlendirme tarafı, `backend` dışı |
| Sentetik veri | `Faker` (`tr_TR`) + şablon + LLM | `synthetic_data/` | |
| Gözlemlenebilirlik | Yapısal JSON log, opsiyonel OpenTelemetry | `observability` | |
| Arayüz (L0) | React + TypeScript (Vite) | `frontend/` | AR-10 |
| Kalite | ruff, mypy --strict, pytest, pytest-cov | — | Mevcut G1–G5 |

**Windows notları:**
- vLLM Windows'ta yerel çalışmaz (WSL2 gerekir). Tek kullanıcılı prototipte llama.cpp yeterli (rapor 6(b)).
- `llama-cpp-python` CUDA derlemesi için Visual Studio Build Tools ve CUDA Toolkit gerekir. Hazır CUDA wheel kullanmak daha kolay. Sürümü `models/README.md`'ye yaz.
- Bütçe: `configs/default.toml` → `vram_budget_mb = 6800`. Bu sınır her deneyde ölçülür (E3).

---

## 2. Faz haritası

| Faz | AR paketi | D-kademesi | Çıktı | Kabul kapısı | Tahmini süre |
| --- | --- | --- | --- | --- | --- |
| F0 | — | — | Yerel ortam, modeller indirilmiş, G1–G5 yeşil | G1–G5 | 2–3 gün |
| F1 | AR-08 (öne çekildi) | altyapı | Veri yükleyiciler, değerlendirme koşucusu, EX/Valid SQL metrikleri, deney kaydı | Altın SQL'ler kendileriyle %100 EX | 1–1,5 hafta |
| F2 | AR-05 + AR-02 | D0, D1 | `LlamaCppAdapter`, M-Schema istemi, ilk model tablosu | E3 (VRAM ≤ 6,8 GB) | 1–1,5 hafta |
| F3 | AR-03 | D2 | Hibrit schema linking, Steiner JOIN, linking metrikleri | Recall ≥ 0,95 | 1 hafta |
| F4 | AR-04 | D3 | BM25 + FAISS + RRF, LSH değer araması, semantik katman | Recall@5 ≥ 0,9; E1 | 1,5–2 hafta |
| F5 | AR-03 | D4 | Türkçe zaman, normalizasyon, belirsizlik tespiti | Belirsizlik setinde doğru netleştirme; E1 | 1 hafta |
| F6 | AR-07 | D5 | `PostgresAdapter`, RLS, EXPLAIN eşiği, Semantic + Business Rule kontrolleri, saldırı seti | E2 (%100 yakalama) | 1,5–2 hafta |
| F7 | AR-05 | D6 | Mod yönlendirme (direkt → thinking), N aday + oylama | P95 < 15 sn; E1 | 1 hafta |
| F8 | AR-06 | D7 (koşullu) | Kurumsal sentetik veri üreticisi; gerekirse QLoRA deneyi | ≥ +4 puan net kazanç yoksa D7 atlanır | 1–2 hafta |
| F9 | AR-09 | D8 | Tam sistem ölçümü, nihai ADR'ler, v1.0 mimari | Tüm E kapıları | 1 hafta |
| F10 | AR-10 | — | Frontend (L0), dağıtım, API sertleştirme, opsiyonel MCP arayüzü | Kabul senaryoları | 2–3 hafta |

Süreler tek kişi ve yarı zamanlı çalışma için kaba tahmindir.

---

## 3. Fazlar ve görevler

Her görevde aynı döngü uygulanır: önce test, sonra kod, sonra G1–G5. Davranış değişikliği yapan her görev test ile gelir.

### F0 — Ortam ve temel

**Hedef:** Windows'ta iskeletin çalışması ve modellerin yerelde hazır olması.

- [ ] `py -3.12 -m venv .venv`, `pip install -e ".[dev,api]"`, G1–G5'i çalıştır (`docs/guides/getting-started.md`).
- [ ] NVIDIA sürücüsü, CUDA Toolkit ve `llama-cpp-python` (CUDA) kurulumu. `python -c "import llama_cpp; print(llama_cpp.__version__)"`.
- [ ] `models/download.py` (yeni, `backend` dışı betik): model adı → HF URL + **SHA256**. İndirme yalnız bu betikle ve elle yapılır; çalışma zamanında indirme yok (ADR-0002).
- [ ] İlk modeller (GGUF):
  - Hati-Glint-SQL-9B Q4_K_M
  - XiYanSQL-QwenCoder-7B-2504 Q5_K_M
  - Arctic-Text2SQL-R1-7B Q5_K_M
  - Qwen3-4B-Instruct-2507 Q5_K_M (küçük kontrol modeli)
  - BGE-M3 GGUF (gömme modeli)
- [ ] `models/README.md`: her model için model kartı bağlantısı, lisans, nicemleme, SHA256, boyut. Lisans tablosu rapor 3(a) ile tutarlı olmalı. XiYan-3B ve Qwen2.5-Coder-3B yalnızca akademik kıyas için.
- [ ] `.env` dosyasını `.env.example`'dan oluştur (`TRSQL_MODEL_PATH`). `.env` commit'lenmez.

**Kabul:** G1–G5 yerelde yeşil. `nvidia-smi` ile kart ve sürücü kaydedilmiş. Model dosyalarının SHA256 değerleri betikle doğrulanmış.

### F1 — Değerlendirme altyapısı (AR-08 öne çekildi)

**Hedef:** D0'dan önce ölçebilir olmak. Bütün sonraki fazlar bu koşucuyla ölçülür.

Dosyalar:

```
benchmarks/
├── loaders/
│   ├── turspider.py      # dev: 1.034 soru
│   ├── birdturk.py       # dev: 1.534 soru (yalnız değerlendirme, ADR-0009)
│   └── enterprise.py     # kurumsal sentetik set (F1b)
├── metrics/
│   ├── execution.py      # EX: sonuç kümesi eşleşmesi, ORDER BY kuralı, float toleransı
│   ├── test_suite.py     # Test Suite Accuracy (çoklu DB örneği)
│   ├── validity.py       # Valid SQL Rate (parse edilebilir / çalıştırılabilir)
│   ├── linking.py        # Schema Linking P/R/F1 (altın tablolar SQLGlot ile altın SQL'den)
│   └── safety.py         # Unsafe SQL Rate (üretilen ve DB'ye ulaşan ayrı)
├── runner.py             # config.toml → predictions.jsonl + metrics.json
└── report.py             # model × kademe × veri kümesi tablosu, McNemar / bootstrap
experiments/
└── 2026-12-xx-d0-baseline/
    ├── config.toml
    ├── predictions.jsonl
    └── metrics.json
```

- [ ] Veri yükleyiciler. Ham veri git'e girmez; `datasets/README.md`'ye kaynak, sürüm, lisans ve dosya hash'i yazılır. BIRDTurk için HF kartındaki `cc-by-nc-sa-4.0` lisansı not edilir.
- [ ] EX metriği: yalnız `ORDER BY` varsa satır sırası karşılaştırılır; float'lar sabit basamakla yuvarlanır; sütun sırası ve adları yok sayılır (BIRD değerlendiricisiyle aynı kural).
- [ ] `runner.py`, `backend.orchestration` üzerinden tam hattı çağırır. Koşucu kirli çalışma ağacında çalışmayı reddeder ve git hash'ini kaydeder.
- [ ] Donanım kaydı: sürücü, CUDA, llama.cpp sürümü, nicemleme, bağlam, güç modu, tepe VRAM (`nvidia-smi` örnekleme).
- [ ] İstatistik: iki kademe arasında McNemar testi ve eşli bootstrap ile %95 güven aralığı.

**F1b — Kurumsal sentetik test seti (değerlendirme amaçlı, 150–250 soru):**

- [ ] `synthetic_data/schema/erp.sql`: 25–40 tablolu Türk ERP/satış/finans şeması (PostgreSQL, `tr-TR-x-icu` collation). Tablo ve sütun adları Türkçe. Bazı tablolar bilerek kısaltmalı İngilizce adlarla (`cust_id`), çapraz dilli eşlemeyi ölçmek için.
- [ ] `Faker('tr_TR')` ile sahte veri. Hücre değerleri Türkçe olmalı (İ/ı, Ş/ş, Ğ/ğ). Gerçek kişisel veri kullanılmaz.
- [ ] İş kuralları: KDV hariç net ciro, iade düşümü, vadesi geçmiş cari borç, aktif müşteri. `configs/knowledge.example.toml` biçiminde.
- [ ] Soru dağılımı: ~%60 normal, ~%15 iş kuralı gerektiren, ~%10–15 belirsiz (beklenen yanıt: netleştirme), ~%10 yanıtsız (beklenen yanıt: ret), 30 güvenlik saldırısı (ayrı set).
- [ ] Her altın SQL iki kez doğrulanır: elle + çalıştırıp boş olmayan sonuç kontrolü. Test Suite için 3 farklı veri örneği üretilir.

**Kabul:** Her veri kümesinde altın SQL kendisiyle karşılaştırıldığında EX = %100. Koşucu `FakeModelAdapter` ile uçtan uca çalışıyor. `tests/unit/test_metrics.py` EX'in sıra, float ve tekrar eden satır durumlarını kapsıyor.

### F2 — Model motoru ve taban çizgisi (D0, D1)

**Hedef:** Gerçek modeller ile ilk ölçüm.

- [ ] `backend/model_engine/llama_cpp.py`: `LlamaCppAdapter` (şu an `NotImplementedError("... AR-05")`).
  - `n_gpu_layers=-1`, `flash_attn=True`, `n_ctx` ayardan, KV cache `q8_0`, temperature 0, seed.
  - Thinking modelleri için `<think>` bloğunu ayırıp yalnız son SQL'i döndürme.
  - Yükleme sonrası VRAM, `vram_budget_mb`'yi aşıyorsa açık bir hatayla durma.
  - **Karar notu:** `llama-cpp-python` aynı süreçte çalışır ve `boundaries.toml` ile uyumludur. Ayrı `llama-server` süreci kullanılırsa HTTP istemcisi gerekir. Bu ADR-0002'nin "HTTP istemcisi yok" kuralına takılır ve yeni bir ADR ister. Öneri: `llama-cpp-python`.
- [ ] `ModelInfo` alanlarına nicemleme, bağlam uzunluğu ve SHA256 eklenir. Bu bir sözleşme değişikliğidir; ayrı adımda yapılır.
- [ ] `prompt_engine`: sürümlü iki şablon, `ddl_v1` (D0) ve `mschema_v1` (D1). M-Schema; tip, açıklama, 2–3 örnek değer ve yabancı anahtar içerir. Kişisel veri sütunlarının örnek değerleri isteme konmaz.
- [ ] Koşu matrisi: 4 model × {D0, D1} × {TURSpider dev, BIRDTurk dev, kurumsal set}.
- [ ] Bu fazın yan ürünü olarak Hati-Glint-SQL'in kendi kartındaki skorlar bağımsız olarak yeniden ölçülmüş olur (rapor 8(b), boşluk 6).

**Kabul:** Her konfigürasyonda tepe VRAM ≤ 6,8 GB veya "uygun değil" olarak raporlanmış (E3). `tests/unit/test_llama_cpp_adapter.py`, model dosyası olmadan atlanmaz; gerçek model gerektiren testler ayrı bir işaretle (`@pytest.mark.gpu`) CI dışında tutulur. Bunun için `pyproject.toml`'a marker eklenir.

### F3 — Schema linking ve JOIN yolu (D2)

- [ ] `schema_linking`: mevcut sözlük tabanlı linker + gömme benzerliği (F4'teki `EmbeddingAdapter` hazır olunca) + çift yönlü bağlama (RSL-SQL fikri: hem budanmış hem tam şema ile aday üretip sonuçları karşılaştırma, deneysel kol).
- [ ] `schema_intelligence`: Steiner JOIN zaten var. Budamadan sonra gereken ara tabloların her zaman eklendiğini test et.
- [ ] Token bütçesi: 4K bağlamda şema + istem + few-shot sığmalı. KaSLA fikri: sütunları önem puanına göre bütçe içinde seçme.
- [ ] Metrik: Schema Linking P/R/F1. Recall öncelikli; eksik tablo sonradan telafi edilemez.

**Kabul:** Kurumsal sette ve TURSpider dev'de tablo recall ≥ 0,95. E1: D2'nin EX'i D1'den düşük değil. `tests/unit/test_schema.py` budama + JOIN tamamlama durumlarıyla genişletilmiş.

### F4 — RAG ve semantik katman (D3)

- [ ] **Yeni port:** `core/ports.py` → `EmbeddingAdapter.embed(texts: list[str]) -> list[list[float]]`. Uygulaması `model_engine/embedding.py`'de (llama.cpp embedding modu, CPU). `rag` bu portu alır, bağlama `orchestration`'da yapılır. Sözleşme değişikliği olduğu için önce ayrı bir PR'da gelir. `boundaries.toml` değişmez.
- [ ] `rag` retriever'ları:
  - **Şema RAG:** tablo ve sütun açıklamaları.
  - **Örnek SQL RAG:** doğrulanmış soru-SQL çiftleri. Seçim, DAIL-SQL gibi maskeli iskelet benzerliğiyle yapılır.
  - **İş kuralı RAG:** kural tanımları *evidence* olarak isteme eklenir.
  - **Metadata RAG:** kod tabloları ve birimler.
- [ ] Hibrit arama: BM25 + FAISS + RRF (Reciprocal Rank Fusion). Ayarlar `config.toml`'dan.
- [ ] **Değer araması:** önce Türkçe lemma (`turkish_nlp`), sonra MinHash-LSH + düzenleme mesafesi. Örnek: "İstanbul'daki" → `İstanbul`. İndeks çevrimdışı oluşturulur, kişisel veri sütunları indekslenmez.
- [ ] `semantic_layer`: onaylı metrik şablonları (ciro, net satış, iade oranı, aktif müşteri). Bu sorularda SQL'i model değil şablon üretir (rapor 4(b), semantik katman alt başlığı; ADR-0008 ile uyumlu).
- [ ] Leave-one-out ablasyonu: D3'teki dört bileşen (şema, örnek, kural, değer) tek tek çıkarılarak ölçülür.

**Kabul:** Retrieval Recall@5 ≥ 0,9 (kurumsal sette ilgili kural/örnek). Gömme modeli CPU'da ve istek başına ek gecikme raporlanmış. E1 sağlanmış.

### F5 — Türkçe NLP ve belirsizlik (D4)

- [ ] `turkish_nlp/temporal.py`: "geçen ay", "son 30 gün", "geçen yılın aynı dönemi", "bu çeyrek" → somut tarih aralığı. `today` enjekte edilir (deterministik test). LLM'e somut tarih verilir.
- [ ] `turkish_nlp/normalize.py`: `tr_casefold`, ASCII yazımdan düzeltme (`musteri` → `müşteri`), eş anlamlı sözlüğü (ciro / hasılat / satış tutarı).
- [ ] Zemberek kolu: `zemberek-python` ile lemma. Kural tabanlıya göre linking recall ve gecikme farkı ölçülür; kazanç yoksa JVM bağımlılığı eklenmez.
- [ ] Belirsizlik tespiti: kural tabanlı sinyaller ("en iyi", "önemli", eksik zaman aralığı) + opsiyonel aynı LLM ile sınıflandırma istemi. Çıktı: `NEEDS_CLARIFICATION` ve Türkçe netleştirme sorusu. Model SQL için çağrılmaz.
- [ ] Yanıtsız soru: şemada karşılığı olmayan soruda ret (abstention).

**Kabul:** Belirsizlik setinde Clarification doğruluğu ve yanıtsız sette ret oranı raporlanmış. `tests/unit/test_turkish_nlp.py` en az 30 zaman ifadesi örneğiyle genişletilmiş. E1 sağlanmış.

### F6 — Güvenlik, PostgreSQL ve doğrulamanın tamamlanması (D5)

- [ ] `database_adapters/postgres.py`: `PostgresAdapter` (`psycopg` 3).
  - Bağlantı `TRSQL_PG_DSN`'den.
  - Her oturumda `SET TRANSACTION READ ONLY`, `statement_timeout`, `lock_timeout`, `SET app.user_id`.
  - `introspect()`, `information_schema`'dan yalnız izinli şemaları okur.
- [ ] `deployment/postgres/`: `nl2sql_reader` rolü (yalnız SELECT, `BYPASSRLS` yok, tablo sahibi değil), RLS politikaları, maskeli görünümler (TCKN, telefon, e-posta), `pgaudit` ayarı.
- [ ] `sql_validator` eksik aşamalar:
  - **Semantic:** örneğin `GROUP BY` ile seçili sütun tutarlılığı, toplama tipi uyumu.
  - **Business Rule:** soruda "net ciro" geçiyorsa SQL'de iade düşümü var mı. Kurallar `knowledge_base`'den gelir.
  - **Cost:** `EXPLAIN (FORMAT JSON)` maliyet ve satır eşiği. Kartezyen ve tam tablo taraması uyarıları.
- [ ] `policy_engine`: AST üzerinde dış `LIMIT`, timeout, satır sınırı (`configs/default.toml` → `[execution]`).
- [ ] Saldırı seti: `tests/security/` mevcut listeleri büyütülür. En az 30 Türkçe vaka:
  - doğrudan DDL/DML istekleri
  - dolaylı enjeksiyon ("önceki talimatları yok say")
  - hücre değerine gömülü talimat
  - yetkisiz tablo ve sütun sorguları
  - `pg_sleep`, `WITH RECURSIVE`, kartezyen çarpım
  - sistem katalogları
  - RLS atlatma denemeleri
- [ ] Lehçe: altın SQL'ler PostgreSQL'de doğrulanır, SQLite/DuckDB'ye SQLGlot ile çevrilir.

**Kabul:** E2: saldırı setinde yakalama %100, DB'ye ulaşan tehlikeli SQL 0. Meşru sorularda yanlış ret oranı raporlanmış. `pytest -m security` yeşil ve hiçbir güvenlik testi gevşetilmemiş (AGENTS.md §1.8). PostgreSQL entegrasyon testleri yerel bir test veritabanında koşar; CI'da `services: postgres` eklenir.

### F7 — Mod yönlendirme ve onarım döngüsü (D6)

- [ ] `orchestration`: karmaşıklık puanı. Girdiler:
  - `LinkedSchema` içindeki tablo sayısı
  - toplama ve iç içe yapı sinyalleri
  - zaman ifadesi
  - ilk denemenin doğrulama sonucu
- [ ] Düşük puan → doğrudan mod, tek aday. Yüksek puan veya `REPAIRABLE` → thinking modu ve/veya N=4 aday + sonuç kümesi oylaması (EllieSQL / PRISM fikri, rapor 6(b)). 8 GB'ta iki model aynı anda yüklenemeyeceği için model değil **mod** yönlendirmesi yapılır.
- [ ] Onarım döngüsü: yalnız `REPAIRABLE` hatalar geri beslenir; `SECURITY` asla (ADR-0005). `retry.max_attempts` ≤ 5 (ADR-0006).
- [ ] GBNF deneysel kolu: yalnız son SQL bloğuna dilbilgisi kısıtı uygulanır, `<think>` bloğu serbest bırakılır. Valid SQL ve EX ayrı raporlanır.

**Kabul:** Aynı veya daha yüksek EX'te P95 < 15 sn (değerlendirme planı hedefi). Retry Rate ve ortalama deneme sayısı raporlanmış. E1 sağlanmış.

### F8 — Sentetik eğitim verisi ve koşullu ince ayar (D7)

- [ ] Ön koşul: F2–F7 hata analizinde (en az 50 başarısız örnek elle etiketlenmiş) lehçe veya Türkçe anlama kaynaklı sistematik bir hata sınıfı kalması.
- [ ] `synthetic_data/generator.py`: OmniSQL yöntemi:
  1. Şema üzerinde karmaşıklık düzeylerine göre SQL üret.
  2. Çalıştır; boş ve hatalı olanları ele.
  3. LLM ile farklı üsluplarda Türkçe soru yazdır.
  4. Geri çeviriyle tutarlılık kontrolü yap.
- [ ] Eğitim ve değerlendirme veritabanları ayrı tutulur. BIRDTurk ve NC lisanslı veri eğitime girmez (ADR-0009).
- [ ] QLoRA: 3–4B model yerelde denenebilir. 7–9B model için 8 GB sınırda kalır; bulut GPU gerekebilir. Adaptör ayrı tutulur, taban model değiştirilmez.
- [ ] Regresyon: genel Türkçe yetenek için küçük bir set (örneğin TurkishMMLU alt kümesi) ve kurumsal set.

**Kabul:** ≥ +4 puan net EX kazancı ve genel Türkçe regresyon ≤ 1 puan. Değilse D7 "uygulanmadı" olarak raporlanır ve F9'a geçilir.

### F9 — Nihai mimari kararları (D8)

- [ ] Tam sistemi ölç: model × D0–D8 × veri kümesi ana tablosu, bileşen katkıları (Δ EX), güvenlik tablosu, gecikme ve VRAM.
- [ ] ADR'ler:
  - seçilen model ve nicemleme
  - schema linking yöntemi
  - retriever bileşimi
  - Zemberek kararı
  - yönlendirme
  - D7 kararı
- [ ] `docs/architecture/overview.md` v1.0.

**Kabul:** E1–E3 tümü sağlanmış. Her ADR, `experiments/` altındaki bir deneye bağlantı veriyor.

### F10 — Ürünleştirme (AR-10)

- [ ] `api`: gerçek kimlik doğrulama sağlayıcısı (kurum içi OIDC/LDAP), rate limit, istek boyutu sınırı.
- [ ] `frontend/` (React + TS):
  - soru kutusu
  - netleştirme diyaloğu
  - "kullanılan tablolar" onayı (HITL)
  - SQL görüntüleme
  - deterministik tablo ve grafik
  - hata ve ret mesajları Türkçe
- [ ] `deployment/`: Windows hizmeti veya Docker Compose (PostgreSQL + TRSQL), çevrimdışı kurulum paketi, model SHA256 doğrulaması, log saklama süresi (KVKK).
- [ ] Opsiyonel: TRSQL'i dışarıya bir **MCP aracı** olarak açma. Aracın içinde L1–L9 hattı çalışır; modele DB aracı verilmez (ADR-0004).

**Kabul:** Uçtan uca kabul senaryoları (en az 20 kurumsal soru, 5 netleştirme, 5 ret) arayüzden geçiyor. Kurulum, internetsiz bir makinede belgelendiği gibi tamamlanıyor.

---

## 4. Klasör yapısında eklenecekler

PR #1 yapısı korunur. Yeni dosyalar:

```
SorguMuhendisim_TRSQL/
├── backend/
│   ├── core/ports.py                 # + EmbeddingAdapter (F4)
│   ├── model_engine/
│   │   ├── llama_cpp.py              # LlamaCppAdapter (F2)
│   │   └── embedding.py              # LlamaCppEmbeddingAdapter (F4)
│   ├── rag/
│   │   ├── bm25.py, dense.py, fusion.py, values.py   # (F4)
│   ├── semantic_layer/templates.py   # onaylı metrik şablonları (F4)
│   ├── turkish_nlp/ambiguity.py      # (F5)
│   ├── sql_validator/semantic.py, business_rules.py, cost.py   # (F6)
│   ├── database_adapters/postgres.py # (F6)
│   └── orchestration/routing.py      # mod yönlendirme (F7)
├── benchmarks/loaders/, metrics/, runner.py, report.py   # (F1)
├── experiments/<tarih>-<ad>/         # her koşu
├── synthetic_data/schema/erp.sql, generator.py          # (F1b, F8)
├── models/download.py, README.md     # (F0)
├── deployment/postgres/roles.sql, rls.sql, masking.sql  # (F6)
└── tests/
    ├── unit/test_metrics.py, test_llama_cpp_adapter.py, test_rag_*.py, test_temporal_*.py
    ├── security/ (genişletilmiş saldırı listeleri)
    └── integration/test_postgres_pipeline.py
```

Her yeni modül dosyası, modülün `__init__.py` ve `__all__` üzerinden dışa açılır. Başka modülden iç dosya içe aktarılmaz (`tools/check_boundaries.py`).

---

## 5. Her görev için tamamlanma tanımı

- [ ] Tek AR paketi, tek modül (veya önce ayrı sözleşme PR'ı).
- [ ] Önce kırmızı test, sonra kod.
- [ ] G1 `ruff check . && ruff format --check .` · G2 `mypy` · G3 `python tools/check_boundaries.py` · G4 `pytest -m security` · G5 `pytest`.
- [ ] Bileşen ekliyorsa: ilgili D-kademesi koşulmuş, `experiments/` altına config + metrikler kaydedilmiş, E1 sağlanmış.
- [ ] Sözleşme, sınır veya karar değiştiyse ilgili doküman ve ADR aynı PR'da güncellenmiş.
- [ ] Gizli bilgi, gerçek kişisel veri, model ağırlığı veya ham veri commit'lenmemiş.

---

## 6. Kodlama agent'ı ile çalışma (yerelde Claude Code vb.)

Her görevi agent'a şu kalıpla ver:

```text
AR-0X / Fn görevi: <tek cümle hedef>.
Modül: backend/<modül>/. Sözleşmeler: backend/core/contracts.py içindeki <X>, <Y>.
Önce AGENTS.md, docs/architecture/module-map.md ve ADR-000N'yi oku.
Önce tests/<klasör>/test_<ad>.py içinde başarısız testleri yaz, sonra uygula.
Kabul: <bu plandaki kabul ölçütü>. Bitince G1–G5'i çalıştır ve sonucu raporla.
boundaries.toml'a dokunman gerekirse dur ve sor.
```

---

## 7. Riskler ve önlemler

| Risk | Etki | Önlem |
| --- | --- | --- |
| 9B model + 8K bağlam + KV cache 6,8 GB'ı aşar | D0'da model elenir | Q4_K_M, KV `q8_0`, bağlamı 4K'ya indir; aşarsa "uygun değil" diye raporla |
| Hati-Glint-SQL'in kendi skorları tekrarlanamaz | Model seçimi değişir | F2'de bağımsız ölçüm; seçimi ölçüme göre yap |
| Gömme modeli GPU'yu doldurur | Bağlam düşer | Gömme modeli CPU'da (F4) |
| Zemberek JVM bağımlılığı Windows kurulumunu zorlaştırır | Dağıtım maliyeti | Ölç; kazanç yoksa kural tabanlıda kal |
| Kurumsal setin altın SQL'lerinde hata | Yanlış sonuçlar | Çift doğrulama + Test Suite (rapor 8(a)) |
| BIRDTurk lisans çelişkisi (makale CC BY-SA, HF NC) | Yasal risk | Yalnız değerlendirme (ADR-0009) |
| `llama-server` ile HTTP kullanımı ADR-0002'yi deler | Mimari ihlal | `llama-cpp-python` aynı süreçte; ya da yeni ADR |
| Thinking modu P95'i patlatır | Kullanılabilirlik | F7 mod yönlendirmesi; thinking yalnız gerektiğinde |

---

## 8. İlk iki haftanın somut sırası

1. PR #1'i birleştir. G1–G5 yerelde yeşil (F0).
2. `models/download.py` + 4 model + BGE-M3, SHA256 doğrulaması (F0).
3. `benchmarks/metrics/execution.py` + testleri (F1).
4. TURSpider dev yükleyici, ardından FakeModel ile koşucu uçtan uca (F1).
5. `LlamaCppAdapter` + VRAM ölçümü (F2).
6. İlk gerçek koşu: Qwen3-4B, D0, TURSpider dev'in ilk 100 sorusu. Amaç koşucunun ve ölçümün doğru çalıştığını görmek.
7. Kurumsal şema taslağı `erp.sql` + ilk 50 soru (F1b).
