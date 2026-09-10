from __future__ import annotations

from copy import deepcopy

import pytest
from PySide6.QtCore import Qt

from ross_studio.app import RossStudioWindow
from ross_studio.icons import engineering_icon
from ross_studio.theme import APP_STYLESHEET


def test_bearing_studio_uses_light_inline_model_driven_workspace(qtbot) -> None:
    pytest.importorskip("ross")
    window = RossStudioWindow()
    qtbot.addWidget(window)
    window.show()
    window._navigate("bearings")

    page = window.bearing_page
    assert page.workspace_scroll.widgetResizable()
    assert page.group_selector.isHidden()  # family is classification, not duplicate navigation
    assert page.input_card.isVisible()
    assert not page.result_card.isVisible()
    assert not page.results_button.isEnabled()

    # Every qualified/blocked model is directly discoverable through its own icon.
    assert len(page.type_buttons) == 9
    assert all(not button.isHidden() for button in page.type_buttons.values())
    for icon_name in (
        "bearing_kc", "ball_bearing", "roller_bearing", "cylindrical_bearing",
        "plain_journal", "tilting_pad", "thrust_pad", "sfd", "amb",
    ):
        assert not engineering_icon(icon_name, 42).isNull()

    # The popup/dialog visibility regression is prevented by explicit light Qt styling.
    assert "QComboBox QAbstractItemView" in APP_STYLESHEET
    assert "background: #ffffff" in APP_STYLESHEET
    assert "QDialog" in APP_STYLESHEET

    original = deepcopy(window.project.engineering)

    qtbot.mouseClick(page.type_buttons["sfd"], Qt.MouseButton.LeftButton)
    assert window._selected_bearing_class() == "SqueezeFilmDamper"
    assert {
        "speed_rpm", "journal_diameter_mm", "radial_clearance_um", "lubricant",
        "axial_length_mm", "eccentricity_ratio", "geometry", "cavitation",
    }.issubset(page.input_panel.fields)
    assert window.project.engineering == original

    qtbot.mouseClick(page.type_buttons["tilting"], Qt.MouseButton.LeftButton)
    assert window._selected_bearing_class() == "TiltingPad"
    assert {"pad_thickness_mm", "n_pad", "pivot_angles_deg", "nx", "nz"}.issubset(
        page.input_panel.fields
    )
    assert window.project.engineering == original

    qtbot.mouseClick(page.type_buttons["ball"], Qt.MouseButton.LeftButton)
    assert window._selected_bearing_class() == "BallBearingElement"
    assert set(page.input_panel.fields) == {
        "n_balls", "d_balls_mm", "static_load_n", "contact_angle_deg"
    }
    assert window.project.engineering == original

    qtbot.mouseClick(page.type_buttons["kc"], Qt.MouseButton.LeftButton)
    assert window._selected_bearing_class() == "BearingElement"
    assert page.input_panel.kc_table is not None
    assert page.input_panel.kc_table.rowCount() == len(original.bearings[0].coefficients)
    assert window.project.engineering == original

    qtbot.mouseClick(page.type_buttons["amb"], Qt.MouseButton.LeftButton)
    assert window._selected_bearing_class() == "MagneticBearingElement"
    assert not page.calculate_button.isEnabled()
    assert "blocked" in page.input_panel.description.text().lower()
    assert window.project.engineering == original


def test_results_live_below_inputs_and_toggle_without_losing_inline_values(qtbot) -> None:
    pytest.importorskip("ross")
    window = RossStudioWindow()
    qtbot.addWidget(window)
    window.show()
    window._navigate("bearings")
    page = window.bearing_page

    qtbot.mouseClick(page.type_buttons["ball"], Qt.MouseButton.LeftButton)
    page.input_panel.fields["n_balls"].setValue(11)
    page.input_panel.fields["d_balls_mm"].setValue(26.0)
    before = page.input_panel.values()

    qtbot.mouseClick(page.calculate_button, Qt.MouseButton.LeftButton)
    assert window.bearing_calculation is not None
    assert page.apply_button.isEnabled()
    assert page.results_button.isEnabled()
    assert not page.result_card.isVisible()
    assert page.input_panel.values() == before  # Calculate does not rebuild/erase the editor.

    qtbot.mouseClick(page.results_button, Qt.MouseButton.LeftButton)
    assert page.result_card.isVisible()
    assert page.results_button.text() == "Hide Results"
    assert page.input_panel.values() == before

    qtbot.mouseClick(page.results_button, Qt.MouseButton.LeftButton)
    assert not page.result_card.isVisible()
    assert page.results_button.text() == "View Results"
    assert page.input_panel.values() == before
