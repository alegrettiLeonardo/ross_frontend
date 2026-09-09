from copy import deepcopy
from pathlib import Path

import pytest

from ross_studio.domain import AdapterStatus, BearingGroup
from ross_studio.legacy_import import load_irdin_project
from ross_studio.models import BearingModel, load_reference_project_model
from ross_studio.ross_backend import RossModelBuilder
from ross_studio.services import BearingCatalogService, EngineeringValidationService, RossCapabilityRegistry
from ross_studio.topology import NodeInsertionService

FIXTURE = Path(__file__).parents[1] / "src" / "ross_studio" / "resources" / "OP-W60-500-60Hz-IC611-P3.txt"


class FakeRoss:
    class BearingElement: pass
    class BallBearingElement: pass
    class RollerBearingElement: pass
    class CylindricalBearing: pass
    class PlainJournal: pass
    class TiltingPad: pass
    class ThrustPad: pass
    class SqueezeFilmDamper: pass
    class MagneticBearingElement: pass


class CaptureElement:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs


class FakeRossAssembly:
    Material = CaptureElement
    ShaftElement = CaptureElement
    BearingElement = CaptureElement
    DiskElement = CaptureElement
    PointMass = CaptureElement

    class Rotor:
        def __init__(self, *, shaft_elements, disk_elements=None, bearing_elements=None, point_mass_elements=None, tag=None):
            self.shaft_elements = shaft_elements
            self.disk_elements = disk_elements or []
            self.bearing_elements = bearing_elements or []
            self.point_mass_elements = point_mass_elements or []
            self.tag = tag


def test_op_w60_import_contract() -> None:
    project = load_irdin_project(FIXTURE)
    assert project.name == "OP-W60-500-60Hz-IC611-P3"
    assert project.line == "W60"
    assert project.frame == "500"
    assert project.poles == 2
    assert project.operating_cases[0].frequency_hz == 60
    assert project.operating_cases[0].rated_speed_rpm == 3600
    assert project.operating_cases[0].speed_max_rpm == 4500
    assert project.total_length_mm == pytest.approx(2555.2)
    assert project.physical_section_count == 15
    assert len(project.distributed_masses) == 4
    assert len(project.bearings) == 2
    assert len(project.supports) == 2
    assert len(project.point_masses) == 1
    assert len(project.loads) == 2
    assert len(project.probes) == 4


def test_reference_view_model_uses_same_importer() -> None:
    view = load_reference_project_model()
    assert view.name == "OP-W60-500-60Hz-IC611-P3"
    assert view.engineering is not None
    assert view.physical_sections == 15
    assert view.ross_shaft_elements == 27
    bearing = BearingModel.from_project(view.engineering)
    assert bearing.name == "dianteiro -quente"
    assert len(bearing.coefficients) == 11


def test_node_insertion_is_explicit_and_deterministic() -> None:
    project = load_irdin_project(FIXTURE)
    plan = NodeInsertionService.plan(project)

    assert project.physical_section_count == 15
    assert project.ross_shaft_element_count == 27
    assert plan.shaft_element_count == 27
    assert len(plan.positions_mm) == 28

    for x in (467.8, 2202.2, 918.0, 1633.0, 105.0, 737.5, 1275.5, 1932.5, 2550.2):
        assert plan.node_for(x) is not None

    centers = {
        item.position_mm
        for item in plan.insertions
        if any(reason.startswith("legacy-mass-center:") for reason in item.reasons)
    }
    assert centers == {737.5, 1275.5, 1932.5, 2550.2}


def test_positions_are_never_silently_snapped() -> None:
    project = load_irdin_project(FIXTURE)
    builder = RossModelBuilder(FakeRoss)
    assert builder.map_position(project, 105.0).exact
    assert builder.map_position(project, 737.5).exact
    assert builder.map_position(project, 918.0).exact
    mapping = builder.map_position(project, 1000.123)
    assert not mapping.exact
    assert mapping.node is None


def test_legacy_mass_inertia_realization_uses_finite_hollow_cylinder() -> None:
    project = load_irdin_project(FIXTURE)
    expected = [
        (0.19483703125, 0.3759140625),
        (43.397426583333335, 25.176051875),
        (0.19483703125, 0.3759140625),
        (0.5248847252083333, 1.04949734375),
    ]
    for mass, (expected_id, expected_ip) in zip(project.distributed_masses, expected):
        id_kg_m2, ip_kg_m2 = mass.equivalent_disk_inertias_kg_m2()
        assert id_kg_m2 == pytest.approx(expected_id)
        assert ip_kg_m2 == pytest.approx(expected_ip)


def test_bearing_tables_are_preserved() -> None:
    project = load_irdin_project(FIXTURE)
    assert len(project.bearings[0].coefficients) == 11
    assert project.bearings[0].coefficients[0].rpm == pytest.approx(900)
    assert project.bearings[0].coefficients[-1].rpm == pytest.approx(5000)


def test_catalog_separates_class_existence_from_adapter_readiness() -> None:
    registry = RossCapabilityRegistry(FakeRoss)
    catalog = BearingCatalogService(registry)
    assert catalog.groups() == (BearingGroup.GENERAL, BearingGroup.THD, BearingGroup.AMB)
    general = {row["class"]: row for row in catalog.entries(BearingGroup.GENERAL)}
    assert general["BearingElement"]["can_execute"] is True
    assert general["CylindricalBearing"]["status"] == AdapterStatus.VALIDATED.value
    thd = {row["class"]: row for row in catalog.entries(BearingGroup.THD)}
    assert thd["ThrustPad"]["status"] == AdapterStatus.PLANNED.value
    amb = catalog.entries(BearingGroup.AMB)[0]
    assert amb["status"] == AdapterStatus.BLOCKED.value


def test_readiness_accepts_mass_and_node_realization_for_op_w60() -> None:
    project = load_irdin_project(FIXTURE)
    issues = EngineeringValidationService().validate(project)
    codes = {issue.code for issue in issues}
    assert "DISTRIBUTED_MASS_REALIZATION" not in codes
    assert "POINT_MASS_NODE_MAPPING" not in codes
    assert "NODE_INSERTION_FAILED" not in codes
    assert "UMP_LOAD_PENDING" in codes
    assert all(issue.severity != "error" for issue in issues)


def test_strict_op_w60_build_closes_all_structural_node_mapping() -> None:
    project = load_irdin_project(FIXTURE)
    result = RossModelBuilder(FakeRossAssembly).build(project, strict=True)

    assert len(result.shaft_plan) == 27
    assert len(result.node_positions_mm) == 28
    assert result.unresolved_positions_mm == []
    assert result.support_link_nodes == {"Support 1": 28, "Support 2": 29}
    assert len(result.rotor.bearing_elements) == 4
    assert len(result.rotor.disk_elements) == 5
    assert len(result.rotor.point_mass_elements) == 2
    assert len(result.equivalent_disks) == 4
    assert len(result.equivalent_point_masses) == 1

    assert [disk.position_mm for disk in result.equivalent_disks] == [737.5, 1275.5, 1932.5, 2550.2]
    assert [disk.mass_kg for disk in result.equivalent_disks] == pytest.approx([12.9, 723.19, 12.9, 25.51])
    assert result.equivalent_disks[1].id_kg_m2 == pytest.approx(43.397426583333335)
    assert result.equivalent_disks[1].ip_kg_m2 == pytest.approx(25.176051875)

    point = result.equivalent_point_masses[0]
    assert point.position_mm == 105.0
    assert point.mass_kg == 34.0
    assert point.node == NodeInsertionService.plan(project).node_for(105.0)
    point_disk = [element for element in result.rotor.disk_elements if element.kwargs.get("tag") == "Point mass 1 / shaft point mass"]
    assert len(point_disk) == 1
    assert point_disk[0].args[1:] == (34.0, 0.0, 0.0)

    bearings_by_tag = {element.kwargs.get("tag"): element for element in result.rotor.bearing_elements}
    assert bearings_by_tag["dianteiro -quente"].kwargs["n_link"] == 28
    assert bearings_by_tag["traseiro -quente"].kwargs["n_link"] == 29
    assert bearings_by_tag["Support 1 / ground"].kwargs["n"] == 28
    assert bearings_by_tag["Support 2 / ground"].kwargs["n"] == 29

    support_masses = [element for element in result.rotor.point_mass_elements if "Support" in element.kwargs.get("tag", "")]
    assert len(support_masses) == 2


def test_duplicate_support_for_same_bearing_is_blocked() -> None:
    project = load_irdin_project(FIXTURE)
    duplicate = deepcopy(project.supports[0])
    duplicate.name = "Duplicate support"
    project.supports.append(duplicate)

    issues = EngineeringValidationService().validate(project)
    assert any(issue.severity == "error" and issue.code == "DUPLICATE_SUPPORT_LINK" for issue in issues)


def test_cylindrical_bearing_with_flexible_support_is_blocked_for_ross_23() -> None:
    project = load_irdin_project(FIXTURE)
    project.bearings[0].ross_class = "CylindricalBearing"

    issues = EngineeringValidationService().validate(project)
    assert any(
        issue.severity == "error" and issue.code == "CYLINDRICAL_SUPPORT_LINK_UNAVAILABLE"
        for issue in issues
    )


def test_invalid_legacy_mass_geometry_blocks_strict_realization() -> None:
    project = load_irdin_project(FIXTURE)
    project.distributed_masses[0].id_mm = project.distributed_masses[0].od_mm
    issues = EngineeringValidationService().validate(project)
    assert any(issue.severity == "error" and issue.code == "DISTRIBUTED_MASS_GEOMETRY" for issue in issues)


def test_directional_shaft_point_mass_is_not_silently_reduced_to_scalar() -> None:
    project = load_irdin_project(FIXTURE)
    project.point_masses[0].mx_kg = 34.0
    project.point_masses[0].my_kg = 20.0
    issues = EngineeringValidationService().validate(project)
    assert any(
        issue.severity == "error" and issue.code == "DIRECTIONAL_SHAFT_POINT_MASS_UNAVAILABLE"
        for issue in issues
    )
