from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import numpy as np
import ross as rs

from ross_studio.bearing_studio_service import BearingStudioService
from ross_studio.legacy_import import load_irdin_project
from ross_studio.ross_backend import RossModelBuilder
from ross_studio.services import EngineeringValidationService


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "src" / "ross_studio" / "resources" / "OP-W60-500-60Hz-IC611-P3.txt"
OUT = ROOT / "artifacts" / "bearing_studio_qualification.json"


def finite_kc(result) -> bool:
    scalar = np.asarray(result.scalar_kc, dtype=float)
    table = np.asarray(
        [[p.kxx, p.kxy, p.kyx, p.kyy, p.cxx, p.cxy, p.cyx, p.cyy] for p in result.coefficients],
        dtype=float,
    ) if result.coefficients else np.empty((0, 8))
    return bool(np.all(np.isfinite(scalar)) and np.all(np.isfinite(table)))


def main() -> int:
    service = BearingStudioService(rs)
    source = load_irdin_project(FIXTURE)

    direct = service.calculate(source, 0, "BearingElement", {"rated_speed_rpm": 3600.0})
    direct_exact = list(direct.coefficients) == source.bearings[0].coefficients

    ball_project = deepcopy(source)
    ball = service.calculate(ball_project, 0, "BallBearingElement", {
        "n_balls": 8,
        "d_balls_m": 0.03,
        "static_load_n": 500.0,
        "contact_angle_rad": float(np.pi / 6.0),
    })
    service.apply(ball_project, 0, ball)
    ball_build = RossModelBuilder(rs).build(ball_project, strict=True)
    ball_link_ok = ball_build.rotor.bearing_elements[0].n_link == 28

    roller_project = deepcopy(source)
    roller = service.calculate(roller_project, 0, "RollerBearingElement", {
        "n_rollers": 10,
        "roller_length_m": 0.025,
        "static_load_n": 1200.0,
        "contact_angle_rad": 0.1,
    })
    service.apply(roller_project, 0, roller)
    roller_build = RossModelBuilder(rs).build(roller_project, strict=True)
    roller_link_ok = roller_build.rotor.bearing_elements[0].n_link == 28

    cylindrical_project = deepcopy(source)
    cylindrical = service.calculate(cylindrical_project, 0, "CylindricalBearing", {
        "speed_rpm": [900.0, 1800.0, 2700.0, 3600.0, 4500.0],
        "weight_n": 525.0,
        "bearing_length_m": 0.03,
        "journal_diameter_m": 0.10,
        "radial_clearance_m": 0.0001,
        "oil_viscosity_pa_s": 0.10,
    })
    applied = service.apply(cylindrical_project, 0, cylindrical)
    validation_errors = [
        issue.message for issue in EngineeringValidationService().validate(cylindrical_project)
        if issue.severity == "error"
    ]
    cylindrical_build = RossModelBuilder(rs).build(cylindrical_project, strict=True)
    cylindrical_link_ok = cylindrical_build.rotor.bearing_elements[0].n_link == 28
    # Prove the equivalent table is executable in a real dynamic ROSS solve.
    modal = cylindrical_build.rotor.run_modal(speed=3600.0 * 2.0 * np.pi / 60.0, num_modes=12)
    modal_finite = bool(np.all(np.isfinite(np.asarray(modal.wd, dtype=float))))

    thd_blocked = True
    try:
        service.calculate(source, 0, "PlainJournal", {})
    except Exception:
        pass
    else:
        thd_blocked = False

    gates = {
        "direct_kc_exact": direct_exact and finite_kc(direct),
        "ball_finite_and_n_link": finite_kc(ball) and ball_link_ok,
        "roller_finite_and_n_link": finite_kc(roller) and roller_link_ok,
        "cylindrical_finite": finite_kc(cylindrical),
        "cylindrical_flexible_support_adapter": (
            cylindrical.source_model == "CylindricalBearing"
            and cylindrical.application_class == "BearingElement"
            and applied.ross_class == "BearingElement"
            and applied.metadata.get("flexible_support_kc_adapter") == 1
            and not validation_errors
            and cylindrical_link_ok
            and modal_finite
        ),
        "thd_remains_gated": thd_blocked,
    }
    passed = all(gates.values())

    def scalar_dict(result):
        names = ("Kxx", "Kxy", "Kyx", "Kyy", "Cxx", "Cxy", "Cyx", "Cyy")
        return dict(zip(names, [float(v) for v in result.scalar_kc]))

    summary = {
        "status": "PASS" if passed else "FAIL",
        "ross_version": getattr(rs, "__version__", "unknown"),
        "gates": gates,
        "models": {
            "BearingElement": {
                "source_rows": len(source.bearings[0].coefficients),
                "result_rows": len(direct.coefficients),
                "rated_or_reference_kc": scalar_dict(direct),
                "note": direct.note,
            },
            "BallBearingElement": {
                "kc": scalar_dict(ball),
                "application_class": ball.application_class,
                "metadata": ball.metadata,
                "note": ball.note,
            },
            "RollerBearingElement": {
                "kc": scalar_dict(roller),
                "application_class": roller.application_class,
                "metadata": roller.metadata,
                "note": roller.note,
            },
            "CylindricalBearing": {
                "speed_rows": len(cylindrical.coefficients),
                "speeds_rpm": [float(p.rpm) for p in cylindrical.coefficients],
                "rated_kc": scalar_dict(cylindrical),
                "application_class": cylindrical.application_class,
                "metadata": cylindrical.metadata,
                "validation_errors": validation_errors,
                "modal_finite_after_apply": modal_finite,
                "note": cylindrical.note,
            },
        },
        "scope_gate": "General / Parametric only. THD and AMB remain disabled until their own qualification tranche.",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
