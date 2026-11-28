# Model Kartı: BGE-M3 GGUF (Gömme Modeli)

| Alan | Değer |
|---|---|
| **Ad / sürüm** | BGE-M3 (~568M parametre, çok dilli gömme modeli) |
| **Kaynak URL ve commit/revizyon** | `https://huggingface.co/BAAI/bge-m3` (GGUF yerel kopyası) |
| **Lisans ve izin verilen kullanım** | `MIT` — ticari kullanım ve dağıtım serbest |
| **Quantization / dosya** | `F16` / `Q8_0` GGUF (`bge-m3-f16.gguf`) |
| **Dosya SHA-256** | Doğrulanacak (`python models/download.py verify` ile sabitlenir) |
| **Bağlam uzunluğu** | 8192 token |
| **Ölçülen tepe VRAM (referans dizüstü)** | `0 MB` — **CPU'da çalışır** (`n_gpu_layers = 0`, 32 GB sistem RAM kullanır) |
| **Port / Arayüz** | `backend.core.ports.EmbeddingAdapter` (`embed(texts: list[str]) -> list[list[float]]`) |
| **Bilinen skorlar ve kaynağı** | Çok dilli (Türkçe dahil) yoğun geri getirme; TRSQL F4 (D3) deneyinde Retrieval Recall@5 ≥ 0.90 hedefiyle ölçülür |

## Donanım ve Mimari Notları

- `trsql-birlesik-arastirma-raporu.md` §4(b) ve §6(b) gereği BGE-M3 FP16'da yaklaşık `1.1 GB` VRAM tükettiği için 7–9B SQL modeliyle aynı 8 GB GPU'ya yüklenmez; CPU üzerinde çalıştırılarak GPU KV-cache bütçesi (`6800 MB`) SQL modeline bırakılır.
- `backend/rag` ve `backend/schema_linking` modülleri `llama_cpp` veya `torch` içe aktarmaz (`boundaries.toml`); yalnızca `EmbeddingAdapter` portu üzerinden erişir.
