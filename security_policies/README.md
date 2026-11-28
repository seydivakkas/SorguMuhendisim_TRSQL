# security_policies/ — Rol ve veri erişim politikaları

Her rol için izin verilen tablolar, yasaklı sütunlar ve satır sınırı. Bu dosyalar
`AuthContext` üretiminde kullanılır (AR-07'de yükleyici eklenecek).

- Varsayılan: **reddet**. Listelenmeyen tablo görünmez.
- Kişisel veri sütunları (`tc_kimlik_no`, `telefon`, `eposta`, `iban`, ...) varsayılan
  olarak `denied_columns` içindedir.
- Politika değişiklikleri PR ile yapılır ve incelenir.

Örnek: [analyst.example.toml](analyst.example.toml)
