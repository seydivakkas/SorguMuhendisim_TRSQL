# ADR-0006: Sınırlı yeniden deneme bütçesi

- **Durum:** Kabul edildi
- **Tarih:** 2026-11-27
- **İlgili AR paketi:** AR-05, AR-08
- **İlgili ilkeler:** 03, 06, 10

## Bağlam
Küçük modellerde düzeltme döngüsü doğruluğu artırır ama her deneme yerel GPU'da saniyeler
sürer. Sınırsız döngü; gecikmeyi, enerji tüketimini ve hizmet reddi riskini artırır.

## Karar
- Toplam üretim denemesi (ilk deneme dahil) `retry.max_attempts` ile sınırlıdır.
  Varsayılan **3**, izin verilen aralık **1–5** (`RetrySettings`).
- Yalnızca `REPAIRABLE` hatalar yeni denemeyi tetikler; geri bildirim yalnızca bu hataların
  mesajlarını içerir.
- Bütçe bittiğinde sistem **güvenli biçimde durur**: `RETRY_BUDGET_EXHAUSTED` ve kullanıcıya
  soruyu yeniden ifade etme önerisi. Son başarısız SQL yürütülmez.
- Belirsiz sorular bütçe harcamaz; doğrudan `NEEDS_CLARIFICATION` döner.
- Yürütme hataları (zaman aşımı vb.) yeniden denenmez.

## Sonuçlar
**Olumlu:** Üst sınırlı gecikme: `max_attempts × (üretim + doğrulama)`.
**Olumsuz:** Bazı sorular 4. denemede çözülebilecekken başarısız olur. Optimum değer
AR-08'de Retry Rate ve Execution Accuracy eğrisiyle belirlenir (D6).

## Doğrulama
`test_retry_budget_is_bounded`, `test_repairable_error_retries_with_feedback`.
