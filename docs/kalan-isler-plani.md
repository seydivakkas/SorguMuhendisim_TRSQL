# TRSQL — Kalan İşler Planı (yerel kodlama agent'ı için)

> **Kime:** Seydi'nin kendi bilgisayarında çalışan kodlama agent'ı (Claude Code, Codex vb.) ve Seydi.
> **Tarih:** 2026-11-28 · **Taban:** `main` @ `ed9b5c0` (PR #2, #3, #4 birleşmiş).
> **Referans makine:** Windows, RTX 4070 Laptop 8 GB VRAM (net bütçe ≈ 6.800 MB), 32 GB RAM.
> **Kaynaklar:** [AGENTS.md](../AGENTS.md), [docs/roadmap.md](roadmap.md),
> [docs/evaluation/evaluation-plan.md](evaluation/evaluation-plan.md), `trsql-kodlama-plani.md` (F0–F10),
> `trsql-birlesik-arastirma-raporu.md`.

---

## 0. Agent için çalışma talimatı (önce bunu oku)

1. **AGENTS.md bağlayıcıdır.** Özellikle §1 değişmez kurallar: model DB'ye dokunmaz
   (`ApprovedQuery` → `execution_engine` tek yol), RBAC şemadan önce, güvenlik ihlali yeniden
   denenmez, `max_attempts ≤ 5`, `backend/` içinde ağ çağrısı yok, `tests/security/` gevşetilmez.
2. Görevleri **bu dosyadaki sırayla** yap. Her görev tek PR (veya tek commit dizisi) olsun;
   bir görevin "Bağımlılık" satırındaki görev bitmeden başlama.
3. Her görevin sonunda **kapıları** çalıştır. Hepsi yeşil olmadan görevi bitmiş sayma:

   | Kapı | Komut |
   |---|---|
   | G1 Lint/format | `ruff check . && ruff format --check .` |
   | G2 Tip | `mypy` |
   | G3 Sınırlar | `python tools/check_boundaries.py` |
   | G4 Güvenlik | `pytest -m security -q` |
   | G5 Tüm testler | `pytest -q` |
   | E1–E3 Deney | `docs/evaluation/evaluation-plan.md` §8 (yalnız deney görevlerinde) |

   PowerShell'de tek satır: `ruff check . ; ruff format --check . ; mypy ; python tools/check_boundaries.py ; pytest -q`
4. Başarısız test olursa yalnız başarısız testleri yeniden çalıştır (`pytest -q --lf`); en sonda
   tüm paketi bir kez çalıştır.
5. Kod/tanımlayıcı/commit **İngilizce**; kullanıcı mesajları ve dokümanlar **Türkçe**.
6. Model ağırlığı, veri kümesi, `.env`, DSN, parola **asla commit'lenmez** (`.gitignore` zaten engelliyor;
   yine de `git status` ile kontrol et).
7. Şu durumlarda **dur ve Seydi'ye sor**: `boundaries.toml`'a yeni izin gerekiyorsa, bir güvenlik
   testini değiştirmek gerekiyormuş gibi görünüyorsa, lisansı belirsiz model/veri gerekiyorsa,
   gerçek kurum verisiyle karşılaşırsan.

### Görev kartı biçimi

Her görevde şunlar var: **Amaç**, **Dosyalar**, **Yapılacaklar**, **Kabul kriterleri**,
**Doğrulama** (çalıştırılacak komutlar), **Bağımlılık**. Görev numaraları `T-xx`.

---

## 1. Mevcut durum (2026-11-28'de doğrulandı)

- `main` @ `ed9b5c0`: F0–F10 iskeleti ve L0–L9 katmanları kodda var.
- Bulut ortamında `pip install -e ".[dev,api]"` sonrası: G1 ✅, G2 ✅ (74 dosya), G3 ✅,
  G5 ✅ **356 test geçti** (5,8 sn).
- Tüm testler `FakeModelAdapter` + SQLite + mock'lanmış `psycopg` ile koşuyor. **Gerçek model,
  gerçek GPU, gerçek PostgreSQL ve gerçek veri kümesiyle hiçbir şey henüz koşmadı.**

### 1.1 Kod incelemesinde bulunan eksikler (kanıtlı)

| # | Eksik | Kanıt | Görev |
|---|---|---|---|
| E-01 | **Docker'daki API açılmaz.** `uvicorn backend.api.app:create_app --factory` argümansız çağırır; `create_app(pipeline, auth_provider, ...)` iki zorunlu argüman ister → `TypeError`. Ortam değişkenlerinden pipeline kuran bir "composition root" yok. | `deployment/Dockerfile:44,68`, `backend/api/app.py:40` | T-01 |
| E-02 | Rol politikası yükleyicisi yok; `security_policies/*.toml` hiçbir yerde okunmuyor. Token → `AuthContext` eşlemesi yalnız testlerde elle kuruluyor. | `security_policies/README.md:4` ("AR-07'de yükleyici eklenecek") | T-02 |
| E-03 | **Benchmark koşucusu D0–D8 basamağını yok sayıyor.** `stage` ve `template_id` yalnızca rapora yazılıyor; her basamak `build_default_pipeline` ile (sözlük linker, DDL istemi, RAG/yönlendirme yok) koşuyor. `build_hybrid_pipeline` testler dışında hiçbir yerde kullanılmıyor. Bu hâliyle ablasyon tablosu anlamsız olur. | `benchmarks/runner.py:428`, `benchmarks/runner.py:684-690` | T-03 |
| E-04 | Koşucu yalnız SQLite açıyor; `dialect = "postgres"` ayarı `PostgresAdapter` kurmuyor. | `benchmarks/runner.py:419-423` | T-04 |
| E-05 | Koşucu ve API gerçek gömme modelini (BGE-M3) bağlamıyor; `create_embedding_adapter` yalnız dışa aktarılmış, kullanılmıyor. Hibrit hatta varsayılan `DeterministicHashEmbedder` (anlamsal değil). | `backend/orchestration/factory.py:92`, `backend/model_engine/registry.py:40` | T-03 |
| E-06 | RBAC kapsamlama tablo adını şemasız (`table.column`) karşılaştırıyor; PostgreSQL'de iki şemada aynı adlı tablo veya `schema.table.column` biçimli yasak sütun doğru işlenmiyor. | `backend/auth/scoping.py:12-34` | T-05 |
| E-07 | Model manifestinde **hiçbir SHA-256 sabitlenmemiş** (`sha256=None`). URL'ler doğrulanmamış; bazı resmî depolar (ör. `BAAI/bge-m3`, `Snowflake/Arctic-Text2SQL-R1-7B`, `Qwen/Qwen3-4B-Instruct-2507`) GGUF dosyası barındırmıyor olabilir. | `models/download.py` (`CANDIDATE_MODELS`) | T-08, T-09 |
| E-08 | `llm`, `rag`, `postgres` ek bağımlılıkları hiç kurulup denenmedi. `rag` ekstrasındaki `rank-bm25`, `faiss-cpu`, `datasketch` **kodda hiç import edilmiyor** (BM25/dense/LSH saf Python). | `pyproject.toml` `[project.optional-dependencies]`; `grep -r "faiss\|rank_bm25\|datasketch" backend` boş | T-07, T-14 |
| E-09 | Gerçek PostgreSQL entegrasyon testi yok; `tests/integration/test_postgres_adapter.py` tamamen mock. `postgres` ve `gpu` pytest işaretleri tanımlı ama **hiç kullanılmıyor**. CI'da `services: postgres` yok. | `pyproject.toml` markers, `.github/workflows/ci.yml` | T-11, T-12 |
| E-10 | Frontend HITL ön onayı `/v1/plan` uç noktasını çağırmıyor; tablolar istemcide tahmin ediliyor. Frontend'de test yok. | `frontend/src/api/client.ts` (yalnız `fetchHealth`, `submitQuery`), `HitlTableConfirmation.tsx` | T-06 |
| E-11 | Üretim kimlik doğrulaması (OIDC/LDAP) yok; `StaticAuthProvider` "yalnız geliştirme ve test" olarak işaretli. | `backend/auth/provider.py:10-15` | T-19 |
| E-12 | ADR-0002'nin istediği "ağ erişimi kapalı ortamda uçtan uca test" yok. llama.cpp kurulumu belgelenmemiş. | `docs/adr/0002-offline-first-on-prem.md:32`, `docs/guides/getting-started.md:7` | T-07, T-20 |
| E-13 | Gerçek veri kümeleri (TURSpider dev, BIRDTurk dev) indirilmemiş; `datasets/<ad>.md` kartları yok. | `datasets/README.md` | T-10 |
| E-14 | D0–D8 deney klasörleri yok; yalnız `experiments/d0-baseline-template/`. AR-09 karar ADR'leri yok. | `experiments/` | T-13…T-17 |
| E-15 | `docs/roadmap.md` "Güncel durum" tablosu her şeyi ✅ gösteriyor; gerçek model/PG/deney yapılmadığı belirtilmiyor. | `docs/roadmap.md` | T-21 |

---

## 2. Sıralı görev listesi (özet)

| Aşama | Görev | Ne | GPU? | Süre (tahmin) |
|---|---|---|---|---|
| **A — Yazılım eksikleri** (GPU gerekmez) | T-01 | API composition root + Dockerfile düzeltmesi | Hayır | 0,5–1 gün |
| | T-02 | Rol politikası yükleyicisi + token dosyası | Hayır | 0,5 gün |
| | T-03 | Koşucuda D0–D8 basamak profilleri + gerçek gömme | Hayır | 1–1,5 gün |
| | T-04 | Koşucuda PostgreSQL lehçesi | Hayır | 0,5 gün |
| | T-05 | Çok şemalı PG için RBAC kapsamlama | Hayır | 0,5–1 gün |
| | T-06 | Frontend `/v1/plan` bağlantısı + frontend testleri | Hayır | 1 gün |
| **B — Yerel ortam** | T-07 | Windows ortamı, CUDA'lı `llama-cpp-python`, ek paketler | Evet | 0,5 gün |
| **C — Modeller** | T-08 | Model URL/dosya doğrulama ve manifest düzeltme | Hayır | 0,5 gün |
| | T-09 | GGUF indirme, SHA-256 sabitleme, GPU duman testi, VRAM ölçümü | Evet | 1 gün |
| **D — Veri** | T-10 | TURSpider/BIRDTurk dev indirme, veri kartları, kurumsal set | Hayır | 0,5 gün |
| **E — PostgreSQL** | T-11 | Yerel PG 16 + rol/RLS betikleri + gerçek entegrasyon testleri | Hayır | 1 gün |
| | T-12 | CI'ya PostgreSQL servisli iş | Hayır | 0,5 gün |
| **F — Deneyler** | T-13 | D0/D1 taban çizgisi (model × veri) | Evet | 1–2 gün |
| | T-14 | D2–D4 (linking, RAG, Türkçe NLP) | Evet | 2 gün |
| | T-15 | D5–D6 (güvenlik, yönlendirme + onarım) | Evet | 1–2 gün |
| | T-16 | D7 koşullu ince ayar kararı | Belki | 0,5 gün – 1 hafta |
| | T-17 | D8 tam sistem + karşılaştırma raporu | Evet | 1 gün |
| **G — Kararlar ve ürün** | T-18 | AR-09 karar ADR'leri, `overview.md` v1.0 | Hayır | 1 gün |
| | T-19 | Üretim kimlik doğrulaması (OIDC/LDAP) | Hayır | 1–2 gün |
| | T-20 | Çevrimdışı uçtan uca test + kabul senaryoları (20/5/5) | Hayır | 1–2 gün |
| | T-21 | Doküman/yol haritası güncellemesi | Hayır | 0,5 gün |

> **Sıra mantığı:** A aşaması bitmeden deney koşma (T-03 olmadan D0–D8 tablosu yanlış olur).
> B–E paralel ilerleyebilir; F aşaması B+C+D'ye bağlı, D5 (T-15) ayrıca E'ye bağlı.

---

## 3. Görev kartları

### Aşama A — Yazılım eksikleri (GPU ve gerçek model gerekmez)

#### T-01 — API composition root ve çalışan Docker girişi

**Amaç:** API, yalnız ortam değişkenleri ve config dosyalarıyla ayağa kalksın (E-01).

**Dosyalar:**
- `backend/orchestration/bootstrap.py` (yeni) — `build_pipeline_from_env(settings, ...) -> Pipeline`
- `backend/orchestration/__init__.py` — `__all__`'a ekle
- `backend/api/app.py` — argümansız `create_default_app() -> FastAPI` fabrikası
- `deployment/Dockerfile` — `TRSQL_ASGI_APP="backend.api.app:create_default_app"`
- `.env.example`, `deployment/README.md`, `docs/guides/getting-started.md`
- `tests/unit/test_bootstrap.py` (yeni), `tests/unit/test_api.py`

**Yapılacaklar:**
1. Bağlama (wiring) yalnız `orchestration` içinde kalır (AGENTS.md §2). `bootstrap.py` şu
   ortam değişkenlerini okur: `TRSQL_CONFIG` (varsayılan `configs/default.toml`),
   `TRSQL_KNOWLEDGE` (opsiyonel TOML), `TRSQL_DB_DIALECT` (`sqlite`|`postgres`),
   `TRSQL_SQLITE_PATH`, `TRSQL_PG_DSN` (adaptör env adını alır, değeri asla loglamaz),
   `TRSQL_PIPELINE` (`default`|`hybrid`, varsayılan `hybrid`).
2. Model: `create_model_adapter(settings.model)`; gömme: `create_embedding_adapter(...)`,
   dosya yoksa `DeterministicHashEmbedder`'a **açıkça loglayarak** düş (sessiz düşüş yok).
3. `create_default_app()` → `load_settings`, `build_pipeline_from_env`, T-02'deki
   `load_auth_provider(...)`, `MetricsCollector`; sonra mevcut `create_app(...)`.
   `api` yalnız `auth`, `orchestration`, `observability` içe aktarır (boundaries değişmez).
4. Eksik/yanlış yapılandırmada `ConfigError` ile Türkçe, gizli bilgi içermeyen mesajla başlangıçta
   dur (fail-closed). `settings.offline = True` iken ağ gerektiren hiçbir şey başlatma.

**Kabul kriterleri:**
- `TRSQL_DB_DIALECT=sqlite`, `TRSQL_SQLITE_PATH=<tests/fixtures/demo_schema.sql ile oluşturulmuş SQLite dosyası>`, `model.adapter="fake"` ile
  `uvicorn backend.api.app:create_default_app --factory` açılır, `/health` 200 döner.
- Geçersiz/eksik DSN'de başlangıç hatası mesajında parola/DSN geçmez (test ile).
- `tests/unit/test_deployment.py` Dockerfile'daki yeni fabrika adını doğrular.

**Doğrulama:**
```powershell
pytest -q tests/unit/test_bootstrap.py tests/unit/test_api.py tests/unit/test_deployment.py
# elle duman testi:
python -c "import sqlite3; c=sqlite3.connect('demo.sqlite'); c.executescript(open('tests/fixtures/demo_schema.sql', encoding='utf-8').read()); c.commit()"
$env:TRSQL_DB_DIALECT="sqlite"; $env:TRSQL_SQLITE_PATH="demo.sqlite"
uvicorn backend.api.app:create_default_app --factory --port 8000
curl http://127.0.0.1:8000/health
```
+ G1–G5.

**Bağımlılık:** T-02 ile aynı PR'da yapılabilir (yükleyiciyi kullanır).

---

#### T-02 — Rol politikası ve token yükleyicisi

**Amaç:** `security_policies/*.toml` → `AuthContext`; token → rol eşlemesi dosya/env'den (E-02).

**Dosyalar:** `backend/auth/policies.py` (yeni), `backend/auth/__init__.py`,
`security_policies/README.md`, `security_policies/analyst.example.toml`,
`tests/unit/test_auth_policies.py`, `tests/security/test_rbac_bypass_regressions.py` (yalnız **ekleme**).

**Yapılacaklar:**
1. `load_role_policies(dir) -> dict[str, RolePolicy]` (allowed_tables, denied_columns, max_rows, tenant).
2. Token dosyası: `TRSQL_TOKENS_FILE` → her satır `sha256(token)` + `user_id` + `role` + `tenant`.
   Düz token dosyada **saklanmaz**; `StaticAuthProvider`'ı hash karşılaştıran bir
   `HashedTokenAuthProvider` ile genişlet (`hmac.compare_digest` korunur).
3. Varsayılan **reddet**: politikada olmayan tablo görünmez; bilinmeyen rol → `AuthorizationError`.
4. Kişisel veri sütunları (`tc_kimlik_no`, `telefon`, `eposta`, `iban`) varsayılan yasak listede.

**Kabul kriterleri:** Bilinmeyen rol, boş `allowed_tables`, bozuk TOML ve tekrarlanan token
hash'i için testler; güvenlik regresyon listesine "politika dosyasında olmayan tablo" vakası eklendi.

**Doğrulama:** `pytest -q tests/unit/test_auth_policies.py ; pytest -m security -q` + G1–G5.

**Bağımlılık:** —

---

#### T-03 — Koşucuda D0–D8 basamak profilleri ve gerçek gömme modeli

**Amaç:** Her ablasyon basamağı gerçekten farklı bir hat kursun (E-03, E-05). Bu görev bitmeden
hiçbir deney sonucu raporlanmaz.

**Dosyalar:** `benchmarks/stages.py` (yeni), `benchmarks/runner.py`,
`experiments/d0-baseline-template/config.toml`, `experiments/README.md`,
`tests/unit/test_benchmark_runner.py`, `tests/unit/test_benchmark_stages.py` (yeni).

**Yapılacaklar:**
1. `StageProfile` (frozen dataclass): `pipeline` (`default`|`hybrid`), `prompt_template_id`,
   `linker` (`lexicon`|`hybrid`), `rag` (kapalı/kurallar/örnekler/değer), `turkish_nlp`
   (temel/morfoloji+belirsizlik), `fail_closed_full`, `routing_enabled`, `vote_candidates`,
   `max_attempts`, `use_kpi_templates`.
2. Kümülatif tablo (evaluation-plan §3 ile birebir):

   | Basamak | Fark |
   |---|---|
   | D0 | default hat, `ddl_v1`, RAG yok, yönlendirme yok, `max_attempts=1` |
   | D1 | D0 + `mschema_v1` |
   | D2 | D1 + `HybridSchemaLinker` + Steiner FK |
   | D3 | D2 + RAG (kurallar + örnekler + LSH değer), BGE-M3 CPU gömme |
   | D4 | D3 + Türkçe morfoloji + belirsizlik/netleştirme |
   | D5 | D4 + tam L6 (8 aşama) + L7 sınırları |
   | D6 | D5 + `ComplexityRouter` + onarım döngüsü + N-aday oylama |
   | D7 | D6 + (varsa) ince ayarlı adaptör |
   | D8 | Tam hibrit (`build_hybrid_pipeline`, tüm bayraklar) |

3. `config.toml`'da `[experiment].stage` profili seçer; `[stage_overrides]` ile tek bayrak
   değiştirilebilir (ör. GBNF kolu). Rapora **çözülmüş profil** yazılır (`metrics.json`).
4. Gömme: `[settings.model].embedding_model_path_env` doluysa `create_embedding_adapter`,
   değilse `DeterministicHashEmbedder` + rapora `embedder: "hash-fallback"` uyarısı.
5. `build_default_pipeline` yerine profile göre `build_default_pipeline` / `build_hybrid_pipeline`.
   Güvenlik çekirdeği (validator + policy + `ApprovedQuery`) **D0'da bile kapatılamaz**; D5
   yalnız ek kontrolleri açar (ADR-0004/0007).

**Kabul kriterleri:**
- `FakeModelAdapter` ile D0 ve D8 aynı veri üzerinde farklı istem metni üretir (test istem
  içeriğine bakar: D0'da `CREATE TABLE`, D1+'da M-Schema başlığı).
- Bilinmeyen basamak adı → `ConfigError`.
- Her basamak için çözülmüş profil `metrics.json`'da var.

**Doğrulama:** `pytest -q tests/unit/test_benchmark_runner.py tests/unit/test_benchmark_stages.py` + G1–G5.

**Bağımlılık:** —

---

#### T-04 — Koşucuda PostgreSQL lehçesi

**Amaç:** `dialect = "postgres"` olan deney `PostgresAdapter` ile koşsun (E-04).

**Dosyalar:** `benchmarks/runner.py`, `benchmarks/metrics/execution.py` (altın SQL'in PG'de
salt okunur çalıştırılması), `tests/unit/test_benchmark_runner.py`.

**Yapılacaklar:** `[database] dsn_env = "TRSQL_PG_DSN"`, `allowed_schemas = ["public"]`;
altın SQL karşılaştırması da salt okunur oturumda; SQLite'a özel `execute_sqlite_readonly`
yanında `execute_postgres_readonly`. `psycopg` yalnız `database_adapters` içinden geçer —
koşucu `benchmarks/` altında olduğu için altın SQL çalıştırması için de `PostgresAdapter`
kullan, doğrudan `psycopg` import etme.

**Kabul kriterleri:** mock'lu testte PG profili seçilince `PostgresAdapter` kuruluyor; DSN
değeri hiçbir çıktıda yok.

**Doğrulama:** `pytest -q tests/unit/test_benchmark_runner.py` + G1–G5. Gerçek PG ile: T-11 sonrası.

**Bağımlılık:** T-03.

---

#### T-05 — Çok şemalı PostgreSQL için RBAC kapsamlama

**Amaç:** `schema.table.column` biçimli yasak sütunlar ve aynı adlı tablolar doğru işlensin (E-06).

**Dosyalar:** `backend/auth/scoping.py`, gerekirse `backend/core/contracts.py` (`TableInfo`'ya
`schema_name` — sözleşme değişikliği **ayrı adım**, `docs/architecture/data-contracts.md` güncellenir),
`backend/database_adapters/postgres.py` (introspect şema adını doldurur),
`backend/sql_validator/validator.py` (yetki aşaması nitelikli adları çözer),
`tests/security/test_rbac_bypass_regressions.py` (**yalnız ekleme**).

**Yapılacaklar:**
1. Yasak sütun eşleşmesi: `column`, `table.column`, `schema.table.column` üçü de desteklenir;
   karşılaştırma `tr_casefold` ile değil, tanımlayıcı kuralıyla (PG: tırnaksız → küçük harf).
2. İki şemada aynı ad: allowed_tables nitelikli değilse **ikisi de** reddedilir (fail-closed),
   nitelikliyse yalnız o şema görünür.
3. Yeni saldırı vakaları: `"Public"."Musteri"` büyük/küçük harf, `search_path` ile niteliksiz erişim,
   yasak sütunun başka şemadaki aynı adlı tablo üzerinden okunması.

**Kabul kriterleri:** Yeni güvenlik vakaları önce kırmızı, sonra yeşil; mevcut hiçbir güvenlik
testi değiştirilmedi.

**Doğrulama:** `pytest -m security -q` + G1–G5.

**Bağımlılık:** —

---

#### T-06 — Frontend `/v1/plan` bağlantısı ve frontend testleri

**Amaç:** HITL "kullanılan tablolar" onayı sunucunun gerçek planına dayansın (E-10).

**Dosyalar:** `frontend/src/api/client.ts` (`previewPlan()`), `frontend/src/types/contracts.ts`
(`PlanPreview`), `frontend/src/App.tsx`, `frontend/src/components/HitlTableConfirmation.tsx`,
`frontend/package.json` (`vitest`, `@testing-library/react`, `test` betiği),
`frontend/src/**/*.test.tsx` (yeni).

**Yapılacaklar:** Ön onayda `POST /v1/plan` → dönen tablo/sütun listesini göster; kullanıcı
onaylarsa `/v1/query`. İstemci tarafı tahmin (`inferInformationalTableHints`) yalnız plan
alınamazsa "bilgi amaçlı" etiketiyle gösterilir. Hiçbir güvenlik kararı istemcide verilmez.

**Kabul kriterleri:** `npm run typecheck`, `npm run build`, `npm test` yeşil; plan hatası
Türkçe mesajla gösteriliyor; testte `fetch` mock'lanıyor.

**Doğrulama:**
```powershell
cd frontend ; npm ci ; npm run typecheck ; npm test ; npm run build
```

**Bağımlılık:** T-01 (gerçek API'ye karşı elle deneme için).

---

### Aşama B — Yerel ortam (referans dizüstü, Windows)

#### T-07 — Python ortamı, CUDA'lı llama-cpp-python ve ek paketler

**Amaç:** Gerçek model ve PG ile koşabilecek tekrarlanabilir yerel ortam (E-08, E-12).

**Dosyalar:** `docs/guides/getting-started.md` ("llama.cpp kurulumu AR-05'te belgelenecek"
satırını gerçek adımlarla değiştir), `docs/guides/local-gpu-setup.md` (yeni),
`tools/env_report.py` (yeni, ağ çağrısı yok: Python/CUDA/llama-cpp sürümü, GPU offload var mı).

**Yapılacaklar (Seydi'nin makinesinde):**
1. Ön koşullar: Python 3.11/3.12, güncel NVIDIA sürücüsü, CUDA Toolkit 12.x, Visual Studio
   Build Tools (C++), Git, (T-11 için) Docker Desktop.
2. Sanal ortam ve paketler:
   ```powershell
   py -3.12 -m venv .venv ; .\.venv\Scripts\Activate.ps1
   pip install -e ".[dev,api,postgres,synthetic]"
   # CUDA'lı llama-cpp-python (kaynaktan derleme):
   $env:CMAKE_ARGS="-DGGML_CUDA=on" ; $env:FORCE_CMAKE="1"
   pip install "llama-cpp-python>=0.3" --no-cache-dir --force-reinstall --upgrade
   pip install "huggingface-hub>=0.24"
   ```
   Derleme sorun çıkarırsa llama-cpp-python'un CUDA için önceden derlenmiş tekerlek dizinini
   kullan (CUDA sürümüne uygun olanı; resmi README'deki komutu takip et) ve hangi yolu
   seçtiğini dokümana yaz.
3. `rag` ekstrası (`rank-bm25`, `faiss-cpu`, `datasketch`) **şu an kodda kullanılmıyor**. Ya
   T-14'te hızlandırıcı arka uç olarak bağla ya da `pyproject.toml`'dan çıkar; karar T-14'te.
4. `tools/env_report.py` çıktısını deney klasörlerine eklenecek `hardware.json` için kullan
   (`benchmarks/hardware.py` ile birleştir, tekrar etme).

**Kabul kriterleri:**
```powershell
python -c "import llama_cpp; print(llama_cpp.__version__, llama_cpp.llama_supports_gpu_offload())"
# → sürüm ve True
python -c "import psycopg; print(psycopg.__version__)"
nvidia-smi
```
G1–G5 bu ortamda da yeşil (356+ test).

**Bağımlılık:** —

---

### Aşama C — Modeller

#### T-08 — Model URL'lerini ve dosya adlarını doğrula, manifesti düzelt

**Amaç:** `models/download.py` içindeki her aday gerçekten indirilebilir, lisansı doğru, revizyonu
sabit olsun (E-07).

**Dosyalar:** `models/download.py` (`CANDIDATE_MODELS`), `models/*.md` kartları, `models/README.md`,
`tests/unit/test_models_manifest.py` (yeni veya mevcut deployment testine ekle).

**Yapılacaklar:**
1. Her model için Hugging Face sayfasını aç: depo GGUF dosyası barındırıyor mu, tam dosya adı ne?
   Resmî depo yalnız `safetensors` veriyorsa iki seçenek:
   (a) güvenilir bir topluluk GGUF deposu (kaynak, yükleyen, revizyon karta yazılır), veya
   (b) llama.cpp ile yerelde dönüştürme: `convert_hf_to_gguf.py` → `llama-quantize ... Q4_K_M/Q5_K_M`.
   Seçimi karta yaz.
2. `ModelSpec`'e `revision` (commit hash) alanı ekle; URL `resolve/<revision>/<dosya>` olsun
   (`main` değil). Lisansı (Apache-2.0 / MIT / NOTICE) model sayfasından yeniden doğrula.
3. `qwen-research` kısıtlı modeller (`Qwen2.5-Coder-3B`, `XiYanSQL-QwenCoder-3B`) listeye
   **eklenmez** (models/README.md lisans uyarısı).
4. Ağ erişimi yalnız `models/download.py`'de; `backend/` değişmez.

**Kabul kriterleri:** Her aday için kartta kaynak URL + revizyon + lisans + nicemleme + dosya
adı dolu; manifest testi `sha256` alanının ya 64-hex ya da `None` olduğunu, URL'nin revizyon
içerdiğini doğrular.

**Doğrulama:** `python models/download.py list` + G1–G5.

**Bağımlılık:** —

---

#### T-09 — GGUF indirme, SHA-256 sabitleme, GPU duman testi ve VRAM ölçümü

**Amaç:** En az bir SQL modeli + BGE-M3 yerelde doğrulanmış olarak çalışsın.

**Dosyalar:** `models/download.py` (`sha256` değerleri), `models/*.md` (SHA + ölçülen VRAM),
`tests/gpu/test_llama_smoke.py` (yeni, `@pytest.mark.gpu`), `tests/conftest.py`
(`gpu` işaretli testleri `TRSQL_MODEL_PATH` yoksa **atla** — bu güvenlik testi değildir),
`.env` (commit'lenmez).

**Yapılacaklar:**
1. İndirme sırası (VRAM bütçesine göre): `qwen3-4b-instruct` (≈3,6 GB, hızlı duman testi) →
   `xiyansql-qwencoder-7b` → `arctic-text2sql-r1-7b` → `hati-glint-sql-9b` (≈6,4 GB, sınırda) →
   `bge-m3-gguf` (CPU).
   ```powershell
   python models/download.py download qwen3-4b-instruct --allow-unverified   # ilk kez, SHA hesaplar
   python models/download.py verify models/weights/<dosya>.gguf --sha256 <hesaplanan>
   ```
2. Hesaplanan SHA-256'yı `CANDIDATE_MODELS[...].sha256` ve model kartına yaz; bundan sonra
   `--allow-unverified` kullanılmaz.
3. `.env`: `TRSQL_MODEL_PATH=...`, `TRSQL_MODEL_PATH_SHA256=<hex>`,
   `TRSQL_EMBEDDING_MODEL_PATH=...` (registry `<env>_SHA256` değişkenini okur).
4. `tests/gpu/test_llama_smoke.py`: `LlamaCppAdapter` modeli yükler, demo şemasında basit bir
   Türkçe soru için SQL üretir; çıktı `SQLValidator`'dan geçer; `query_nvidia_smi_vram_mb()` ile
   tepe VRAM ≤ `vram_budget_mb` (6.800) doğrulanır. `<think>` bloğu ayrıştırılır (Arctic).
5. Her model için `n_ctx` 4096 ve 8192, `kv_cache_type=q8_0`, `flash_attn=True` ile tepe VRAM
   ve tokens/s ölç; sonuçları kartın "Ölçülen tepe VRAM" alanına yaz. 9B model 8192'de
   bütçeyi aşarsa 4096'da kalır (kartta not).

**Kabul kriterleri:** En az iki SQL modeli + BGE-M3 için SHA sabit; `pytest -m gpu -q` yerelde
yeşil; tepe VRAM ≤ 6.800 MB (aşan konfigürasyon kartta "uygun değil" diye işaretli).
Bulut/CI'da `gpu` testleri atlanır, G5 yine yeşil.

**Doğrulama:**
```powershell
pytest -m gpu -q
python models/download.py verify models/weights/<dosya>.gguf --sha256 <hex>
python deployment/verify_models.py --models-dir models/weights
```

**Bağımlılık:** T-07, T-08.

---

### Aşama D — Veri kümeleri

#### T-10 — TURSpider dev, BIRDTurk dev ve kurumsal sentetik set

**Amaç:** Değerlendirme verisi yerelde, lisans kurallarına uygun ve sürüm/SHA kayıtlı (E-13).

**Dosyalar:** `datasets/turspider.md`, `datasets/birdturk.md`, `datasets/enterprise.md` (yeni kartlar),
`tools/fetch_datasets.py` (yeni, `backend/` dışında; ağ yalnız burada),
`synthetic_data/populate.py` (SQLite + PG doldurma).

**Yapılacaklar:**
1. TURSpider `dev` (1.034 soru) ve veritabanları → `datasets/external/turspider/`.
   Lisansı HF kartından birincil kaynakla doğrula (rapor "CC BY 4.0" diyor, kontrol gerekli).
2. BIRDTurk yalnız **`dev`** (1.534) → `datasets/external/birdturk/`. **`train` indirilmez;**
   `cc-by-nc-sa-4.0` → yalnız değerlendirme (ADR-0009). Yükleyici zaten `train`'i reddediyor.
3. Her dosya için SHA-256 ve kaynak revizyonu karta yazılır (`benchmarks.sha256_file`).
4. Kurumsal sentetik set: `synthetic_data` ile SQLite (`erp_sqlite.sql`) ve PG (`erp.sql`)
   veritabanlarını doldur; 150–250 soru + 30 saldırı vakası `enterprise_dataset.py`'den.
   Eğitim bölümü (F8) farklı şema/tohumda; değerlendirmeyle **kesişmediğini** test et.

**Kabul kriterleri:** `load_turspider`, `load_birdturk(split="dev")`, `load_enterprise` gerçek
dosyalarla örnek sayılarını doğru döndürür; `git status` temiz (veri git'e girmedi).

**Doğrulama:**
```powershell
python -c "from benchmarks.loaders import load_turspider; print(len(load_turspider('datasets/external/turspider/dev.json').examples))"
git status --short
```

**Bağımlılık:** —

---

### Aşama E — PostgreSQL

#### T-11 — Yerel PostgreSQL 16 ve gerçek entegrasyon testleri

**Amaç:** `PostgresAdapter`, salt okunur rol, RLS ve maskeleme gerçek PG'de kanıtlansın (E-09).

**Dosyalar:** `tests/integration/test_postgres_live.py` (yeni, `@pytest.mark.postgres`),
`tests/security/test_postgres_live_attacks.py` (yeni, `@pytest.mark.security` + `@pytest.mark.postgres`),
`tests/conftest.py` (`TRSQL_PG_TEST_DSN` yoksa `postgres` testlerini atla),
`deployment/postgres/*.sql`, `deployment/docker-compose.yml`.

**Yapılacaklar:**
1. `docker compose -f deployment/docker-compose.yml up -d postgres`; `roles.sql`, `rls.sql`,
   `masking.sql` (ve uygunsa `pgaudit.sql`) uygula; `synthetic_data` ile `erp.sql` doldur.
2. Canlı testler (yalnız **sentetik** veri):
   - `nl2sql_reader` ile `INSERT/UPDATE/DELETE/DDL` → PG tarafında da reddedilir (savunma derinliği).
   - `statement_timeout`: `SELECT pg_sleep(10)` doğrulayıcıdan kaçsa bile PG keser
     (doğrulayıcı zaten reddetmeli; test adaptörü doğrudan `ApprovedQuery` ile zorlar).
   - RLS: `app.user_id`/tenant farklı iki kullanıcı farklı satır görür.
   - Maskeli görünümler: TCKN/telefon/e-posta açık metin dönmez.
   - `introspect()` yalnız izinli şemaları döndürür; `pg_catalog`/`information_schema` görünmez.
   - Satır sınırı ve dış `LIMIT` gerçek sonuçta uygulanır.
3. Güvenlik testleri **atlanamaz** kuralı: `tests/security/` altındaki canlı PG testi, DSN yokken
   atlanabilir olmalı mı? **Hayır** — canlı PG testlerini `tests/integration/` altında tut;
   `tests/security/` altına yalnız DSN gerektirmeyen vakaları ekle. (AGENTS.md §1.8 ile çelişme.)

**Kabul kriterleri:** `pytest -m postgres -q` yerelde yeşil; DSN tanımsızken G5 yine yeşil ve
`postgres` testleri "skipped" görünür; hiçbir mevcut güvenlik testi değişmedi.

**Doğrulama:**
```powershell
$env:TRSQL_PG_TEST_DSN="postgresql://nl2sql_reader:<parola>@localhost:5432/trsql"   # .env'den, commit yok
pytest -m postgres -q
pytest -m security -q
```

**Bağımlılık:** T-07 (psycopg), T-10 (sentetik veri), T-05 önerilir.

---

#### T-12 — CI'ya PostgreSQL servisli iş

**Dosyalar:** `.github/workflows/ci.yml`.

**Yapılacaklar:** Ayrı `postgres-integration` işi: `services: postgres:16`, sağlık kontrolü,
`deployment/postgres/*.sql` + sentetik veri, `pip install -e ".[dev,api,postgres]"`,
`pytest -m postgres -q`. Parolalar yalnız iş içi geçici değer (gerçek gizli bilgi yok).
Mevcut `gates` işi değişmez.

**Kabul kriterleri:** PR'da iki iş de yeşil.

**Bağımlılık:** T-11.

---

### Aşama F — Canlı D0–D8 ablasyon deneyleri

**Ortak kurallar (tüm F görevleri):**
- Klasör: `experiments/YYYY-AA-GG-<basamak>-<model>-<veri>/` → `config.toml`, `README.md`,
  `metrics.json` commit'lenir; `predictions.jsonl` ve `runs/` **commit'lenmez**.
- Kirli çalışma ağacında koşma (`DirtyWorkingTreeError`); önce commit.
- Seed 42; aynı veri bölümü; model + nicemleme + `template_id` + revizyon + SHA `metrics.json`'da.
- Önce `max_examples = 50` ile kısa koşu, sonra tam koşu.
- Her basamakta E1 (EX düşmez), E2 (saldırı yakalama %100, `db_reached_unsafe_rate = 0`),
  E3 (tepe VRAM ≤ 6.800 MB, p95 < 15 sn) kontrol edilir.
- Karşılaştırma: `python -m benchmarks.report <önceki> <yeni> --output report.md`
  (McNemar + %95 eşli bootstrap Gİ).

#### T-13 — D0 ve D1 taban çizgisi

**Yapılacaklar:** 2–4 aday model × {TURSpider dev, BIRDTurk dev, kurumsal} × {D0 `ddl_v1`, D1 `mschema_v1`}.
```powershell
python -m benchmarks.runner --config experiments/2026-12-01-d0-qwen3-turspider/config.toml
python -m benchmarks.runner --config experiments/2026-12-01-d1-qwen3-turspider/config.toml
python -m benchmarks.report experiments/2026-12-01-d0-qwen3-turspider experiments/2026-12-01-d1-qwen3-turspider --output experiments/reports/d0-d1.md
```
**Kabul:** Model × veri × basamak EX tablosu; Valid SQL, p50/p95, tepe VRAM, tokens/s; en iyi
1–2 model sonraki basamaklara taşınır (gerekçe README'de).
**Bağımlılık:** T-03, T-09, T-10.

#### T-14 — D2, D3, D4

**Yapılacaklar:** D2 (hibrit linker + Steiner; Schema Linking Recall ≥ 0,95 hedef), D3 (RAG +
BGE-M3 CPU; Recall@5 ≥ 0,9), D4 (morfoloji + belirsizlik; Clarification Rate). D3'te
`rank-bm25`/`faiss-cpu`/`datasketch` hızlandırıcı arka uçları deneyip saf Python'a göre
gecikme/doğruluk farkını ölç; fark yoksa ekstrayı `pyproject.toml`'dan çıkar (E-08).
Zemberek: `is_zemberek_available()` ise D4'ü iki kolda (kural tabanlı / Zemberek) koş.
**Kabul:** Ardışık Δ EX ve anlamlılık raporlu; E1 sağlanmış veya gerekçelendirilmiş.
**Bağımlılık:** T-13.

#### T-15 — D5 ve D6

**Yapılacaklar:** D5: tam L6 + L7, saldırı seti (kurumsal setin 30 vakası + `tests/security`
listeleri) **SQLite ve PostgreSQL'de**; meşru sorularda yanlış ret oranı. D6: `ComplexityRouter`
eşiği (`thinking_threshold`), `vote_candidates ∈ {1, 2, 4}`, `max_attempts ∈ {1, 3, 5}` ızgarası;
GBNF kolu (yalnız son SQL bloğu kısıtlı). Retry Rate ve ortalama deneme sayısı.
**Kabul:** E2 = %100, `db_reached_unsafe_rate = 0`; D6'da aynı/daha yüksek EX'te p95 < 15 sn.
**Bağımlılık:** T-14, T-11, T-04.

#### T-16 — D7 koşullu ince ayar kararı

**Yapılacaklar:** Önce D6 sonrası **en az 50 başarısız örneği elle etiketle** (lehçe / Türkçe
anlama / şema / değer / mantık). Sistematik Türkçe/lehçe hata sınıfı yoksa D7 = "uygulanmadı"
yaz ve T-17'ye geç. Varsa: yalnız sentetik + lisansı uygun veriyle QLoRA (3–4B yerelde; 7–9B için
8 GB sınırda → bulut GPU gerekebilir); BIRDTurk ve NC lisanslı veri **eğitime girmez**;
adaptör ayrı tutulur. `training/` klasörü `backend/` dışında olur.
**Kabul:** ≥ +4 puan net EX ve genel Türkçe regresyon ≤ 1 puan; aksi hâlde "uygulanmadı".
**Bağımlılık:** T-15.

#### T-17 — D8 tam sistem ve ana rapor

**Yapılacaklar:** `build_hybrid_pipeline` tüm bayraklar açık; model × D0–D8 × veri ana tablosu,
bileşen katkıları (Δ EX), güvenlik tablosu, gecikme/VRAM tablosu →
`experiments/reports/ablation-summary.md`.
**Kabul:** E1–E3 tümü sağlanmış; her satır bir `experiments/` klasörüne bağlı.
**Bağımlılık:** T-14…T-16.

---

### Aşama G — Kararlar ve ürünleştirme

#### T-18 — AR-09 karar ADR'leri

**Dosyalar:** `docs/adr/0011-...md` ve sonrası (`docs/adr/template.md`), `docs/adr/README.md`,
`docs/architecture/overview.md` (v1.0).
**ADR'ler:** seçilen model + nicemleme; schema linking yöntemi; retriever bileşimi; Zemberek kararı;
yönlendirme/oylama ayarı; D7 kararı; `rag` ekstrası kararı. ADR-0010'u "karara bağlandı" diye güncelle.
**Kabul:** Her ADR bir deney klasörüne bağlantı veriyor.
**Bağımlılık:** T-17.

#### T-19 — Üretim kimlik doğrulaması (OIDC/LDAP)

**Dosyalar:** `backend/auth/oidc.py` (yeni), `backend/auth/__init__.py`, `tests/unit/test_auth_oidc.py`,
`tests/security/` (yalnız ekleme), `docs/security/`.
**Yapılacaklar:** Kurum içi OIDC sağlayıcısı (ör. Keycloak) için JWT doğrulama: imza (yerel JWKS
dosyası — çalışma zamanında ağdan JWKS çekme **yok**, ADR-0002), `iss`, `aud`, `exp`, `nbf`;
grup/rol talebi → T-02 rol politikası. `authenticate(token) -> AuthContext` arayüzü aynı kalır.
JWT kütüphanesi gerekiyorsa `boundaries.toml` `[external]`'a yalnız `auth` için ekle → **önce sor**.
**Kabul:** Süresi geçmiş, yanlış `aud`, `alg=none`, imzasız token testleri reddediliyor.
**Bağımlılık:** T-02.

#### T-20 — Çevrimdışı uçtan uca test ve kabul senaryoları

**Dosyalar:** `tests/integration/test_offline_e2e.py` (yeni), `tests/acceptance/` (yeni; 20 kurumsal
soru, 5 netleştirme, 5 ret), `frontend/` için Playwright senaryosu (opsiyonel),
`deployment/install.ps1` / `install.sh`.
**Yapılacaklar:**
1. Ağ kapalı test: `socket.socket.connect`'i test boyunca yasaklayan fixture; `create_default_app`
   + Fake model + SQLite ile tam istek; herhangi bir dış bağlantı denemesi testi düşürür (ADR-0002).
2. Kabul senaryoları API üzerinden (ve mümkünse arayüzden) geçer.
3. `install.ps1` ile internetsiz bir makinede (veya ağı kapalı bir VM'de) belgelendiği gibi
   kurulum; çıkan sorunlar `deployment/README.md`'ye.
**Kabul:** 30 senaryo geçiyor; ağ kapalı test yeşil; kurulum adımları doğrulandı.
**Bağımlılık:** T-01, T-02, T-06.

#### T-21 — Doküman ve yol haritası güncellemesi

**Dosyalar:** `docs/roadmap.md`, `README.md`, `CHANGELOG.md`, `docs/architecture/module-map.md`,
bu dosya.
**Yapılacaklar:** "Güncel durum" tablosuna "kodda var" ile "gerçek model/PG/veriyle ölçüldü"
ayrımını ekle (E-15). Tamamlanan görevleri bu dosyada `[x]` yap.
**Bağımlılık:** Her aşama sonunda kısmen; son hâli T-18 sonrası.

---

## 4. İlerleme kontrol listesi

- [x] T-01 API composition root + Dockerfile
- [x] T-02 Rol politikası ve token yükleyicisi
- [x] T-03 D0–D8 basamak profilleri + gerçek gömme
- [x] T-04 Koşucuda PostgreSQL
- [x] T-05 Çok şemalı RBAC
- [x] T-06 Frontend `/v1/plan` + testler
- [ ] T-07 Yerel ortam (CUDA llama-cpp-python, psycopg, …)
- [x] T-08 Model manifest doğrulama
- [ ] T-09 GGUF indirme + SHA + GPU duman testi + VRAM
- [x] T-10 Veri kümeleri
- [ ] T-11 Yerel PG + canlı entegrasyon testleri
- [ ] T-12 CI PostgreSQL işi
- [ ] T-13 D0/D1
- [ ] T-14 D2–D4
- [ ] T-15 D5–D6
- [ ] T-16 D7 kararı
- [ ] T-17 D8 + ana rapor
- [ ] T-18 AR-09 ADR'leri
- [ ] T-19 OIDC/LDAP
- [ ] T-20 Çevrimdışı e2e + kabul senaryoları
- [ ] T-21 Doküman güncellemesi

## 5. Agent'a verilecek örnek başlangıç komutu

```text
docs/kalan-isler-plani.md dosyasını ve AGENTS.md'yi oku. T-01'den başla.
Her görevde: yeni dal aç (feat/t-01-composition-root gibi), önce testi yaz, sonra kodu,
G1–G5'i çalıştır, plan dosyasında görevi [x] yap, PR aç. Bir görevin kabul kriterini
karşılayamıyorsan ya da AGENTS.md §7'deki bir duruma düşersen dur ve bana sor.
```

## 6. Riskler

| Risk | Etki | Önlem |
|---|---|---|
| Resmî model depolarında GGUF yok / dosya adı farklı | T-09 gecikir | T-08'de önce doğrula; gerekirse yerelde dönüştür |
| 9B model 8 GB'a sığmaz (KV cache ile) | E3 ihlali | `n_ctx=4096`, `q8_0` KV, katman boşaltma; uymazsa adaydan çıkar |
| Windows'ta CUDA derlemesi başarısız | T-07 durur | Önceden derlenmiş CUDA tekerleği; WSL2 alternatifi |
| BIRDTurk lisansı | Eğitim yasağı ihlali | Yükleyici `train`'i reddediyor; T-16'da veri listesi denetimi |
| T-03 yapılmadan deney koşulması | Yanlış ablasyon tablosu | Aşama A bitmeden F başlamaz |
| Canlı PG testlerinin `tests/security/`'ye konması | "Atlanamaz" kuralıyla çelişki | Canlı PG testleri `tests/integration/` altında |
