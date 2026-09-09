from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import numpy as np
import pytest

from ross_studio.domain import AdapterStatus, BearingGroup
from ross_studio.legacy_import import load_irdin_project
from ross_studio.ross_backend import RossModelBuilder
from ross_studio.services import BearingCatalogService, RossCapabilityRegistry
from ross_studio.thd_bearing_service import THDBearingStudioService


FIXTURE = Path(__file__).parents[1] / "src" / "ross_studio" / "resources" / "OP-W60-500-60Hz-IC611-P3.txt"


def _finite_coefficients(result) -> None:
    values = np.asarray(
        [[p.kxx, p.kxy, p.kyx, p.kyy, p.cxx, p.cxy, p.cyx, p.cyy] for p in result.coefficients],
        dtype=float,
    )
    assert values.size > 0
    assert np.all(np.isfinite(values))


def test_thd_registry_enables_only_qualified_lateral_models() -> None:
    rs = pytest.importorskip("ross")
    registry = RossCapabilityRegistry(rs)
    catalog = BearingCatalogService(registry)
    rows = {row["class"]: row for row in catalog.entries(BearingGroup.THD)}
    assert rows["PlainJournal"]["status"] == AdapterStatus.VALIDATED.value
    assert rows["TiltingPad"]["status"] == AdapterStatus.VALIDATED.value
    assert rows["SqueezeFilmDamper"]["status"] == AdapterStatus.VALIDATED.value
    assert rows["ThrustPad"]["status"] == AdapterStatus.PLANNED.value


def test_plain_journal_runs_native_ross_and_caches_solved_kc() -> None:
    rs = pytest.importorskip("ross")
    project = load_irdin_project(FIXTURE)
    service = THDBearingStudioService(rs)
    result = service.calculate(project, 0, "PlainJournal", {
        "speed_rpm": [900.0],
        "pad_axial_length_m": 0.263144,
        "journal_diameter_m": 0.4,
        "radial_clearance_m": 1.95e-4,
        "n_pads": 2,
        "pad_arc_deg": 176.0,
        "preload": 0.0,
        "oil_supply_temperature_c": 50.0,
        "fxs_load_n": 0.0,
        "fys_load_n": -112814.91,
        "lubricant": "ISOVG32",
        "oil_flow_l_min": 37.86,
        "thermal_type": "adiabatic",
        "total_ex_film": 20,
        "total_ez_film": 10,
        "total_ey_film": 10,
        "total_ey_pad": 10,
    })

    assert result.source_model == "PlainJournal"
    assert result.application_class == "BearingElement"
    assert type(result.native_element).__name__ == "PlainJournal"
    assert len(result.coefficients) == 1
    _finite_coefficients(result)
    assert len(result.operating_points) == 1
    op = result.operating_points[0]
    assert op.rpm == pytest.approx(900.0)
    assert op.max_pressure_pa is None or np.isfinite(op.max_pressure_pa)
    assert op.max_temperature_k is None or np.isfinite(op.max_temperature_k)
    assert op.min_film_thickness_m is None or op.min_film_thickness_m > 0.0
    assert result.metadata["solved_kc_cache"] == 1

    applied_project = deepcopy(project)
    applied = service.apply(applied_project, 0, result)
    assert applied.group == BearingGroup.THD
    assert applied.ross_class == "BearingElement"
    assert applied.metadata["source_model"] == "PlainJournal"
    build = RossModelBuilder(rs).build(applied_project, strict=True)
    assert build.rotor.bearing_elements[0].n_link == 28


def test_tilting_pad_runs_native_ross_adiabatic_solution() -> None:
    rs = pytest.importorskip("ross")
    project = load_irdin_project(FIXTURE)
    service = THDBearingStudioService(rs)
    result = service.calculate(project, 0, "TiltingPad", {
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
        "oil_flow_l_min": 10.0,
        "fxs_load_n": 884.05,
        "fys_load_n": -2670.4,
        "thermal_type": "adiabatic",
        "total_ex_film": 20,
        "total_ez_film": 10,
        "total_ey_film": 10,
        "total_ey_pad": 10,
    })

    assert result.source_model == "TiltingPad"
    assert type(result.native_element).__name__ == "TiltingPad"
    assert len(result.coefficients) == 1
    _finite_coefficients(result)
    op = result.operating_points[0]
    assert op.max_pressure_pa is None or op.max_pressure_pa >= 0.0
    assert op.max_temperature_k is None or op.max_temperature_k > 0.0
    assert op.eccentricity_ratio is None or 0.0 <= op.eccentricity_ratio < 1.0


def test_squeeze_film_damper_runs_native_ross_and_has_exact_hmin() -> None:
    rs = pytest.importorskip("ross")
    project = load_irdin_project(FIXTURE)
    service = THDBearingStudioService(rs)
    result = service.calculate(project, 0, "SqueezeFilmDamper", {
        "speed_rpm": [18600.0, 20000.0, 22000.0],
        "axial_length_m": 0.02286,
        "journal_diameter_m": 0.12954,
        "radial_clearance_m": 7.62e-5,
        "eccentricity_ratio": 0.5,
        "lubricant": "ISOVG32",
        "geometry": "groove",
        "cavitation": True,
    })

    assert result.source_model == "SqueezeFilmDamper"
    assert type(result.native_element).__name__ == "SqueezeFilmDamper"
    assert [p.rpm for p in result.coefficients] == [18600.0, 20000.0, 22000.0]
    _finite_coefficients(result)
    for op in result.operating_points:
        assert op.max_pressure_pa is None or np.isfinite(op.max_pressure_pa)
        assert op.min_film_thickness_m == pytest.approx(3.81e-5)


def test_thrust_pad_and_amb_are_not_silently_reduced_to_lateral_kc() -> None:
    project = load_irdin_project(FIXTURE)
    service = THDBearingStudioService()
    for ross_class in ("ThrustPad", "MagneticBearingElement"):
        with pytest.raises(Exception, match="independent scientific gates"):
            service.calculate(project, 0, ross_class, {})
