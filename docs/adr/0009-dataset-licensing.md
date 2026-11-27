# ADR-0009: Veri kümesi lisansları; BIRDTurk yalnız değerlendirme

- **Durum:** Kabul edildi
- **Tarih:** 2026-11-27
- **İlgili AR paketi:** AR-06, AR-08
- **İlgili ilkeler:** 10

## Bağlam
Türkçe Text-to-SQL için kullanılabilecek veri kümeleri farklı lisanslara sahiptir.
BIRDTurk'ün makalesi CC BY-SA 4.0 belirtse de Hugging Face veri kartı
**cc-by-nc-sa-4.0** (ticari olmayan) olarak işaretlidir. Model lisansları da farklıdır
(ör. Qwen2.5-Coder-3B `qwen-research` lisanslıdır).

## Karar
- Daha kısıtlayıcı lisans esas alınır: **BIRDTurk yalnızca değerlendirme (dev/test)
  amacıyla kullanılır**, eğitim/ince ayar verisine karıştırılmaz.
- Her veri kümesi ve model için `datasets/` veya `models/` altında lisans, kaynak, sürüm
  ve izin verilen kullanım (eğitim / değerlendirme / yasak) bir kartla kayıt altına alınır.
- Ham veri ve model ağırlıkları git'e konmaz (`.gitignore`).
- İnce ayar (AR-06) için yalnızca lisansı izin veren veri ve **sentetik kurumsal veri**
  (`synthetic_data/`) kullanılır.
- Değerlendirme ile eğitim kümeleri arasında sızıntı (aynı veritabanı/soru) kontrol edilir.

## Doğrulama
PR şablonundaki kontrol maddesi; AR-08 raporunda veri kümesi kartlarına bağlantı.
