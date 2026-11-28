# Veri Kümesi Kartı: Kurumsal Sentetik ERP Seti

| Alan | Değer |
|---|---|
| **Kaynak** | Proje içi sentetik üreteç (`synthetic_data/populate.py` ve `synthetic_data/enterprise_dataset.py`) |
| **Şema** | `synthetic_data/schema/erp_sqlite.sql` (SQLite) ve `synthetic_data/schema/erp.sql` (PostgreSQL 16) |
| **Lisans** | TRSQL özel lisansı — tüm hakları saklıdır; %100 sentetik veri (gerçek kişisel veri yok) |
| **Bölümler** | Değerlendirme seti: 160 kurumsal soru (96 normal, 24 iş kuralı, 24 belirsiz, 16 yanıtlanamaz) + 30 güvenlik saldırısı (`datasets/external/enterprise/eval.jsonl`). Koşullu eğitim bölümü (D7): `build_disjoint_training_db` ile ayrık şema ve tohumda üretilir (**kesişme yok**). |
| **Şema & Hücre dili** | **Türkçe** (`İ/ı, Ş/ş, Ğ/ğ, Ü/ü, Ö/ö, Ç/ç`) + bilinçli İngilizce kısaltmalar (`sku`, `tax_no`, `erp_code`) |
| **Ayrıklık Doğrulaması** | `synthetic_data.validate_disjoint_dbs` ve `pytest tests/unit/test_synthetic_data.py` eğitim ile değerlendirme veritabanlarının kesişmediğini doğrular. |
| **Üretim komutu** | `python tools/fetch_datasets.py --enterprise-only` (ham çıktı `datasets/external/` altında, git'e girmez) |
