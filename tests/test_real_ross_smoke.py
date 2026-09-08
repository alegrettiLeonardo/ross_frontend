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
