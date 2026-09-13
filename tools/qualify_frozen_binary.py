from __future__ import annotations

import json
from pathlib import Path
import platform
import subprocess
import sys

from ross_studio import __version__ as EXPECTED_STUDIO_VERSION

EXPECTED_EXECUTABLE = {
    "BearingElement", "BallBearingElement", "RollerBearingElement", "CylindricalBearing",
    "PlainJournal", "TiltingPad", "SqueezeFilmDamper", "ThrustPad", "MagneticBearingElement",
}
EXPECTED_GENERAL = {"BearingElement", "BallBearingElement", "RollerBearingElement", "CylindricalBearing"}
EXPECTED_THD = {"PlainJournal", "TiltingPad", "SqueezeFilmDamper", "ThrustPad"}
EXPECTED_MODEL_BUILDERS = {"disks", "seals", "couplings", "loads", "probes"}
EXPECTED_TRANSACTION_KINDS = {"distributed_mass", "disk", "point_mass", "seal", "coupling", "load", "probe"}
EXPECTED_LEGACY_SIDEBAR_COMPAT = {"rotor", "disks", "bearings", "seals", "supports", "couplings", "loads", "ump", "probes"}


def executable_path(dist_root: Path) -> Path:
    name = "ROSS-Studio.exe" if platform.system() == "Windows" else "ROSS-Studio"
    return dist_root / "ROSS-Studio" / name


def _run_json_gate(exe: Path, args: list[str], output: Path, label: str) -> dict[str, object]:
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run([str(exe), *args, str(output)], check=False, timeout=300)
    if not output.is_file():
        raise SystemExit(f"Frozen executable returned {proc.returncode} without producing {output} for {label}")
    payload = json.loads(output.read_text(encoding="utf-8"))
    if proc.returncode != 0 or payload.get("status") != "PASS":
        raise SystemExit(f"Frozen executable {label} failed:\n" + json.dumps(payload, indent=2, ensure_ascii=False))
    if payload.get("frozen") is not True:
        raise SystemExit(f"{label} was not executed from a frozen runtime: {payload}")
    return payload


def main() -> int:
    dist_root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("dist")
    output = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("artifacts/frozen_selftest.json")
    exe = executable_path(dist_root).resolve()
    if not exe.is_file():
        raise SystemExit(f"Frozen executable not found: {exe}")

    self_payload = _run_json_gate(exe, ["--self-test", "--self-test-output"], output, "scientific self-test")
    assert self_payload["ross_version"] == "2.3.0", self_payload
    assert self_payload["physical_sections"] == 15, self_payload
    assert self_payload["requested_base_elements"] == 15, self_payload
    assert self_payload["effective_shaft_elements"] == 27, self_payload
    assert self_payload["shaft_nodes"] == 28, self_payload
    assert self_payload["unresolved_positions_mm"] == [], self_payload
    assert self_payload["native_plot_traces"] > 0, self_payload
    assert set(self_payload["executable_classes"]) == EXPECTED_EXECUTABLE, self_payload
    assert self_payload["blocked_classes"] == [], self_payload
    assert self_payload["validation_errors"] == [], self_payload

    io_output = output.with_name(output.stem + "_project_io" + output.suffix)
    io_payload = _run_json_gate(exe, ["--project-io-self-test", "--project-io-output"], io_output, "project file I/O")
    assert io_payload["ross_version"] == "2.3.0", io_payload
    assert io_payload["ross_studio_version"] == EXPECTED_STUDIO_VERSION, io_payload
    assert io_payload["irdin_sections"] == 15, io_payload
    assert io_payload["irdin_shaft_elements"] == 27, io_payload
    assert io_payload["irdin_bearings"] == 2, io_payload
    assert io_payload["irdin_supports"] == 2, io_payload
    assert io_payload["native_roundtrip_equal"] is True, io_payload
    assert io_payload["blank_roundtrip_empty"] is True, io_payload
    assert io_payload["dyrobes_model_summary_sections"] == 4, io_payload
    assert io_payload["dyrobes_model_summary_base_elements"] == 8, io_payload
    assert io_payload["dyrobes_model_summary_disks"] == 1, io_payload
    assert io_payload["dyrobes_raw_vendor_cases"] == 0, io_payload
    assert io_payload["dyrobes_raw_vendor_gate"] == "WAITING_FOR_REPRESENTATIVE_FILES", io_payload

    gui_output = output.with_name(output.stem + "_gui" + output.suffix)
    gui_payload = _run_json_gate(exe, ["--gui-smoke", "--gui-smoke-output"], gui_output, "GUI startup and model-builder smoke")
    assert gui_payload["project"] == "OP-W60-500-60Hz-IC611-P3", gui_payload
    assert gui_payload["view_modes"] == [], gui_payload
    assert gui_payload["rotor_editor_count"] == 8, gui_payload
    assert gui_payload["bearing_station_count"] == 2, gui_payload
    assert gui_payload["bearing_direct_route"] is True, gui_payload
    assert gui_payload["bearing_selection_synced"] is True, gui_payload
    assert gui_payload["bearing_station_inventory"] == [["radial_anchor"], ["radial_anchor"]], gui_payload
    assert set(gui_payload["general_executable"]) == EXPECTED_GENERAL, gui_payload
    assert set(gui_payload["thd_executable"]) == EXPECTED_THD, gui_payload
    assert gui_payload["amb_blocked"] == [], gui_payload
    assert set(gui_payload["sidebar_routes"]) == EXPECTED_LEGACY_SIDEBAR_COMPAT, gui_payload
    assert "shaft" not in set(gui_payload["sidebar_routes"]), gui_payload
    assert gui_payload["bearing_model_icon_count"] == 8, gui_payload
    assert gui_payload["bearing_inline_input"] is True, gui_payload
    assert gui_payload["bearing_results_below"] is True, gui_payload

    model_builder = gui_payload["model_builder_014"]
    assert model_builder["status"] == "PASS", model_builder
    assert set(model_builder["enabled_editor_groups"]) == EXPECTED_MODEL_BUILDERS, model_builder
    assert set(model_builder["transaction_nodes"]) == EXPECTED_TRANSACTION_KINDS, model_builder
    assert all(node is not None for node in model_builder["transaction_nodes"].values()), model_builder
    assert model_builder["concent_table_visible"] is True, model_builder
    assert model_builder["concent_sketch_visible"] is True, model_builder
    assert model_builder["concent_inertias_preserved"] is True, model_builder
    assert model_builder["seal_native_class"] == "SealElement", model_builder
    assert model_builder["coupling_native_mapping"] == "NATIVE_TWO_NODE_COUPLING", model_builder
    assert model_builder["load_realization"] == "ANALYSIS_INPUT_EXACT_NODE", model_builder
    assert model_builder["unresolved_positions_mm"] == [], model_builder

    outputs_output = output.with_name(output.stem + "_engineering_outputs" + output.suffix)
    outputs_payload = _run_json_gate(
        exe, ["--engineering-outputs-self-test", "--engineering-outputs-output"], outputs_output,
        "Engineering Outputs rich export runtime",
    )
    assert outputs_payload["ross_version"] == "2.3.0", outputs_payload
    assert outputs_payload["ross_studio_version"] == EXPECTED_STUDIO_VERSION, outputs_payload
    assert outputs_payload["native_ross_plot_traces"] > 0, outputs_payload
    assert outputs_payload["png_bytes"] > 0, outputs_payload
    assert outputs_payload["xlsx_bytes"] > 0, outputs_payload
    assert outputs_payload["pdf_bytes"] > 0, outputs_payload

    decoupled_output = output.with_name(output.stem + "_static_modal_020" + output.suffix)
    decoupled_payload = _run_json_gate(
        exe, ["--static-modal-020-self-test", "--static-modal-020-output"], decoupled_output,
        "Static/Modal decoupled 0.20 runtime",
    )
    assert decoupled_payload["static_after_calls"] == {"build": 1, "static": 1, "modal": 0, "campbell": 0}, decoupled_payload
    assert decoupled_payload["final_calls"] == {"build": 2, "static": 1, "modal": 1, "campbell": 1}, decoupled_payload
    assert decoupled_payload["independent_strict_builds"] is True, decoupled_payload
    assert decoupled_payload["static_unresolved_positions_mm"] == [], decoupled_payload
    assert decoupled_payload["modal_unresolved_positions_mm"] == [], decoupled_payload
    assert decoupled_payload["modal_mode_count"] > 0, decoupled_payload

    tf_output = output.with_name(output.stem + "_time_frequency_021" + output.suffix)
    tf_payload = _run_json_gate(
        exe, ["--time-frequency-021-self-test", "--time-frequency-021-output"], tf_output,
        "Time/Frequency native 0.21 runtime",
    )
    assert tf_payload["ross_version"] == "2.3.0", tf_payload
    assert tf_payload["frequency_traces"] > 0, tf_payload
    assert tf_payload["unbalance_traces"] > 0, tf_payload
    assert tf_payload["time_traces"] > 0, tf_payload
    assert tf_payload["hbm_traces"] > 0, tf_payload
    assert tf_payload["ucs_traces"] > 0, tf_payload
    assert tf_payload["clearance_traces"] > 0, tf_payload
    assert tf_payload["clearance_rows"] == 2, tf_payload
    assert tf_payload["scientific_recompute"] is False, tf_payload

    stochastic_output = output.with_name(output.stem + "_stochastic_022" + output.suffix)
    stochastic_payload = _run_json_gate(
        exe, ["--stochastic-022-self-test", "--stochastic-022-output"], stochastic_output,
        "Native ROSS Stochastic 0.22 runtime",
    )
    assert stochastic_payload["ross_version"] == "2.3.0", stochastic_payload
    assert stochastic_payload["sample_count"] == 2, stochastic_payload
    assert stochastic_payload["native_st_rotor"] is True, stochastic_payload
    assert stochastic_payload["sample_seed_reproducible"] is True, stochastic_payload
    assert stochastic_payload["input_histogram_traces"] > 0, stochastic_payload
    assert stochastic_payload["campbell_traces"] > 0, stochastic_payload
    assert stochastic_payload["frequency_traces"] > 0, stochastic_payload
    assert stochastic_payload["unbalance_traces"] > 0, stochastic_payload
    assert stochastic_payload["time_1d_traces"] > 0, stochastic_payload
    assert stochastic_payload["time_2d_traces"] > 0, stochastic_payload
    assert stochastic_payload["time_3d_traces"] > 0, stochastic_payload
    assert stochastic_payload["scientific_recompute"] is False, stochastic_payload

    combined = {
        "status": "PASS",
        "platform": platform.system(),
        "ross_studio_version": EXPECTED_STUDIO_VERSION,
        "executable": str(exe),
        "scientific": self_payload,
        "project_io": io_payload,
        "gui": gui_payload,
        "engineering_outputs": outputs_payload,
        "static_modal_020": decoupled_payload,
        "time_frequency_021": tf_payload,
        "stochastic_022": stochastic_payload,
    }
    print(json.dumps(combined, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
