import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from ross_frontend.legacy_import import load_irdin_project
from ross_frontend.ui.main_window import RossStudioWindow


CASE = Path(__file__).resolve().parents[1] / "cases" / "OP-W60-500-60Hz-IC611-P3" / "irdin_input.txt"


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_imported_w60_populates_real_component_tables(app):
    project = load_irdin_project(CASE)
    window = RossStudioWindow()
    window._set_project(project)

    assert window.titlebar.project_label.text() == "OP"
    assert window.model_page.table.rowCount() == 15
    assert window.model_page.disk_table.rowCount() == 4
    assert window.model_page.bearing_table.rowCount() == 2
    assert window.model_page.support_table.rowCount() == 2
    assert window.model_page.loads_table.rowCount() == 7  # 2 unbalances + 4 probes + 1 UMP region
    assert window.model_page.sketch.project.shaft_length_mm == pytest.approx(2555.2)
    assert window.model_page.speed.text().replace(",", "") == "3600"

    ump_rows = [
        row
        for row in range(window.model_page.loads_table.rowCount())
        if window.model_page.loads_table.item(row, 0).text() == "UMP"
    ]
    assert ump_rows == [6]
    ump_row = ump_rows[0]
    assert "918.0" in window.model_page.loads_table.item(ump_row, 2).text()
    assert "1633.0" in window.model_page.loads_table.item(ump_row, 2).text()
    assert "N/m²" in window.model_page.loads_table.item(ump_row, 3).text()
    assert "K−KUMP" in window.model_page.loads_table.item(ump_row, 4).text()

    window.navigate("loads")
    assert window.model_page.tabs.currentWidget() is window.model_page.loads_table.parentWidget()
    window.close()
