# synthetic_data/ — Sentetik Kurumsal Şema, Veri Kümesi ve Üretici (F1b & F8 / AR-06)

Bu paket gerçek kurum veya kişi verisi kullanmadan Türk ERP/Satış/Finans/Stok/İK senaryolarını temsil eden PostgreSQL 16 ve SQLite 3 veritabanlarını, 160 soruluk kurumsal Türkçe ölçüt kümesini, 30 Türkçe güvenlik saldırısı listesini ve OmniSQL esinli sentetik veri üreticisini içerir.

## Dosyalar

| Dosya | Açıklama |
| --- | --- |
| `schema/erp.sql` | 28 tablolu PostgreSQL 16 ERP şeması (`tr-TR-x-icu` ICU collation, 24 Türkçe tablo + 4 çapraz dilli kısaltmalı tablo `cust_loyalty`, `inv_ledger`, `prod_pricing_hist`, `wh_stock_snap`). |
| `schema/erp_sqlite.sql` | Aynı 28 tablo ve yabancı anahtar yapısının yerel test/benchmark için SQLite 3 uyumlu sürümü. |
| `populate.py` | Deterministik `tr_TR` sentetik veri doldurucu (`seed` destekli; `Faker('tr_TR')` varsa kullanır, yoksa yerleşik Türkçe üreticiye düşer). Test Suite Accuracy için `seed=1, 2, 3` mutasyonlu DB örnekleri üretir. |
| `enterprise_dataset.py` | 160 maddelik doğrulanmış kurumsal set (`96` normal, `24` iş kuralı, `24` belirsiz, `16` yanıtsız) + ayrı 30 maddelik Türkçe güvenlik saldırı seti + tüm yanıtlanabilir altın SQL'leri çalıştıran doğrulayıcı. |
| `generator.py` | OmniSQL esinli `SyntheticSQLGenerator`: karmaşıklık düzeylerine (`easy`, `medium`, `hard`, `nested`) göre aday SQL üretir, izole salt okunur SQLite üzerinde hatalı/boş sonuçları eler, 3 farklı Türkçe üslupta (`formal`, `colloquial`, `abbreviated`) soru üretir ve geri çeviri tutarlılık kancası uygular. |

## Güvenlik ve Lisans İlkeleri

- **Sıfır gerçek kişisel veri:** Tüm `tckn` değerleri `00...` ile başlayan geçersiz 11 haneli dizeler, tüm `iban` değerleri `TR00...` ile başlayan ISO 13616 dışı sahte değerler, telefonlar `+90 000 ...` ve e-postalar `.invalid` alan adıdır.
- **RBAC hassas varlıklar:** `maaslar` tablosu ve `tckn`/`vergi_no`/`iban` sütunları standart analist rolüne kapalı olacak şekilde modellenmiştir; `SyntheticSQLGenerator` bu alanları eğitim istemlerinden hariç tutar.
- **ADR-0009 uyumu:** `SyntheticSQLGenerator`, BIRDTurk ve `cc-by-nc*` / `qwen-research` lisanslı kaynakları reddeder (`LicenseComplianceError`) ve eğitim ile değerlendirme veritabanlarının ad/özet düzeyinde ayrık olmasını zorunlu kılar (`DisjointSplitError`).

## Hızlı Doğrulama

```powershell
.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests/unit/test_synthetic_data.py -q
```
