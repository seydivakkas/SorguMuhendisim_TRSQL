# Yerel GPU ve CUDA Ortamı Kurulumu (Windows / RTX 4070 Laptop 8 GB)

Bu kılavuz, TRSQL'i gerçek yerel GGUF modelleri ve PostgreSQL 16 ile çalıştırmak için
gereken Python ve CUDA ortamını belgeler (**T-07**).

## 1. Ön Koşullar

- **İşletim Sistemi:** Windows 11 (x64) veya Linux x86_64
- **Python:** 3.12 (`py -3.12`)
- **NVIDIA Sürücüsü ve CUDA:** Güncel NVIDIA sürücüsü (`nvidia-smi` ile doğrulanır) + CUDA 12.x (veya önceden derlenmiş `cu124` tekerleği)
- **PostgreSQL 16 (opsiyonel canlı testler için):** Docker Desktop + Docker Compose v2

## 2. Sanal Ortam ve Paket Kurulumu

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev,api,postgres,synthetic]"
pip install "huggingface-hub>=0.24"
```

## 3. CUDA Destekli `llama-cpp-python`

### Yol A — Önceden Derlenmiş CUDA Tekerleği (Önerilen, VS Build Tools Gerektirmez)

```powershell
pip install "llama-cpp-python>=0.3" --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cu124
```

### Yol B — Kaynaktan Derleme (Visual Studio C++ Build Tools + CUDA Toolkit 12.x ile)

```powershell
$env:CMAKE_ARGS = "-DGGML_CUDA=on"
$env:FORCE_CMAKE = "1"
pip install "llama-cpp-python>=0.3" --no-cache-dir --force-reinstall --upgrade
```

## 4. Ortam Doğrulama (Çevrimdışı)

```powershell
python tools/env_report.py
python -c "import llama_cpp; print(llama_cpp.__version__, llama_cpp.llama_supports_gpu_offload())"
python -c "import psycopg; print(psycopg.__version__)"
nvidia-smi
```

Beklenen çıktılar:
- `llama_supports_gpu_offload()` → `True`
- `tools/env_report.py --output hardware.json` çıktısı deney klasörlerindeki `hardware.json` alanıyla uyumludur (ağ çağrısı içermez).

## 5. 8 GB VRAM Bütçesi Notları

- Net VRAM bütçesi: `6.800 MB` (`configs/default.toml`: `vram_budget_mb = 6800`).
- Önerilen ayarlar: `n_ctx = 4096` (veya VRAM yetiyorsa `8192`), `kv_cache_type = "q8_0"`, `flash_attn = true`, `n_gpu_layers = -1`.
- Gömme modeli (`bge-m3-q8_0.gguf`) CPU üzerinde (`n_gpu_layers = 0`) çalışır; VRAM tüketmez.
