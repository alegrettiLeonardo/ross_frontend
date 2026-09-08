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
def test_real_w60_legacy_ump_supports_and_point_mass_are_matrix_equivalent():
    project = load_irdin_project(CASE)
    build = RossModelBuilder().build(project)

    assert project.ump_regions[0].formulation == UmpFormulation.ROTORDIN_LEGACY_COMPAT
    assert type(build.rotor).__name__ == "UmpRotor"
    assert len(build.ump_contributions) == 2
    assert [(item.start_mm, item.end_mm) for item in build.ump_contributions] == pytest.approx(
        [(918.0, 1275.5), (1275.5, 1633.0)]
    )
    assert all(item.legacy_rotary_term for item in build.ump_contributions)

    # The historical 34 kg [Concent] item is carried by a zero-inertia native
    # DiskElement because ROSS 2.3.0 cannot position PointMass at shaft-only
    # stations. Its local mass matrix is exactly the intended translational mass.
    assert len(build.point_mass_elements) == 1
    carrier = build.point_mass_elements[0]
    assert type(carrier).__name__ == "DiskElement"
    carrier_m = np.asarray(carrier.M(), dtype=float)
    assert np.diag(carrier_m)[:3] == pytest.approx([34.0, 34.0, 34.0])
    assert np.diag(carrier_m)[3:] == pytest.approx([0.0, 0.0, 0.0])
    assert np.allclose(carrier.G(), np.zeros((6, 6)), atol=1e-12)

    front_support = build.bearing_elements[1]
    rear_support = build.bearing_elements[3]
    assert type(front_support).__name__ == "RossFlexibleSupportElement"
    assert type(rear_support).__name__ == "RossFlexibleSupportElement"
    assert front_support.n == build.node_by_position_mm[467.8]
    assert rear_support.n == build.node_by_position_mm[2202.2]
    assert front_support.n_link == build.support_link_node_by_bearing[0]
    assert rear_support.n_link == build.support_link_node_by_bearing[1]

    # Support-to-ground matrices must act only on housing/link DOFs. The upper
    # rotor block and cross blocks are identically zero.
    front_m = np.asarray(front_support.M(0.0), dtype=float)
    front_k = np.asarray(front_support.K(0.0), dtype=float)
    front_c = np.asarray(front_support.C(0.0), dtype=float)
    for matrix in (front_m, front_k, front_c):
        assert matrix.shape == (6, 6)
        assert np.allclose(matrix[:3, :], 0.0, atol=1e-12)
        assert np.allclose(matrix[:, :3], 0.0, atol=1e-12)

    assert np.diag(front_m)[3:] == pytest.approx([175.0, 175.0, 0.0])
    assert front_k[3, 3] == pytest.approx(project.supports[0].kxx)
    assert front_k[4, 4] == pytest.approx(project.supports[0].kzz)
    assert front_c[3, 3] == pytest.approx(project.supports[0].cxx)
    assert front_c[4, 4] == pytest.approx(project.supports[0].czz)

    global_mass = np.asarray(build.rotor.M(0.0), dtype=float)
    front_dofs = list(front_support.dof_global_index.values())
    rear_dofs = list(rear_support.dof_global_index.values())
    assert len(front_dofs) == 6
    assert len(rear_dofs) == 6
    assert global_mass[front_dofs[3], front_dofs[3]] == pytest.approx(175.0)
    assert global_mass[front_dofs[4], front_dofs[4]] == pytest.approx(175.0)
    assert global_mass[rear_dofs[3], rear_dofs[3]] == pytest.approx(175.0)
    assert global_mass[rear_dofs[4], rear_dofs[4]] == pytest.approx(175.0)

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
