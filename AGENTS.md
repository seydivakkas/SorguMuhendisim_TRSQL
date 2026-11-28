# AGENTS.md — TRSQL için yapay zekâ agent'ı ve geliştirici kuralları

Bu dosya, bu repoda çalışan **her** kodlama agent'ı (Claude Code, Codex, Copilot vb.) ve
insan geliştirici için bağlayıcıdır. `CLAUDE.md` bu dosyaya yönlendirir.

Önce oku: [mimari](docs/architecture/overview.md) ·
[yaşam döngüsü](docs/architecture/request-lifecycle.md) ·
[sözleşmeler](docs/architecture/data-contracts.md) ·
[modül haritası](docs/architecture/module-map.md) · [ilkeler](docs/principles.md) ·
[ADR'ler](docs/adr/README.md)

---

## 1. Değişmez kurallar (asla ihlal etme)

1. **Model veritabanına asla dokunmaz.** `model_engine` yalnızca `core`'u içe aktarır.
   Veritabanına giden tek yol: `SQLCandidate → sql_validator → policy_engine →
   ApprovedQuery → execution_engine → database_adapters`. Bu zinciri kısaltan, atlayan veya
   `ApprovedQuery` doğrulayıcısını gevşeten değişiklik yapma. (ADR-0004)
2. **RBAC şemadan önce.** L2–L5'e giden her şema `auth.scope_schema()` çıktısıdır. Tam şemayı
   yalnızca `sql_validator` ve `database_adapters` görür. (ADR-0004)
3. **Güvenlik ihlali yeniden denenmez.** `Severity.SECURITY` → `REJECTED`. Bu hataları modele
   geri bildirim olarak gönderme; ret mesajlarına gizli tablo/sütun adı yazma. (ADR-0005)
4. **Yeniden deneme bütçesi sınırlıdır.** Sonsuz döngü, bütçeyi atlayan özyineleme veya
   `max_attempts` üst sınırını (5) kaldırma yok. (ADR-0006)
5. **Offline-first.** `backend/` içinde ağ çağrısı yapma; HTTP istemcisi ekleme; çalışma
   zamanında model/veri indirme. (ADR-0002)
6. **Sayılar deterministik.** L8'de kullanıcıya gösterilen hiçbir sayı modelden gelmez. (ADR-0008)
7. **Gizli bilgi yok.** DSN, parola, anahtar, gerçek kişisel veri commit'leme. Yalnız ortam
   değişkenleri; test verisi sentetik.
8. **Güvenlik testleri kutsaldır.** `tests/security/` altındaki testleri silme, `skip`/`xfail`
   ekleme, saldırı örneklerini listeden çıkarma veya beklenen sonucu gevşetme. Bir test
   kırılıyorsa **kodu** düzelt.
9. **Lisanslar.** BIRDTurk ve NC lisanslı veri eğitim verisine karışmaz; model ağırlıkları ve
   ham veri git'e girmez. (ADR-0009)

## 2. Modül sınırı kuralları (Modular Monolith, ADR-0001)

- Her modül `backend/<modül>/`; genel API `__init__.py` + `__all__`.
- Başka modülü yalnızca **genel API'sinden** içe aktar: `from backend.rag import X`.
  `from backend.rag.retriever import X` başka modülden **yasak**.
- İzin verilen bağımlılıklar yalnızca `backend/boundaries.toml`'da. Yeni bağımlılık
  gerekiyorsa önce bir portla çözmeyi dene; olmuyorsa `boundaries.toml` + ADR değişikliği
  aynı PR'da ve gerekçeli.
- `core` hiçbir `backend` modülünü içe aktaramaz.
- Modüller arası veri **yalnızca** `backend/core/contracts.py` sözleşmeleriyle taşınır.
  Modülün iç sınıfını başka modüle sızdırma, `dict` ile veri taşıma.
- Birleştirme (wiring) yalnızca `orchestration` içinde.
- Dış paket kısıtları: veritabanı sürücüleri → `database_adapters`; `fastapi` → `api`;
  çıkarım kütüphaneleri → `model_engine`; `sqlglot` → `sql_validator`, `policy_engine`.
- Yeni modül eklerken: `boundaries.toml`'a ekle, `module-map.md`'yi güncelle.

Kontrol: `python tools/check_boundaries.py`

## 3. Kodlama standartları

- Python ≥ 3.11, her dosyada `from __future__ import annotations`.
- **Tam tip açıklaması**; `mypy --strict` temiz olmalı. `Any` yalnızca veritabanı satır
  değerlerinde.
- Ruff kuralları (`pyproject.toml`); satır uzunluğu 110; `ruff format`.
- **Kod, tanımlayıcılar, docstring'ler ve commit mesajları İngilizce.** Kullanıcıya dönen
  mesajlar, hata metinleri ve dokümantasyon **Türkçe**.
- Türkçe metin üzerinde `.lower()`/`.upper()` kullanma → `backend.turkish_nlp.tr_casefold`.
- Sözleşmeler değiştirilemez (`frozen`); yeni sürüm için `model_copy(update=...)`.
- Saat/tarih bağımlı kod `today`/`now` enjeksiyonu alır (deterministik test).
- SQL'i string birleştirme ile kurma; AST (SQLGlot) veya parametre bağlama kullan.
- Hata hiyerarşisi: `backend/core/errors.py`. Çıplak `except:` yok; yutulan hata yok.
- Loglanan her serbest metin `observability.mask_sensitive()`'ten geçer.
- Henüz yazılmamış davranış için `NotImplementedError("... AR-0X")` + docstring'de plan.
  Sessizce "geçti" dönen sahte kontrol yazma; yazıyorsan raporda açıkça belirt
  (örnek: L6 semantic check mesajı).

## 4. Test kuralları

| Klasör | Kapsam | İşaret |
|---|---|---|
| `tests/unit/` | Tek modül, saf fonksiyonlar | — |
| `tests/security/` | Saldırı örnekleri, derinlemesine savunma | `@pytest.mark.security` |
| `tests/integration/` | Uçtan uca pipeline, SQLite + `FakeModelAdapter` | `@pytest.mark.integration` |
| `tests/architecture/` | Modül sınırları | — |

- Her davranış değişikliği bir test ile gelir; her hata düzeltmesi önce kırmızı test.
- Testler GPU, ağ ve gerçek model gerektirmez (`FakeModelAdapter`).
- Test verisi `tests/fixtures/` altında ve **sentetik**.
- Yeni bir saldırı sınıfı keşfedersen `tests/security/test_validator.py` listelerine ekle.
- Başarısız testleri düzeltirken yalnızca başarısız olanları yeniden çalıştır; sonunda tüm
  paketi bir kez çalıştır.

## 5. Kapılar (gates) — PR birleşmeden önce

| Gate | Komut |
|---|---|
| G1 Lint/format | `ruff check . && ruff format --check .` |
| G2 Tip | `mypy` |
| G3 Sınırlar | `python tools/check_boundaries.py` |
| G4 Güvenlik | `pytest -m security` |
| G5 Tüm testler | `pytest` |
| E1–E3 Deney | `docs/evaluation/evaluation-plan.md` §8 (bileşen birleştirmeden önce) |

Bir gate'i geçmek için gate'i gevşetme (kural kapatma, `# type: ignore` yağmuru, test silme).

## 6. Çalışma akışı (agent için)

1. Görevi bir AR paketine ve tek bir modüle bağla. Birden fazla modüle dokunuyorsa
   önce sözleşme değişikliğini ayrı adım olarak yap.
2. İlgili ADR'leri oku. Karar değiştiriyorsan yeni ADR yaz (`docs/adr/template.md`).
3. Küçük, odaklı değişiklik; ilgisiz yeniden düzenleme yapma.
4. Test yaz → kodu yaz → G1–G5'i çalıştır.
5. Sözleşme/sınır/karar değiştiyse ilgili dokümanı **aynı PR'da** güncelle.
6. PR şablonunu doldur. `main`'e doğrudan push yok.

## 7. Durup sormanı gerektiren durumlar

- Bir değişmez kuralı (§1) ihlal etmeden görevi yapamıyorsan.
- `boundaries.toml`'a yeni bir izin eklemen gerekiyorsa.
- Güvenlik testini değiştirmen gerekiyormuş gibi görünüyorsa.
- Lisansı belirsiz veri/model kullanman gerekiyorsa.
- Gerçek kurum verisi veya gizli bilgiyle karşılaşırsan (dokunma, bildir).

## 8. Sözlük (tutarlı adlandırma)

| Türkçe | Kodda |
|---|---|
| soru | `question` |
| niyet | `intent` |
| varlık / bahis | `entity` / `mention` |
| zaman ifadesi | `temporal` |
| şema eşleştirme | `schema linking` |
| iş kuralı | `business rule` |
| metrik tanımı | `metric definition` |
| aday SQL | `SQLCandidate` |
| doğrulama raporu | `ValidationReport` |
| onaylı sorgu | `ApprovedQuery` |
| netleştirme | `clarification` |
| kiracı / kurum | `tenant` |
