from __future__ import annotations

import numpy as np
import pytest

from ross_studio.domain import EngineeringError
from ross_studio.multirotor.analysis import ModalRequest, MultiRotorAnalysisService
from ross_studio.multirotor.builder import MultiRotorBuilder
from ross_studio.multirotor.domain import METHOD_QUALIFICATION, MultiRotorMethodStatus
from ross_studio.multirotor.io import load_multirotor_project, save_multirotor_project
from ross_studio.multirotor.qualification import three_shaft_project
from ross_studio.page_registry import PAGE_ROUTES


def test_multirotor_route_is_operational_023():
    spec = PAGE_ROUTES["analysis.multirotor"]; assert spec.implementation_phase == "0.23.0"; assert spec.operational is True


def test_multirotor_three_shaft_strict_native_assembly():
    project = three_shaft_project(); build = MultiRotorBuilder().build(project); assert build.rotor.__class__.__name__ == "MultiRotor"; assert len(build.connection_ratios) == 2; assert all(v > 0 for v in build.connection_ratios); assert {i for i,_ in build.local_to_global_nodes} == {0,1,2}; modal = build.rotor.run_modal(speed=0.0, num_modes=8); assert np.all(np.isfinite(np.asarray(modal.wd, dtype=float)))


def test_multirotor_exact_gear_node_gate():
    project = three_shaft_project(); project.gears[0].position_mm = 99.999
    with pytest.raises(EngineeringError, match="exact ROSS node"): MultiRotorBuilder().build(project)


def test_multirotor_speed_mapping_is_native():
    from ross.multi_rotor.multi_rotor import two_shaft_rotor_example
    rotor = two_shaft_rotor_example(); omega = 100.0; assert rotor.check_speed(rotor.nodes[0], omega) == pytest.approx(omega); assert rotor.check_speed(rotor.driven_nodes[0], omega) == pytest.approx(-rotor.mesh.gear_ratio * omega)


def test_multirotor_blocked_inherited_methods():
    assert METHOD_QUALIFICATION["static"] == MultiRotorMethodStatus.BLOCKED; assert METHOD_QUALIFICATION["ucs"] == MultiRotorMethodStatus.BLOCKED; assert METHOD_QUALIFICATION["level1"] == MultiRotorMethodStatus.BLOCKED; assert METHOD_QUALIFICATION["critical_speed"] == MultiRotorMethodStatus.EXPERIMENTAL
    service = MultiRotorAnalysisService()
    with pytest.raises(EngineeringError, match="not qualified"): service.run_blocked("static")
    with pytest.raises(EngineeringError, match="EXPERIMENTAL"): service.run_blocked("critical_speed")


def test_multirotor_roundtrip(tmp_path):
    project = three_shaft_project(); path = save_multirotor_project(project, tmp_path / "gear_train"); loaded = load_multirotor_project(path); assert loaded.name == project.name; assert [r.name for r in loaded.rotors] == [r.name for r in project.rotors]; assert [(g.name,g.model,g.position_mm) for g in loaded.gears] == [(g.name,g.model,g.position_mm) for g in project.gears]; assert len(loaded.connections) == 2; assert MultiRotorBuilder().build(loaded).rotor.__class__.__name__ == "MultiRotor"


def test_multirotor_modal_service_uses_driving_speed():
    result = MultiRotorAnalysisService().run_modal(three_shaft_project(), ModalRequest(0.0,8)); assert result.kind == "modal"; assert result.metadata["driving_speed_rpm"] == 0.0; assert np.all(np.isfinite(np.asarray(result.native_result.wd, dtype=float)))
