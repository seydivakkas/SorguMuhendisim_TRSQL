# benchmarks/ — Değerlendirme koşucuları

Metrik tanımları ve koşucular (AR-08). Plan: [docs/evaluation/evaluation-plan.md](../docs/evaluation/evaluation-plan.md).

Koşucular `backend` paketini yalnızca genel API'si üzerinden kullanır
(`build_default_pipeline` + port uygulamaları). Sonuçlar `benchmarks/results/` altına yazılır
(git'e girmez); özet `experiments/` kaydına eklenir.
