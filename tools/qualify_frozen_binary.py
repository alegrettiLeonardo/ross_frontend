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
EXPECTED_GENERAL = {
    "BearingElement",
    "BallBearingElement",
    "RollerBearingElement",
    "CylindricalBearing",
}
EXPECTED_THD = {
    "PlainJournal",
    "TiltingPad",
    "SqueezeFilmDamper",
    "ThrustPad",
}


def executable_path(dist_root: Path) -> Path:
    name = "ROSS-Studio.exe" if platform.system() == "Windows" else "ROSS-Studio"
    return dist_root / "ROSS-Studio" / name


def _run_json_gate(exe: Path, args: list[str], output: Path, label: str) -> dict[str, object]:
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run([str(exe), *args, str(output)], check=False, timeout=240)
    if not output.is_file():
        raise SystemExit(f"Frozen executable returned {proc.returncode} without producing {output} for {label}")
    payload = json.loads(output.read_text(encoding="utf-8"))
    if proc.returncode != 0 or payload.get("status") != "PASS":
        raise SystemExit(
            f"Frozen executable {label} failed:\n" + json.dumps(payload, indent=2, ensure_ascii=False)
        )
    if payload.get("frozen") is not True:
        raise SystemExit(f"{label} was not executed from a frozen runtime: {payload}")
    return payload


def main() -> int:
    dist_root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("dist")
    output = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("artifacts/frozen_selftest.json")
    exe = executable_path(dist_root).resolve()
    if not exe.is_file():
        raise SystemExit(f"Frozen executable not found: {exe}")

    self_payload = _run_json_gate(
        exe,
        ["--self-test", "--self-test-output"],
        output,
        "scientific self-test",
    )
    assert self_payload["ross_version"] == "2.3.0", self_payload
    assert self_payload["physical_sections"] == 15, self_payload
    assert self_payload["requested_base_elements"] == 15, self_payload
    assert self_payload["effective_shaft_elements"] == 27, self_payload
    assert self_payload["shaft_nodes"] == 28, self_payload
    assert self_payload["unresolved_positions_mm"] == [], self_payload
    assert self_payload["native_plot_traces"] > 0, self_payload
    assert set(self_payload["executable_classes"]) == EXPECTED_EXECUTABLE, self_payload
    assert self_payload["blocked_classes"] == ["MagneticBearingElement"], self_payload
    assert self_payload["validation_errors"] == [], self_payload

    gui_output = output.with_name(output.stem + "_gui" + output.suffix)
    gui_payload = _run_json_gate(
        exe,
        ["--gui-smoke", "--gui-smoke-output"],
        gui_output,
        "GUI startup smoke",
    )
    assert gui_payload["project"] == "OP-W60-500-60Hz-IC611-P3", gui_payload
    assert gui_payload["view_modes"] == ["Engineering 2D", "ROSS Native"], gui_payload
    assert gui_payload["rotor_editor_count"] == 8, gui_payload
    assert gui_payload["bearing_station_count"] == 2, gui_payload
    assert gui_payload["bearing_direct_route"] is True, gui_payload
    assert gui_payload["bearing_selection_synced"] is True, gui_payload
    assert gui_payload["bearing_station_inventory"] == [["radial_anchor"], ["radial_anchor"]], gui_payload
    assert set(gui_payload["general_executable"]) == EXPECTED_GENERAL, gui_payload
    assert set(gui_payload["thd_executable"]) == EXPECTED_THD, gui_payload
    assert gui_payload["amb_blocked"] == ["MagneticBearingElement"], gui_payload
    assert {"ump", "probes", "shaft", "bearings"}.issubset(set(gui_payload["sidebar_routes"])), gui_payload

    combined = {
        "status": "PASS",
        "platform": platform.system(),
        "executable": str(exe),
        "scientific": self_payload,
        "gui": gui_payload,
    }
    print(json.dumps(combined, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
