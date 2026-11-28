# Model Kartı: XiYanSQL-QwenCoder-7B-2504

| Alan | Değer |
|---|---|
| **Ad / sürüm** | XiYanSQL-QwenCoder-7B-2504 (taban: `Qwen/Qwen2.5-Coder-7B`) |
| **Kaynak URL ve commit/revizyon** | `https://huggingface.co/XGenerationLab/XiYanSQL-QwenCoder-7B-2504` (revizyon indirme sırasında sabitlenir) |
| **Lisans ve izin verilen kullanım** | `Apache-2.0` — ticari üretim, ince ayar ve dağıtım serbest (`LICENSE` + `NOTICE` korunur) |
| **Quantization / dosya** | `Q5_K_M` GGUF (`XiYanSQL-QwenCoder-7B-2504.Q5_K_M.gguf`) |
| **Dosya SHA-256** | Doğrulanacak (`python models/download.py verify` ile sabitlenir) |
| **Bağlam uzunluğu** | Taban 128K; 8 GB referans dizüstünde 4096–8192 (`kv_cache_type = "q8_0"`) |
| **Ölçülen tepe VRAM (referans dizüstü)** | Henüz F2 (D0/D1) deneyinde ölçülmedi (bütçe sınırı: `6800 MB`) |
| **İstem şablonu (`template_id`)** | `mschema_v1` (D1, eğitim formatı) ve `ddl_v1` (D0) |
| **Bilinen skorlar ve kaynağı** | **Yalnızca kendi kartı (İngilizce, Türkçede ölçülmemiş):** BIRD dev EX `62.13` (M-Schema) / `57.43` (DDL); Spider test EX `85.97` (M-Schema) / `82.48` (DDL) |

## Lisans ve Kullanım Uyarısı (`qwen-research`)

> **Uyarı:** Aynı ailenin **3B** sürümü (`XiYanSQL-QwenCoder-3B-2504`), **`qwen-research`** lisanslı `Qwen2.5-Coder-3B` tabanından türetildiği için türev eser kısıtı taşır ve hukuki onay olmadan ticari üründe kullanılamaz. **`XiYanSQL-QwenCoder-7B-2504`** ise Apache-2.0 lisanslı `Qwen2.5-Coder-7B` tabanlıdır ve ticari kullanım açısından güvenlidir.

## Eğitim ve Lehçe Notu

- Çok üreteçli SFT ile M-Schema biçimi üzerinde eğitilmiştir; SQLite, PostgreSQL ve MySQL lehçelerini kapsar.
- Şema formatına 3–5 puan duyarlı olduğu için D0 (`ddl_v1`) ve D1 (`mschema_v1`) kademelerinde ayrı ölçülür.
