from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def _find_executable(dist: Path) -> Path:
    candidates = [dist / "ROSS-Studio" / "ROSS-Studio", dist / "ROSS-Studio" / "ROSS-Studio.exe"]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    matches = list(dist.rglob("ROSS-Studio.exe")) + [p for p in dist.rglob("ROSS-Studio") if p.is_file()]
    if len(matches) != 1:
        raise RuntimeError(f"Expected one frozen ROSS-Studio executable under {dist}, found {matches}.")
    return matches[0]


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        raise SystemExit("usage: qualify_frozen_thd_027.py DIST OUTPUT_JSON")
    dist = Path(argv[0]).resolve()
    output = Path(argv[1]).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    exe = _find_executable(dist)
    completed = subprocess.run(
        [str(exe), "--thd-027-self-test", "--thd-027-output", str(output)],
        check=False,
        timeout=2400,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"Frozen THD Bearings 0.27 qualification failed with exit code {completed.returncode}; evidence={output}"
        )
    if not output.exists():
        raise RuntimeError(f"Frozen THD Bearings 0.27 executable did not create {output}.")
    print(output.read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
