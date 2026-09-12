from __future__ import annotations

import json
from pathlib import Path
import platform
import subprocess
import sys


def executable_path(dist_root: Path) -> Path:
    name = "ROSS-Studio.exe" if platform.system() == "Windows" else "ROSS-Studio"
    return dist_root / "ROSS-Studio" / name


def main() -> int:
    dist_root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("dist")
    output = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("artifacts/frozen_multirotor_023.json")
    exe = executable_path(dist_root).resolve(); output = output.resolve(); output.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run([str(exe), "--multirotor-023-self-test", "--multirotor-023-output", str(output)], check=False, timeout=300)
    if not output.is_file(): raise SystemExit(f"Frozen MultiRotor gate produced no output; returncode={proc.returncode}")
    payload = json.loads(output.read_text(encoding="utf-8"))
    if proc.returncode != 0 or payload.get("status") != "PASS" or payload.get("frozen") is not True: raise SystemExit(json.dumps(payload, indent=2, ensure_ascii=False))
    assert payload["ross_version"] == "2.3.0"; assert payload["two_shaft_native_class"] == "MultiRotor"; assert payload["three_shaft_native_class"] == "MultiRotor"; assert payload["speed_mapping_pass"] is True; assert payload["max_error_percent"] < 0.01; assert payload["blocked_methods"] == ["level1", "static", "ucs"]; assert payload["experimental_methods"] == ["critical_speed"]; assert payload["tvms_stiffness_positive"] is True
    print(json.dumps(payload, indent=2, ensure_ascii=False)); return 0


if __name__ == "__main__": raise SystemExit(main())
