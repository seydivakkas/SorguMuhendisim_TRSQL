# models/ — Model kartları

**Model ağırlıkları git'e girmez** (`.gitignore`: `*.gguf`, `*.safetensors`, ...).

Her aday model için `models/<model-adı>.md` kartı oluşturun:

| Alan | Örnek |
|---|---|
| Ad / sürüm | Hati-Glint-SQL-9B |
| Kaynak URL ve commit/revizyon | |
| Lisans ve izin verilen kullanım | |
| Quantization / dosya | Q4_K_M GGUF |
| Dosya SHA-256 | (bütünlük doğrulaması, ADR-0007/T12) |
| Bağlam uzunluğu | |
| Ölçülen tepe VRAM (referans dizüstü) | |
| İstem şablonu (`template_id`) | |
| Bilinen skorlar ve kaynağı | (kendi beyanı mı, bağımsız mı?) |

Adaylar (AR-02): Hati-Glint-SQL-9B, Arctic-Text2SQL-R1-7B, XiYanSQL-QwenCoder-7B, ≈3B kontrol modeli.
Yalnızca pickle içermeyen formatlar (GGUF, safetensors) kabul edilir.
