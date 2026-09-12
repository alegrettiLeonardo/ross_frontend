from __future__ import annotations

from copy import deepcopy

import pytest

from ross_studio.bearing_studio_service import BearingStudioService
from ross_studio.domain import (
    AdapterStatus, BearingGroup, BearingSpec, CouplingSpec, EngineeringError,
    MaterialSpec, RotorProject, SealModel, SealSpec, ShaftSection,
)
from ross_studio.models import ProjectModel
from ross_studio.project_io import load_project, save_project
from ross_studio.ross_backend import RossBackend
from ross_studio.services import RossCapabilityRegistry
from ross_studio.time_frequency_analysis import TimeResponseRequest, TimeResponseService
from ross_studio.time_frequency_native import AMB_TIME_PLOT_LABELS, TIME_PLOT_LABELS


def project() -> RotorProject:
    return RotorProject(
        name="native-030",
        materials={"Steel": MaterialSpec()},
        shaft_sections=[ShaftSection(1, 300.0, 40.0, material="Steel", fe_elements=3)],
    )


def amb_spec() -> BearingSpec:
    return BearingSpec(
        name="AMB", position_mm=0.0, group=BearingGroup.AMB, ross_class="MagneticBearingElement",
        metadata={
            "source_model": "MagneticBearingElement",
            "engineering_input": {
                "speed_rpm": [500.0, 1000.0], "g0_m": 1e-3, "i0_a": 1.0, "ag_m2": 1e-4,
                "nw": 200, "alpha_rad": 0.3926990817, "k_amp": 1.0, "k_sense": 1.0,
                "kp_pid": 1500.0, "kd_pid": 10.0, "ki_pid": 100.0, "n_f_rad_s": 10000.0,
                "sensors_axis_rotation_rad": 0.7853981634,
            },
        },
    )


def test_shaft_switches_reach_native_ross() -> None:
    p = project()
    section = p.shaft_sections[0]
    section.shear_effects = False
    section.rotary_inertia = False
    section.gyroscopic = False
    built = RossBackend().build_rotor(p)
    assert all(elm.shear_effects is False for elm in built.rotor.shaft_elements)
    assert all(elm.rotary_inertia is False for elm in built.rotor.shaft_elements)
    assert all(elm.gyroscopic is False for elm in built.rotor.shaft_elements)


def test_native_coupling_replaces_exact_interval() -> None:
    p = project()
    p.couplings.append(CouplingSpec(
        "C1", 100.0, 1.0, 1.0, 0.01, 0.01, length_mm=100.0,
        left_id_kg_m2=0.005, right_id_kg_m2=0.005, kt_x_n_m=1e6, kt_y_n_m=1e6,
    ))
    built = RossBackend().build_rotor(p)
    assert [type(elm).__name__ for elm in built.rotor.shaft_elements] == ["ShaftElement", "CouplingElement", "ShaftElement"]


def test_legacy_single_station_coupling_fails_closed() -> None:
    p = project()
    p.couplings.append(CouplingSpec("legacy", 100.0, 0, 0, 0, 0))
    with pytest.raises(EngineeringError, match="positive length|single-station"):
        RossBackend().build_rotor(p)


def test_direct_seal_preserves_native_model_provenance() -> None:
    p = project()
    p.seals.append(SealSpec("S", 100.0, 1e6, 1e6, 1e3, 1e3, model=SealModel.DIRECT))
    built = RossBackend().build_rotor(p)
    assert any(type(elm).__name__ == "SealElement" for elm in built.rotor.bearing_elements)


def test_amb_is_validated_and_builder_materializes_native_element() -> None:
    status, _reason = RossCapabilityRegistry().effective_status("MagneticBearingElement")
    assert status == AdapterStatus.VALIDATED
    p = project()
    p.bearings.append(amb_spec())
    built = RossBackend().build_rotor(p)
    assert any(type(elm).__name__ == "MagneticBearingElement" for elm in built.rotor.bearing_elements)


def test_bearing_studio_calculates_and_applies_amb() -> None:
    p = project()
    p.bearings.append(BearingSpec("B1", 0.0, kxx=1.0, kyy=1.0))
    inputs = deepcopy(amb_spec().metadata["engineering_input"])
    result = BearingStudioService().calculate(p, 0, "MagneticBearingElement", inputs)
    applied = BearingStudioService().apply(p, 0, result)
    assert result.source_model == "MagneticBearingElement"
    assert applied.group == BearingGroup.AMB
    assert applied.ross_class == "MagneticBearingElement"
    assert applied.metadata["engineering_input"]["g0_m"] == pytest.approx(1e-3)


def test_amb_time_response_rejects_non_newmark_before_integration() -> None:
    p = project()
    p.bearings.append(amb_spec())
    request = TimeResponseRequest(
        speed_start_rpm=1000.0, speed_end_rpm=1000.0, duration_s=0.01, samples=11,
        method="default", include_project_unbalance=False, include_gravity=True,
    )
    with pytest.raises(EngineeringError, match="Active Magnetic Bearings require method='newmark'"):
        TimeResponseService().run(p, request)


def test_amb_time_outputs_extend_the_generic_time_plot_contract() -> None:
    assert set(TIME_PLOT_LABELS) == {"time_1d", "orbit_2d", "orbits_3d", "dfft"}
    assert set(AMB_TIME_PLOT_LABELS) == {"amb_disps", "amb_currents", "amb_forces"}
    assert set(TIME_PLOT_LABELS).isdisjoint(AMB_TIME_PLOT_LABELS)


def test_schema3_round_trip_keeps_native_contracts(tmp_path) -> None:
    p = project()
    p.shaft_sections[0].gyroscopic = False
    p.seals.append(SealSpec("S", 100.0, 1, 2, 3, 4, model=SealModel.HYBRID, metadata={"engineering_input": {"frequency_rpm": [1000.0]}}))
    p.couplings.append(CouplingSpec("C", 100.0, 1, 1, 0.1, 0.1, length_mm=100.0, cr_z_n_m_s_rad=5.0))
    model = ProjectModel.from_engineering(p)
    path = save_project(model, tmp_path / "native.rossproj")
    loaded = load_project(path)
    assert loaded.engineering is not None
    assert loaded.engineering.shaft_sections[0].gyroscopic is False
    assert loaded.engineering.seals[0].model == SealModel.HYBRID
    assert loaded.engineering.couplings[0].length_mm == pytest.approx(100.0)
    assert loaded.engineering.couplings[0].cr_z_n_m_s_rad == pytest.approx(5.0)
