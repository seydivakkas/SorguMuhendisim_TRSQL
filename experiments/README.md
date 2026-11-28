# experiments/ — Deney Kayıtları (D0–D8)

Her deney bir klasör altında saklanır: `experiments/YYYY-AA-GG-<basamak>-<kısa-ad>/`

```text
config.toml      # basamak, model, quantization, template_id, retriever, seed, max_attempts
README.md        # hipotez, sonuç, yorum, sonraki adım
metrics.json     # özet metrikler ve kırılımlar (küçük, commit'lenir)
```

Ham tahmin dosyaları (`predictions.jsonl` ve `runs/`) git'e girmez (`.gitignore`).
Tam protokol: [docs/evaluation/evaluation-plan.md](../docs/evaluation/evaluation-plan.md) §6.

## Şablon ve Koşu Komutları

Başlangıç şablonu: [d0-baseline-template/config.toml](d0-baseline-template/config.toml).

Tek deney koşusu:

```bash
python -m benchmarks.runner --config experiments/2026-12-01-d0-qwen3/config.toml
```

> Kirli Git çalışma ağacında deney koşulmaz (`DirtyWorkingTreeError`); geçici yerel
> denemeler için `--allow-dirty` veya `allow_dirty = true` kullanılır.

Birden fazla deneyi karşılaştıran Markdown raporu (McNemar + %95 eşli bootstrap Gİ):

```bash
python -m benchmarks.report experiments/exp-d0 experiments/exp-d1 --output report.md
```

## D0–D8 Ablasyon Basamakları ve Kapılar

- **D0–D8** kümülatiftir ([benchmarks/stages.py](../benchmarks/stages.py) `StageProfile`); çözülmüş profil ve gömme arka ucu (`embedder`) her deneyin `metrics.json` dosyasına yazılır. Ardışık basamaklar arası Δ EX ve istatistiksel anlamlılık raporlanır.
- **E1:** Yeni bileşen, önceki basamağa göre EX'i düşürmez (veya güvenlik/açıklanabilirlik kazancıyla gerekçelendirilir).
- **E2:** Saldırı setinde yakalama oranı = %100 (`db_reached_unsafe_rate = 0`).
- **E3:** Tepe VRAM ≤ 6.800 MB (`vram_budget_mb`), p95 gecikme hedefte.
