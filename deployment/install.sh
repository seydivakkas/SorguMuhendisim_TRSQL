#!/usr/bin/env bash
# TRSQL kurum ici (on-prem) cevrimdisi kurulum ve dogrulama betigi (Linux / macOS).
# Kullanim:
#   ./deployment/install.sh [--wheelhouse /opt/trsql-wheels] [--manifest models/manifest.json] [--create-venv] [--skip-install] [--allow-empty-models]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

WHEELHOUSE="${TRSQL_WHEELHOUSE:-}"
MANIFEST=""
CREATE_VENV=0
SKIP_INSTALL=0
ALLOW_EMPTY_MODELS=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --wheelhouse)
      WHEELHOUSE="$2"
      shift 2
      ;;
    --manifest)
      MANIFEST="$2"
      shift 2
      ;;
    --create-venv)
      CREATE_VENV=1
      shift
      ;;
    --skip-install)
      SKIP_INSTALL=1
      shift
      ;;
    --allow-empty-models)
      ALLOW_EMPTY_MODELS=1
      shift
      ;;
    *)
      echo "[HATA] Bilinmeyen parametre: $1" >&2
      exit 2
      ;;
  esac
done

# Enforce offline-first environment variables (ADR-0002)
export TRSQL_OFFLINE=1
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1

echo "=== TRSQL On-Prem Kurulum (Linux) ==="

VENV_PY="${REPO_ROOT}/.venv/bin/python"

find_host_python() {
  for candidate in python3.12 python3 python; do
    if command -v "${candidate}" >/dev/null 2>&1; then
      if "${candidate}" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)" >/dev/null 2>&1; then
        echo "${candidate}"
        return 0
      fi
    fi
  done
  return 1
}

if [[ ! -x "${VENV_PY}" ]]; then
  if [[ "${CREATE_VENV}" -eq 1 ]]; then
    HOST_PY="$(find_host_python || true)"
    if [[ -z "${HOST_PY}" ]]; then
      echo "[HATA] Python 3.12+ bulunamadi." >&2
      exit 1
    fi
    echo "[1/5] .venv olusturuluyor (${HOST_PY})..."
    "${HOST_PY}" -m venv "${REPO_ROOT}/.venv"
  else
    echo "[HATA] .venv bulunamadi (${VENV_PY}). Olusturmak icin --create-venv kullanin." >&2
    exit 1
  fi
fi

VENV_VERSION="$("${VENV_PY}" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')")"
"${VENV_PY}" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)" || {
  echo "[HATA] Python 3.12+ gerekli; .venv surumu: ${VENV_VERSION}" >&2
  exit 1
}
echo "[1/5] Python dogrulandi: ${VENV_VERSION} (.venv)"

if [[ "${SKIP_INSTALL}" -eq 0 ]]; then
  if [[ -n "${WHEELHOUSE}" ]]; then
    if [[ ! -d "${WHEELHOUSE}" ]]; then
      echo "[HATA] Wheelhouse dizini bulunamadi: ${WHEELHOUSE}" >&2
      exit 1
    fi
    echo "[2/5] Cevrimdisi paket kurulumu (wheelhouse: ${WHEELHOUSE})..."
    "${VENV_PY}" -m pip install --no-index --find-links="${WHEELHOUSE}" -e ".[api,dev]"
  else
    echo "[2/5] Wheelhouse belirtilmedi; mevcut .venv paketleri korunuyor (ag indirmesi yapilmaz)."
  fi
else
  echo "[2/5] Paket kurulumu atlandi (--skip-install)."
fi

if [[ ! -f "${REPO_ROOT}/.env" ]]; then
  echo "[UYARI] .env dosyasi bulunamadi. .env.example dosyasini .env olarak kopyalayip TRSQL_PG_DSN ve TRSQL_MODEL_PATH ayarlayin." >&2
else
  echo "[3/5] .env dosyasi mevcut."
fi

echo "[4/5] Model agirliklari ve SHA-256 butunlugu dogrulaniyor..."
VERIFY_ARGS=("deployment/verify_models.py" "--models-dir" "models")
if [[ -n "${MANIFEST}" ]]; then
  VERIFY_ARGS+=("--manifest" "${MANIFEST}")
fi
if [[ "${ALLOW_EMPTY_MODELS}" -eq 1 ]] || [[ -z "${MANIFEST}" && -z "$(find models -type f \( -name '*.gguf' -o -name '*.safetensors' \) 2>/dev/null)" ]]; then
  VERIFY_ARGS+=("--allow-empty")
fi
"${VENV_PY}" "${VERIFY_ARGS[@]}"

echo "[5/5] Kalite ve guvenlik kapilari calistiriliyor (G3 + G4)..."
"${VENV_PY}" tools/check_boundaries.py
"${VENV_PY}" -m pytest -p no:cacheprovider --basetemp="${TMPDIR:-/tmp}/trsql_pt_install" -m security -q

echo "=== Kurulum ve G3/G4 dogrulamalari basariyla tamamlandi. ==="
