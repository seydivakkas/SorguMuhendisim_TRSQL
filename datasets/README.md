# datasets/ — Veri Kümesi Kartları ve Lisans Politikası

**Ham veri ve veritabanı dosyaları git'e girmez** (`.gitignore`: `datasets/raw/`, `datasets/external/`, `*.sqlite`, `*.db`).
Bu klasörde yalnızca veri kümesi dokümantasyonu, lisans kısıtları ve doğrulama kuralları yer alır (ADR-0009).

## Veri Kümeleri Özeti

| Veri Kümesi | Kaynak / Künye | Boyut ve Bölümler | Şema & Hücre Dili | Lisans | TRSQL'de İzin Verilen Kullanım |
|---|---|---|---|---|---|
| **TURSpider** | Kanburoğlu & Tek, IEEE Access 12 (2024), DOI `10.1109/ACCESS.2024.3498841` | Spider'ın insan çevirisi (`dev`: 1.034 soru) | Şema ve hücre değerleri **İngilizce**, sorular Türkçe | Rapora göre HF kartında `CC BY 4.0` (birincil kontrol gerekli) | **Değerlendirme** (D0–D8 ablasyonu) |
| **BIRDTurk** | Aktaş vd. (Roketsan + ODTÜ), SIGTURK 2026 @ EACL (`metunlp/birdturk`) | 10.962 çift (`train`: 9.428, `dev`: 1.534; test yok) | Şema tablo/sütun adları **Türkçe**, hücre değerleri **İngilizce** | Makale: `CC BY-SA 4.0`; **HF veri kartı: `cc-by-nc-sa-4.0`** | **YALNIZCA Değerlendirme (`dev`)** — eğitim/ince ayar yasaktır (ADR-0009) |
| **TUR2SQL** | Kanburoğlu & Tek, UBMK 2023, DOI `10.1109/UBMK59864.2023.10286686` (`alibugra/TUR2SQL`) | 10.809 soru-SQL çifti | Türkçe sorular | **Depoda lisans beyanı yok** | **Ana ölçüt değil** (%96–98 EX doygun); yazılı izin olmadan eğitim/ticari kullanım yasaktır |
| **Kurumsal Sentetik Set** | Proje içi üretim (`synthetic_data/`) | Değerlendirme seti (150–250 soru + 30 güvenlik saldırısı) + ayrı eğitim bölümü (F8) | Şema (Türkçe + bilinçli İngilizce kısaltmalar) ve hücre değerleri **Türkçe** (`İ/ı/Ş/ş/Ğ/ğ`) | Proje içi (TRSQL özel lisansı) | Değerlendirme + (ayrı şema/bölümde) koşullu eğitim (F8) |

## Kritik Lisans ve Metodoloji Kuralları (ADR-0009)

1. **BIRDTurk (`cc-by-nc-sa-4.0`) yalnızca değerlendirme içindir:**
   - Makalede `CC BY-SA 4.0` yazsa da Hugging Face veri kartında **`cc-by-nc-sa-4.0`** (ticari olmayan) belirtildiği için daha kısıtlayıcı lisans esas alınır.
   - `benchmarks/loaders/birdturk.py` yükleyicisi `eval_only=True` olarak işaretlenmiştir ve `train` bölümü veya eğitim amaçlı yükleme istendiğinde hata verir.
   - BIRDTurk `dev` sonuçları raporlanırken BIRD Mini-Dev kaynaklı etiket hatalarının (Jin vd. 2026: %52,8) miras alındığı ve hücre değerlerinin İngilizce kaldığı açıkça belirtilir.
2. **Eğitim / Değerlendirme Sızıntı Önleme:**
   - Kurumsal sentetik veri üretiminde (`F8 / AR-06`) eğitim ve değerlendirme veritabanları birbirinden ayrılır.
   - Değerlendirmede kullanılan soru ve şema örnekleri hiçbir ince ayar (`LoRA / QLoRA`) kümesine karıştırılmaz.
3. **TUR2SQL ve TURSpider:**
   - TUR2SQL yüksek doymuşluk (%96–98 EX) ve şema sızıntısı şüphesi nedeniyle ana kıyas ölçütü olarak kullanılmaz.
   - Lisansı belirsiz veya beyansız dış veri kümeleri yazar izni olmadan eğitim verisine alınmaz.

## Veri Kümesi Kartı Alanları (`datasets/<ad>.md`)

Yerel indirilen her dış veri kümesi için aşağıdaki bilgiler kaydedilir:

- Kaynak URL ve sürüm / commit revizyonu
- Dosya SHA-256 özeti
- Lisans türü ve ticari / eğitim kısıtı
- Bölümler (`train` / `dev` / `test`) ve satır sayıları
- Bilinen kalite/çeviri sorunları (örn. çevrilmemiş hücre değerleri, etiket gürültüsü)
