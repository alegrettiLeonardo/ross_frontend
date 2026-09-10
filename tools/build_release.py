"""Build and validate a native ROSS Studio 0.11.0 PyInstaller bundle.

This script is intentionally OS-neutral and is executed on native GitHub-hosted
Linux and Windows runners. PyInstaller does not cross-compile, so each bundle is
created and smoke-tested on its target operating system.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

import PyInstaller
import PyInstaller.__main__


APP_NAME = "ROSS-Studio"
VERSION = "0.11.0"
SCIENTIFIC_BASELINE_SHA = "a8765f26610e43b506d534c53253fbf54c070d53"
ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist" / APP_NAME


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    args = [
        str(ROOT / "tools" / "ross_studio_entry.py"),
        "--name", APP_NAME,
        "--onedir",
        "--windowed",
        "--noconfirm",
        "--clean",
        "--collect-data", "ross_studio",
        "--collect-data", "ross",
        "--collect-submodules", "ross",
        "--collect-data", "plotly",
        "--collect-data", "pint",
        "--copy-metadata", "ross-rotordynamics",
        "--copy-metadata", "ross-studio",
        "--distpath", str(ROOT / "dist"),
        "--workpath", str(ROOT / "build" / "pyinstaller"),
        "--specpath", str(ROOT / "build"),
    ]
    PyInstaller.__main__.run(args)

    executable = DIST / (f"{APP_NAME}.exe" if os.name == "nt" else APP_NAME)
    if not executable.is_file():
        raise FileNotFoundError(f"Packaged executable was not created: {executable}")

    smoke_env = os.environ.copy()
    smoke_env["ROSS_STUDIO_SMOKE_TEST"] = "1"
    smoke_env.setdefault("QT_QPA_PLATFORM", "offscreen")
    completed = subprocess.run(
        [str(executable)],
        cwd=str(DIST),
        env=smoke_env,
        check=False,
        timeout=180,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "Packaged executable smoke test failed.\n"
            f"returncode={completed.returncode}\n"
            f"stdout={completed.stdout}\n"
            f"stderr={completed.stderr}"
        )

    # Import versions from the same environment used to build the executable.
    import ross as rs
    import ross_studio

    build_info = {
        "product": "ROSS Studio",
        "version": ross_studio.__version__,
        "ross_version": getattr(rs, "__version__", "unknown"),
        "scientific_baseline_main_sha": SCIENTIFIC_BASELINE_SHA,
        "release_build_sha": os.environ.get("GITHUB_SHA", "local"),
        "operating_system": platform.system(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "pyinstaller": PyInstaller.__version__,
        "bundle_mode": "onedir",
        "entry_executable": executable.name,
        "entry_executable_sha256": _sha256(executable),
        "smoke_test": "PASS",
    }
    if build_info["version"] != VERSION:
        raise RuntimeError(f"Expected ROSS Studio {VERSION}, got {build_info['version']}")
    if build_info["ross_version"] != "2.3.0":
        raise RuntimeError(f"Expected ROSS 2.3.0, got {build_info['ross_version']}")

    (DIST / "BUILD_INFO.json").write_text(
        json.dumps(build_info, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(build_info, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
