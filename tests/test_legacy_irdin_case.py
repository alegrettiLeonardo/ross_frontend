from pathlib import Path

import pytest

from ross_frontend.backends.ross.builder import RossModelBuilder
from ross_frontend.domain import UmpFormulation
from ross_frontend.legacy_import import LegacyImportError, load_irdin_project
from fakes import FakeDiskElement, FakePointMass, FakeRoss, FakeShaftElement


CASE = Path(__file__).resolve().parents[1] / "cases" / "OP-W60-500-60Hz-IC611-P3" / "irdin_input.txt"


def test_w60_case_imports_without_losing_legacy_physics():
    project = load_irdin_project(CASE)

    assert project.reference == "OP"
    assert project.metadata["component"] == "W60-500-60Hz-IC611-P3"
    assert project.metadata["rotor_speed_rpm"] == pytest.approx(3600.0)
    assert len(project.shaft) == 15
    assert project.shaft_length_mm == pytest.approx(2555.2)

    assert len(project.disks) == 4
    assert [d.position_mm for d in project.disks] == pytest.approx([737.5, 1275.5, 1932.5, 2550.2])
    assert project.disks[1].mass_kg == pytest.approx(723.19)
    assert project.disks[1].diametral_inertia_kg_m2 == pytest.approx(43.39742658333333)
    assert project.disks[1].polar_inertia_kg_m2 == pytest.approx(25.176051875)

    assert len(project.ump_regions) == 1
    ump = project.ump_regions[0]
    assert ump.start_mm == pytest.approx(918.0)
    assert ump.end_mm == pytest.approx(1633.0)
    assert ump.source_value == pytest.approx(1.002)
    assert ump.source_unit == "legacy_unknown"
    assert ump.solver_interpretation == "N/m²"
    assert ump.formulation == UmpFormulation.ROTORDIN_LEGACY_COMPAT
    assert ump.kxx_prime_n_m2 == pytest.approx(1.002)
    assert ump.kyy_prime_n_m2 == pytest.approx(1.002)

    audit = project.metadata["legacy_import"]["ump_audit"][0]
    assert audit["mass_row"] == 2
    assert audit["formulation"] == "rotordin_legacy_compat"
    assert audit["undefined_region_pointer_bug_emulated"] is False
    assert audit["mkb_contamination_bug_emulated"] is False

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
    assert any("legacy_unknown" in warning and "fail-closed" in warning for warning in warnings)


def test_w60_supports_and_ump_build_as_native_ross_link_topology():
    project = load_irdin_project(CASE)
    build = RossModelBuilder(FakeRoss()).build(project)

    assert set(build.support_link_node_by_bearing) == {0, 1}
    assert len(build.bearing_elements) == 4
    assert len(build.point_mass_elements) == 1
    assert len(build.support_mass_elements) == 2

    front_link = build.support_link_node_by_bearing[0]
    rear_link = build.support_link_node_by_bearing[1]
    rotor_front = build.bearing_elements[0].kwargs
    support_front = build.bearing_elements[1].kwargs
    rotor_rear = build.bearing_elements[2].kwargs
    support_rear = build.bearing_elements[3].kwargs

    # Canonical ROSS pattern: rotor bearing points to n_link; ground support and
    # housing PointMass both live at that link node.
    assert rotor_front["n"] == build.node_by_position_mm[467.8]
    assert rotor_front["n_link"] == front_link
    assert rotor_rear["n"] == build.node_by_position_mm[2202.2]
    assert rotor_rear["n_link"] == rear_link
    assert support_front["n"] == front_link
    assert support_rear["n"] == rear_link
    assert support_front["kxx"] == pytest.approx(43.68e7)
    assert support_front["kyy"] == pytest.approx(90.34e7)
    assert "kzz" not in support_front

    front_mass = build.support_mass_elements[0]
    rear_mass = build.support_mass_elements[1]
    assert type(front_mass) is FakePointMass
    assert type(rear_mass) is FakePointMass
    assert front_mass.kwargs["n"] == front_link
    assert rear_mass.kwargs["n"] == rear_link
    assert front_mass.kwargs["mx"] == pytest.approx(175.0)
    assert front_mass.kwargs["my"] == pytest.approx(175.0)
    assert front_mass.kwargs["mz"] == pytest.approx(175.0)
    assert rear_mass.kwargs["mx"] == pytest.approx(175.0)
    assert rear_mass.kwargs["my"] == pytest.approx(175.0)
    assert rear_mass.kwargs["mz"] == pytest.approx(175.0)

    # ROSS creates x/y/z translations for every n_link. The legacy support is
    # lateral-only, so mz is a positive numerical completion of an otherwise
    # decoupled axial DOF; it is not a new lateral RotorDin parameter.

    # Shaft-only [Concent] mass is a zero-inertia disk carrier internally but
    # stays separately classified as a point mass in RossBuild/domain output.
    carrier = build.point_mass_elements[0]
    assert type(carrier) is FakeDiskElement
    assert carrier.kwargs["n"] == build.node_by_position_mm[105.0]
    assert carrier.kwargs["m"] == pytest.approx(34.0)
    assert carrier.kwargs["Id"] == pytest.approx(0.0)
    assert carrier.kwargs["Ip"] == pytest.approx(0.0)
    assert len(build.rotor.disk_elements) == 5
    assert len(build.rotor.point_mass_elements) == 2

    assert 918.0 in build.node_by_position_mm
    assert 1275.5 in build.node_by_position_mm
    assert 1633.0 in build.node_by_position_mm
    assert all(type(element) is FakeShaftElement for element in build.shaft_elements)
    assert build.base_rotor is not build.rotor
    assert build.K_ump is not None
    assert build.ump_contributions
    active_spans = [(item.start_mm, item.end_mm) for item in build.ump_contributions]
    assert active_spans == pytest.approx([(918.0, 1275.5), (1275.5, 1633.0)])
    assert all(item.formulation == "rotordin_legacy_compat" for item in build.ump_contributions)
    assert all(item.legacy_rotary_term for item in build.ump_contributions)
    assert len({element.kwargs["tag"] for element in build.shaft_elements}) == len(build.shaft_elements)


def test_w60_physical_corrected_requires_explicit_source_unit():
    with pytest.raises(LegacyImportError, match="cannot be imported"):
        load_irdin_project(
            CASE,
            ump_formulation=UmpFormulation.PHYSICAL_CORRECTED,
        )

    project = load_irdin_project(
        CASE,
        ump_source_unit="N/m2",
        ump_formulation=UmpFormulation.PHYSICAL_CORRECTED,
    )
    ump = project.ump_regions[0]
    assert ump.formulation == UmpFormulation.PHYSICAL_CORRECTED
    assert ump.source_unit == "N/m²"
    assert ump.kxx_prime_n_m2 == pytest.approx(1.002)
