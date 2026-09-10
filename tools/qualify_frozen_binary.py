from __future__ import annotations

import json
from pathlib import Path
import platform
import subprocess
import sys

EXPECTED_EXECUTABLE = {
    "BearingElement",
    "BallBearingElement",
    "RollerBearingElement",
    "CylindricalBearing",
    "PlainJournal",
    "TiltingPad",
    "SqueezeFilmDamper",
    "ThrustPad",
}


def executable_path(dist_root: Path) -> Path:
    name = "ROSS-Studio.exe" if platform.system() == "Windows" else "ROSS-Studio"
    return dist_root / "ROSS-Studio" / name


def main() -> int:
    dist_root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("dist")
    output = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("artifacts/frozen_selftest.json")
    exe = executable_path(dist_root).resolve()
    if not exe.is_file():
        raise SystemExit(f"Frozen executable not found: {exe}")

    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [str(exe), "--self-test", "--self-test-output", str(output)],
        check=False,
        timeout=240,
    )
    if not output.is_file():
        raise SystemExit(f"Frozen executable returned {proc.returncode} without producing {output}")
    payload = json.loads(output.read_text(encoding="utf-8"))
    if proc.returncode != 0 or payload.get("status") != "PASS":
        raise SystemExit(
            "Frozen executable self-test failed:\n" + json.dumps(payload, indent=2, ensure_ascii=False)
        )

    assert payload["frozen"] is True, payload
    assert payload["ross_version"] == "2.3.0", payload
    assert payload["physical_sections"] == 15, payload
    assert payload["requested_base_elements"] == 15, payload
    assert payload["effective_shaft_elements"] == 27, payload
    assert payload["shaft_nodes"] == 28, payload
    assert payload["unresolved_positions_mm"] == [], payload
    assert payload["native_plot_traces"] > 0, payload
    assert set(payload["executable_classes"]) == EXPECTED_EXECUTABLE, payload
    assert payload["blocked_classes"] == ["MagneticBearingElement"], payload
    assert payload["validation_errors"] == [], payload

    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
