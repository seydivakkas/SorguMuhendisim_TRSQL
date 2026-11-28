# CLAUDE.md

Bu repodaki tüm kurallar **[AGENTS.md](AGENTS.md)** dosyasındadır; önce onu oku ve uygula.

Kısa özet (ayrıntı ve gerekçe AGENTS.md'de):

- Modular monolith: modüller arası içe aktarma yalnızca genel API üzerinden ve
  `backend/boundaries.toml` izinleriyle. Kontrol: `python tools/check_boundaries.py`.
- Model veritabanına asla dokunmaz; DB'ye giden tek yol `ApprovedQuery` → `execution_engine`.
- RBAC şemadan önce (`auth.scope_schema`); güvenlik ihlali yeniden denenmez; yeniden deneme
  bütçesi sınırlı.
- Offline-first: `backend/` içinde ağ çağrısı yok.
- Kod/tanımlayıcı/commit İngilizce; kullanıcı mesajları ve dokümanlar Türkçe.
- `tests/security/` testleri atlanamaz ve gevşetilemez.
- Her PR öncesi: `ruff check . && ruff format --check . && mypy && python tools/check_boundaries.py && pytest`.
