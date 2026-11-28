# frontend/ — L0 Client Layer

React + TypeScript (aday, AR-10). Planlanan ekranlar: Türkçe sohbet, SQL editörü, bağlantı
yönetimi, şema görselleştirme, tablo/grafik (Apache ECharts adayı), sorgu geçmişi,
yönetici paneli (rol, politika, iş kuralı onayı).

Kurallar:
- Hiçbir güvenlik kararı istemcide verilmez; her şey sunucuda tekrar denetlenir.
- Yalnızca `PipelineOutcome` / `ResultReport` sözleşmelerini tüketir.
- Sayıları yeniden hesaplamaz; sunucunun verdiği değerleri gösterir.
