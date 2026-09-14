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
    output = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("artifacts/frozen_foundation_024.json")
    exe = executable_path(dist_root).resolve()
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [str(exe), "--foundation-024-self-test", "--foundation-024-output", str(output)],
        check=False,
        timeout=300,
    )
    if not output.is_file():
        raise SystemExit(f"Frozen Foundation 0.24 gate produced no output; returncode={proc.returncode}")
    payload = json.loads(output.read_text(encoding="utf-8"))
    if proc.returncode != 0 or payload.get("status") != "PASS" or payload.get("frozen") is not True:
        raise SystemExit(json.dumps(payload, indent=2, ensure_ascii=False))

    # Previously qualified scientific Foundation 0.24 gates remain mandatory.
    assert payload["ross_version"] == "2.3.0"
    assert payload["legacy_scientific_status"] == "PASS"
    assert payload["rigid_exact_m_parity"] is True
    assert payload["rigid_exact_k_parity"] is True
    assert payload["rigid_exact_c_parity"] is True
    assert payload["high_stiffness_convergence_pass"] is True
    assert payload["high_stiffness_sweep_n_m"] == [1.0e10, 1.0e12, 1.0e14]
    sweep_errors = payload["high_stiffness_sweep_error_percent"]
    assert len(sweep_errors) == 3
    assert sweep_errors[1] <= sweep_errors[0] + max(1.0e-9, 1.0e-6 * max(abs(sweep_errors[0]), 1.0))
    assert sweep_errors[2] <= sweep_errors[1] + max(1.0e-9, 1.0e-6 * max(abs(sweep_errors[1]), 1.0))
    assert payload["high_stiffness_max_error_percent"] < 0.5
    assert payload["massless_kc_no_internal_mass_pass"] is True
    assert payload["massless_damped_kc_blocked"] is True
    assert payload["modal_sensitivity_max_shift_percent"] > 0.5
    assert payload["matrix_delta_norm_m"] > 0.0
    assert payload["matrix_delta_norm_k"] > 0.0
    assert payload["matrix_delta_norm_c"] > 0.0
    assert payload["matrix_trace_delta_m"] > 0.0
    assert payload["expected_foundation_mass_kg"] > 0.0
    assert payload["cross_coupled_k_pass"] is True
    assert payload["cross_coupled_c_pass"] is True
    assert payload["frequency_axis_rad_s_pass"] is True
    assert payload["frequency_interpolation_pass"] is True
    assert payload["unsupported_contracts_blocked"] is True
    assert payload["exact_support_ownership_pass"] is True

    # New end-to-end feature chain closes the GUI/domain/native/persistence/staleness gap.
    feature = payload["feature_chain"]
    assert feature["status"] == "PASS", feature
    assert feature["ross_version"] == "2.3.0", feature
    required_gates = {
        "distinct_bearing_support_foundation_sentinels",
        "gui_input_to_domain_commit",
        "unit_identity_si_boundary",
        "frequency_hz_to_rad_s_conversion",
        "identity_topology_station_dof_signs",
        "independent_global_mck_parity",
        "matrix_structural_properties",
        "four_case_physical_response",
        "native_modal_numeric_result",
        "gui_result_rendering",
        "save_reopen_recompute",
        "stale_result_invalidation",
        "async_race_obsolete_result_rejected",
        "no_silent_fallback",
    }
    assert set(feature["gates"]) == required_gates, feature["gates"]
    assert all(feature["gates"].values()), feature["gates"]
    assert feature["frequency_conversion"]["pass"] is True
    assert feature["topology"]["foundation_dof_contract"] == 2
    assert feature["topology"]["foundation_n_link"] is None
    assert feature["global_matrix_parity"]["M"]["pass"] is True
    assert feature["global_matrix_parity"]["K0"]["pass"] is True
    assert feature["global_matrix_parity"]["C0"]["pass"] is True
    assert feature["cases"]["physically_coherent_response_pass"] is True
    assert feature["gui_result"]["pass"] is True
    assert feature["persistence"]["foundation_equal"] is True
    assert feature["persistence"]["support_equal"] is True
    assert feature["persistence"]["bearing_equal"] is True
    assert feature["stale_results"]["pass"] is True
    assert feature["race_protection"]["pass"] is True
    assert feature["no_silent_fallback"] is True

    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
