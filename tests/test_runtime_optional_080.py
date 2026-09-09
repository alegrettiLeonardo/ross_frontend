from __future__ import annotations

import os

import pytest

from ross_studio.legacy_import import load_irdin_project
from ross_studio.models import load_reference_project_model
from ross_studio.ross_backend import RossModelBuilder


FIXTURE = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "src",
    "ross_studio",
    "resources",
    "OP-W60-500-60Hz-IC611-P3.txt",
)


def test_real_ross_23_strict_builds_op_w60_with_inserted_nodes_and_legacy_masses() -> None:
    rs = pytest.importorskip("ross")
    project = load_irdin_project(FIXTURE)
    result = RossModelBuilder(rs).build(project, strict=True)

    assert len(result.rotor.shaft_elements) == 27
    assert len(result.node_positions_mm) == 28
    assert result.unresolved_positions_mm == []
    assert result.support_link_nodes == {"Support 1": 28, "Support 2": 29}
    assert len(result.rotor.bearing_elements) == 4
    assert len(result.rotor.disk_elements) == 4
    assert len(result.rotor.point_mass_elements) == 3
    assert len(result.equivalent_disks) == 4

    bearings_by_tag = {bearing.tag: bearing for bearing in result.rotor.bearing_elements}
    assert bearings_by_tag["dianteiro -quente"].n_link == 28
    assert bearings_by_tag["traseiro -quente"].n_link == 29
    assert bearings_by_tag["Support 1 / ground"].n == 28
    assert bearings_by_tag["Support 2 / ground"].n == 29

    disk_by_tag = {disk.tag: disk for disk in result.rotor.disk_elements}
    assert disk_by_tag["Rotor mass 2 / legacy equivalent"].m == pytest.approx(723.19)
    assert disk_by_tag["Rotor mass 2 / legacy equivalent"].Id == pytest.approx(43.397426583333335)
    assert disk_by_tag["Rotor mass 2 / legacy equivalent"].Ip == pytest.approx(25.176051875)

    point_by_tag = {mass.tag: mass for mass in result.rotor.point_mass_elements}
    assert point_by_tag["Point mass 1"].m == pytest.approx(project.point_masses[0].mass_kg)


def test_qt_engineering_routes_and_bearing_groups() -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    from ross_studio.app import RossStudioWindow

    app = QApplication.instance() or QApplication([])
    window = RossStudioWindow()
    assert window.project.name == "OP-W60-500-60Hz-IC611-P3"

    expected_tabs = {
        "shaft": 0,
        "disks": 1,
        "supports": 2,
        "seals": 3,
        "couplings": 4,
        "loads": 5,
    }
    for route, tab_index in expected_tabs.items():
        window._navigate(route)
        assert window.stack.currentWidget() is window.rotor_page
        assert window.rotor_page.tabs.currentIndex() == tab_index

    window._navigate("bearings")
    assert window.stack.currentWidget() is window.bearing_groups_page

    window._open_bearing_group("THD")
    assert window.stack.currentWidget() is window.bearing_page
    visible_classes = {
        window.bearing_page.type_metadata[key][1]
        for key, button in window.bearing_page.type_buttons.items()
        if not button.isHidden()
    }
    assert visible_classes == {"PlainJournal", "TiltingPad", "ThrustPad", "SqueezeFilmDamper"}
    assert not window.bearing_page.calculate_button.isEnabled()

    window.close()
    app.processEvents()


def test_reference_model_is_loaded_without_hardcoded_ui_geometry() -> None:
    project = load_reference_project_model()
    assert project.engineering is not None
    assert project.physical_sections == project.engineering.physical_section_count == 15
    assert project.ross_shaft_elements == project.engineering.ross_shaft_element_count == 27
