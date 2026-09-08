import numpy as np
import pytest

pytest.importorskip("ross")

from ross_frontend.backends.coordinates import rpm_to_rad_s
from ross_frontend.backends.ross.bearing_calculator import RossBearingCalculator
from ross_frontend.backends.ross.builder import RossModelBuilder
from ross_frontend.backends.ross.response_calculator import FrequencyResponseRequest, RossResponseCalculator
from ross_frontend.domain import (
    BallBearingSpec,
    CoefficientBearingSpec,
    DiskSpec,
    MaterialSpec,
    RotorProject,
    ShaftSectionSpec,
    UMPRegionSpec,
)


def real_project():
    steel = MaterialSpec(name="AISI 4140")
    return RotorProject(
        reference="real-ross-smoke",
        materials=[steel],
        shaft=[
            ShaftSectionSpec(250.0, 50.0, material=steel.name),
            ShaftSectionSpec(250.0, 60.0, material=steel.name),
        ],
        disks=[DiskSpec(250.0, 10.0, 0.05, 0.10)],
        bearings=[
            CoefficientBearingSpec(0.0, 1e7, 1e7, 1e4, 1e4),
            CoefficientBearingSpec(500.0, 1e7, 1e7, 1e4, 1e4),
        ],
    )


@pytest.mark.ross
def test_real_ross_build_modal_and_frequency_response():
    project = real_project()
    build = RossModelBuilder().build(project)
    assert build.rotor.ndof > 0
    modal = build.rotor.run_modal(speed=rpm_to_rad_s(1800.0), num_modes=4)
    assert len(modal.wd) >= 2

    response = RossResponseCalculator().frequency_response(
        project,
        FrequencyResponseRequest(0.0, 3600.0, points=5, input_dof=0, output_dof=0),
    )
    assert response.kind == "frequency_response"
    assert len(response.curves[0].x) == 5
    assert len(response.curves[0].magnitude) == 5


@pytest.mark.ross
def test_real_ross_linearized_ump_reduces_global_radial_stiffness():
    baseline = real_project()
    with_ump = real_project()
    with_ump.ump_regions = [
        UMPRegionSpec(
            start_mm=0.0,
            end_mm=500.0,
            stiffness_per_length_n_m2=2.0e6,
            tag="test UMP",
        )
    ]

    base_build = RossModelBuilder().build(baseline)
    ump_build = RossModelBuilder().build(with_ump)
    k0 = np.asarray(base_build.rotor.K(0.0), dtype=float)
    k1 = np.asarray(ump_build.rotor.K(0.0), dtype=float)
    delta = k0 - k1

    assert ump_build.ump_shaft_elements
    assert k0.shape == k1.shape
    assert np.linalg.norm(delta) > 0.0
    assert np.allclose(delta, delta.T, rtol=1e-10, atol=1e-8)
    # UMP is destabilizing: it removes positive radial stiffness.
    assert delta[0, 0] > 0.0
    assert delta[1, 1] > 0.0
    # It must not create axial/torsional electromagnetic stiffness.
    assert delta[2, 2] == pytest.approx(0.0, abs=1e-8)
    assert delta[5, 5] == pytest.approx(0.0, abs=1e-8)


@pytest.mark.ross
def test_real_ross_ball_bearing_coefficients_are_extracted():
    result = RossBearingCalculator().calculate(
        BallBearingSpec(
            position_mm=0.0,
            n_balls=8,
            ball_diameter_mm=12.0,
            static_load_n=5000.0,
            contact_angle_deg=0.0,
        )
    )
    assert len(result.coefficients) == 1
    assert result.coefficients[0].kxx > 0
    assert result.coefficients[0].kyy > 0
