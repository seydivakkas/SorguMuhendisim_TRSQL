# Katkı ve Çalışma Akışı Rehberi

Kurallar: [AGENTS.md](AGENTS.md) (insanlar ve agent'lar için aynıdır).

## Dal stratejisi

- `main` her zaman yeşildir; doğrudan push yapılmaz.
- Dal adları: `feat/<modül>-<kısa-açıklama>`, `fix/...`, `docs/...`, `exp/<D-basamağı>-<ad>`,
  `adr/<no>-<ad>`.
- Her dal tek bir amaca hizmet eder; PR'lar küçük tutulur (ideal < 400 satır kod).

## Commit mesajları

İngilizce, [Conventional Commits](https://www.conventionalcommits.org/) biçiminde:

```
feat(sql_validator): reject window functions over denied columns
fix(turkish_nlp): handle "geçen hafta"
docs(adr): add ADR-0011 hybrid schema linking
exp(D3): BM25+FAISS RRF on TURSpider dev
```

## PR süreci

1. Issue (tercihen AR iş paketi şablonu) → dal.
2. Test önce; sonra kod.
3. Yerelde G1–G5 kapıları (`docs/guides/getting-started.md`).
4. PR şablonunu doldur; etkilenen katmanları ve sözleşme değişikliklerini belirt.
5. CI yeşil + inceleme → **squash merge**.

## Ne zaman ADR yazılır?

- Yeni modül, modül sınırı veya `boundaries.toml` değişikliği
- Bir değişmez kuralı (AGENTS.md §1) etkileyen her şey
- Teknoloji seçimi (aday → kalıcı), özellikle AR-09 kararları
- Veri sözleşmesinde kırıcı değişiklik

## Deneyler

- Deney kodu `experiments/` veya `benchmarks/` altında; üretim koduna (`backend/`) deney
  amaçlı dal (`if experiment:`) eklenmez — farklı davranış portla takılır.
- Her deney `docs/evaluation/evaluation-plan.md` §6 protokolüne uyar.
- Sonuç özeti PR açıklamasına eklenir; ham çıktılar git'e girmez.

## Sürümleme

- `0.x`: araştırma (v0.2 = Research Candidate).
- `1.0`: AR-09 nihai mimarisi.
- Sürüm notları `CHANGELOG.md` içinde.
