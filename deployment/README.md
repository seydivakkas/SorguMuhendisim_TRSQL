# deployment/ — Kurum İçi (On-Premises) Dağıtım Rehberi (AR-10)

TRSQL, **6698 sayılı KVKK** ve kurumsal veri güvenliği ilkeleri gereği tamamen **çevrimdışı (air-gapped / offline-first)** ve tek sunucu veya iç ağ üzerinde çalışacak biçimde tasarlanmıştır (bkz. [ADR-0002](../docs/adr/0002-offline-first-on-prem.md), [ADR-0007](../docs/adr/0007-defense-in-depth-sql-security.md)).

Çalışma zamanında dış ağa çıkılmaz (`HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`, `TRSQL_OFFLINE=1`) ve hiçbir gizli bilgi repoya yazılmaz.

---

## 1. Dosya Yapısı

| Dosya | Amaç |
|---|---|
| `deployment/Dockerfile` | Python 3.12 tabanlı çok aşamalı (multi-stage) çevrimdışı API imajı |
| `deployment/docker-compose.yml` | PostgreSQL 16 + TRSQL API + Frontend (Nginx) yığını |
| `deployment/install.ps1` | Windows Server / Windows 11 için air-gapped kurulum ve G3/G4 doğrulama betiği |
| `deployment/install.sh` | Linux (Ubuntu/RHEL/Debian) için air-gapped kurulum ve G3/G4 doğrulama betiği |
| `deployment/verify_models.py` | `.gguf` / `.safetensors` SHA-256 bütünlük doğrulayıcısı (`.bin` ve pickle formatlarını reddeder) |
| `deployment/postgres/*.sql` | PostgreSQL 16 salt okunur rol (`nl2sql_reader`), RLS, maskeleme ve `pgaudit` betikleri |

---

## 2. Donanım ve Yazılım Gereksinimleri

- **İşletim Sistemi:** Windows 10/11 / Server 2022 veya Linux (Ubuntu 22.04+, Debian 12+, RHEL 9+)
- **Python:** 3.12 (`py -3.12` veya `python3.12`)
- **Veritabanı:** PostgreSQL 16 (önerilen) veya yerel doğrulama için SQLite
- **Donanım (Referans):** 8 GB VRAM (net bütçe ≈ 6,8 GB), 32 GB sistem RAM; gömme modeli (BGE-M3) CPU'da çalışır
- **Frontend derleme / konteyner:** Docker Engine + Docker Compose v2 veya Node.js 20+

---

## 3. İnternetsiz (Air-Gapped) Kurulum Adımları

### Adım 1 — Çevrimdışı Paket Havuzu (Wheelhouse) Hazırlama

İnternete erişimi olan bir hazırlık makinesinde bağımlılıklar indirilir ve kurum içi sunucuya kopyalanır:

```bash
mkdir -p trsql-wheels
pip download --dest trsql-wheels ".[api,dev,postgres]"
```

### Adım 2 — Ortam Değişkenlerini Tanımlama (`.env`)

`.env.example` dosyasını `.env` olarak kopyalayın. **Parola ve DSN değerlerini asla git'e eklemeyin.**

```dotenv
TRSQL_OFFLINE=1
HF_HUB_OFFLINE=1
TRANSFORMERS_OFFLINE=1

POSTGRES_PASSWORD=GUCLU_RASTGELE_PAROLA
TRSQL_PG_USER=trsql_admin
TRSQL_PG_DB=trsql
TRSQL_PG_DSN=postgresql://nl2sql_reader:READER_PAROLASI@postgres:5432/trsql

TRSQL_MODEL_PATH=/app/models/hati-glint-sql-9b-q4_k_m.gguf
TRSQL_EMBEDDING_MODEL_PATH=/app/models/bge-m3-q8_0.gguf

# KVKK log saklama politikası
TRSQL_LOG_RETENTION_DAYS=180
TRSQL_LOG_ARCHIVE_AFTER_DAYS=30
TRSQL_LOG_PURGE_MODE=anonymize
```

### Adım 3 — Model Ağırlıklarını ve SHA-256 Bütünlüğünü Doğrulama

TRSQL yalnızca pickle içermeyen `.gguf` ve `.safetensors` ağırlıklarını kabul eder. `.bin`, `.pt`, `.pth`, `.pkl`, `.ckpt` gibi kod çalıştırma riski taşıyan biçimler reddedilir:

```bash
python deployment/verify_models.py --models-dir models --manifest models/manifest.json
```

Henüz ağırlık kopyalanmamış ilk kurulum kontrolü için `--allow-empty` kullanılabilir; dizinde zararlı `.bin` dosyası varsa `--allow-empty` kullanılsa bile kurulum durdurulur.

### Adım 4 — Kurulum Betiğini Çalıştırma (G3 + G4 Kapıları Dahil)

**Windows (PowerShell):**

```powershell
.\deployment\install.ps1 -CreateVenv -Wheelhouse C:\opt\trsql-wheels
```

**Linux (Bash):**

```bash
chmod +x deployment/install.sh
./deployment/install.sh --create-venv --wheelhouse /opt/trsql-wheels
```

Her iki betik sırasıyla:
1. `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`, `TRSQL_OFFLINE=1` değişkenlerini ayarlar,
2. Python 3.12+ ve `.venv` varlığını denetler,
3. Varsa yerel wheelhouse'dan `--no-index` ile kurulum yapar,
4. `deployment/verify_models.py` ile model bütünlüğünü denetler,
5. `tools/check_boundaries.py` (**G3**) ve `pytest -m security` (**G4**) kapılarını çalıştırır.

---

## 4. Docker Compose ile Kurum İçi Çalıştırma

`docker-compose.yml` dosyası **repo kök dizininden** çalıştırılmalıdır:

```bash
docker compose --project-directory . -f deployment/docker-compose.yml up -d --build
```

Sağlanan güvenlik değişmezleri:
- `./models` dizini API konteynerine **salt okunur (`:ro`)** bağlanır.
- `./deployment/postgres/*.sql` betikleri PostgreSQL 16 ilk başlatma dizinine (`/docker-entrypoint-initdb.d:ro`) bağlanır.
- `HF_HUB_OFFLINE=1` ve `TRSQL_OFFLINE=1` konteyner ortamında zorunludur.
- Tüm parolalar ve `TRSQL_PG_DSN` yalnızca `.env` ortam değişkenlerinden okunur; dosyada sabit parola yoktur.
- API (`127.0.0.1:8000`) ve Frontend (`127.0.0.1:3000`) yalnızca yerel arayüze bağlanır; dış erişim kurum içi reverse proxy (TLS sonlandırma) arkasından verilmelidir.

---

## 5. KVKK (6698 Sayılı Kanun) Log Saklama ve İmha Politikası

TRSQL denetim izleri (`AuditEvent`), `backend.observability.mask_sensitive()` üzerinden geçirilerek **TCKN, IBAN, telefon, e-posta, kart numarası ve gizli anahtarları** loglanmadan önce maskeler. Buna rağmen kullanıcı soruları bağlam gereği kişisel veri içerebileceği için aşağıdaki saklama politikası uygulanır:

| Politika Parametresi | Varsayılan | Açıklama |
|---|---|---|
| `TRSQL_LOG_RETENTION_DAYS` | `180` | Denetim kayıtlarının çevrimiçi/arşiv toplam saklama süresi (gün). Kurum uyumluluk biriminin onayına göre 180–730 gün arasında ayarlanır. |
| `TRSQL_LOG_ARCHIVE_AFTER_DAYS` | `30` | Aktif diskten salt-ekleme (append-only) şifreli arşive aktarım eşiği. |
| `TRSQL_LOG_PURGE_MODE` | `anonymize` | Süre dolumunda uygulanacak işlem: `anonymize` (soru metnini kalıcı hash/maske ile anonimleştirir, güvenlik istatistiklerini korur) veya `delete` (kalıcı silme). |
| `TRSQL_KVKK_PII_MASKING` | `1` | Log yazımından önce zorunlu maskeleme bayrağı (kapatılmamalıdır). |

**Operasyonel Kurallar:**
1. Audit log dosyaları yalnızca servis kullanıcısının (`trsql`) yazabileceği, diğer kullanıcıların değiştiremeyeceği (append-only / `chattr +a` veya WORM depolama) dizinlerde tutulur.
2. Süresi dolan loglar günlük zamanlanmış görev (cron / Windows Görev Zamanlayıcı) ile `TRSQL_LOG_RETENTION_DAYS` sınırına göre imha/anonimleştirme işlemine tabi tutulur ve imha tutanağı kaydedilir.
3. Geliştirme ve test ortamlarında **asla gerçek kurum verisi** kullanılmaz; yalnızca sentetik veri üretilir.

---

## 6. Servis Olarak Çalıştırma

### Linux — `systemd` Birim Dosyası (`/etc/systemd/system/trsql-api.service`)

En az yetkili `trsql` sistem kullanıcısı oluşturun (`useradd --system --no-create-home trsql`) ve aşağıdaki unit dosyasını tanımlayın:

```ini
[Unit]
Description=TRSQL Kurumsal NL2SQL API Servisi
After=network-online.target postgresql.service
Wants=postgresql.service

[Service]
Type=simple
User=trsql
Group=trsql
WorkingDirectory=/opt/trsql
EnvironmentFile=/opt/trsql/.env
Environment=TRSQL_OFFLINE=1
Environment=HF_HUB_OFFLINE=1
Environment=TRANSFORMERS_OFFLINE=1
ExecStartPre=/opt/trsql/.venv/bin/python /opt/trsql/deployment/verify_models.py --models-dir /opt/trsql/models --manifest /opt/trsql/models/manifest.json
ExecStart=/opt/trsql/.venv/bin/uvicorn backend.api.app:create_app --factory --host 127.0.0.1 --port 8000
Restart=on-failure
RestartSec=5

# Sertleştirme (Hardening)
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
ReadOnlyPaths=/opt/trsql/models /opt/trsql/configs /opt/trsql/security_policies
ReadWritePaths=/var/log/trsql

[Install]
WantedBy=multi-user.target
```

Etkinleştirme:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now trsql-api.service
sudo systemctl status trsql-api.service
```

### Windows — Windows Service (NSSM ile)

Windows Sunucuda servis yöneticisi olarak **NSSM (Non-Sucking Service Manager)** veya Windows Görev Zamanlayıcı kullanılabilir:

```powershell
# Yönetici PowerShell ile
nssm install TRSQL-API "C:\opt\trsql\.venv\Scripts\python.exe" `
  "-m uvicorn backend.api.app:create_app --factory --host 127.0.0.1 --port 8000"
nssm set TRSQL-API AppDirectory "C:\opt\trsql"
nssm set TRSQL-API AppEnvironmentExtra `
  "TRSQL_OFFLINE=1" `
  "HF_HUB_OFFLINE=1" `
  "TRANSFORMERS_OFFLINE=1" `
  "TRSQL_LOG_RETENTION_DAYS=180"
nssm set TRSQL-API AppStdout "C:\opt\trsql\logs\service-stdout.log"
nssm set TRSQL-API AppStderr "C:\opt\trsql\logs\service-stderr.log"
nssm set TRSQL-API AppRotateFiles 1
nssm set TRSQL-API AppRotateSeconds 86400
nssm start TRSQL-API
```

**Windows Güvenlik Notları:**
- Servis için ayrılmış, yerel yönetici yetkisi olmayan bir hizmet hesabı kullanın.
- `C:\opt\trsql\models` klasörüne hizmet hesabı için yalnızca **Okuma (Read)** izni verin.
- Başlatma öncesi `deployment\verify_models.py` kontrolünü görev zincirine veya başlatma sarmalayıcısına ekleyin.

---

## 7. Yedekleme ve Güncelleme Kontrol Listesi

- [ ] Güncelleme öncesi `.env` ve `security_policies/` ile `configs/` yedeklenir.
- [ ] Yeni model ağırlıkları çevrimdışı ortama alındıktan sonra `verify_models.py` ile SHA-256 doğrulaması tekrarlanır.
- [ ] PostgreSQL salt okunur rol (`nl2sql_reader`) ve RLS politikalarının `BYPASSRLS` içermediği doğrulanır.
- [ ] Güncelleme sonrasında `install.ps1` / `install.sh` çalıştırılarak G3 ve G4 kapılarının yeşil olduğu onaylanır.
