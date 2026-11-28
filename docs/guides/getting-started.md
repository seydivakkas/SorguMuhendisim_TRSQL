# Geliştirme Ortamı Kurulumu

## Gereksinimler

- Python 3.11+ (3.12 önerilir)
- Git
- (Model deneyleri için) NVIDIA sürücüsü + CUDA; llama.cpp kurulumu AR-05'te belgelenecek

## Kurulum

Windows (PowerShell):

```powershell
git clone https://github.com/seydivakkas/SorguMuhendisim_TRSQL.git
cd SorguMuhendisim_TRSQL
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev,api]"
```

Linux / macOS:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,api]"
```

## Kalite kapıları (CI ile aynı)

```bash
ruff check . && ruff format --check .   # G1
mypy                                     # G2
python tools/check_boundaries.py         # G3
pytest -m security                       # G4
pytest                                   # G5
```

## Ortam değişkenleri

`.env.example` dosyasını `.env` olarak kopyalayın ve doldurun. `.env` asla commit'lenmez.

| Değişken | Açıklama |
|---|---|
| `TRSQL_MODEL_PATH` | Yerel GGUF model dosyası |
| `TRSQL_EMBEDDING_MODEL_PATH` | Yerel gömme (BGE-M3) GGUF dosyası |
| `TRSQL_DB_DIALECT` | `sqlite` veya `postgres` |
| `TRSQL_SQLITE_PATH` | Yerel SQLite veritabanı yolu |
| `TRSQL_PG_DSN` | Salt okunur PostgreSQL bağlantısı (AR-07) |
| `TRSQL_TOKENS_FILE` | SHA-256 özetli token dosyası (`T-02`) |

### API'yi yerel olarak çalıştırma (duman testi)

```powershell
$env:TRSQL_DB_DIALECT="sqlite"
$env:TRSQL_SQLITE_PATH="demo.sqlite"
$env:TRSQL_MODEL_ADAPTER="fake"
uvicorn backend.api.app:create_default_app --factory --port 8000
```

## Bir aşamayı değiştirmek

1. İlgili portu `backend/core/ports.py` içinde bulun.
2. Yeni sınıfı **kendi modülünde** yazın ve modülün `__init__.py`'sinden dışa açın.
3. `backend/orchestration/factory.py` içinde bağlayın (veya deney konfigürasyonundan seçin).
4. Birim testi + gerekiyorsa entegrasyon testi ekleyin.
5. Deneyse `experiments/` altına konfigürasyon ve sonuçları kaydedin.
