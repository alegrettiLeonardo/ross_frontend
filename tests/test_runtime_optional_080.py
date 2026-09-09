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


def test_real_ross_23_builds_op_w60_support_topology() -> None:
    rs = pytest.importorskip("ross")
    project = load_irdin_project(FIXTURE)
    result = RossModelBuilder(rs).build(project, strict=False)

    assert len(result.rotor.shaft_elements) == 22
    assert result.support_link_nodes == {"Support 1": 23, "Support 2": 24}
    assert len(result.rotor.bearing_elements) == 4
    assert len(result.rotor.point_mass_elements) == 2
    assert result.rotor.bearing_elements[0].n_link == 23
    assert result.rotor.bearing_elements[2].n_link == 24


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
    assert project.ross_shaft_elements == project.engineering.ross_shaft_element_count == 22
