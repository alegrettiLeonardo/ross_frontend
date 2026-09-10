from __future__ import annotations

from copy import deepcopy
from math import pi
from pathlib import Path

import numpy as np
import pytest
import ross as rs

from ross_studio.analysis_backend import RossAnalysisBackend
from ross_studio.legacy_import import load_irdin_project
from ross_studio.ross_backend import RossModelBuilder
from ross_studio.thrust_pad_service import ThrustPadStudioService


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "src" / "ross_studio" / "resources" / "OP-W60-500-60Hz-IC611-P3.txt"


CANONICAL_INPUT = {
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


def test_thrust_pad_matches_pinned_ross_23_reference_and_has_axial_only_contract():
    assert rs.__version__ == "2.3.0"
    project = load_irdin_project(FIXTURE)
    before = deepcopy(project)
    service = ThrustPadStudioService(rs)
    result = service.calculate(project, 0, "ThrustPad", CANONICAL_INPUT)

    assert project == before  # Calculate is preview-only.
    assert result.source_model == "ThrustPad"
    assert result.application_class == "BearingElement"
    assert result.native_element.__class__.__name__ == "ThrustPad"
    assert not hasattr(result, "coefficients")  # Never masquerade Kzz/Czz as lateral K/C.
    assert len(result.axial_coefficients) == 1

    axial = result.axial_coefficients[0]
    # Canonical values are the ROSS v2.3.0 test_thrust_pad reference case.
    assert axial.kzz == pytest.approx(317633126111.6322, rel=0.02)
    assert axial.czz == pytest.approx(10805941381.16573, rel=0.02)
    op = result.operating_points[0]
    assert op.max_pressure_pa == pytest.approx(6957021.42, rel=0.02)
    assert op.max_temperature_c == pytest.approx(70.4, rel=0.02)
    assert op.min_film_thickness_m == pytest.approx(82e-6, rel=0.05)
    assert op.pivot_film_thickness_m == pytest.approx(131e-6, rel=0.05)

    normalized = result.metadata["normalized_input"]
    assert normalized["pad_inner_radius_m"] == pytest.approx(1.15)
    assert normalized["pad_outer_radius_m"] == pytest.approx(1.725)
    assert normalized["pad_pivot_radius_m"] == pytest.approx(1.4425)
    assert normalized["initial_film_thickness_m"] == pytest.approx(200e-6)
    assert normalized["radial_inclination_angle_rad"] == pytest.approx(-2.75e-4)
    assert normalized["circumferential_inclination_angle_rad"] == pytest.approx(-1.70e-5)
    assert result.metadata["ross_api_contract"] == "2.3.0"
    assert result.metadata["solved_axial_kc_cache"] == 1

    omega = 90.0 * 2.0 * pi / 60.0
    native_k = rs.BearingElement.K(result.native_element, omega)
    native_c = rs.BearingElement.C(result.native_element, omega)
    assert result.native_element.dof_mapping() == {"x_0": 0, "y_0": 1, "z_0": 2}
    assert np.allclose(np.asarray(native_k)[:2, :2], 0.0)
    assert np.allclose(np.asarray(native_c)[:2, :2], 0.0)
    assert native_k[2, 2] == pytest.approx(axial.kzz)
    assert native_c[2, 2] == pytest.approx(axial.czz)


def test_thrust_pad_apply_adds_independent_axial_element_and_strict_builder_assembles_only_z():
    project = load_irdin_project(FIXTURE)
    service = ThrustPadStudioService(rs)
    result = service.calculate(project, 0, "ThrustPad", CANONICAL_INPUT)

    baseline = RossModelBuilder(rs).build(project, strict=True)
    candidate = deepcopy(project)
    radial_before = deepcopy(candidate.bearings[0])
    bearing_count = len(candidate.bearings)
    applied = service.apply(candidate, 0, result)

    assert candidate.bearings[0] == radial_before
    assert len(candidate.bearings) == bearing_count + 1
    assert candidate.bearings[-1] is applied
    assert applied.metadata["source_model"] == "ThrustPad"
    assert applied.metadata["application_mode"] == "independent_axial_bearing_same_shaft_node"
    assert applied.metadata["lateral_coefficients_forced_zero"] == 1
    assert applied.coefficients == []
    assert not any(support.bearing_index == len(candidate.bearings) - 1 for support in candidate.supports)

    build = RossModelBuilder(rs).build(candidate, strict=True)
    thrust = next(element for element in build.rotor.bearing_elements if element.tag == applied.name)
    radial = next(element for element in build.rotor.bearing_elements if element.tag == radial_before.name)
    assert thrust.n_link is None
    assert radial.n_link == 28
    assert build.rotor.bearing_elements[2].n_link == 29
    assert len(build.rotor.shaft_elements) == 27

    omega = 90.0 * 2.0 * pi / 60.0
    axial = result.axial_coefficients[0]
    local_k = np.asarray(thrust.K(omega), dtype=float)
    local_c = np.asarray(thrust.C(omega), dtype=float)
    assert local_k[2, 2] == pytest.approx(axial.kzz)
    assert local_c[2, 2] == pytest.approx(axial.czz)
    assert np.allclose(local_k[:2, :], 0.0) and np.allclose(local_k[:, :2], 0.0)
    assert np.allclose(local_c[:2, :], 0.0) and np.allclose(local_c[:, :2], 0.0)

    k0 = np.asarray(baseline.rotor.K(omega), dtype=float)
    k1 = np.asarray(build.rotor.K(omega), dtype=float)
    c0 = np.asarray(baseline.rotor.C(omega), dtype=float)
    c1 = np.asarray(build.rotor.C(omega), dtype=float)
    m0 = np.asarray(baseline.rotor.M(omega), dtype=float)
    m1 = np.asarray(build.rotor.M(omega), dtype=float)
    g0 = np.asarray(baseline.rotor.G(), dtype=float)
    g1 = np.asarray(build.rotor.G(), dtype=float)

    assert k0.shape == k1.shape and c0.shape == c1.shape
    dk = k1 - k0
    dc = c1 - c0
    nz_k = np.argwhere(np.abs(dk) > max(1e-6, abs(axial.kzz) * 1e-10))
    nz_c = np.argwhere(np.abs(dc) > max(1e-6, abs(axial.czz) * 1e-10))
    assert nz_k.shape == (1, 2)
    assert nz_c.shape == (1, 2)
    assert tuple(nz_k[0]) == tuple(nz_c[0])
    assert nz_k[0, 0] == nz_k[0, 1]  # one direct global axial DOF only
    assert dk[tuple(nz_k[0])] == pytest.approx(axial.kzz, rel=1e-10)
    assert dc[tuple(nz_c[0])] == pytest.approx(axial.czz, rel=1e-10)
    assert np.allclose(m1, m0)
    assert np.allclose(g1, g0)

    modal = RossAnalysisBackend(rs).run_modal_build(build, 90.0, num_modes=12)
    assert len(modal.wn) > 0
    assert np.all(np.isfinite(np.asarray(modal.wn, dtype=float)))


def test_builder_blocks_axial_kc_through_undefined_lateral_support_chain():
    project = load_irdin_project(FIXTURE)
    service = ThrustPadStudioService(rs)
    result = service.calculate(project, 0, "ThrustPad", CANONICAL_INPUT)
    candidate = deepcopy(project)
    service.apply(candidate, 0, result)
    thrust_index = len(candidate.bearings) - 1
    candidate.supports[0].bearing_index = thrust_index

    with pytest.raises(Exception, match="explicit axial support Kzz/Czz contract"):
        RossModelBuilder(rs).build(candidate, strict=True)
