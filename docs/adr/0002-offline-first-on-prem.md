# ADR-0002: Offline-first ve on-prem çalışma (KVKK)

- **Durum:** Kabul edildi
- **Tarih:** 2026-11-27
- **İlgili AR paketi:** AR-05, AR-07
- **İlgili ilkeler:** 02, 03, 06

## Bağlam
Kurumsal veritabanları kişisel veri içerir. 6698 sayılı KVKK kapsamında kişisel verinin
yurt dışına aktarımı ve üçüncü taraf işleyicilere gönderilmesi sıkı koşullara bağlıdır.
Soru metni, şema adları ve sonuç satırları da kişisel/gizli veri içerebilir. Bulut LLM
API'leri bu nedenle üretim yolunda kullanılamaz.

## Karar
TRSQL **tamamen yerel (on-prem) çalışır ve çalışma zamanında dış ağa çıkmaz.**

- LLM, gömme modeli (ör. BGE-M3) ve tüm yardımcı modeller yerel dosyadan yüklenir;
  çalışma zamanında indirme yapılmaz.
- `Settings.offline = true` varsayılandır.
- `backend/` içinde HTTP istemci kütüphaneleri (`requests`, `httpx`, `urllib3`)
  içe aktarılamaz (`boundaries.toml`).
- Telemetri/observability verisi kurum içindeki hedeflere yazılır.
- Model ve veri indirmeleri yalnızca kurulum aşamasında, ayrı betiklerle
  (`models/`, `datasets/`) yapılır.

## Sonuçlar
**Olumlu:** Veri kurum dışına çıkmaz; ağ kesintisinden etkilenmez; maliyet öngörülebilir.
**Olumsuz:** Büyük bulut modellerinin doğruluğundan vazgeçilir; bu fark L2–L4 katmanları
ve küçük model seçimiyle kapatılmaya çalışılır (ilke 03). Model güncellemeleri elle yapılır.

## Doğrulama
Sınır denetimi (G3). AR-07'de ağ erişimi kapalı bir ortamda uçtan uca test eklenecek.
