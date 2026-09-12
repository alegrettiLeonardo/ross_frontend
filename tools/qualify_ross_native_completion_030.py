from __future__ import annotations

# Final full-suite gate: tests.yml qualifies the aligned 0.30 branch HEAD before PR creation.

import inspect
import numpy as np
import ross as rs

from ross_studio.amb_analysis import AMBSensitivityRequest
from ross_studio.domain import (
    BearingGroup, BearingSpec, CouplingSpec, MaterialSpec, RotorProject, SealModel, SealSpec, ShaftSection,
)
from ross_studio.ross_backend import RossBackend
from ross_studio.seal_studio_service import SealStudioService


def base_project(*, fe_elements: int = 3) -> RotorProject:
    return RotorProject(
        name="qualification-030",
        materials={"Steel": MaterialSpec()},
        shaft_sections=[ShaftSection(1, 300.0, 40.0, material="Steel", fe_elements=fe_elements)],
    )


def qualify_shaft_flags() -> None:
    project = base_project(fe_elements=1)
    project.shaft_sections[0].shear_effects = False
    project.shaft_sections[0].rotary_inertia = False
    project.shaft_sections[0].gyroscopic = False
    built = RossBackend().build_rotor(project)
    elm = built.rotor.shaft_elements[0]
    assert elm.shear_effects is False
    assert elm.rotary_inertia is False
    assert elm.gyroscopic is False


def qualify_coupling() -> None:
    project = base_project(fe_elements=3)
    project.couplings.append(CouplingSpec(
        name="C1", position_mm=100.0, length_mm=100.0,
        left_mass_kg=1.0, right_mass_kg=1.0,
        left_ip_kg_m2=0.01, right_ip_kg_m2=0.01,
        left_id_kg_m2=0.005, right_id_kg_m2=0.005,
        kt_x_n_m=1e7, kt_y_n_m=1e7, kt_z_n_m=1e7,
        kr_x_n_m_rad=1e5, kr_y_n_m_rad=1e5, kr_z_n_m_rad=1e5,
        ct_x_n_s_m=100.0, ct_y_n_s_m=100.0, ct_z_n_s_m=100.0,
        cr_x_n_m_s_rad=10.0, cr_y_n_m_s_rad=10.0, cr_z_n_m_s_rad=10.0,
        od_mm=60.0,
    ))
    built = RossBackend().build_rotor(project)
    classes = [type(elm).__name__ for elm in built.rotor.shaft_elements]
    assert classes == ["ShaftElement", "CouplingElement", "ShaftElement"], classes
    coupling = built.rotor.shaft_elements[1]
    assert coupling.n_l == 1 and coupling.n_r == 2


def qualify_seals() -> None:
    project = base_project(fe_elements=2)
    project.seals.append(SealSpec("S1", 150.0, 1e6, 1.1e6, 1e3, 1.2e3, model=SealModel.DIRECT))
    built = RossBackend().build_rotor(project)
    assert any(type(elm).__name__ == "SealElement" for elm in built.rotor.bearing_elements)
    for module, name in (
        ("ross.seals.labyrinth_seal", "LabyrinthSeal"),
        ("ross.seals.holepattern_seal", "HolePatternSeal"),
        ("ross.seals.hybrid_seal", "HybridSeal"),
    ):
        cls = getattr(__import__(module, fromlist=[name]), name)
        assert "frequency" in inspect.signature(cls).parameters
    assert hasattr(SealStudioService(), "calculate")


def qualify_amb() -> None:
    project = base_project(fe_elements=1)
    project.bearings.append(BearingSpec(
        name="AMB-1", position_mm=0.0, ross_class="MagneticBearingElement", group=BearingGroup.AMB,
        metadata={
            "source_model": "MagneticBearingElement",
            "engineering_input": {
                "speed_rpm": [500.0, 1000.0, 3000.0], "g0_m": 1e-3, "i0_a": 1.0,
                "ag_m2": 1e-4, "nw": 200, "alpha_rad": np.pi / 8, "k_amp": 1.0,
                "k_sense": 1.0, "kp_pid": 1500.0, "kd_pid": 10.0, "ki_pid": 100.0,
                "n_f_rad_s": 10000.0, "sensors_axis_rotation_rad": np.pi / 4,
            },
        },
    ))
    built = RossBackend().build_rotor(project)
    assert any(type(elm).__name__ == "MagneticBearingElement" for elm in built.rotor.bearing_elements)
    AMBSensitivityRequest(speed_rpm=0.0, t_max_s=1.0, dt_s=0.01).validate()

    rotor = rs.rotor_amb_example()
    t = np.arange(0.0, 0.011, 0.001)
    force = np.zeros((len(t), rotor.ndof))
    result = rotor.run_time_response(100.0, force, t, method="newmark")
    assert hasattr(result, "plot_amb_currents")
    assert hasattr(result, "plot_amb_forces")
    assert hasattr(result, "plot_amb_disps")


def qualify_fault_api() -> None:
    for name in ("run_misalignment", "run_rubbing", "run_crack", "run_amb_sensitivity"):
        assert hasattr(rs.Rotor, name), name
    assert "coupling" in inspect.signature(rs.Rotor.run_misalignment).parameters
    assert "depth_ratio" in inspect.signature(rs.Rotor.run_crack).parameters


if __name__ == "__main__":
    qualify_shaft_flags()
    qualify_coupling()
    qualify_seals()
    qualify_amb()
    qualify_fault_api()
    print("ROSS Studio 0.30 native ROSS completion qualification: PASS")