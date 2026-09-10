# ROSS Studio 0.14.0 — Linux build

This source package is intended for Ubuntu 24.04 x86_64 / WSL2 Ubuntu 24.04 and reproduces the ROSS Studio 0.14.0 Linux packaging path. The scientific runtime remains pinned to `ross-rotordynamics==2.3.0`.

## 1. System dependencies

```bash
sudo apt update
sudo apt install -y \
  python3.12 python3.12-venv python3-pip \
  build-essential git zip unzip \
  libdbus-1-3 libegl1 libfontconfig1 libgl1 libglib2.0-0 libtbb12 \
  libx11-xcb1 libxcb-cursor0 libxcb-icccm4 libxcb-image0 \
  libxcb-keysyms1 libxcb-render-util0 libxcb-shape0 libxcb-util1 \
  libxcb-xkb1 libxkbcommon-x11-0
```

If `python3.12` is not available on your distribution, use a supported Python >=3.11, but Python 3.12 is the qualified release interpreter.

## 2. Build with the included script

From the extracted project directory:

```bash
chmod +x build_linux.sh
./build_linux.sh
```

The script will:

1. create `.venv-build-linux`;
2. install `.[dev,package]`;
3. run the project pytest suite;
4. build the one-directory PyInstaller application using `packaging/ROSS-Studio.spec`;
5. run the frozen scientific/GUI qualification;
6. create `artifacts/ROSS-Studio-0.14.0-Linux-x86_64.zip` and its SHA-256 file.

## 3. Manual equivalent

```bash
cd /path/to/ross_frontend

python3.12 -m venv .venv-build-linux
source .venv-build-linux/bin/activate

python -m pip install --upgrade pip setuptools wheel
python -m pip install -e ".[dev,package]"

python -m pytest -q

rm -rf build dist
python -m PyInstaller --clean --noconfirm packaging/ROSS-Studio.spec

mkdir -p artifacts
QT_QPA_PLATFORM=offscreen \
  python tools/qualify_frozen_binary.py \
  dist artifacts/frozen_selftest_Linux.json

(cd dist && zip -r -9 -q ../artifacts/ROSS-Studio-0.14.0-Linux-x86_64.zip ROSS-Studio)
sha256sum artifacts/ROSS-Studio-0.14.0-Linux-x86_64.zip \
  > artifacts/ROSS-Studio-0.14.0-Linux-x86_64.SHA256
```

## 4. Run the executable

```bash
cd dist/ROSS-Studio
./ROSS-Studio
```

Do not move the `ROSS-Studio` executable out of its directory: this is a PyInstaller `onedir` bundle and depends on the adjacent runtime files.

## 5. Build without tests (development only)

```bash
RUN_TESTS=0 RUN_FROZEN_QUALIFICATION=0 ./build_linux.sh
```

This is faster, but it is **not** the qualified release path.

## Scientific baseline

- ROSS Studio: 0.14.0
- ROSS Rotordynamics: 2.3.0
- integrated scientific `main` baseline: `e25e167516e828f7f002be6fe65b6ea12487346a`
- packaging branch contains no changes to the scientific model; it only carries release/build support.
