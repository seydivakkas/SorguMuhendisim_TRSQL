# Model Kartı: BGE-M3 GGUF (Gömme Modeli)

| Alan | Değer |
|---|---|
| **Ad / sürüm** | BGE-M3 (~568M parametre, çok dilli gömme modeli) |
| **Resmî kaynak depo** | `https://huggingface.co/BAAI/bge-m3` (safetensors, revizyon `5617a9f61b028005a4858fdac845db406aefb181`) |
| **GGUF depo ve revizyon** | `https://huggingface.co/ggml-org/bge-m3-Q8_0-GGUF` · commit `9eba04c5d75ba5a1595e45de734d36bef4e5cb98` (resmî `ggml-org` GGUF) |
| **Lisans ve izin verilen kullanım** | `MIT` — ticari kullanım ve dağıtım serbest |
| **Quantization / dosya** | `Q8_0` GGUF (`bge-m3-q8_0.gguf`, 634,5 MB) |
| **Dosya SHA-256** | `aa473d51f451a22f0fcf39ba3330c14bed38a385712b1113440f69df4047a173` (T-09 yerel doğrulama ile sabitlendi) |
| **Bağlam uzunluğu** | 8192 token |
| **Ölçülen tepe VRAM (referans dizüstü)** | `0 MB` GPU VRAM — **CPU'da çalışır** (`n_gpu_layers = 0`, 32 GB sistem RAM; `n_ctx = 8192`, `1024` boyutlu vektör, 2 Türkçe sorgu `1.93 sn`) |
| **Port / Arayüz** | `backend.core.ports.EmbeddingAdapter` (`embed(texts: list[str]) -> list[list[float]]`) |
| **Bilinen skorlar ve kaynağı** | Çok dilli (Türkçe dahil) yoğun geri getirme; TRSQL F4 (D3) deneyinde Retrieval Recall@5 ≥ 0.90 hedefiyle ölçülür |

## Donanım ve Mimari Notları

- `trsql-birlesik-arastirma-raporu.md` §4(b) ve §6(b) gereği BGE-M3 FP16'da yaklaşık `1.1 GB` VRAM tükettiği için 7–9B SQL modeliyle aynı 8 GB GPU'ya yüklenmez; CPU üzerinde çalıştırılarak GPU KV-cache bütçesi (`6800 MB`) SQL modeline bırakılır.
- `backend/rag` ve `backend/schema_linking` modülleri `llama_cpp` veya `torch` içe aktarmaz (`boundaries.toml`); yalnızca `EmbeddingAdapter` portu üzerinden erişir.
