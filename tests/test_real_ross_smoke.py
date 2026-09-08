from pathlib import Path

import pytest

pytest.importorskip("ross")

import numpy as np

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
    UmpFormulation,
)
from ross_frontend.legacy_import import load_irdin_project


CASE = Path(__file__).resolve().parents[1] / "cases" / "OP-W60-500-60Hz-IC611-P3" / "irdin_input.txt"


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


def project_with_ump():
    project = real_project()
    project.ump_regions = [
        UMPRegionSpec(
            start_mm=0.0,
            end_mm=500.0,
            kxx_prime_n_m2=2.0e6,
            kyy_prime_n_m2=2.0e6,
            formulation=UmpFormulation.PHYSICAL_CORRECTED,
            source_unit="N/m²",
            tag="test UMP",
        )
    ]
    return project


@pytest.mark.ross
def test_real_ross_build_modal_and_frequency_response():
    project = real_project()
    build = RossModelBuilder().build(project)
    assert build.rotor.ndof > 0
    assert build.rotor is build.base_rotor
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
def test_real_ross_ump_rotor_has_single_global_negative_stiffness_path():
    build = RossModelBuilder().build(project_with_ump())
    rotor = build.rotor

    assert rotor is not build.base_rotor
    assert type(build.shaft_elements[0]).__name__ == "ShaftElement"
    assert hasattr(rotor, "K_without_ump")
    assert not hasattr(build, "ump_rhs_callback")

    k_without = np.asarray(rotor.K_without_ump(0.0), dtype=float)
    k_ump = np.asarray(build.K_ump, dtype=float)
    k_effective = np.asarray(rotor.K(0.0), dtype=float)
    k_base = np.asarray(build.base_rotor.K(0.0), dtype=float)

    assert k_without.shape == k_ump.shape == k_effective.shape
    assert np.linalg.norm(k_ump) > 0.0
    assert np.allclose(k_without, k_base, rtol=1e-12, atol=1e-9)
    assert np.allclose(k_effective, k_without - k_ump, rtol=1e-12, atol=1e-9)
    assert np.allclose(k_ump, k_ump.T, rtol=1e-12, atol=1e-9)
    assert k_ump[0, 0] > 0.0
    assert k_ump[1, 1] > 0.0
    assert k_ump[2, 2] == pytest.approx(0.0, abs=1e-9)
    assert k_ump[5, 5] == pytest.approx(0.0, abs=1e-9)


@pytest.mark.ross
def test_real_w60_legacy_ump_is_continuous_across_internal_station():
    project = load_irdin_project(CASE)
    build = RossModelBuilder().build(project)

    assert project.ump_regions[0].formulation == UmpFormulation.ROTORDIN_LEGACY_COMPAT
    assert type(build.rotor).__name__ == "UmpRotor"
    assert len(build.ump_contributions) == 2
    assert [(item.start_mm, item.end_mm) for item in build.ump_contributions] == pytest.approx(
        [(918.0, 1275.5), (1275.5, 1633.0)]
    )
    assert all(item.legacy_rotary_term for item in build.ump_contributions)

    # The only PointMass is the historical [Concent] mass. Housing masses live
    # on the native support BearingElements at the link DOFs.
    assert len(build.point_mass_elements) == 1
    front_support = build.bearing_elements[1]
    rear_support = build.bearing_elements[3]
    assert front_support.n == build.support_link_node_by_bearing[0]
    assert rear_support.n == build.support_link_node_by_bearing[1]
    assert np.asarray(front_support.M(0.0))[0, 0] == pytest.approx(175.0)
    assert np.asarray(front_support.M(0.0))[1, 1] == pytest.approx(175.0)
    assert np.asarray(front_support.M(0.0))[2, 2] == pytest.approx(0.0)
    assert np.asarray(rear_support.M(0.0))[0, 0] == pytest.approx(175.0)
    assert np.asarray(rear_support.M(0.0))[1, 1] == pytest.approx(175.0)

    global_mass = np.asarray(build.rotor.M(0.0), dtype=float)
    front_dofs = list(front_support.dof_global_index.values())
    rear_dofs = list(rear_support.dof_global_index.values())
    assert global_mass[front_dofs[0], front_dofs[0]] == pytest.approx(175.0)
    assert global_mass[front_dofs[1], front_dofs[1]] == pytest.approx(175.0)
    assert global_mass[rear_dofs[0], rear_dofs[0]] == pytest.approx(175.0)
    assert global_mass[rear_dofs[1], rear_dofs[1]] == pytest.approx(175.0)

    k_without = np.asarray(build.rotor.K_without_ump(0.0), dtype=float)
    k_ump = np.asarray(build.K_ump, dtype=float)
    assert np.linalg.norm(k_ump) > 0.0
    assert np.allclose(build.rotor.K(0.0), k_without - k_ump, rtol=1e-12, atol=1e-9)


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
