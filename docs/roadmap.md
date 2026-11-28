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

## İskeletin bugünkü durumu (v0.2.0)

| Katman | Durum |
|---|---|
| L1 | Kimlik doğrulama: yalnız geliştirme sağlayıcısı. Şema kapsamlama: ✅ |
| L2 | Kural tabanlı temel ayrıştırıcı ✅ (Zemberek: AR-03) |
| L3 | Sözlük tabanlı linker + BFS/Steiner JOIN ✅ (hibrit: AR-03) |
| L4 | Anahtar kelime retriever + semantik katman ✅ (BM25/FAISS/RRF: AR-04) |
| L5 | Planner, prompt builder, `ModelAdapter`, `FakeModelAdapter` ✅; `LlamaCppAdapter`: AR-05 |
| L6 | Syntax, AST, Schema, Authorization, Injection, Cost ✅; Semantic, Business Rule: AR-07 |
| L7 | SQLite salt okunur adaptör ✅; PostgreSQL: AR-07 |
| L8 | Deterministik Türkçe özet + grafik önerisi ✅ |
| L9 | Audit + maskeleme ✅; metrik dışa aktarımı: AR-08 |
| L0 | Yok (AR-10) |

## Agent ile çalışma

AR-10'da her atomik görev, `.github/ISSUE_TEMPLATE/work-package.md` biçiminde bir issue
olur: tek modül, net girdi/çıktı sözleşmesi, ölçülebilir kabul kriteri ve kapatıcı gate.
Agent'lar [AGENTS.md](../AGENTS.md) kurallarıyla çalışır.
