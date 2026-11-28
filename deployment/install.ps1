#Requires -Version 5.1
<#
.SYNOPSIS
    TRSQL kurum ici (on-prem) cevrimdisi kurulum ve dogrulama betigi (Windows PowerShell).
.DESCRIPTION
    Internet baglantisi olmadan Python 3.12+, .venv, yerel wheelhouse kurulumu,
    model SHA-256 dogrulamasi (verify_models.py) ve G3/G4 guvenlik kapilarini calistirir.
#>
[CmdletBinding()]
param(
    [string]$Wheelhouse = "",
    [string]$Manifest = "",
    [switch]$CreateVenv,
    [switch]$SkipInstall,
    [switch]$AllowEmptyModels
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

Write-Host "=== TRSQL On-Prem Kurulum (Windows) ===" -ForegroundColor Cyan

# Enforce offline-first environment variables (ADR-0002)
$env:TRSQL_OFFLINE = "1"
$env:HF_HUB_OFFLINE = "1"
$env:TRANSFORMERS_OFFLINE = "1"

# 1. Check Python 3.12+
$VenvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$HostPython = $null

if (Get-Command py -ErrorAction SilentlyContinue) {
    try {
        $pyVer = & py -3.12 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
        if ($LASTEXITCODE -eq 0 -and $pyVer -eq "3.12") {
            $HostPython = @("py", "-3.12")
        }
    } catch {}
}
if (-not $HostPython -and (Get-Command python -ErrorAction SilentlyContinue)) {
    $verOut = & python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
    if ($LASTEXITCODE -eq 0 -and ([version]$verOut -ge [version]"3.12")) {
        $HostPython = @("python")
    }
}

# 2. Check or create .venv
if (-not (Test-Path $VenvPython)) {
    if ($CreateVenv) {
        if (-not $HostPython) {
            throw "Python 3.12 bulunamadi. Lutfen Python 3.12 yukleyin."
        }
        Write-Host "[1/5] .venv olusturuluyor..."
        if ($HostPython.Count -eq 2) {
            & $HostPython[0] $HostPython[1] -m venv (Join-Path $RepoRoot ".venv")
        } else {
            & $HostPython[0] -m venv (Join-Path $RepoRoot ".venv")
        }
        if ($LASTEXITCODE -ne 0) { throw ".venv olusturulamadi." }
    } else {
        throw ".venv bulunamadi ($VenvPython). Olusturmak icin -CreateVenv parametresi ile calistirin."
    }
}

$VenvVersion = & $VenvPython -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')"
if ($LASTEXITCODE -ne 0) { throw ".venv Python calistirilamadi." }
$MajorMinor = ($VenvVersion.Split('.')[0..1] -join '.')
if ([version]$MajorMinor -lt [version]"3.12") {
    throw "Python 3.12+ gerekli; .venv surumu: $VenvVersion"
}
Write-Host "[1/5] Python dogrulandi: $VenvVersion (.venv)" -ForegroundColor Green

# 3. Offline package installation from wheelhouse (optional)
if (-not $SkipInstall) {
    $WheelDir = if ($Wheelhouse) { $Wheelhouse } elseif ($env:TRSQL_WHEELHOUSE) { $env:TRSQL_WHEELHOUSE } else { "" }
    if ($WheelDir) {
        if (-not (Test-Path $WheelDir)) {
            throw "Wheelhouse dizini bulunamadi: $WheelDir"
        }
        Write-Host "[2/5] Cevrimdisi paket kurulumu (wheelhouse: $WheelDir)..."
        & $VenvPython -m pip install --no-index --find-links="$WheelDir" -e ".[api,dev]"
        if ($LASTEXITCODE -ne 0) { throw "Cevrimdisi pip install basarisiz." }
    } else {
        Write-Host "[2/5] Wheelhouse belirtilmedi; mevcut .venv paketleri korunuyor (ag indirmesi yapilmaz)." -ForegroundColor Yellow
    }
} else {
    Write-Host "[2/5] Paket kurulumu atlandi (-SkipInstall)."
}

# 4. Environment file check (never store secrets in repo)
$EnvFile = Join-Path $RepoRoot ".env"
if (-not (Test-Path $EnvFile)) {
    Write-Warning ".env dosyasi bulunamadi. .env.example sablonunu .env olarak kopyalayip TRSQL_PG_DSN ve TRSQL_MODEL_PATH degerlerini doldurun."
} else {
    Write-Host "[3/5] .env dosyasi mevcut." -ForegroundColor Green
}

# 5. Model integrity verification (reject .bin/pickle, verify SHA256)
Write-Host "[4/5] Model agirliklari ve SHA-256 butunlugu dogrulaniyor..."
$VerifyArgs = @("deployment/verify_models.py", "--models-dir", "models")
if ($Manifest) {
    $VerifyArgs += @("--manifest", $Manifest)
}
if ($AllowEmptyModels -or (-not $Manifest -and -not (Get-ChildItem -Path (Join-Path $RepoRoot "models") -Include *.gguf, *.safetensors -Recurse -ErrorAction SilentlyContinue))) {
    $VerifyArgs += "--allow-empty"
}
& $VenvPython @VerifyArgs
if ($LASTEXITCODE -ne 0) { throw "Model dogrulamasi basarisiz (Guvensiz dosya veya SHA-256 uyusmazligi)." }

# 6. Run G3 (Module Boundaries) & G4 (Security Gate Tests)
Write-Host "[5/5] Kalite ve guvenlik kapilari calistiriliyor (G3 + G4)..."
& $VenvPython "tools/check_boundaries.py"
if ($LASTEXITCODE -ne 0) { throw "G3 modul siniri kontrolu basarisiz." }

$PytestTemp = Join-Path $env:TEMP "trsql_pt_install"
& $VenvPython -m pytest -p no:cacheprovider --basetemp="$PytestTemp" -m security -q
if ($LASTEXITCODE -ne 0) { throw "G4 guvenlik testleri basarisiz." }

Write-Host "=== Kurulum ve G3/G4 dogrulamalari basariyla tamamlandi. ===" -ForegroundColor Green
