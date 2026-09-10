#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

PYTHON_BIN="${PYTHON_BIN:-python3.12}"
VENV_DIR="${VENV_DIR:-.venv-build-linux}"
RUN_TESTS="${RUN_TESTS:-1}"
RUN_FROZEN_QUALIFICATION="${RUN_FROZEN_QUALIFICATION:-1}"
CREATE_ZIP="${CREATE_ZIP:-1}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "ERROR: $PYTHON_BIN not found. ROSS Studio 0.14.0 Linux release is qualified with Python 3.12." >&2
  exit 2
fi

"$PYTHON_BIN" - <<'PY'
import sys
if sys.version_info < (3, 11):
    raise SystemExit("Python >= 3.11 is required; Python 3.12 is recommended/qualified.")
print("Python:", sys.version)
PY

if [[ ! -d "$VENV_DIR" ]]; then
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

# shellcheck disable=SC1090
source "$VENV_DIR/bin/activate"

python -m pip install --upgrade pip setuptools wheel
python -m pip install -e ".[dev,package]"

if [[ "$RUN_TESTS" == "1" ]]; then
  python -m pytest -q
fi

rm -rf build dist
python -m PyInstaller --clean --noconfirm packaging/ROSS-Studio.spec

EXE="$ROOT/dist/ROSS-Studio/ROSS-Studio"
if [[ ! -x "$EXE" ]]; then
  echo "ERROR: executable was not generated at $EXE" >&2
  exit 3
fi

if [[ "$RUN_FROZEN_QUALIFICATION" == "1" ]]; then
  mkdir -p artifacts
  QT_QPA_PLATFORM=offscreen python tools/qualify_frozen_binary.py \
    dist artifacts/frozen_selftest_Linux.json
fi

if [[ "$CREATE_ZIP" == "1" ]]; then
  if ! command -v zip >/dev/null 2>&1; then
    echo "ERROR: zip is required to create the distributable archive." >&2
    exit 4
  fi
  mkdir -p artifacts
  rm -f artifacts/ROSS-Studio-0.14.0-Linux-x86_64.zip \
        artifacts/ROSS-Studio-0.14.0-Linux-x86_64.SHA256
  (
    cd dist
    zip -r -9 -q ../artifacts/ROSS-Studio-0.14.0-Linux-x86_64.zip ROSS-Studio
  )
  sha256sum artifacts/ROSS-Studio-0.14.0-Linux-x86_64.zip \
    > artifacts/ROSS-Studio-0.14.0-Linux-x86_64.SHA256
fi

echo
echo "ROSS Studio Linux build completed."
echo "Executable directory: $ROOT/dist/ROSS-Studio"
echo "Executable:           $EXE"
if [[ "$CREATE_ZIP" == "1" ]]; then
  echo "ZIP:                  $ROOT/artifacts/ROSS-Studio-0.14.0-Linux-x86_64.zip"
  cat "$ROOT/artifacts/ROSS-Studio-0.14.0-Linux-x86_64.SHA256"
fi
