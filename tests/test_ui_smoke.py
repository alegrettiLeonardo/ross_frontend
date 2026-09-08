import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from ross_frontend.domain import BearingKind
from ross_frontend.ui.main_window import RossStudioWindow


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_main_window_matches_approved_workspace_structure(app):
    window = RossStudioWindow()
    assert window.windowTitle() == "ROSS STUDIO"
    assert window.sidebar.buttons["rotor"].isChecked()
    assert window.model_page.table.rowCount() == 6
    assert window.model_page.project.reference == "WGM20"
    assert window.bearing_page.type_buttons["tilting"].isChecked()
    assert window.results_page.table.rowCount() == 12
    window.close()


def test_tilting_pad_form_applies_to_domain(app):
    window = RossStudioWindow()
    window.bearing_page.apply_to_rotor()
    assert window.project.bearings[0].kind == BearingKind.TILTING_PAD
    assert window.project.bearings[0].journal_diameter_mm == pytest.approx(100.0)
    assert window.project.bearings[0].radial_clearance_mm == pytest.approx(0.10)
    window.close()
