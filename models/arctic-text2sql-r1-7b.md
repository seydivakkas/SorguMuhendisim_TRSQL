# Model Kartı: Arctic-Text2SQL-R1-7B

| Alan | Değer |
|---|---|
| **Ad / sürüm** | Arctic-Text2SQL-R1-7B (taban: `Qwen/Qwen2.5-Coder-7B-Instruct`, GRPO RL) |
| **Resmî kaynak depo** | `https://huggingface.co/Snowflake/Arctic-Text2SQL-R1-7B` (safetensors, revizyon `2d73facaf7e15831d0b918d219e0d565f113f592`) · Makale: `https://arxiv.org/abs/2505.20315` |
| **GGUF depo ve revizyon** | `https://huggingface.co/mradermacher/Arctic-Text2SQL-R1-7B-GGUF` · commit `8e1a51188952afa8021bce6c8b3e5b495b3e85cd` (topluluk GGUF, yükleyen: `mradermacher`) |
| **Lisans ve izin verilen kullanım** | `Apache-2.0` — ticari üretim, ince ayar ve dağıtım serbest |
| **Quantization / dosya** | `Q5_K_M` GGUF (`Arctic-Text2SQL-R1-7B.Q5_K_M.gguf`, 5,44 GB) |
| **Dosya SHA-256** | Yerel doğrulama T-09'da sabitlenir (HF LFS özeti: `157cc3e1caafb02a7e4c7abc6e23fbe1bb1b75ef1623fc54885bd17b1a8c0c5d`) |
| **Bağlam uzunluğu** | 8 GB referans dizüstünde 4096–8192 (`kv_cache_type = "q8_0"`) |
| **Ölçülen tepe VRAM (referans dizüstü)** | Henüz F2 deneyinde ölçülmedi (bütçe sınırı: `6800 MB`) |
| **İstem şablonu (`template_id`)** | `ddl_v1` / `mschema_v1`; `<think>` akıl yürütme bloğu üretebilir (`ReasoningMode.THINKING`) |
| **Bilinen skorlar ve kaynağı** | **Kendi kartı ve makalesi (İngilizce, Türkçede ölçülmemiş):** BIRD dev EX `68.9` (test `68.5`), Spider test EX `88.8`, Spider 2.0-DK `15.6` |

## Teknik Notlar

- Çalıştırma doğruluğu ödüllü GRPO (Group Relative Policy Optimization) ile eğitilmiştir.
- Çıktıda `<think>...</think>` bloğu üretildiğinde yalnızca son SQL bloğu `SQLCandidate.sql` içine alınır; düşünme metni isteğe bağlı olarak `SQLCandidate.reasoning` alanında tutulabilir.
- Türkçede bağımsız ölçümü bulunmadığı için F2'de TURSpider dev, BIRDTurk dev ve kurumsal sentetik sette ölçülecektir.
