from __future__ import annotations

from copy import deepcopy
import json
from math import pi
from pathlib import Path

import numpy as np
import ross as rs

from ross_studio.analysis_backend import RossAnalysisBackend
from ross_studio.legacy_import import load_irdin_project
from ross_studio.ross_backend import RossModelBuilder
from ross_studio.thrust_pad_service import ThrustPadStudioService


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "src" / "ross_studio" / "resources" / "OP-W60-500-60Hz-IC611-P3.txt"
OUT = ROOT / "artifacts" / "thrust_pad_qualification.json"

INPUT = {
    "speed_rpm": [90.0],
    "pad_inner_radius_mm": 1150.0,
    "pad_outer_radius_mm": 1725.0,
    "pad_pivot_radius_mm": 1442.5,
    "pad_arc_deg": 26.0,
    "angular_pivot_position_deg": 15.0,
    "oil_supply_temperature_c": 40.0,
    "lubricant": "ISOVG68",
    "n_pad": 12,
    "n_theta": 10,
    "n_radial": 10,
    "equilibrium_position_mode": "calculate",
    "axial_load_n": 13.320e6,
    "radial_inclination_angle_mrad": -0.275,
    "circumferential_inclination_angle_mrad": -0.017,
    "initial_film_thickness_um": 200.0,
    "tolerance_force_moment_n": 0.1,
    "residual_force_moment_n": 50.0,
}


def close(value, reference, rel):
    return bool(np.isfinite(value) and abs(value - reference) <= rel * abs(reference))


def main() -> int:
    project = load_irdin_project(FIXTURE)
    service = ThrustPadStudioService(rs)
    result = service.calculate(project, 0, "ThrustPad", INPUT)
    axial = result.axial_coefficients[0]
    op = result.operating_points[0]

    before = RossModelBuilder(rs).build(project, strict=True)
    candidate = deepcopy(project)
    radial = deepcopy(candidate.bearings[0])
    service.apply(candidate, 0, result)
    applied = candidate.bearings[-1]
    after = RossModelBuilder(rs).build(candidate, strict=True)

    omega = 90.0 * 2.0 * pi / 60.0
    thrust = next(e for e in after.rotor.bearing_elements if e.tag == applied.name)
    dk = np.asarray(after.rotor.K(omega), dtype=float) - np.asarray(before.rotor.K(omega), dtype=float)
    dc = np.asarray(after.rotor.C(omega), dtype=float) - np.asarray(before.rotor.C(omega), dtype=float)
    dm = np.asarray(after.rotor.M(omega), dtype=float) - np.asarray(before.rotor.M(omega), dtype=float)
    dg = np.asarray(after.rotor.G(), dtype=float) - np.asarray(before.rotor.G(), dtype=float)
    nz_k = np.argwhere(np.abs(dk) > max(1e-6, abs(axial.kzz) * 1e-10))
    nz_c = np.argwhere(np.abs(dc) > max(1e-6, abs(axial.czz) * 1e-10))

    modal = RossAnalysisBackend(rs).run_modal_build(after, 90.0, num_modes=12)
    modal_finite = bool(len(modal.wn) and np.all(np.isfinite(np.asarray(modal.wn, dtype=float))))

    gates = {
        "ross_version_exact": str(rs.__version__) == "2.3.0",
        "native_thrust_pad": result.native_element.__class__.__name__ == "ThrustPad",
        "axial_contract_only": not hasattr(result, "coefficients"),
        "canonical_kzz": close(axial.kzz, 317633126111.6322, 0.02),
        "canonical_czz": close(axial.czz, 10805941381.16573, 0.02),
        "canonical_pressure": close(float(op.max_pressure_pa), 6957021.42, 0.02),
        "canonical_temperature": close(float(op.max_temperature_c), 70.4, 0.02),
        "canonical_hmin": close(float(op.min_film_thickness_m), 82e-6, 0.05),
        "radial_bearing_preserved": candidate.bearings[0] == radial,
        "independent_axial_bearing": applied.metadata.get("application_mode") == "independent_axial_bearing_same_shaft_node",
        "thrust_has_no_n_link": thrust.n_link is None,
        "radial_n_link_preserved": next(e for e in after.rotor.bearing_elements if e.tag == radial.name).n_link == 28,
        "local_matrix_is_axial_only": bool(
            np.allclose(np.asarray(thrust.K(omega))[:2, :], 0.0)
            and np.allclose(np.asarray(thrust.K(omega))[:, :2], 0.0)
            and np.allclose(np.asarray(thrust.C(omega))[:2, :], 0.0)
            and np.allclose(np.asarray(thrust.C(omega))[:, :2], 0.0)
        ),
        "global_k_single_axial_entry": bool(nz_k.shape == (1, 2) and nz_k[0, 0] == nz_k[0, 1]),
        "global_c_single_axial_entry": bool(nz_c.shape == (1, 2) and nz_c[0, 0] == nz_c[0, 1]),
        "mass_unchanged": bool(np.allclose(dm, 0.0)),
        "gyro_unchanged": bool(np.allclose(dg, 0.0)),
        "strict_modal_finite": modal_finite,
        "op_w60_shaft_topology_preserved": len(after.rotor.shaft_elements) == 27,
    }
    passed = all(gates.values())

    payload = {
        "status": "PASS" if passed else "FAIL",
        "ross_version": str(rs.__version__),
        "scope": "Axial ThrustPad scientific and strict ROSS assembly gate; desktop capability remains independently gated until GUI E2E qualification.",
        "physical_contract": {
            "native_model": "ThrustPad",
            "application_class": "BearingElement",
            "active_dof": "z",
            "dynamic_coefficients": ["Kzz", "Czz"],
            "lateral_coefficients": "forced zero; never synthesized from thrust data",
            "radial_bearing_policy": "preserved as a separate bearing element",
            "flexible_support_policy": "ThrustPad is grounded independently until an axial support Kzz/Czz domain exists; lateral n_link is not reused.",
        },
        "gates": gates,
        "input_engineering_domain": INPUT,
        "si_normalized_input": result.metadata["si_input"],
        "axial_coefficients": result.metadata["axial_coefficients"],
        "operating_points": [
            {
                "rpm": p.rpm,
                "max_pressure_pa": p.max_pressure_pa,
                "max_temperature_c": p.max_temperature_c,
                "min_film_thickness_m": p.min_film_thickness_m,
                "max_film_thickness_m": p.max_film_thickness_m,
                "pivot_film_thickness_m": p.pivot_film_thickness_m,
            }
            for p in result.operating_points
        ],
        "global_assembly": {
            "nonzero_K_delta_indices": nz_k.tolist(),
            "nonzero_C_delta_indices": nz_c.tolist(),
            "K_delta_n_m": float(dk[tuple(nz_k[0])]) if nz_k.shape == (1, 2) else None,
            "C_delta_n_s_m": float(dc[tuple(nz_c[0])]) if nz_c.shape == (1, 2) else None,
            "modal_wn_rad_s": [float(v) for v in modal.wn],
        },
        "next_gate": "Desktop input -> Calculate -> axial preview -> native fields -> independent Apply -> strict builder -> axial result workflow, then capability promotion.",
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
