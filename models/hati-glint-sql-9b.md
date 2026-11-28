# Model Kartı: Hati-Glint-SQL-9B-v1

| Alan | Değer |
|---|---|
| **Ad / sürüm** | Hati-Glint-SQL-9B-v1 (taban: `Qwen/Qwen3.5-9B` LoRA SFT) |
| **Kaynak URL ve commit/revizyon** | `https://huggingface.co/runelab-ai/Hati-Glint-SQL-9B-v1` (revizyon indirme sırasında sabitlenir) |
| **Lisans ve izin verilen kullanım** | `Apache-2.0 + NOTICE` — ticari kullanım serbest, `NOTICE` dosyasındaki atıflar korunur |
| **Quantization / dosya** | `Q4_K_M` GGUF (`Hati-Glint-SQL-9B-v1.Q4_K_M.gguf`) |
| **Dosya SHA-256** | Doğrulanacak (`python models/download.py verify` ile sabitlenir) |
| **Bağlam uzunluğu** | Taban 262K; 8 GB referans dizüstünde 4096–8192 (`kv_cache_type = "q8_0"`) |
| **Ölçülen tepe VRAM (referans dizüstü)** | Henüz F2 (D0/D1) deneyinde ölçülmedi (bütçe sınırı: `6800 MB`) |
| **İstem şablonu (`template_id`)** | `ddl_v1` (D0), `mschema_v1` (D1); `<think>` ve `direct` modlarını destekler |
| **Bilinen skorlar ve kaynağı** | **Yalnızca kendi kartı (bağımsız doğrulanmamış):** TURSpider dev EX `73.21` (direct) / `76.79` (thinking) / `77.85` (ajan); BIRDTurk dev EX `47.26` / `54.37` / `55.35` |

## Mimari ve Güvenlik Notları

- Tabanı `Qwen3.5-9B`, her 4 katmanın 3'ünde Gated DeltaNet (doğrusal dikkat) ve 1'inde tam dikkat kullanır; KV cache yalnızca tam dikkat katmanlarında büyür. `llama.cpp` uyumu F2'de doğrulanır.
- Model kartında salt okunur / SQLite kullanımı vurgulanır; TRSQL L6 (`SQLValidator` + `PolicyEngine`) ve L7 salt okunur DB rolleriyle güvence altına alınır.
- Hati kartındaki TurkishMMLU regresyonu (`66.22 → 65.11`, `-1.1`) ve kendi beyanı skorlar F2'de bağımsız olarak yeniden ölçülecektir.
