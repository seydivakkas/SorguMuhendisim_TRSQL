# Model Kartı: Qwen3-4B-Instruct-2507

| Alan | Değer |
|---|---|
| **Ad / sürüm** | Qwen3-4B-Instruct-2507 (4.0B parametre) |
| **Resmî kaynak depo** | `https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507` (safetensors, revizyon `cdbee75f17c01a7cc42f958dc650907174af0554`) |
| **GGUF depo ve revizyon** | `https://huggingface.co/unsloth/Qwen3-4B-Instruct-2507-GGUF` · commit `a06e946bb6b655725eafa393f4a9745d460374c9` (GGUF, yükleyen: `unsloth`) |
| **Lisans ve izin verilen kullanım** | `Apache-2.0` — ticari kullanım, ince ayar ve dağıtım serbest |
| **Quantization / dosya** | `Q5_K_M` GGUF (`Qwen3-4B-Instruct-2507-Q5_K_M.gguf`, 2,89 GB; alternatif `unsloth` / `ggml-org` Q8_0) |
| **Dosya SHA-256** | Yerel doğrulama T-09'da sabitlenir (HF LFS özeti: `5bde5e9d883622acb02bf77fe7dcbc56a8b9a9ad4be78a72ca23a532658b4ecb`) |
| **Bağlam uzunluğu** | Taban 262K; 8 GB referans dizüstünde 4096–16384 |
| **Ölçülen tepe VRAM (referans dizüstü)** | Henüz F2 deneyinde ölçülmedi (8 GB altında geniş bağlamla çalışması beklenir) |
| **İstem şablonu (`template_id`)** | `ddl_v1` (D0), `mschema_v1` (D1) |
| **Bilinen skorlar ve kaynağı** | Resmi kartta Spider/BIRD skoru bulunmuyor; ilk uçtan uca kontrol modeli |

## Rol ve Lisans Gerekçesi

- `trsql-birlesik-arastirma-raporu.md` §3(a) ve §6(a) uyarınca:
  - 3B sınıfındaki `Qwen2.5-Coder-3B-Instruct`, **`qwen-research`** lisansı nedeniyle ticari kullanım kısıtına sahiptir; **`Qwen3-4B-Instruct-2507`** (`Apache-2.0`) ticari olarak güvenli küçük kontrol modelidir.
  - 3–4B sınıfında `Q4_K_M` biçim hatalarını artırdığı için `Q5_K_M` (veya `Q6_K`) nicemleme seçilir; `Valid SQL Rate` ayrıca raporlanır.
