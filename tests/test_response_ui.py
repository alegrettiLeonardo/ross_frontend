import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from ross_frontend.backends.ross.response_calculator import ComplexResponseCurve, RotorResponseResult
from ross_frontend.ui.main_window import RossStudioWindow


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_response_result_reuses_approved_results_workspace(app):
    window = RossStudioWindow()
    page = window.results_page
    result = RotorResponseResult(
        kind="project_unbalance_response",
        curves=[
            ComplexResponseCurve(
                x=[1200.0, 3600.0, 7200.0],
                magnitude=[1.0e-6, 8.5e-6, 2.0e-6],
                phase_deg=[10.0, 82.5, 170.0],
                label="DE-H 45deg",
                magnitude_unit="m",
            ),
            ComplexResponseCurve(
                x=[1200.0, 3600.0, 7200.0],
                magnitude=[0.5e-6, 4.0e-6, 1.5e-6],
                phase_deg=[5.0, 70.0, 160.0],
                label="NDE-H 45deg",
                magnitude_unit="m",
            ),
        ],
    )

    page._on_response_completed(result)

    assert page.analysis_stack.currentWidget() is page.response_chart
    assert page.response_chart.result is result
    assert page.table.rowCount() == 2
    assert page.table.item(0, 0).text() == "DE-H 45deg"
    assert page.table.item(0, 1).text() == "8.500"
    assert page.table.item(0, 2).text() == "3,600"
    assert page.table.item(0, 3).text() == "82.50"
    assert page.table.item(0, 4).text() == "µm"

    page._restore_rotor_table()
    assert page.table.columnCount() == 5
    window.close()


def test_time_response_tab_is_fail_closed_without_transient_load_definition(app):
    window = RossStudioWindow()
    page = window.results_page
    selector_buttons = [b for b in page.findChildren(type(page.k1).mro()[1]) if False]
    # Call the same selection handler used by the approved button while avoiding
    # a real solver thread in this UI-only smoke test.
    from PySide6.QtWidgets import QPushButton, QWidget

    host = QWidget()
    button = QPushButton("Time Response", host)
    button.setCheckable(True)
    button.setChecked(True)
    page._select_analysis(button, host)
    assert page.analysis_stack.currentWidget() is page.response_chart
    assert "transient force" in page.table.item(0, 0).text().lower()
    window.close()
