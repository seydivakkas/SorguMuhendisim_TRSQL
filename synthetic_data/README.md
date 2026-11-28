# synthetic_data/ — Sentetik kurumsal veri (AR-06)

Amaç: Gerçek kişisel veri kullanmadan kurumsal senaryoları (bayi, satış, iade, hedef,
müşteri) temsil eden PostgreSQL/SQLite veritabanları ve 150–250 Türkçe soru-SQL çifti üretmek.

Kurallar:
- Hiçbir gerçek kişi/kurum verisi kullanılmaz; TCKN, IBAN vb. biçimsel olarak geçersiz üretilir.
- İş kuralları (`configs/knowledge.example.toml`) ve RBAC senaryoları (`security_policies/`)
  sorulara dahil edilir.
- Değerlendirme ve eğitim bölümleri veritabanı düzeyinde ayrıdır.
