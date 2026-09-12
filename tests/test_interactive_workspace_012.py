from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTabWidget

from ross_studio.domain import AdapterStatus, BearingGroup, EngineeringError
from ross_studio.legacy_import import load_irdin_project
from ross_studio.models import load_reference_project_model
from ross_studio.pages.rotor_model import RotorModelPage
from ross_studio.ross_backend import RossModelBuilder
from ross_studio.ross_native_view import RossRotorPlotService
from ross_studio.services import BearingCatalogService
from ross_studio.topology import NodeInsertionService


FIXTURE = Path(__file__).parents[1] / "src" / "ross_studio" / "resources" / "OP-W60-500-60Hz-IC611-P3.txt"


def test_op_w60_default_mesh_preserves_qualified_topology() -> None:
    project = load_irdin_project(FIXTURE)
    plan = NodeInsertionService.plan(project)

    assert [section.fe_elements for section in project.shaft_sections] == [1] * 15
    assert project.requested_shaft_element_count == 15
    assert plan.shaft_element_count == 27
    assert len(plan.positions_mm) == 28
    assert project.ross_shaft_element_count == 27


def test_per_section_discretization_is_unioned_with_exact_engineering_nodes() -> None:
    project = load_irdin_project(FIXTURE)
    project.shaft_sections[7].fe_elements = 5
    project.validate()
    plan = NodeInsertionService.plan(project)

    # Section 8 starts at 777.5 mm and is 1115 mm long. Five uniform base
    # elements therefore request four internal mesh nodes at these exact values.
    for x in (1000.5, 1223.5, 1446.5, 1669.5):
        assert plan.node_for(x) is not None
        assert x in plan.mesh_positions_mm

    # Existing OP-W60 engineering stations remain exact; they are not snapped to
    # the new uniform section mesh.
    for x in (467.8, 2202.2, 918.0, 1633.0, 105.0, 737.5, 1275.5, 1932.5, 2550.2):
        assert plan.node_for(x) is not None

    assert project.requested_shaft_element_count == 19
    assert plan.shaft_element_count > 27


def test_invalid_per_section_fe_count_is_rejected() -> None:
    project = load_irdin_project(FIXTURE)
    project.shaft_sections[0].fe_elements = 0
    with pytest.raises(EngineeringError, match="FE element count"):
        project.validate()


def test_ross_builder_uses_same_discretized_topology_and_physical_section_mapping() -> None:
    project = load_irdin_project(FIXTURE)
    project.shaft_sections[7].fe_elements = 5
    plan = NodeInsertionService.plan(project)
    shaft_plan = RossModelBuilder.shaft_plan(project)

    assert len(shaft_plan) == plan.shaft_element_count
    assert shaft_plan[0].n == 0
    assert all(element.x1_mm > element.x0_mm for element in shaft_plan)
    section_8 = [element for element in shaft_plan if element.physical_section == 8]
    assert len(section_8) >= 5
    assert section_8[0].x0_mm == pytest.approx(777.5)
    assert section_8[-1].x1_mm == pytest.approx(1892.5)


def test_native_ross_plot_is_built_from_strict_rotor_object() -> None:
    project = load_irdin_project(FIXTURE)
    result = RossRotorPlotService().build_figure(project)

    assert result.shaft_elements == 27
    assert result.nodes == 28
    assert result.node_increment >= 1
    assert len(result.figure.data) > 0
    assert result.figure.layout is not None


def test_real_catalog_has_all_qualified_bearing_adapters_executable() -> None:
    catalog = BearingCatalogService()
    expected_ready = {
        "BearingElement",
        "BallBearingElement",
        "RollerBearingElement",
        "CylindricalBearing",
        "PlainJournal",
        "TiltingPad",
        "ThrustPad",
        "SqueezeFilmDamper",
        "MagneticBearingElement",
    }
    rows = {
        row["class"]: row
        for group in (BearingGroup.GENERAL, BearingGroup.THD, BearingGroup.AMB)
        for row in catalog.entries(group)
    }
    for ross_class in expected_ready:
        assert rows[ross_class]["status"] == AdapterStatus.VALIDATED.value
        assert rows[ross_class]["can_execute"] is True
    assert rows["MagneticBearingElement"]["status"] == AdapterStatus.VALIDATED.value
    assert rows["MagneticBearingElement"]["can_execute"] is True


def test_rotor_page_has_single_navigation_and_editable_mesh_column(qtbot) -> None:
    project = load_reference_project_model()
    page = RotorModelPage(project)
    qtbot.addWidget(page)

    # Model navigation is owned by the sidebar; the workspace contains no second
    # horizontal QTabWidget navigation bar.
    assert page.findChildren(QTabWidget) == []
    assert page.editor_stack.count() == 8
    assert page.segment_table.horizontalHeaderItem(6).text() == "Base FE Elements"
    assert page.segment_table.horizontalHeaderItem(7).text() == "Effective ROSS Elements"
    assert not bool(page.segment_table.item(0, 0).flags() & Qt.ItemFlag.ItemIsEditable)
    assert bool(page.segment_table.item(0, 6).flags() & Qt.ItemFlag.ItemIsEditable)

    old_effective = project.ross_shaft_elements
    page.segment_table.item(7, 6).setText("3")
    assert project.engineering is not None
    assert project.engineering.shaft_sections[7].fe_elements == 3
    assert project.ross_shaft_elements > old_effective
    assert int(page.segment_table.item(7, 7).text()) >= 3


def test_interactive_sketch_zoom_and_fit_contract(qtbot) -> None:
    project = load_reference_project_model()
    page = RotorModelPage(project)
    qtbot.addWidget(page)
    page.resize(1200, 760)
    page.show()
    qtbot.wait(10)

    assert page.sketch.zoom == pytest.approx(1.0)
    page.sketch.zoom_in()
    assert page.sketch.zoom > 1.0
    page.sketch.zoom_out()
    assert page.sketch.zoom == pytest.approx(1.0)
    page.sketch.zoom_in()
    page.sketch.fit()
    assert page.sketch.zoom == pytest.approx(1.0)
