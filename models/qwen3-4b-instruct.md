# Model Kartı: Qwen3-4B-Instruct-2507

| Alan | Değer |
|---|---|
| **Ad / sürüm** | Qwen3-4B-Instruct-2507 (4.0B parametre) |
| **Kaynak URL ve commit/revizyon** | `https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507` |
| **Lisans ve izin verilen kullanım** | `Apache-2.0` — ticari kullanım, ince ayar ve dağıtım serbest |
| **Quantization / dosya** | `Q5_K_M` GGUF (`Qwen3-4B-Instruct-2507.Q5_K_M.gguf`; alternatif `Q6_K`) |
| **Dosya SHA-256** | Doğrulanacak (`python models/download.py verify` ile sabitlenir) |
| **Bağlam uzunluğu** | Taban 262K; 8 GB referans dizüstünde 4096–16384 |
| **Ölçülen tepe VRAM (referans dizüstü)** | Henüz F2 deneyinde ölçülmedi (8 GB altında geniş bağlamla çalışması beklenir) |
| **İstem şablonu (`template_id`)** | `ddl_v1` (D0), `mschema_v1` (D1) |
| **Bilinen skorlar ve kaynağı** | Resmi kartta Spider/BIRD skoru bulunmuyor; ilk uçtan uca kontrol modeli |

## Rol ve Lisans Gerekçesi

- `trsql-birlesik-arastirma-raporu.md` §3(a) ve §6(a) uyarınca:
  - 3B sınıfındaki `Qwen2.5-Coder-3B-Instruct`, **`qwen-research`** lisansı nedeniyle ticari kullanım kısıtına sahiptir; **`Qwen3-4B-Instruct-2507`** (`Apache-2.0`) ticari olarak güvenli küçük kontrol modelidir.
  - 3–4B sınıfında `Q4_K_M` biçim hatalarını artırdığı için `Q5_K_M` (veya `Q6_K`) nicemleme seçilir; `Valid SQL Rate` ayrıca raporlanır.
