from __future__ import annotations

from PySide6.QtWidgets import QPushButton

from ross_studio import app
from ross_studio.navigation_registry import public_routes
from ross_studio.pages.engineering_results import EngineeringAnalysisResultsPage
from ross_studio.models import load_reference_project_model


def test_engineering_outputs_does_not_add_global_results_sidebar_route() -> None:
    routes = set(public_routes())
    assert "results" not in routes
    assert "engineering_outputs" not in routes
    assert all("engineering_outputs" not in route for route in routes)


def test_app_composes_local_engineering_results_page() -> None:
    assert app._legacy.AnalysisResultsPage is EngineeringAnalysisResultsPage


def test_engineering_outputs_button_is_local_and_disabled_until_real_result(qtbot) -> None:
    page = EngineeringAnalysisResultsPage(load_reference_project_model())
    qtbot.addWidget(page)
    page.resize(1400, 800)
    page.show()
    assert page.engineering_outputs_button.parent() is page
    assert page.engineering_outputs_button.isEnabled() is False
    assert page.engineering_snapshot is None
    assert page.engineering_figure_catalog is None

    placeholder_labels = {button.text(): button for button in page.findChildren(QPushButton)}
    for text in ("Export PNG", "Export CSV", "Generate Report"):
        assert placeholder_labels[text].isHidden()
