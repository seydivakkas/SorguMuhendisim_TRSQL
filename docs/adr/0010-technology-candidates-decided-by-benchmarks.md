# ADR-0010: Teknoloji yığını aday; karar AR-09'da ölçümle

- **Durum:** Kabul edildi
- **Tarih:** 2026-11-27
- **İlgili AR paketi:** AR-01–AR-09
- **İlgili ilkeler:** 10

## Bağlam
Önerilen yığın (llama.cpp/ONNX Runtime, GGUF 4-bit, Zemberek, NetworkX, FAISS, BM25, RRF,
LoRA/QLoRA, OpenTelemetry, ECharts) makul adaylardan oluşur ama hiçbiri bu donanım ve
Türkçe kurumsal veri üzerinde henüz ölçülmemiştir.

## Karar
- İskelette yalnızca düşük riskli, değişmesi ucuz temeller kullanılır: Python, Pydantic v2,
  SQLGlot, SQLite, Pytest, FastAPI (opsiyonel).
- Diğer her teknoloji **aday** kabul edilir ve bir port arkasına yerleştirilir; ilgili AR
  paketinde D0–D8 ablasyonuyla ölçülür.
- Kesin seçim **AR-09**'da, ölçüm sonuçlarına dayanan ayrı bir ADR ile yapılır.
- Bir aday, AR-09'dan önce koda girebilir ama yalnızca kendi modülünün içinde ve
  boundaries.toml'daki dış paket kısıtlarıyla.

## Doğrulama
`docs/evaluation/evaluation-plan.md` ve AR-09 karar ADR'leri.
