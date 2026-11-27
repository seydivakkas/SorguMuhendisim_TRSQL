# ADR-0008: Sonuç sayıları deterministik; model sayı üretmez

- **Durum:** Kabul edildi
- **Tarih:** 2026-11-27
- **İlgili AR paketi:** AR-10
- **İlgili ilkeler:** 09

## Bağlam
LLM'ler özetleme sırasında sayıları yuvarlayabilir, karıştırabilir veya uydurabilir.
Kurumsal raporda yanlış bir tutar, yanlış SQL kadar zararlıdır.

## Karar
- L8 raporundaki her sayı **doğrudan `ExecutionResult` satırlarından** ya da deterministik
  bir hesaplama fonksiyonundan gelir.
- Türkçe açıklama şablon tabanlıdır; ileride bir dil modeli metni akıcılaştırmak için
  kullanılırsa, çıktısındaki her sayı sonuç kümesiyle karşılaştırılır, eşleşmeyen çıktı atılır.
- Rapor; SQL'i, kullanılan metrik tanımını ve sürümünü (`net_sales@v1`) ve satır sınırı
  nedeniyle kısaltma olup olmadığını gösterir.
- Sayı biçimi Türkçedir: `1.250.000,50`.

## Doğrulama
`tests/unit/test_result_and_masking.py`, `test_happy_path`.
