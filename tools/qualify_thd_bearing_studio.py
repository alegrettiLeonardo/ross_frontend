from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import numpy as np
import ross as rs

from ross_studio.legacy_import import load_irdin_project
from ross_studio.ross_backend import RossModelBuilder
from ross_studio.thd_bearing_service import THDBearingStudioService


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "src" / "ross_studio" / "resources" / "OP-W60-500-60Hz-IC611-P3.txt"
OUT = ROOT / "artifacts" / "thd_bearing_studio_qualification.json"


def coefficients_payload(result):
    return [
        {
            "rpm": float(row.rpm),
            "kxx": float(row.kxx),
            "kxy": float(row.kxy),
            "kyx": float(row.kyx),
            "kyy": float(row.kyy),
            "cxx": float(row.cxx),
            "cxy": float(row.cxy),
            "cyx": float(row.cyx),
            "cyy": float(row.cyy),
        }
        for row in result.coefficients
    ]


def operating_payload(result):
    return [
        {
            "rpm": float(row.rpm),
            "max_pressure_pa": row.max_pressure_pa,
            "max_temperature_c": row.max_temperature_c,
            "min_film_thickness_m": row.min_film_thickness_m,
            "eccentricity_ratio": row.eccentricity_ratio,
            "attitude_angle_rad": row.attitude_angle_rad,
        }
        for row in result.operating_points
    ]


def finite_coefficients(result) -> bool:
    values = np.asarray(
        [[p.kxx, p.kxy, p.kyx, p.kyy, p.cxx, p.cxy, p.cyx, p.cyy] for p in result.coefficients],
        dtype=float,
    )
    return bool(values.size and np.all(np.isfinite(values)))


def main() -> int:
    service = THDBearingStudioService(rs)
    project = load_irdin_project(FIXTURE)

    plain = service.calculate(project, 0, "PlainJournal", {
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
    })
    plain_project = deepcopy(project)
    service.apply(plain_project, 0, plain)
    plain_build = RossModelBuilder(rs).build(plain_project, strict=True)

    tilting = service.calculate(project, 0, "TiltingPad", {
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
    })
    tilting_project = deepcopy(project)
    service.apply(tilting_project, 0, tilting)
    tilting_build = RossModelBuilder(rs).build(tilting_project, strict=True)

    sfd = service.calculate(project, 0, "SqueezeFilmDamper", {
        "speed_rpm": [18600.0, 20000.0, 22000.0],
        "axial_length_m": 0.02286,
        "journal_diameter_m": 0.12954,
        "radial_clearance_m": 7.62e-5,
        "eccentricity_ratio": 0.5,
        "lubricant": "ISOVG32",
        "geometry": "groove",
        "cavitation": True,
    })

    gates = {
        "ross_version_exact": getattr(rs, "__version__", None) == "2.3.0",
        "plain_native_and_finite": type(plain.native_element).__name__ == "PlainJournal" and finite_coefficients(plain),
        "plain_pressure_temperature": (
            plain.operating_points[0].max_pressure_pa is not None
            and plain.operating_points[0].max_pressure_pa > 0.0
            and plain.operating_points[0].max_temperature_c is not None
            and np.isfinite(plain.operating_points[0].max_temperature_c)
        ),
        "plain_flexible_support_apply": plain_build.rotor.bearing_elements[0].n_link == 28,
        "tilting_native_and_finite": type(tilting.native_element).__name__ == "TiltingPad" and finite_coefficients(tilting),
        "tilting_fields": (
            tilting.operating_points[0].max_pressure_pa is not None
            and tilting.operating_points[0].max_pressure_pa >= 0.0
            and tilting.operating_points[0].max_temperature_c is not None
            and np.isfinite(tilting.operating_points[0].max_temperature_c)
        ),
        "tilting_flexible_support_apply": tilting_build.rotor.bearing_elements[0].n_link == 28,
        "sfd_native_and_finite": type(sfd.native_element).__name__ == "SqueezeFilmDamper" and finite_coefficients(sfd),
        "sfd_pressure_and_hmin": all(
            op.max_pressure_pa is not None
            and np.isfinite(op.max_pressure_pa)
            and np.isclose(op.min_film_thickness_m, 3.81e-5)
            for op in sfd.operating_points
        ),
        "thrust_not_silently_lateralized": True,
    }
    try:
        service.calculate(project, 0, "ThrustPad", {})
    except Exception:
        pass
    else:
        gates["thrust_not_silently_lateralized"] = False

    passed = all(gates.values())
    payload = {
        "status": "PASS" if passed else "FAIL",
        "ross_version": getattr(rs, "__version__", "unknown"),
        "scope": "Native ROSS 2.3 lateral THD calculation. ThrustPad remains a separate axial gate.",
        "application_policy": "Cache solved K/C into BearingElement for rotor execution and flexible n_link support; retain native element as field-result evidence.",
        "gates": gates,
        "models": {
            "PlainJournal": {
                "coefficients": coefficients_payload(plain),
                "operating_points": operating_payload(plain),
                "metadata": plain.metadata,
                "note": plain.note,
            },
            "TiltingPad": {
                "coefficients": coefficients_payload(tilting),
                "operating_points": operating_payload(tilting),
                "metadata": tilting.metadata,
                "note": tilting.note,
            },
            "SqueezeFilmDamper": {
                "coefficients": coefficients_payload(sfd),
                "operating_points": operating_payload(sfd),
                "metadata": sfd.metadata,
                "note": sfd.note,
            },
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
