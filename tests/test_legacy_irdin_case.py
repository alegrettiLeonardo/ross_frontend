from pathlib import Path

import pytest

from ross_frontend.backends.ross.builder import RossModelBuilder
from ross_frontend.domain import UmpFormulation
from ross_frontend.legacy_import import LegacyImportError, load_irdin_project
from fakes import FakeDiskElement, FakeRoss, FakeShaftElement


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


def test_w60_supports_and_ump_build_as_global_rotor_stiffness_extension():
    project = load_irdin_project(CASE)
    build = RossModelBuilder(FakeRoss()).build(project)

    assert set(build.support_link_node_by_bearing) == {0, 1}
    assert len(build.bearing_elements) == 4
    assert len(build.point_mass_elements) == 1

    front_link = build.support_link_node_by_bearing[0]
    rear_link = build.support_link_node_by_bearing[1]
    front_shaft_node = build.node_by_position_mm[467.8]
    rear_shaft_node = build.node_by_position_mm[2202.2]
    rotor_front = build.bearing_elements[0].kwargs
    support_front = build.bearing_elements[1].kwargs
    rotor_rear = build.bearing_elements[2].kwargs
    support_rear = build.bearing_elements[3].kwargs

    # Both support elements retain a valid physical shaft node as n; the housing
    # exists exclusively as n_link. Their overridden matrices act only on the
    # lower-right link block.
    assert rotor_front["n"] == front_shaft_node
    assert rotor_front["n_link"] == front_link
    assert rotor_rear["n"] == rear_shaft_node
    assert rotor_rear["n_link"] == rear_link
    assert support_front["n"] == front_shaft_node
    assert support_front["n_link"] == front_link
    assert support_rear["n"] == rear_shaft_node
    assert support_rear["n_link"] == rear_link
    assert type(build.bearing_elements[1]).__name__ == "RossFlexibleSupportElement"
    assert type(build.bearing_elements[3]).__name__ == "RossFlexibleSupportElement"
    assert support_front["kxx"] == pytest.approx(43.68e7)
    assert support_front["kyy"] == pytest.approx(90.34e7)
    assert support_front["mxx"] == pytest.approx(175.0)
    assert support_front["myy"] == pytest.approx(175.0)
    assert support_front["mzz"] == pytest.approx(0.0)
    assert support_rear["mxx"] == pytest.approx(175.0)
    assert support_rear["myy"] == pytest.approx(175.0)

    # ROSS 2.3.0 cannot position PointMass at a shaft-only station. The adapter
    # uses a dynamically equivalent zero-inertia DiskElement carrier and keeps
    # it separately classified as a point mass in RossBuild.
    carrier = build.point_mass_elements[0]
    assert type(carrier) is FakeDiskElement
    assert carrier.kwargs["n"] == build.node_by_position_mm[105.0]
    assert carrier.kwargs["m"] == pytest.approx(34.0)
    assert carrier.kwargs["Id"] == pytest.approx(0.0)
    assert carrier.kwargs["Ip"] == pytest.approx(0.0)
    assert len(build.rotor.disk_elements) == 5
    assert build.rotor.point_mass_elements == []

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
