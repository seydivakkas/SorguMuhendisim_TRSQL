# Veri Kümesi Kartı: BIRDTurk (yalnız `dev`)

| Alan | Değer |
|---|---|
| **Kaynak URL** | `https://huggingface.co/datasets/metunlp/birdturk` |
| **Makale / Künye** | Aktaş vd. (Roketsan & ODTÜ), SIGTURK 2026 @ EACL |
| **Commit / Revizyon** | `bb1c95577395223a8f893693b164bd8384089c7a` |
| **Kaynak dosya** | `dev/dev_tr.json` ve `dev/dev_databases/` (`train_tr.json` **ASLA** indirilmez) |
| **Lisans ve kısıt** | `cc-by-nc-sa-4.0` (HF veri kartı esas alınır, **yalnızca değerlendirme** — ADR-0009; `benchmarks/loaders/birdturk.py` `train` bölümünü ve `for_training=True` bayrağını reddeder) |
| **Bölüm** | Yalnızca `dev` (1.534 soru) |
| **Şema & Hücre dili** | Tablo ve sütun adları **Türkçe**, veritabanı hücre değerlerinin bir kısmı İngilizce |
| **Yerel dosya SHA-256** | İndirme sırasında `tools/fetch_datasets.py` ile hesaplanır (`datasets/external/` git'e girmez) |
| **Bilinen sınırlılıklar** | BIRD Mini-Dev kaynaklı etiket gürültüsünü (~%52,8, Jin vd. 2026) ve çevrilmemiş hücre değerlerini devralır. Sonuçlar raporlanırken bu kısıtlar açıkça belirtilir. |
