from __future__ import annotations

"""ROSS Studio 0.15.1 — Bearing Native Outputs qualification.

This gate is deliberately end-to-end and pinned to ROSS 2.3.0.  It proves that
Bearing Studio does not duplicate ROSS post-processing semantics, that every public
plot*/show_* method exposed by each solved THD object has an explicit Studio route,
and that every calculated bearing can be committed to the strict OP-W60 rotor and
participate in a finite modal solve.
"""

from copy import deepcopy
import json
from pathlib import Path
from typing import Any

import numpy as np
import ross as rs

from ross_studio.analysis_backend import RossAnalysisBackend
from ross_studio.bearing_native_inventory import inventory_native_outputs
from ross_studio.bearing_studio_service import BearingStudioService
from ross_studio.legacy_import import load_irdin_project
from ross_studio.ross_backend import RossModelBuilder
from ross_studio.ross_native_plots import NativeRossPlotUnavailable, RossBearingNativePlotService
from ross_studio.services import RossCapabilityRegistry
from ross_studio.thd_bearing_service import THDBearingStudioService
from ross_studio.thrust_pad_service import ThrustPadStudioService


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "src" / "ross_studio" / "resources" / "OP-W60-500-60Hz-IC611-P3.txt"
OUT = ROOT / "artifacts" / "bearing_native_outputs_0151_qualification.json"


GENERAL_CASES: dict[str, tuple[float, dict[str, Any]]] = {
    "BallBearingElement": (
        3600.0,
        {
            "n_balls": 8,
            "d_balls_m": 0.03,
            "static_load_n": 500.0,
            "contact_angle_rad": float(np.pi / 6.0),
        },
    ),
    "RollerBearingElement": (
        3600.0,
        {
            "n_rollers": 10,
            "roller_length_m": 0.025,
            "static_load_n": 1200.0,
            "contact_angle_rad": 0.1,
        },
    ),
    "CylindricalBearing": (
        3600.0,
        {
            "speed_rpm": [900.0, 1800.0, 2700.0, 3600.0, 4500.0],
            "weight_n": 525.0,
            "bearing_length_m": 0.03,
            "journal_diameter_m": 0.10,
            "radial_clearance_m": 0.0001,
            "oil_viscosity_pa_s": 0.10,
        },
    ),
}


THD_CASES: dict[str, tuple[float, dict[str, Any]]] = {
    "PlainJournal": (
        900.0,
        {
            "speed_rpm": [900.0],
            "axial_length_m": 0.263144,
            "journal_diameter_m": 0.4,
            "radial_clearance_m": 1.95e-4,
            "elements_circumferential": 11,
            "elements_axial": 3,
            "n_pad": 2,
            "pad_arc_deg": 176.0,
            "preload": 0.0,
            "geometry": "circular",
            "reference_temperature_c": 50.0,
            "fxs_load_n": 0.0,
            "fys_load_n": -112814.91,
            "groove_factor": [0.52, 0.48],
            "lubricant": "ISOVG32",
            "oil_flow_l_min": 37.86,
            "oil_supply_pressure_pa": 0.0,
            "sommerfeld_type": 2,
            "initial_guess": [0.1, -0.1],
            "method": "perturbation",
            "operating_type": "flooded",
        },
    ),
    "TiltingPad": (
        3000.0,
        {
            "speed_rpm": [3000.0],
            "journal_diameter_m": 101.6e-3,
            "radial_clearance_m": 74.9e-6,
            "pad_thickness_m": 12.7e-3,
            "n_pads": 5,
            "pivot_angles_deg": [18.0, 90.0, 162.0, 234.0, 306.0],
            "pad_arc_deg": 60.0,
            "pad_axial_length_m": 50.8e-3,
            "preload": 0.5,
            "offset": 0.5,
            "lubricant": "ISOVG32",
            "oil_supply_temperature_c": 40.0,
            "fxs_load_n": 884.05,
            "fys_load_n": -2670.4,
            "equilibrium_type": "match_eccentricity",
            "eccentricity_ratio": 0.35,
            "attitude_angle_deg": 287.5,
            "thermal_type": "adiabatic",
            "nx": 10,
            "nz": 10,
        },
    ),
    "SqueezeFilmDamper": (
        900.0,
        {
            "speed_rpm": [900.0, 3600.0],
            "axial_length_m": 0.02286,
            "journal_diameter_m": 0.12954,
            "radial_clearance_m": 7.62e-5,
            "eccentricity_ratio": 0.5,
            "lubricant": "ISOVG32",
            "geometry": "groove",
            "cavitation": True,
        },
    ),
}


THRUST_INPUT: dict[str, Any] = {
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


def _finite_modal(modal: Any) -> bool:
    wn = np.asarray(modal.wn, dtype=float)
    return bool(wn.size and np.all(np.isfinite(wn)))


def _strict_modal(project: Any, service: Any, result: Any, speed_rpm: float) -> dict[str, Any]:
    candidate = deepcopy(project)
    service.apply(candidate, 0, result)
    build = RossModelBuilder(rs).build(candidate, strict=True)
    modal = RossAnalysisBackend(rs).run_modal_build(build, speed_rpm, num_modes=12)
    return {
        "strict_rotor": True,
        "shaft_elements": len(build.rotor.shaft_elements),
        "bearing_elements": len(build.rotor.bearing_elements),
        "modal_finite": _finite_modal(modal),
        "modal_wn_rad_s": [float(value) for value in modal.wn],
    }


def _native_output_payload(native: Any) -> dict[str, Any]:
    inventory = inventory_native_outputs(native)
    adapter = RossBearingNativePlotService()
    diagnostics: list[str] = []
    figures: list[str] = []
    text_outputs: list[str] = []
    kc_available = False

    try:
        kc = adapter.kc_figure(native)
        kc_available = kc is not None
    except NativeRossPlotUnavailable as exc:
        diagnostics.append(f"K/C: {exc}")

    try:
        dimensional = adapter.dimensional_outputs(native, freq_index=0)
        figures = list(dimensional.figures)
        text_outputs = list(dimensional.text_outputs)
        diagnostics.extend(dimensional.diagnostics)
    except NativeRossPlotUnavailable as exc:
        diagnostics.append(f"Dimensional: {exc}")

    mapped = [method.name for method in inventory.methods if method.route != "unmapped"]
    return {
        "inventory": inventory.to_dict(),
        "mapped_methods": mapped,
        "kc_native_figure": kc_available,
        "dimensional_figures": figures,
        "text_outputs": text_outputs,
        "diagnostics": diagnostics,
        "studio_surfaces": ["K/C", "K/C curves", "Dimensional"],
    }


def main() -> int:
    if str(getattr(rs, "__version__", "unknown")) != "2.3.0":
        raise SystemExit(f"ROSS 2.3.0 required, received {getattr(rs, '__version__', 'unknown')}")

    source = load_irdin_project(FIXTURE)
    general_service = BearingStudioService(rs)
    thd_service = THDBearingStudioService(rs)
    thrust_service = ThrustPadStudioService(rs)
    registry = RossCapabilityRegistry(rs)

    models: dict[str, Any] = {}
    gates: dict[str, bool] = {}

    for model, (speed, inputs) in GENERAL_CASES.items():
        result = general_service.calculate(source, 0, model, inputs)
        strict = _strict_modal(source, general_service, result, speed)
        models[model] = {
            "family": "General",
            "output_contract": "K/C only",
            "coefficient_rows": len(result.coefficients),
            "application_class": result.application_class,
            "strict_and_modal": strict,
        }
        gates[f"{model}_kc"] = bool(result.coefficients or np.all(np.isfinite(result.scalar_kc)))
        gates[f"{model}_strict_modal"] = bool(strict["strict_rotor"] and strict["modal_finite"])

    for model, (speed, inputs) in THD_CASES.items():
        result = thd_service.calculate(source, 0, model, inputs)
        native = _native_output_payload(result.native_element)
        strict = _strict_modal(source, thd_service, result, speed)
        models[model] = {
            "family": "THD",
            "output_contract": "K/C + curves + Dimensional",
            "coefficient_rows": len(result.coefficients),
            "application_class": result.application_class,
            "native_outputs": native,
            "strict_and_modal": strict,
        }
        gates[f"{model}_inventory_covered"] = bool(native["inventory"]["fully_covered"])
        gates[f"{model}_kc_native"] = bool(native["kc_native_figure"])
        # SFD is analytical and legitimately exposes fewer dimensional field plots;
        # accessibility means the native result/report surface is present, not that
        # pressure/temperature fields are fabricated by Studio.
        gates[f"{model}_dimensional_surface"] = bool(native["dimensional_figures"] or native["text_outputs"])
        gates[f"{model}_strict_modal"] = bool(strict["strict_rotor"] and strict["modal_finite"])

    thrust = thrust_service.calculate(source, 0, "ThrustPad", THRUST_INPUT)
    thrust_native = _native_output_payload(thrust.native_element)
    thrust_strict = _strict_modal(source, thrust_service, thrust, 90.0)
    models["ThrustPad"] = {
        "family": "THD",
        "output_contract": "Kzz/Czz + curves + Dimensional",
        "axial_coefficient_rows": len(thrust.axial_coefficients),
        "application_class": thrust.application_class,
        "native_outputs": thrust_native,
        "strict_and_modal": thrust_strict,
    }
    gates["ThrustPad_inventory_covered"] = bool(thrust_native["inventory"]["fully_covered"])
    gates["ThrustPad_dimensional_surface"] = bool(thrust_native["dimensional_figures"] or thrust_native["text_outputs"])
    gates["ThrustPad_strict_modal"] = bool(thrust_strict["strict_rotor"] and thrust_strict["modal_finite"])
    gates["ThrustPad_axial_not_lateralized"] = bool(
        thrust.axial_coefficients and not hasattr(thrust, "coefficients")
    )

    amb_status, amb_reason = registry.effective_status("MagneticBearingElement")
    # AMB was outside the 0.15.1 Bearing Native Outputs qualification scope.
    # Its current capability status is reported below, while the dedicated 0.30 gate
    # qualifies MagneticBearingElement, Newmark feedback outputs and ISO sensitivity.
    gates["all_general_kc_only"] = all(
        model["output_contract"] == "K/C only"
        for model in models.values()
        if model["family"] == "General"
    )
    gates["all_thd_native_output_inventory_covered"] = all(
        model["native_outputs"]["inventory"]["fully_covered"]
        for model in models.values()
        if model["family"] == "THD"
    )
    gates["all_bearings_strict_modal"] = all(
        model["strict_and_modal"]["strict_rotor"] and model["strict_and_modal"]["modal_finite"]
        for model in models.values()
    )

    passed = all(bool(value) for value in gates.values())
    payload = {
        "status": "PASS" if passed else "FAIL",
        "ross_version": str(rs.__version__),
        "scope": "ROSS Studio 0.15.1 Bearing Native Outputs Qualification",
        "policy": {
            "General": "calculated K/C only; no fabricated dimensional post-processing",
            "THD": "calculated K/C plus native ROSS curves and dimensional outputs; model-specific unavailable fields remain unavailable",
            "RotorModel": "nominal K/C for all; cached K/C curves only for committed THD; never rerun THD from inspector",
            "AMB": "outside the 0.15.1 pass/fail scope; current registry status is informational and native AMB is qualified by the 0.30 gate",
        },
        "amb": {"status": amb_status.value, "reason": amb_reason},
        "gates": gates,
        "models": models,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
