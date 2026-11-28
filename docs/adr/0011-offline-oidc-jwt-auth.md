# ADR-0011: Çevrimdışı OIDC / JWT Doğrulaması için `PyJWT[crypto]`

- **Durum:** Kabul edildi
- **Tarih:** 2026-11-28
- **İlgili AR paketi:** AR-07 / T-19
- **İlgili ilkeler:** 02, 04

## Bağlam
Kurum içi OIDC sağlayıcılarından (Keycloak vb.) gelen JWT erişim belirteçlerinin
L1 kimlik doğrulama katmanında imzalı olarak doğrulanması gerekiyor. ADR-0002
gereği çalışma zamanında dış ağa (ör. uzak JWKS URL'ine) istek atılamaz ve
kriptografik imza doğrulamasının standart kütüphaneyle elle yazılması kritik
güvenlik riski (ör. `alg=none`, anahtar karıştırma) doğurur.

## Karar
`PyJWT[crypto]` (`jwt` + `cryptography`) yalnızca `backend/auth` modülü için
`backend/boundaries.toml` `[external]` listesine eklendi. `OIDCAuthProvider`,
yalnızca yerel dosya sistemindeki bir JWKS (`jwks.json`) dosyasını başlangıçta
yükler; asimetrik imzaları (`RS256`/`ES256`/`EdDSA`), `iss`, `aud`, `exp` ve
`nbf` alanlarını doğrular; çıkan rol taleplerini `security_policies/*.toml`
kurallarına bağlar.

## Sonuçlar
**Olumlu:** Kanıtlanmış JWS imza doğrulaması, sıfır çalışma zamanı ağ çağrısı,
`StaticAuthProvider` / `HashedTokenAuthProvider` ile aynı `authenticate(token)`
arayüzü.
**Olumsuz / bedeli:** `auth` dış bağımlılık listesine `pyjwt[crypto]` eklenir;
anahtar rotasyonunda yerel `jwks.json` dosyası güncellenmelidir.

## Değerlendirilen alternatifler
| Alternatif | Neden seçilmedi |
|---|---|
| Standart kütüphaneyle elle RSA/ECDSA JWT doğrulama | Kriptografik doğrulama hatası ve yan kanal riski |
| `python-jose` | Bakımı zayıf ve bilinen eski güvenlik açıkları |
| Çalışma zamanında OIDC JWKS URL çekimi | ADR-0002 çevrimdışı kuralı ihlali |

## Doğrulama
`python tools/check_boundaries.py`, `pytest -m security -q` (`test_oidc_jwt_security.py`)
ve `pytest -q tests/unit/test_auth_oidc.py`.
