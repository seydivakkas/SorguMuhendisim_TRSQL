# ADR-0005: Güvenlik ihlalleri reddedilir, yeniden denenmez

- **Durum:** Kabul edildi
- **Tarih:** 2026-11-27
- **İlgili AR paketi:** AR-07
- **İlgili ilkeler:** 06

## Bağlam
v0.1'deki "Error Feedback Loop", her doğrulama hatasını modele geri gönderiyordu.
Güvenlik ihlali (DDL/DML, yetkisiz tablo, yasaklı sütun, sistem kataloğu, `pg_sleep`,
çoklu ifade) modele geri bildirildiğinde: (a) model kısıtı aşmanın yolunu "öğrenmeye"
yönlendirilir, (b) ret mesajı gizli şema hakkında bilgi sızdırabilir, (c) kötü niyetli bir
soru, deneme bütçesini savunmayı yoklamak için kullanabilir.

## Karar
Doğrulama sonucu her başarısız kontrol için bir şiddet taşır:

- `REPAIRABLE` → yeniden üretilebilir (ADR-0006 bütçesiyle).
- `SECURITY` → **istek anında `REJECTED` ile sonlanır.** Model yeniden çağrılmaz, modele
  ret gerekçesi verilmez, kullanıcıya genel bir Türkçe mesaj döner, olay audit'e yazılır.

Herhangi bir `SECURITY` hatası, aynı rapordaki `REPAIRABLE` hatalardan önceliklidir.

## Sonuçlar
**Olumlu:** Saldırı yüzeyi daralır; davranış öngörülebilir ve denetlenebilir.
**Olumsuz:** Modelin masum bir hatası (ör. yanlışlıkla `SELECT *` ile yasaklı sütun) da
reddedilir. Bu, Security Violation Rate metriğiyle izlenir ve L5 iyileştirilerek azaltılır;
**kural gevşetilerek değil.**

## Doğrulama
`test_security_violation_is_not_retried` (model tam 1 kez çağrılır),
`tests/security/test_validator.py`.
