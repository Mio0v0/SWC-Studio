#!/usr/bin/env bash
# Build the modular macOS app. The PyInstaller runtime contains heavy
# dependencies; replaceable SWC-Studio code and models are staged under
# Contents/Resources after the runtime build.
#
# Result: dist/SWC-Studio.app where Resources/ looks like:
#     app/swcstudio/...   (~5 MB, swappable code)
#     models/*            (~75 MB raw model files, swappable models)

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${VENV_DIR:-${ROOT_DIR}/.venv-packaging-macos}"
PYTHON_BIN="${PYTHON_BIN:-python3.12}"

echo "[SWC-Studio] repo root: ${ROOT_DIR}"
echo "[SWC-Studio] python:    ${PYTHON_BIN}"
echo "[SWC-Studio] venv:      ${VENV_DIR}"

rm -rf "${ROOT_DIR}/build" "${ROOT_DIR}/dist"

"${PYTHON_BIN}" -m venv "${VENV_DIR}"
# shellcheck source=/dev/null
source "${VENV_DIR}/bin/activate"

python -m pip install --upgrade pip setuptools wheel
python -m pip install --no-cache-dir -e ".[build]"

pyinstaller --noconfirm --clean "${ROOT_DIR}/packaging/swcstudio_gui_macos.spec"

APP_DIR="${ROOT_DIR}/dist/SWC-Studio.app"
RES_DIR="${APP_DIR}/Contents/Resources"
python "${ROOT_DIR}/packaging/stage_modular_payload.py" \
  --source-root "${ROOT_DIR}" \
  --runtime-root "${RES_DIR}"

# Summary
echo ""
echo "[SWC-Studio] modular build complete: ${APP_DIR}"
echo "    Resources/app/swcstudio/  (replaceable code)"
echo "    Resources/models/         (replaceable models)"
echo ""
echo "Code/model updates are installed in the user data override directories."
