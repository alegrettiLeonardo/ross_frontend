from pathlib import Path

import pytest

from ross_studio.domain import AdapterStatus, BearingGroup
from ross_studio.legacy_import import load_irdin_project
from ross_studio.models import BearingModel, load_reference_project_model
from ross_studio.ross_backend import RossModelBuilder
from ross_studio.services import BearingCatalogService, EngineeringValidationService, RossCapabilityRegistry

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
    assert view.ross_shaft_elements == 22
    bearing = BearingModel.from_project(view.engineering)
    assert bearing.name == "dianteiro -quente"
    assert len(bearing.coefficients) == 11


def test_physical_to_fem_topology_is_explicit() -> None:
    project = load_irdin_project(FIXTURE)
    assert project.physical_section_count == 15
    assert project.ross_shaft_element_count == 22
    split = project.topology_split_positions_mm()
    assert 467.8 in split
    assert 2202.2 in split
    assert 918.0 in split
    assert 1633.0 in split
    assert 105.0 not in split


def test_positions_are_not_silently_snapped() -> None:
    project = load_irdin_project(FIXTURE)
    builder = RossModelBuilder(FakeRoss)
    assert builder.map_position(project, 918.0).exact
    assert builder.map_position(project, 1633.0).exact
    mapping = builder.map_position(project, 1000.123)
    assert not mapping.exact
    assert mapping.node is None


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


def test_readiness_flags_unqualified_realizations_without_destroying_data() -> None:
    project = load_irdin_project(FIXTURE)
    issues = EngineeringValidationService().validate(project)
    codes = {i.code for i in issues}
    assert "DISTRIBUTED_MASS_REALIZATION" in codes
    assert "POINT_MASS_NODE_MAPPING" in codes
    assert all(i.severity != "error" for i in issues)
