from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import numpy as np
import ross as rs

from ross_studio.analysis_backend import RossAnalysisBackend
from ross_studio.concentrated import concentrated_disk_class
from ross_studio.legacy_import import load_irdin_project


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "src" / "ross_studio" / "resources" / "OP-W60-500-60Hz-IC611-P3.txt"
OUT = ROOT / "artifacts" / "concentrated_mass_qualification.json"


def main() -> int:
    element_cls = concentrated_disk_class(rs)
    ix, iy, iz, mass = 1.25, 2.50, 3.75, 34.0
    element = element_cls(0, mass, ix, iy, iz, tag="qualification")
    expected_local_m = np.diag([mass, mass, mass, ix, iz, iy])
    expected_local_g = np.zeros((6, 6))
    expected_local_g[3, 4] = iy
    expected_local_g[4, 3] = -iy
    local_m_error = float(np.max(np.abs(np.asarray(element.M()) - expected_local_m)))
    local_g_error = float(np.max(np.abs(np.asarray(element.G()) - expected_local_g)))

    backend = RossAnalysisBackend(rs)
    baseline = load_irdin_project(FIXTURE)
    modified = deepcopy(baseline)
    spec = modified.point_masses[0]
    spec.ix_kg_m2 = ix
    spec.iy_kg_m2 = iy
    spec.iz_kg_m2 = iz

    build_0 = backend.build_rotor(baseline, strict=True)
    build_1 = backend.build_rotor(modified, strict=True)
    node = build_1.node_insertion_plan.node_for(spec.position_mm)
    if node is None:
        raise RuntimeError("Concentrated mass qualification lost the exact OP-W60 node at 105 mm.")
    ndof = int(build_1.rotor.number_dof)
    omega = 3600.0 * 2.0 * np.pi / 60.0
    delta_m = np.asarray(build_1.rotor.M(omega)) - np.asarray(build_0.rotor.M(omega))
    delta_g = np.asarray(build_1.rotor.G()) - np.asarray(build_0.rotor.G())
    expected_global_m = np.zeros_like(delta_m)
    expected_global_g = np.zeros_like(delta_g)
    alpha = node * ndof + 3
    beta = node * ndof + 4
    theta = node * ndof + 5
    expected_global_m[alpha, alpha] = ix
    expected_global_m[beta, beta] = iz
    expected_global_m[theta, theta] = iy
    expected_global_g[alpha, beta] = -iy
    expected_global_g[beta, alpha] = iy
    global_m_error = float(np.max(np.abs(delta_m - expected_global_m)))
    global_g_error = float(np.max(np.abs(delta_g - expected_global_g)))

    c_error = float(np.max(np.abs(np.asarray(build_1.rotor.C(omega)) - np.asarray(build_0.rotor.C(omega)))))
    k_error = float(np.max(np.abs(np.asarray(build_1.rotor.K(omega)) - np.asarray(build_0.rotor.K(omega)))))
    static_0 = backend.run_static_build(build_0)
    static_1 = backend.run_static_build(build_1)
    static_error = float(np.max(np.abs(np.asarray(static_1.deformation) - np.asarray(static_0.deformation))))

    imported = baseline.point_masses[0]
    pass_gate = all(
        value <= 1e-12
        for value in (local_m_error, local_g_error, global_m_error, global_g_error, c_error, k_error, static_error)
    )
    summary = {
        "status": "PASS" if pass_gate else "FAIL",
        "contract": {
            "source": "RotorDin [Concent] / entrada.f + matrizes.f",
            "columns": ["position_mm", "mass_kg", "Ix_kg_m2", "Iy_kg_m2", "Iz_kg_m2"],
            "axis_map": {
                "RotorDin Ix": "ROSS alpha-alpha inertia",
                "RotorDin Iz": "ROSS beta-beta inertia",
                "RotorDin Iy": "ROSS theta-theta polar inertia + alpha/beta gyroscopic pair",
            },
            "rotordin_positive_global_G": {
                "G_alpha_beta": "-Iy",
                "G_beta_alpha": "+Iy",
            },
        },
        "analytical_element": {
            "mass_kg": mass,
            "Ix_kg_m2": ix,
            "Iy_kg_m2": iy,
            "Iz_kg_m2": iz,
            "max_abs_M_error": local_m_error,
            "max_abs_G_error": local_g_error,
        },
        "op_w60_source": {
            "position_mm": imported.position_mm,
            "mass_kg": imported.mass_kg,
            "Ix_kg_m2": imported.ix_kg_m2,
            "Iy_kg_m2": imported.iy_kg_m2,
            "Iz_kg_m2": imported.iz_kg_m2,
            "note": "The supplied OP-W60 case has zero principal inertias, so its qualified baseline response is unchanged.",
        },
        "op_w60_synthetic_nonzero_inertia_gate": {
            "node": node,
            "max_abs_M_delta_error": global_m_error,
            "max_abs_G_delta_error": global_g_error,
            "max_abs_C_change": c_error,
            "max_abs_K_change": k_error,
            "max_abs_static_deformation_change_m": static_error,
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if pass_gate else 2


if __name__ == "__main__":
    raise SystemExit(main())
