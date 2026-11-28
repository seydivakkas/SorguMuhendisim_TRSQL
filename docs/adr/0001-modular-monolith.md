# ADR-0001: Modular Monolith

- **Durum:** Kabul edildi
- **Tarih:** 2026-11-27
- **İlgili AR paketi:** AR-01, AR-09
- **İlgili ilkeler:** 03, 06, 07, 08

## Bağlam
v0.1 diyagramları servis tabanlı bir mimariye işaret ediyordu. TRSQL tek geliştiricili bir
tez projesi olarak başlıyor, 8 GB VRAM / 32 GB RAM'li tek bir dizüstü bilgisayarda çalışmak
zorunda ve on-prem dağıtılacak. Aynı zamanda katmanların (L0–L9) bağımsız geliştirilebilmesi,
deneylerde tek tek değiştirilebilmesi (ablasyon) ve ileride ayrılabilmesi gerekiyor.

## Karar
Backend, **tek süreçte çalışan, katı modül sınırlarına sahip bir Modular Monolith** olarak
geliştirilir.

- Her modül `backend/<modül>/` altında bir Python paketidir ve genel API'sini
  `__init__.py` ile açar.
- Modüller arası veri yalnızca `backend/core/contracts.py` sözleşmeleriyle taşınır.
- Modüller arası çağrılar `backend/core/ports.py` arayüzleri üzerinden yapılır;
  birleştirme (wiring) yalnızca `orchestration` içinde yapılır.
- İzin verilen bağımlılıklar `backend/boundaries.toml` içinde tanımlıdır ve CI'da
  `tools/check_boundaries.py` ile zorunlu tutulur.

| Özellik | Modular Monolith | Microservices |
|---|---|---|
| Geliştirme kolaylığı | Yüksek | Daha düşük |
| Donanım tüketimi | Genellikle daha düşük | Genellikle daha yüksek |
| Debug | Kolay | Karmaşık |
| Dağıtım | Tek uygulama | Birden fazla servis |
| Bağımsız ölçeklendirme | Sınırlı | Yüksek |
| TRSQL başlangıç aşaması | Uygun | Gereksiz karmaşıklık |

## Sonuçlar
**Olumlu:** Tek süreç → düşük bellek, ağ gecikmesi yok, uçtan uca debug kolay; tek
`pip install`; ablasyon için aşamalar port üzerinden takılıp çıkarılabilir.
**Olumsuz:** Modüller bağımsız ölçeklenemez; model çıkarımı (GPU) ile API aynı süreçte
olduğundan uzun çıkarım istekleri eşzamanlılığı sınırlar. Sınır disiplini araçla
korunmazsa "büyük çamur topu"na dönüşme riski vardır (bu yüzden CI gate).

## Değerlendirilen alternatifler
| Alternatif | Neden seçilmedi |
|---|---|
| Microservices | Tek makinede gereksiz kaynak tüketimi ve işletim yükü; tez kapsamında fayda sağlamaz. |
| Sınırsız monolit | Ablasyon, test ve ileride ayırma imkânsızlaşır. |

## Ayrılma kriteri
Bir modül ancak şu durumda servise ayrılır: ölçülmüş bir ihtiyaç (ör. model sunucusunun
ayrı GPU makinesine taşınması) + yeni bir ADR. Ayrılırken modülün genel API'si ve
sözleşmeleri değişmez; yalnızca port uygulaması (yerel çağrı → HTTP/gRPC) değişir.

## Doğrulama
`tests/architecture/test_boundaries.py`, CI gate **G3**.
