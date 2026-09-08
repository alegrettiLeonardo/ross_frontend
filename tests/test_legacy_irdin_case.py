from pathlib import Path

import pytest

from ross_frontend.backends.ross.builder import RossModelBuilder
from ross_frontend.legacy_import import load_irdin_project
from fakes import FakeRoss


CASE = Path(__file__).resolve().parents[1] / "cases" / "OP-W60-500-60Hz-IC611-P3" / "irdin_input.txt"


def test_w60_case_imports_without_losing_legacy_physics():
    project = load_irdin_project(CASE)

    assert project.reference == "OP"
    assert project.metadata["component"] == "W60-500-60Hz-IC611-P3"
    assert project.metadata["rotor_speed_rpm"] == pytest.approx(3600.0)
    assert len(project.shaft) == 15
    assert project.shaft_length_mm == pytest.approx(2555.2)

    # RotorDin [Massas] rows are converted to rigid disks using the exact
    # predad.f mmmidkf/smindkf inertia equations.
    assert len(project.disks) == 4
    assert [d.position_mm for d in project.disks] == pytest.approx([737.5, 1275.5, 1932.5, 2550.2])
    assert project.disks[1].mass_kg == pytest.approx(723.19)
    assert project.disks[1].diametral_inertia_kg_m2 == pytest.approx(43.39742658333333)
    assert project.disks[1].polar_inertia_kg_m2 == pytest.approx(25.176051875)

    assert len(project.bearings) == 2
    front, rear = project.bearings
    assert front.position_mm == pytest.approx(467.8)
    assert rear.position_mm == pytest.approx(2202.2)
    assert len(front.frequency_rpm) == 11
    assert front.frequency_rpm[0] == pytest.approx(900.0)
    assert front.kxx[0] == pytest.approx(1.66e8)
    assert front.kxz[0] == pytest.approx(-9.02e7)
    assert front.kzz[0] == pytest.approx(-5.08e8)
    assert front.kzx[0] == pytest.approx(1.05e9)

    assert len(project.unbalances) == 2
    assert project.unbalances[0].position_mm == pytest.approx(918.0)
    assert project.unbalances[0].magnitude_g_mm == pytest.approx(4581.2)
    assert len(project.probes) == 4
    assert {p.position_mm for p in project.probes} == {467.8, 2202.2}
    assert len(project.point_masses) == 1
    assert project.point_masses[0].position_mm == pytest.approx(105.0)
    assert project.point_masses[0].mass_kg == pytest.approx(34.0)

    assert len(project.supports) == 2
    assert project.supports[0].mass_kg == pytest.approx(175.0)
    assert project.supports[0].kxx == pytest.approx(43.68e7)
    assert project.supports[0].kzz == pytest.approx(90.34e7)

    warnings = project.metadata["legacy_import"]["warnings"]
    assert any("UMP" in warning for warning in warnings)


def test_w60_supports_build_as_series_n_link_housing_nodes():
    project = load_irdin_project(CASE)
    build = RossModelBuilder(FakeRoss()).build(project)

    assert set(build.support_link_node_by_bearing) == {0, 1}
    assert len(build.bearing_elements) == 4  # two rotor bearings + two support-to-ground elements
    assert len(build.point_mass_elements) == 3  # 34 kg concentrated + two 175 kg housings

    front_link = build.support_link_node_by_bearing[0]
    rear_link = build.support_link_node_by_bearing[1]
    rotor_front = build.bearing_elements[0].kwargs
    support_front = build.bearing_elements[1].kwargs
    rotor_rear = build.bearing_elements[2].kwargs
    support_rear = build.bearing_elements[3].kwargs

    assert rotor_front["n_link"] == front_link
    assert rotor_rear["n_link"] == rear_link
    assert support_front["n"] == front_link
    assert support_rear["n"] == rear_link
    # RotorDin lateral x/z support stiffness is explicitly mapped to ROSS x/y.
    assert support_front["kxx"] == pytest.approx(43.68e7)
    assert support_front["kyy"] == pytest.approx(90.34e7)
    assert "kzz" not in support_front
