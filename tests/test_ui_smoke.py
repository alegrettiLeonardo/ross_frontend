import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from ross_frontend.backends.ross.bearing_calculator import (
    BearingCalculationResult,
    BearingCoefficientRow,
    BearingOperatingPoint,
)
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
    bearing = window.project.bearings[0]
    assert bearing.kind == BearingKind.TILTING_PAD
    assert bearing.journal_diameter_mm == pytest.approx(100.0)
    assert bearing.radial_clearance_mm == pytest.approx(0.10)
    assert bearing.equilibrium_type == "match_load"
    assert bearing.oil_supply_pressure_pa == pytest.approx(200000.0)
    assert bearing.frequency_rpm == [500.0, 1000.0, 2000.0, 4000.0, 6000.0, 8000.0, 10000.0]
    window.close()


def test_native_bearing_result_updates_approved_studio_views(app):
    window = RossStudioWindow()
    page = window.bearing_page
    result = BearingCalculationResult(
        bearing_type="TiltingPadBearingSpec",
        tag="DE Journal Bearing",
        coefficients=[
            BearingCoefficientRow(4000, 1.0e7, -2.0e6, 3.0e6, 1.1e7, 1.0e5, -2.0e4, 3.0e4, 1.1e5),
            BearingCoefficientRow(6000, 1.5e7, -2.5e6, 3.5e6, 1.6e7, 1.3e5, -2.2e4, 3.2e4, 1.4e5),
        ],
        operating_points=[
            BearingOperatingPoint(4000, 0.31, 48.0, 0.060, 7.0e6, 67.0, 1.5, 25.0, 0.1, -0.29),
            BearingOperatingPoint(6000, 0.42, 53.2, 0.050, 8.0e6, 78.6, 1.86, 32.4, 0.2, -0.37),
        ],
        pressure_fields_pa=[[[[1.0e6, 2.0e6], [3.0e6, 4.0e6]]], [[[2.0e6, 3.0e6], [4.0e6, 5.0e6]]]],
        temperature_fields_c=[[[[40.0, 50.0], [60.0, 70.0]]], [[[45.0, 55.0], [65.0, 78.6]]]],
        film_thickness_fields_mm=[[[[0.08, 0.07], [0.06, 0.05]]], [[[0.07, 0.06], [0.055, 0.05]]]],
        theta_grids_rad=[[[[0.0, 0.0], [1.0, 1.0]]], [[[0.0, 0.0], [1.0, 1.0]]]],
        axial_grids_mm=[[[[0.0, 10.0], [0.0, 10.0]]], [[[0.0, 10.0], [0.0, 10.0]]]],
        execution_time_s=2.5,
    )
    page._apply_calculation_result(result)
    assert page.table.rowCount() == 2
    assert page.table.item(1, 0).text() == "6,000"
    assert page.operating_title.text() == "Operating Point (at 6,000 rpm)"
    assert page.operating_values["eccentricity"].text() == "0.420"
    assert page.operating_values["temperature"].text() == "78.6"
    assert page.pressure_view.values == result.pressure_fields_pa[1]
    assert page.temperature_view.values == result.temperature_fields_c[1]
    assert page.film_view.values == result.film_thickness_fields_mm[1]
    assert len(page.journal_view.points) == 2
    assert "Maximum pressure: 8.000 MPa" in page.convergence_details.text()
    window.close()
