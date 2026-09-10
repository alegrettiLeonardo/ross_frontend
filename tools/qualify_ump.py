from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import numpy as np
import ross as rs

from ross_studio.analysis_backend import RossAnalysisBackend, RossUnbalanceInput
from ross_studio.legacy_import import load_irdin_project
from ross_studio.ump import consistent_lateral_ump_matrix, project_ump_specs


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "src" / "ross_studio" / "resources" / "OP-W60-500-60Hz-IC611-P3.txt"
OUT = ROOT / "artifacts" / "ump_qualification.json"


def rel_norm(a: np.ndarray, b: np.ndarray) -> float:
    den = float(np.linalg.norm(b))
    return float(np.linalg.norm(a - b) / den) if den else float(np.linalg.norm(a - b))


def main() -> int:
    backend = RossAnalysisBackend(rs)

    L = 2.0
    kq = 100.0
    local = consistent_lateral_ump_matrix(L, kq)
    qx = np.zeros(12)
    qx[[0, 6]] = 1.0
    qy = np.zeros(12)
    qy[[1, 7]] = 1.0
    analytical_x = float(qx @ local @ qx)
    analytical_y = float(qy @ local @ qy)
    expected = kq * L
    analytical_pass = (
        np.allclose(local, local.T, rtol=0.0, atol=1e-12)
        and abs(analytical_x - expected) <= 1e-10
        and abs(analytical_y - expected) <= 1e-10
    )

    project_on = load_irdin_project(FIXTURE)
    project_off = deepcopy(project_on)
    for mass in project_off.distributed_masses:
        mass.ump_enabled = False
        mass.ump_value = 0.0

    specs = project_ump_specs(project_on)
    if len(specs) != 1:
        raise RuntimeError(f"OP-W60 UMP gate expected one active span; received {len(specs)}")

    build_on = backend.build_rotor(project_on, strict=True)
    build_off = backend.build_rotor(project_off, strict=True)
    assembly = build_on.rotor.ump_assembly
    omega = 3600.0 * 2.0 * np.pi / 60.0

    m_error = rel_norm(np.asarray(build_on.rotor.M(omega)), np.asarray(build_off.rotor.M(omega)))
    c_error = rel_norm(np.asarray(build_on.rotor.C(omega)), np.asarray(build_off.rotor.C(omega)))
    g_error = rel_norm(np.asarray(build_on.rotor.G()), np.asarray(build_off.rotor.G()))

    k_delta_residual = (
        np.asarray(build_off.rotor.K(omega))
        - np.asarray(build_on.rotor.K(omega))
        - np.asarray(assembly.matrix_n_m)
    )
    k_delta_max_abs_error_n_m = float(np.max(np.abs(k_delta_residual)))
    k_delta_relative_error = float(
        np.linalg.norm(k_delta_residual) / max(np.linalg.norm(assembly.matrix_n_m), 1.0)
    )
    # The mechanical K is O(1e9) N/m while OP-W60 UMP is O(1) N/m. The
    # independently assembled matrix subtraction has unavoidable floating
    # cancellation around 1e-7..1e-6 N/m. This gate is still several orders
    # tighter than any engineering significance of the imported coefficient.
    k_delta_pass = k_delta_max_abs_error_n_m <= 2e-6
    invariants_pass = m_error <= 1e-12 and c_error <= 1e-12 and g_error <= 1e-12 and k_delta_pass

    static_on = backend.run_static_build(build_on)
    static_off = backend.run_static_build(build_off)
    static_error = rel_norm(np.asarray(static_on.deformation), np.asarray(static_off.deformation))
    static_pass = static_error <= 1e-12

    project_amp = deepcopy(project_on)
    active = [mass for mass in project_amp.distributed_masses if mass.ump_enabled]
    active[0].ump_value = 1.0e8
    build_amp = backend.build_rotor(project_amp, strict=True)

    raw_loads = [load for load in project_on.loads if load.kind.strip().casefold() == "unbalance"]
    inputs_off: list[RossUnbalanceInput] = []
    inputs_amp: list[RossUnbalanceInput] = []
    for load in raw_loads:
        node_off = build_off.node_insertion_plan.node_for(load.position_mm)
        node_amp = build_amp.node_insertion_plan.node_for(load.position_mm)
        if node_off is None or node_amp is None:
            raise RuntimeError("UMP harmonic qualification lost an exact unbalance node.")
        source_unit = str(load.metadata["source_unit"])
        phase_rad = float(np.deg2rad(load.phase_deg))
        inputs_off.append(RossUnbalanceInput(node_off, load.magnitude, source_unit, phase_rad))
        inputs_amp.append(RossUnbalanceInput(node_amp, load.magnitude, source_unit, phase_rad))

    response_off = np.asarray(
        backend.run_unbalance_build(build_off, inputs_off, [3600.0]).response.forced_resp,
        dtype=complex,
    )
    response_amp = np.asarray(
        backend.run_unbalance_build(build_amp, inputs_amp, [3600.0]).response.forced_resp,
        dtype=complex,
    )
    harmonic_relative_change = float(np.linalg.norm(response_amp - response_off) / np.linalg.norm(response_off))
    harmonic_pass = bool(np.all(np.isfinite(np.abs(response_amp))) and harmonic_relative_change > 1e-4)

    op = specs[0]
    span = assembly.spans[0]
    summary = {
        "status": "PASS" if all((analytical_pass, invariants_pass, static_pass, harmonic_pass)) else "FAIL",
        "model": {
            "law": "f_UMP(x) = k'_UMP * u(x)",
            "equation": "M qdd + (C + Omega G) qd + (K - K_UMP) q = F",
            "source_unit": "N/m^2",
            "assembly": "consistent Hermite distributed negative stiffness; no UMP rotary-inertia term",
        },
        "analytical": {
            "qualified": analytical_pass,
            "length_m": L,
            "stiffness_per_length_n_m2": kq,
            "expected_integrated_stiffness_n_m": expected,
            "x_energy_n_m": analytical_x,
            "y_energy_n_m": analytical_y,
            "matrix_symmetric": bool(np.allclose(local, local.T, rtol=0.0, atol=1e-12)),
        },
        "op_w60": {
            "qualified": invariants_pass and static_pass,
            "span": {
                "name": op.name,
                "start_mm": op.start_mm,
                "end_mm": op.end_mm,
                "length_mm": op.length_mm,
                "k_prime_n_m2": op.stiffness_per_length_n_m2,
                "integrated_stiffness_n_m": span.integrated_stiffness_n_m,
                "shaft_element_indices": list(span.shaft_element_indices),
                "max_abs_global_matrix_entry_n_m": assembly.max_abs_entry_n_m,
            },
            "invariants": {
                "relative_M_change": m_error,
                "relative_C_change": c_error,
                "relative_G_change": g_error,
                "K_delta_max_abs_error_n_m": k_delta_max_abs_error_n_m,
                "K_delta_relative_error": k_delta_relative_error,
                "static_deformation_relative_change": static_error,
            },
        },
        "harmonic_participation": {
            "qualified": harmonic_pass,
            "synthetic_k_prime_n_m2": 1.0e8,
            "speed_rpm": 3600.0,
            "relative_response_change": harmonic_relative_change,
            "note": "Synthetic coefficient is a numerical participation test only; OP-W60 raw 1.002 N/m^2 is not rescaled.",
        },
        "legacy_contract_audit": {
            "predad_comment": "ump N/m/m",
            "matrizes_comment": "UMP inertia term = 0; rho*S*dy/420 -> ump*dy/420",
            "implementation_policy": "Use the dimensionally consistent translational term only; do not reproduce the apparent legacy coemas rotary-inertia side term.",
        },
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if summary["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
