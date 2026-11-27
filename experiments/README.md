# experiments/ — Deney kayıtları (D0–D8)

Her deney bir klasör: `experiments/YYYY-AA-GG-<basamak>-<kısa-ad>/`

```
config.toml      # basamak, model, quantization, template_id, retriever, seed, max_attempts
README.md        # hipotez, sonuç, yorum, sonraki adım
metrics.json     # özet metrikler (küçük, commit'lenir)
```

Ham tahminler (`runs/`) git'e girmez. Protokol: evaluation-plan §6.
