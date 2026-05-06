#!/usr/bin/env bash
# Modular Mac build: produces dist/SWC-Studio.app where the swcstudio
# code and model files live as PLAIN files inside Contents/Resources/,
# so they can be replaced by the in-app auto-updater without
# re-downloading the whole bundle.
#
# Differences from build_macos.sh:
#   * Uses packaging/swcstudio_gui_modular.spec (entry point =
#     swcstudio_bootstrap.py; swcstudio package is excluded from PyInstaller)
#   * After PyInstaller finishes, copies the swcstudio/ source tree
#     verbatim into Contents/Resources/app/swcstudio/
#   * Copies model files into Contents/Resources/models/
#
# Result: dist/SWC-Studio.app where Resources/ looks like:
#     app/swcstudio/...   (~5 MB, swappable code)
#     models/*.{pkl,pt}   (~60 MB, swappable models)

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${VENV_DIR:-${ROOT_DIR}/.venv-packaging-macos}"
PYTHON_BIN="${PYTHON_BIN:-python3.11}"

echo "[SWC-Studio modular] repo root: ${ROOT_DIR}"
echo "[SWC-Studio modular] python:    ${PYTHON_BIN}"
echo "[SWC-Studio modular] venv:      ${VENV_DIR}"

rm -rf "${ROOT_DIR}/build" "${ROOT_DIR}/dist"

"${PYTHON_BIN}" -m venv "${VENV_DIR}"
# shellcheck source=/dev/null
source "${VENV_DIR}/bin/activate"

python -m pip install --upgrade pip setuptools wheel
pip install --no-cache-dir -e ".[build]"

pyinstaller --noconfirm --clean "${ROOT_DIR}/packaging/swcstudio_gui_modular.spec"

# Post-build: copy the swcstudio code as plain .py files into the app's
# Resources/app/swcstudio/. This is the directory the bootstrap searches
# for at startup. Replacing this folder = installing a code update.
APP_DIR="${ROOT_DIR}/dist/SWC-Studio.app"
RES_DIR="${APP_DIR}/Contents/Resources"
APP_CODE_DIR="${RES_DIR}/app"
MODELS_DIR="${RES_DIR}/models"

mkdir -p "${APP_CODE_DIR}"
mkdir -p "${MODELS_DIR}"

echo "[SWC-Studio modular] copying swcstudio source -> ${APP_CODE_DIR}/swcstudio"
# Use rsync to skip __pycache__ and .pyc by default. cp -R would also work
# but rsync gives clean exclude patterns.
rsync -a \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='*.pyo' \
    --exclude='data/models' \
    "${ROOT_DIR}/swcstudio/" \
    "${APP_CODE_DIR}/swcstudio/"

# Stamp a VERSION file so the bootstrap and updater can tell which code
# version the user is running.
APP_VER="$(python -c 'from importlib.metadata import version, PackageNotFoundError; \
import sys; \
sys.stdout.write(version("swcstudio")) if True else None' 2>/dev/null || echo "0.1.0")"
echo "${APP_VER}" > "${APP_CODE_DIR}/VERSION"

# Models — copy if present in the source tree.
if [ -d "${ROOT_DIR}/swcstudio/data/models" ]; then
  echo "[SWC-Studio modular] copying models -> ${MODELS_DIR}"
  rsync -a "${ROOT_DIR}/swcstudio/data/models/" "${MODELS_DIR}/"
  echo "${APP_VER}" > "${MODELS_DIR}/VERSION"
else
  echo "[SWC-Studio modular] no models found at ${ROOT_DIR}/swcstudio/data/models — skipping (will download on first launch)"
fi

# Summary
echo ""
echo "[SWC-Studio modular] build complete: ${APP_DIR}"
echo "    Resources/app/swcstudio/  (code, version ${APP_VER})"
echo "    Resources/models/         (models, version ${APP_VER})"
echo ""
echo "Update workflow:"
echo "  - Code-only:  unzip new swcstudio/ over Resources/app/swcstudio/"
echo "                or into ~/Library/Application Support/SWC-Studio/app/"
echo "  - Models:     same idea, into Resources/models/ or"
echo "                ~/Library/Application Support/SWC-Studio/models/"
echo "  - Major bump: full .app re-download (libraries / Python interpreter changed)"
