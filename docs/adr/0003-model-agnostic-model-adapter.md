# ADR-0003: Modelden bağımsızlık — `ModelAdapter`

- **Durum:** Kabul edildi
- **Tarih:** 2026-11-27
- **İlgili AR paketi:** AR-02, AR-05
- **İlgili ilkeler:** 03, 07, 10

## Bağlam
Aday modeller (Hati-Glint-SQL-9B, Arctic-Text2SQL-R1-7B, XiYanSQL-QwenCoder-7B ve
Qwen/Gemma/Llama türevleri) farklı istem biçimleri, bağlam uzunlukları, lisanslar ve
çalışma zamanları (llama.cpp, ONNX Runtime) gerektirir. Tez, modeller arası adil
karşılaştırma yapmayı ve en iyisini AR-09'da seçmeyi hedefler.

## Karar
Her model `backend.core.ports.ModelAdapter` protokolünün arkasında çalışır:

```python
class ModelAdapter(Protocol):
    @property
    def info(self) -> ModelInfo: ...
    def generate(self, prompt: PromptBundle, params: GenerationParams) -> str: ...
```

- Adaptörler yalnızca `backend/model_engine/` içinde yazılır; ağır çıkarım kütüphaneleri
  yalnızca burada içe aktarılabilir.
- Adaptör **yalnızca metin döndürür**; SQL çıkarımı `sql_generator`, doğrulama L6'nın işidir.
- Modele özgü istem farklılıkları `prompt_engine` şablon sürümleriyle (`template_id`) yönetilir.
- Adaptör seçimi `configs/*.toml` → `model.adapter` ile yapılır.

## Sonuçlar
**Olumlu:** Model değişimi = yeni bir adaptör sınıfı + konfig. Testler `FakeModelAdapter`
ile GPU'suz ve deterministik çalışır.
**Olumsuz:** Modele özgü yetenekler (ör. yapılandırılmış çıktı, araç çağırma) ortak
arayüzde yoksa kullanılamaz; gerektiğinde `GenerationParams` genişletilir (ADR güncellemesi).

## Doğrulama
`tests/integration/test_pipeline.py` tüm akışı `FakeModelAdapter` ile çalıştırır;
sınır denetimi `model_engine` dışından model kütüphanesi içe aktarılmasını engeller.
