# Güvenlik

Ayrıntılı güvenlik modeli: [docs/security/security-policy.md](docs/security/security-policy.md).

## Desteklenen sürümler

Proje araştırma aşamasındadır (v0.2 Research Candidate). Yalnızca `main` dalı desteklenir.

## Güvenlik açığı bildirme

Güvenlik açıklarını **herkese açık issue olarak açmayın.** GitHub'ın
"Report a vulnerability" (Security → Advisories) özelliğini kullanarak özel bildirim yapın.
Bildirime şunları ekleyin: etkilenen katman/modül, yeniden üretme adımları, beklenen ve
gözlenen davranış. Gerçek kişisel veri paylaşmayın.

## Temel kurallar

- LLM çıktısı güvenilmeyen girdidir.
- Model veritabanına doğrudan erişemez.
- Yetkilendirme şema erişiminden önce yapılır.
- Güvenlik ihlalleri reddedilir, yeniden denenmez.
- Gizli bilgiler yalnızca ortam değişkenlerindedir.
