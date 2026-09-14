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
    output = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("artifacts/frozen_coupling_025.json")
    exe = executable_path(dist_root).resolve()
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [str(exe), "--coupling-025-self-test", "--coupling-025-output", str(output)],
        check=False,
        timeout=300,
    )
    if not output.is_file():
        raise SystemExit(f"Frozen Coupling 0.25 gate produced no output; returncode={proc.returncode}")
    payload = json.loads(output.read_text(encoding="utf-8"))
    if proc.returncode != 0 or payload.get("status") != "PASS" or payload.get("frozen") is not True:
        raise SystemExit(json.dumps(payload, indent=2, ensure_ascii=False))

    assert payload["ross_version"] == "2.3.0"
    required_gates = {
        "gui_input_to_domain_commit",
        "unit_conversion_and_native_field_identity",
        "exact_two_node_topology_and_6dof_contract",
        "local_12x12_mckg_independent_parity",
        "assembled_global_mckg_independent_parity",
        "matrix_structure_and_signs",
        "no_coupling_baseline_stiffer_softer_physical_response",
        "native_modal_numeric_result",
        "gui_result_rendering",
        "save_reopen_recompute",
        "stale_preview_rejected",
        "stale_result_invalidation",
        "async_race_obsolete_result_rejected",
        "fail_closed_invalid_contracts",
        "no_silent_fallback",
    }
    assert set(payload["gates"]) == required_gates, payload["gates"]
    assert all(payload["gates"].values()), payload["gates"]
    topology = payload["topology"]
    assert topology["native_class"] == "CouplingElement"
    assert topology["adjacent"] is True
    assert topology["dof_per_node"] == 6
    assert topology["native_n"] == topology["left_node"]
    assert topology["native_n_r"] == topology["right_node"]
    assert topology["right_node"] == topology["left_node"] + 1
    for group in ("local_matrix_parity", "global_matrix_parity"):
        assert all(item["pass"] is True for item in payload[group].values()), payload[group]
    assert payload["cases"]["physically_coherent_response_pass"] is True
    assert payload["gui_result"]["pass"] is True
    assert payload["persistence"]["coupling_equal"] is True
    assert payload["stale_preview"]["pass"] is True
    assert payload["stale_results"]["pass"] is True
    assert payload["race_protection"]["pass"] is True
    assert all(item["pass"] is True for item in payload["fail_closed"].values()), payload["fail_closed"]
    assert payload["no_silent_fallback"] is True

    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
