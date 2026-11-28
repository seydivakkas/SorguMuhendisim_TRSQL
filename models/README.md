# models/ — Model Kartları ve İndirme Manifesti

**Model ağırlıkları git'e girmez** (`.gitignore`: `*.gguf`, `*.safetensors`, `*.bin`, `models/**/weights/`).
Çalışma zamanında dış ağ çağrısı yapılmaz (ADR-0002); modeller kurulum sırasında `models/download.py` ile indirilir ve SHA-256 ile doğrulanır.

## Güvenlik ve Format Politikası

- **Kabul edilen formatlar:** Yalnızca pickle içermeyen `.gguf` ve `.safetensors`.
- **Reddedilen formatlar:** `.bin`, `.pt`, `.pth`, `.ckpt`, `.pkl`, `.pickle` (rastgele kod çalıştırma riski, ADR-0007 / `trsql-birlesik-arastirma-raporu.md` §3(b)).
- **Bütünlük doğrulaması:** Her yerel ağırlık dosyası `SHA-256` özeti ile doğrulanır.

## Aday Model Envanteri (Referans: RTX 4070 Laptop 8 GB, net ≈ 6.8 GB)

| Model | Kart | Rol | Nicemleme | Lisans | Ticari |
|---|---|---|---|---|---|
| Hati-Glint-SQL-9B-v1 | [hati-glint-sql-9b.md](hati-glint-sql-9b.md) | Türkçe SQL adayı | Q4_K_M GGUF | Apache-2.0 + NOTICE | Evet |
| XiYanSQL-QwenCoder-7B-2504 | [xiyansql-qwencoder-7b.md](xiyansql-qwencoder-7b.md) | SQL adayı (M-Schema) | Q5_K_M GGUF | Apache-2.0 | Evet |
| Arctic-Text2SQL-R1-7B | [arctic-text2sql-r1-7b.md](arctic-text2sql-r1-7b.md) | SQL adayı (GRPO RL) | Q5_K_M GGUF | Apache-2.0 | Evet |
| Qwen3-4B-Instruct-2507 | [qwen3-4b-instruct.md](qwen3-4b-instruct.md) | Küçük kontrol modeli | Q5_K_M GGUF | Apache-2.0 | Evet |
| BGE-M3 GGUF | [bge-m3-gguf.md](bge-m3-gguf.md) | Gömme modeli (CPU) | Q8_0 GGUF (`ggml-org`) | MIT | Evet |

## Lisans Uyarısı (`qwen-research`)

`trsql-birlesik-arastirma-raporu.md` §3(a) uyarınca:

- **`Qwen2.5-Coder-3B-Instruct`**: `qwen-research` lisanslıdır; ticari kullanım için ayrıca izin gerekir.
- **`XiYanSQL-QwenCoder-3B-2504`**: Kartı `apache-2.0` gösterse de tabanı `qwen-research` lisanslı `Qwen2.5-Coder-3B` olduğundan türev eser olarak ticari risk taşır; hukuki görüş olmadan ticari üründe kullanılmaz, yalnızca akademik karşılaştırma içindir.
- Bu nedenle TRSQL'de küçük kontrol modeli olarak **`Qwen3-4B-Instruct-2507`** (Apache-2.0), 7B sınıfında **`XiYanSQL-QwenCoder-7B-2504`** (Apache-2.0) seçilmiştir.

## `models/download.py` Kullanımı

```powershell
# Manifesti listele
python models/download.py list

# Sabitlenmiş veya verilen SHA-256 ile indir
python models/download.py download qwen3-4b-instruct --sha256 <64-hex>

# İlk kez SHA-256 hesaplamak için (pinleme öncesi)
python models/download.py download qwen3-4b-instruct --allow-unverified

# Yerel dosyayı doğrula (.bin/pickle otomatik reddedilir)
python models/download.py verify models/weights/Qwen3-4B-Instruct-2507.Q5_K_M.gguf --sha256 <64-hex>
```

## Model Kartı Şablonu

Her model kartında aşağıdaki alanlar tutulur:

| Alan | Örnek |
|---|---|
| Ad / sürüm | Hati-Glint-SQL-9B-v1 |
| Kaynak URL ve commit/revizyon | `https://huggingface.co/runelab-ai/Hati-Glint-SQL-9B-v1` |
| Lisans ve izin verilen kullanım | Apache-2.0 + NOTICE |
| Quantization / dosya | Q4_K_M GGUF |
| Dosya SHA-256 | İndirme sonrası `models/download.py verify` ile kaydedilir |
| Bağlam uzunluğu | 4096–8192 (`kv_cache_type=q8_0`) |
| Ölçülen tepe VRAM (referans dizüstü) | F2'de ölçülür (hedef ≤ 6800 MB) |
| İstem şablonu (`template_id`) | `ddl_v1` / `mschema_v1` |
| Bilinen skorlar ve kaynağı | Kendi beyanı mı, bağımsız mı? |
