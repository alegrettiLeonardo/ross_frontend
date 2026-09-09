from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import numpy as np
import pytest

from ross_studio.bearing_studio_service import BearingStudioService
from ross_studio.domain import BearingCoefficientPoint
from ross_studio.legacy_import import load_irdin_project
from ross_studio.ross_backend import RossModelBuilder
from ross_studio.services import EngineeringValidationService


FIXTURE = Path(__file__).parents[1] / "src" / "ross_studio" / "resources" / "OP-W60-500-60Hz-IC611-P3.txt"


def test_direct_kc_table_is_preserved_exactly() -> None:
    project = load_irdin_project(FIXTURE)
    service = BearingStudioService()
    before = deepcopy(project.bearings[0].coefficients)
    result = service.calculate(project, 0, "BearingElement")

    assert result.source_model == "BearingElement"
    assert result.application_class == "BearingElement"
    assert list(result.coefficients) == before
    assert result.metadata["input_mode"] == "speed-dependent K/C table"

    service.apply(project, 0, result)
    assert project.bearings[0].coefficients == before


def test_direct_kc_rejects_unsorted_speed_rows() -> None:
    project = load_irdin_project(FIXTURE)
    service = BearingStudioService()
    p = project.bearings[0].coefficients[0]
    rows = [
        p,
        BearingCoefficientPoint(800.0, p.kxx, p.kxy, p.kyx, p.kyy, p.cxx, p.cxy, p.cyx, p.cyy),
    ]
    with pytest.raises(Exception, match="strictly increasing"):
        service.calculate(project, 0, "BearingElement", {"coefficients": rows})


def test_ball_bearing_calculation_matches_ross_element() -> None:
    rs = pytest.importorskip("ross")
    project = load_irdin_project(FIXTURE)
    service = BearingStudioService(rs)
    inputs = {
        "n_balls": 8,
        "d_balls_m": 0.03,
        "static_load_n": 500.0,
        "contact_angle_rad": np.pi / 6.0,
    }
    result = service.calculate(project, 0, "BallBearingElement", inputs)
    direct = rs.BallBearingElement(n=0, n_balls=8, d_balls=0.03, fs=500.0, alpha=np.pi / 6.0)
    k = np.asarray(direct.K(0.0), dtype=float)
    c = np.asarray(direct.C(0.0), dtype=float)

    assert result.application_class == "BallBearingElement"
    assert result.coefficients == ()
    assert result.scalar_kc == pytest.approx((k[0,0], k[0,1], k[1,0], k[1,1], c[0,0], c[0,1], c[1,0], c[1,1]))

    applied = service.apply(project, 0, result)
    assert applied.ross_class == "BallBearingElement"
    assert applied.metadata["n_balls"] == 8
    # Native BallBearingElement supports n_link, so OP-W60 flexible support remains valid.
    build = RossModelBuilder(rs).build(project, strict=True)
    assert build.rotor.bearing_elements[0].n_link == 28


def test_roller_bearing_calculation_matches_ross_element() -> None:
    rs = pytest.importorskip("ross")
    project = load_irdin_project(FIXTURE)
    service = BearingStudioService(rs)
    inputs = {
        "n_rollers": 10,
        "roller_length_m": 0.025,
        "static_load_n": 1200.0,
        "contact_angle_rad": 0.1,
    }
    result = service.calculate(project, 0, "RollerBearingElement", inputs)
    direct = rs.RollerBearingElement(n=0, n_rollers=10, l_rollers=0.025, fs=1200.0, alpha=0.1)
    k = np.asarray(direct.K(0.0), dtype=float)
    c = np.asarray(direct.C(0.0), dtype=float)
    assert result.scalar_kc == pytest.approx((k[0,0], k[0,1], k[1,0], k[1,1], c[0,0], c[0,1], c[1,0], c[1,1]))


def test_cylindrical_calculation_generates_finite_speed_dependent_kc() -> None:
    rs = pytest.importorskip("ross")
    project = load_irdin_project(FIXTURE)
    service = BearingStudioService(rs)
    result = service.calculate(
        project,
        0,
        "CylindricalBearing",
        {
            "speed_rpm": [900.0, 1800.0, 3600.0, 4500.0],
            "weight_n": 525.0,
            "bearing_length_m": 0.03,
            "journal_diameter_m": 0.10,
            "radial_clearance_m": 0.0001,
            "oil_viscosity_pa_s": 0.10,
        },
    )

    assert result.source_model == "CylindricalBearing"
    # OP-W60 bearing has a flexible support; the calculated hydrodynamic K/C is
    # therefore applied via BearingElement because ROSS 2.3 CylindricalBearing has no n_link.
    assert result.application_class == "BearingElement"
    assert len(result.coefficients) == 4
    assert [p.rpm for p in result.coefficients] == [900.0, 1800.0, 3600.0, 4500.0]
    values = np.array([
        [p.kxx, p.kxy, p.kyx, p.kyy, p.cxx, p.cxy, p.cyx, p.cyy]
        for p in result.coefficients
    ])
    assert np.all(np.isfinite(values))

    applied = service.apply(project, 0, result)
    assert applied.ross_class == "BearingElement"
    assert applied.metadata["source_model"] == "CylindricalBearing"
    assert applied.metadata["flexible_support_kc_adapter"] == 1
    assert not any(issue.severity == "error" for issue in EngineeringValidationService().validate(project))
    build = RossModelBuilder(rs).build(project, strict=True)
    assert build.rotor.bearing_elements[0].n_link == 28


def test_thd_and_amb_are_not_silently_enabled_by_general_service() -> None:
    project = load_irdin_project(FIXTURE)
    service = BearingStudioService()
    for ross_class in ("PlainJournal", "TiltingPad", "ThrustPad", "SqueezeFilmDamper", "MagneticBearingElement"):
        with pytest.raises(Exception, match="separately gated"):
            service.calculate(project, 0, ross_class, {})
