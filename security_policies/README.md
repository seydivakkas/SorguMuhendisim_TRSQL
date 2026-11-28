# security_policies/ — Rol ve veri erişim politikaları

Her rol için izin verilen tablolar, yasaklı sütunlar ve satır sınırı. Bu dosyalar
[backend/auth/policies.py](../backend/auth/policies.py) tarafından `AuthContext`
üretiminde yüklenir (`load_role_policies`).

- Varsayılan: **reddet**. Listelenmeyen tablo görünmez; boş `allowed_tables = []`
  hiçbir tabloya izin vermez.
- Kişisel veri sütunları (`tc_kimlik_no`, `telefon`, `eposta`, `iban`) yükleyici
  tarafından varsayılan olarak `denied_columns` listesine eklenir.
- `*.example.toml` şablon dosyaları varsayılan olarak atlanır; etkinleştirmek için
  `<rol>.toml` olarak kopyalayın.
- `TRSQL_TOKENS_FILE` ortam değişkeni ile verilen token dosyası **düz metin token
  içermez**; her satır `sha256(token):user_id:role:tenant` biçiminde özet tutar ve
  `HashedTokenAuthProvider` (`hmac.compare_digest`) tarafından doğrulanır.
- Politika değişiklikleri PR ile yapılır ve incelenir.

Örnek: [analyst.example.toml](analyst.example.toml)
