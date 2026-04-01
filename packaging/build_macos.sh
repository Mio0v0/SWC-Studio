#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${VENV_DIR:-${ROOT_DIR}/.venv-packaging-macos}"
PYTHON_BIN="${PYTHON_BIN:-python3.11}"

echo "[SWC-Studio] repo root: ${ROOT_DIR}"
echo "[SWC-Studio] python: ${PYTHON_BIN}"
echo "[SWC-Studio] venv: ${VENV_DIR}"

rm -rf "${ROOT_DIR}/build" "${ROOT_DIR}/dist"

"${PYTHON_BIN}" -m venv "${VENV_DIR}"
source "${VENV_DIR}/bin/activate"

python -m pip install --upgrade pip setuptools wheel
pip install --no-cache-dir -e ".[gui,build]"

pyinstaller --noconfirm --clean "${ROOT_DIR}/packaging/swcstudio_gui.spec"

echo "[SWC-Studio] build complete: ${ROOT_DIR}/dist/SWC-Studio.app"
