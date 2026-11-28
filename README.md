# TRSQL — Sorgu Mühendisim

**Türkçe doğal dil ile kurumsal veritabanları arasında güvenli, açıklanabilir ve yerel
çalışan bir veri erişim platformu.**

> *Geçen ay Trabzon'daki en çok satış yapan beş bayimiz hangileri?*
> → yetki kontrolü → Türkçe çözümleme → şema eşleştirme → kurumsal kurallar → küçük yerel
> model → 8 aşamalı SQL doğrulama → salt okunur yürütme → tablo, grafik ve Türkçe açıklama

![status](https://img.shields.io/badge/mimari-v0.2%20Research%20Candidate-orange)
![python](https://img.shields.io/badge/python-3.11%2B-blue)
![license](https://img.shields.io/badge/license-All%20Rights%20Reserved-red?style=flat-square)

TRSQL yalnızca Türkçe metni SQL'e çeviren bir uygulama değildir. Yapay zekâ modeli sistemin
tamamı değil, **değiştirilebilir bir bileşenidir**; yetkilendirme, iş kuralları, sayısal
sonuçlar ve veritabanı erişimi deterministik katmanlarda kalır.

## Öne çıkanlar

- **Turkish Linguistic Intelligence** — ekler, göreli zaman, sayı sözcükleri, belirsizlik tespiti
- **Graph-based Schema Linking** — PK/FK grafı, JOIN yolu keşfi
- **Enterprise RAG & Semantic Intelligence** — onaylı iş kuralları, sürümlü metrikler
- **Hardware-aware Small Language Models** — 3B–9B, 4-bit, 8 GB VRAM
- **Multi-stage SQL Verification** — 8 kontrol, fail-closed, derinlemesine savunma
- **Scientific Benchmark & Evaluation** — D0–D8 ablasyonu, TURSpider / BIRDTurk

## Mimari (L0–L9)

| Katman | Görev | Modüller |
|---|---|---|
| L0 Client | Türkçe sohbet, SQL editörü, grafikler | `frontend/` |
| L1 API & Security Gateway | Kimlik, RBAC, **şemadan önce yetkilendirme** | `api`, `auth` |
| L2 Turkish NLP | Niyet, varlık, yer, zaman, sıralama, limit | `turkish_nlp` |
| L3 Schema Linking | Kelime → tablo/sütun, JOIN yolu | `schema_intelligence`, `schema_linking` |
| L4 Enterprise RAG & Semantic | İş kuralları, metrikler, few-shot | `knowledge_base`, `rag`, `semantic_layer` |
| L5 SQL Generation | Plan, istem, `ModelAdapter`, aday SQL | `query_planner`, `prompt_engine`, `model_engine`, `sql_generator` |
| L6 Verification & Security | Syntax, AST, şema, yetki, maliyet, enjeksiyon… | `sql_validator`, `policy_engine` |
| L7 Execution | Salt okunur, zaman aşımı, satır sınırı | `execution_engine`, `database_adapters` |
| L8 Result Intelligence | Tablo, grafik, deterministik Türkçe açıklama | `result_engine` |
| L9 Evaluation & Observability | Audit, maskeleme, metrikler | `observability`, `benchmarks/` |

Akışı yöneten modül: `orchestration` (bkz. [istek yaşam döngüsü](docs/architecture/request-lifecycle.md)).

**Modular Monolith** ([ADR-0001](docs/adr/0001-modular-monolith.md)): tek süreç, katı modül
sınırları (`backend/boundaries.toml`, CI'da denetlenir).

## Hızlı başlangıç

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\Activate.ps1
pip install -e ".[dev,api]"
pytest                                # tüm testler (GPU/ağ gerekmez)
python tools/check_boundaries.py      # modül sınırları
```

Ayrıntılar: [geliştirme ortamı](docs/guides/getting-started.md).

## Dokümantasyon

| Doküman | İçerik |
|---|---|
| [Mimari genel bakış](docs/architecture/overview.md) | Vizyon, v0.1 değerlendirmesi, L0–L9, teknoloji adayları |
| [İstek yaşam döngüsü](docs/architecture/request-lifecycle.md) | Adımlar, sıra diyagramı, üç hata sınıfı, algoritma |
| [Veri sözleşmeleri](docs/architecture/data-contracts.md) | Pydantic sözleşmeleri ve portlar |
| [Modül haritası](docs/architecture/module-map.md) | Repo yapısı, bağımlılık kuralları |
| [Tasarım ilkeleri](docs/principles.md) | 10 ilke ve nasıl denetlendikleri |
| [ADR'ler](docs/adr/README.md) | Mimari kararlar (0001–0010) |
| [Güvenlik politikası](docs/security/security-policy.md) | Tehdit modeli, katman kontrolleri, KVKK |
| [Değerlendirme planı](docs/evaluation/evaluation-plan.md) | Metrikler, veri kümeleri, D0–D8 |
| [Yol haritası](docs/roadmap.md) | AR-01–AR-10, iskeletin durumu |
| [AGENTS.md](AGENTS.md) | Agent ve geliştirici kuralları |
| [Katkı rehberi](CONTRIBUTING.md) | Dal, commit, PR, ADR süreci |

## Referans donanım

RTX 4070 Laptop (8 GB VRAM, net ≈ 6,8 GB) · 32 GB RAM · Windows. Bütün model kararları bu
donanımda ölçülür.

## Durum

v0.2 **araştırma adayıdır**. AR-01–AR-08 deneylerinden sonra AR-09'da kesinleşir. İskelette
çalışan kısımlar ve eksikler: [yol haritası](docs/roadmap.md#iskeletin-bugünkü-durumu-v020).
