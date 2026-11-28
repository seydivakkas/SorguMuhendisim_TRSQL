# Yol Haritası ve Araştırma Paketleri (AR-01–AR-10)

Mimari v0.2 bir **araştırma adayıdır**. Süreç:

```text
AR-01 … AR-08  →  araştırma + prototip deneyleri (D0–D8)
AR-09          →  nihai mimari kararları (ADR'ler, v1.0)
AR-10          →  atomik görevler, agent paketleri, veri sözleşmeleri,
                  test registry ve entegrasyon gate'leri → geliştirme
```

## Paketler

| Paket | Etkilediği mimari alan | Ana sorular | Çıktılar | Ablasyon |
|---|---|---|---|---|
| **AR-01** | Tüm mimari | Literatür ve mevcut sistemler; katman sınırları doğru mu? | Literatür raporu (`research/`), v0.2 gözden geçirme | — |
| **AR-02** | Model Engine | Hangi küçük model, hangi istem biçimi? | Model karşılaştırma tablosu, `ModelAdapter` uygulamaları | D0, D1 |
| **AR-03** | Turkish NLP & Schema Linking | Kural tabanlı vs. Zemberek; sözlük vs. hibrit linking; Steiner JOIN | `turkish_nlp`, `schema_linking` iyileştirmeleri, linking metrikleri | D2, D4 |
| **AR-04** | RAG & Semantic Layer | BM25, FAISS (BGE-M3, CPU), RRF; LSH değer araması; metrik katmanı | Retriever adayları, Recall@K raporu | D3 |
| **AR-05** | Inference Engine | llama.cpp vs. ONNX Runtime; quantization; VRAM/gecikme; thinking yönlendirme | Çıkarım ölçümleri, `LlamaCppAdapter`, yeniden deneme bütçesi ayarı | D6 |
| **AR-06** | Model Training & Synthetic Data | Sentetik kurumsal veri; LoRA/QLoRA, RAFT gerekli mi? | `synthetic_data/` üreticisi, ince ayar deneyi | D7 |
| **AR-07** | Security, Validation & Execution | Semantik/iş kuralı doğrulaması; PostgreSQL salt okunur rol + RLS; rate limit; kimlik doğrulama | `PostgresAdapter`, L6 tamamlanması, güvenlik saldırı seti | D5 |
| **AR-08** | Evaluation & Benchmark | Metrikler, koşucular, istatistiksel test; observability | `benchmarks/` koşucuları, OpenTelemetry, rapor şablonu | Tümü |
| **AR-09** | Nihai mimari kararları | Hangi adaylar kalıcı? | v1.0 mimari dokümanı, karar ADR'leri | D8 |
| **AR-10** | Geliştirme ve entegrasyon | Ürünleştirme | Frontend (L0), dağıtım, atomik görev listesi, agent paketleri, test registry, entegrasyon gate'leri | — |

## Güncel durum (v1.0.0 — AR-01–AR-10)

| Katman / Alan | Durum |
|---|---|
| L1 (`api`, `auth`) | ✅ Bearer auth, RBAC şema kapsamlama, kayan pencere rate limit (`429`), boyut kontrolü (`413`), tenant/bağlantı sahipliği (`403`), `/v1/plan` HITL önizleme, çevrimdışı `TRSQLMCPServer` |
| L2 (`turkish_nlp`) | ✅ Morfolojik çözümleme, ASCII→Türkçe normalizasyon, eş anlamlılar, göreli zaman çözümleme, belirsizlik tespiti, opsiyonel Zemberek kancası |
| L3 (`schema_linking`, `schema_intelligence`) | ✅ `SchemaGraph` Steiner JOIN onarımı + `HybridSchemaLinker` (sözlük + morfoloji + bulanık eşleşme + gömme + çift yönlü doğrulama + token bütçesi) |
| L4 (`knowledge_base`, `rag`, `semantic_layer`) | ✅ `BM25Retriever` + `DenseRetriever` + `HybridKnowledgeRetriever` (RRF) + `ValueLinker` (MinHash-LSH) + `SemanticLayer` deterministik KPI şablonları |
| L5 (`query_planner`, `prompt_engine`, `model_engine`, `sql_generator`, `orchestration`) | ✅ `M-Schema` / `DDL` / `sql-gen/v1` şablonları, GBNF kısıtlı üretim, `LlamaCppAdapter` + `FakeModelAdapter`, `ComplexityRouter` (`DIRECT`/`THINKING`), N-aday tutarlılık oylaması (`build_hybrid_pipeline`) |
| L6 (`sql_validator`, `policy_engine`) | ✅ 8 aşamalı doğrulama (Syntax, AST, Schema, Semantic, Authorization, Business Rule, Cost/EXPLAIN, Injection) + `ApprovedQuery` zorunluluğu |
| L7 (`execution_engine`, `database_adapters`) | ✅ Salt okunur `SQLiteAdapter` + `PostgresAdapter` (RLS, `statement_timeout`, satır sınırı) |
| L8 (`result_engine`) | ✅ Deterministik Türkçe sayı/özet biçimlendirme + grafik önerisi |
| L9 (`observability`, `benchmarks`) | ✅ KVKK maskelemeli JSONL audit izi, `MetricsCollector` (aşama gecikme/tekrar/güvenlik sayaçları + korumalı OpenTelemetry köprüsü), `benchmarks/` koşucuları |
| L0 & Dağıtım (`frontend/`, `deployment/`, `synthetic_data/`) | ✅ React + TypeScript L0 arayüzü (HITL plan önizleme dahil), Docker Compose on-prem dağıtım paketi, sentetik kurumsal veri üreticisi |

## Agent ile çalışma

AR-10'da her atomik görev, `.github/ISSUE_TEMPLATE/work-package.md` biçiminde bir issue
olur: tek modül, net girdi/çıktı sözleşmesi, ölçülebilir kabul kriteri ve kapatıcı gate.
Agent'lar [AGENTS.md](../AGENTS.md) kurallarıyla çalışır.
