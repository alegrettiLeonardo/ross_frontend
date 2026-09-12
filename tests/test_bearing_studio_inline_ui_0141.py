from __future__ import annotations

from copy import deepcopy

import pytest
from PySide6.QtCore import Qt

from ross_studio.app import RossStudioWindow
from ross_studio.icons import engineering_icon
from ross_studio.theme import APP_STYLESHEET


def test_bearing_studio_uses_requested_model_tree_and_vertical_workspace(qtbot) -> None:
    pytest.importorskip("ross")
    window = RossStudioWindow()
    qtbot.addWidget(window)
    window.show()
    window._navigate("bearings")

    page = window.bearing_page
    assert page.__class__.__module__.endswith("bearing_workspace_page")
    assert page.workspace_scroll.widgetResizable()
    assert page.group_selector.isHidden()
    assert page.input_card.isVisible()
    assert not page.result_card.isVisible()
    assert hasattr(page, "bearing_rail")
    assert "exact ROSS node" in page.target_node_label.text()

    # Calculation-model surface requested for 0.15. Direct BearingElement K/C is an
    # application/persistence class, not a Bearing Studio model tile.
    assert set(page.type_buttons) == {
        "ball", "roller", "cyl", "plain", "tilting", "thrust", "sfd", "amb"
    }
    assert len(page.type_buttons) == 8
    assert "kc" not in page.type_buttons
    assert all(not button.isHidden() for button in page.type_buttons.values())
    for icon_name in (
        "ball_bearing", "roller_bearing", "cylindrical_bearing",
        "plain_journal", "tilting_pad", "thrust_pad", "sfd", "amb",
    ):
        assert not engineering_icon(icon_name, 42).isNull()

    # Popup/dialog visibility remains explicitly light and readable.
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
    assert page.output_dimensional_button.isEnabled() is False  # result not solved yet
    assert window.project.engineering == original

    qtbot.mouseClick(page.type_buttons["tilting"], Qt.MouseButton.LeftButton)
    assert window._selected_bearing_class() == "TiltingPad"
    assert {"pad_thickness_mm", "n_pads", "pivot_angles_deg", "nx", "nz"}.issubset(
        page.input_panel.fields
    )
    assert window.project.engineering == original

    qtbot.mouseClick(page.type_buttons["ball"], Qt.MouseButton.LeftButton)
    assert window._selected_bearing_class() == "BallBearingElement"
    assert set(page.input_panel.fields) == {
        "n_balls", "d_balls_mm", "static_load_n", "contact_angle_deg"
    }
    assert window.project.engineering == original

    qtbot.mouseClick(page.type_buttons["amb"], Qt.MouseButton.LeftButton)
    assert window._selected_bearing_class() == "MagneticBearingElement"
    assert page.calculate_button.isEnabled()
    assert {"speed_rpm", "g0_mm", "i0_a", "ag_mm2", "nw", "kp_pid", "kd_pid", "ki_pid"} <= set(
        page.input_panel.fields
    )
    assert "native ross active magnetic bearing" in page.input_panel.description.text().lower()
    assert window.project.engineering == original


def test_general_bearing_exposes_kc_values_but_never_thd_dimensional_output_or_curves(qtbot) -> None:
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
    assert page.output_kc_button.isEnabled()
    assert not page.output_dimensional_button.isEnabled()
    assert not page.result_card.isVisible()
    assert page.input_panel.values() == before
    assert page.kc_table.rowCount() == 1
    assert page.kc_native_view.figure is None
    assert "only for calculated THD bearings" in page.kc_native_view._message.text()

    qtbot.mouseClick(page.output_kc_button, Qt.MouseButton.LeftButton)
    assert page.result_card.isVisible()
    assert page.tabs.currentIndex() == 0
    assert page.input_panel.values() == before

    page.set_results_visible(False)
    assert not page.result_card.isVisible()
    assert page.input_panel.values() == before
