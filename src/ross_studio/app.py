from __future__ import annotations

"""ROSS Studio 0.21 application composition root.

The qualified 0.15 scientific transaction logic remains in ``app_legacy`` while
0.17 owns hierarchical navigation, 0.18 adds local Engineering Outputs, 0.19 adds
native Static/Modal plots, 0.20 decouples Static from Modal/Campbell, and 0.21 adds
independent native ROSS Time & Frequency transactions without introducing a
public/global Results route in the sidebar.
"""

import sys

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QWidget

from . import app_legacy as _legacy
from .engineering_report_pdf import install_engineering_report_export
from .navigation_registry import canonical_route
from .page_registry import route_spec
from .pages import bearing_studio as _bearing_base_module
from .pages import rotor_model as _rotor_base_module
from .pages.architecture_workspaces import AnalysisRoutePage, FoundationWorkspacePage
from .pages.bearing_workspace_page import BearingStudioPage
from .pages.engineering_results import EngineeringAnalysisResultsPage
from .pages.project_home import ProjectHomePage
from .pages.rotor_workspace import RotorModelPage
from .pages.static_modal_workspace import StaticModalWorkspacePage
from .pages.time_frequency_workspace import TimeFrequencyWorkspacePage
from .theme import APP_STYLESHEET

install_engineering_report_export()

_legacy.BearingStudioPage = BearingStudioPage
_legacy.RotorModelPage = RotorModelPage
_legacy.AnalysisResultsPage = EngineeringAnalysisResultsPage
_bearing_base_module.BearingStudioPage = BearingStudioPage
_rotor_base_module.RotorModelPage = RotorModelPage

TitleBar = _legacy.TitleBar


class RossStudioWindow(_legacy.RossStudioWindow):
    """0.21 shell with independent native ROSS analysis workspaces."""

    def __init__(self) -> None:
        self._architecture_pages: dict[str, QWidget] = {}
        super().__init__()

    def _architecture_page(self, route_id: str) -> QWidget:
        current = self._architecture_pages.get(route_id)
        if current is not None and getattr(current, "project", None) is self.project:
            return current
        if current is not None:
            self.stack.removeWidget(current)
            current.deleteLater()

        spec = route_spec(route_id)
        if spec.owner == "home":
            page: QWidget = ProjectHomePage(self.project)
        elif spec.owner == "foundation":
            page = FoundationWorkspacePage(self.project)
        elif route_id == "analysis.static_modal.lateral":
            page = StaticModalWorkspacePage(self.project, mode_filter="Lateral")
        elif route_id == "analysis.static_modal.torsional":
            page = StaticModalWorkspacePage(self.project, mode_filter="Torsional")
        elif route_id == "analysis.time_frequency":
            page = TimeFrequencyWorkspacePage(self.project)
        elif spec.owner == "analysis":
            page = AnalysisRoutePage(self.project, spec)
        else:
            raise ValueError(f"Route {route_id!r} does not own a standalone architecture page.")
        self.stack.addWidget(page)
        self._architecture_pages[route_id] = page
        return page

    def _navigate(self, key: str) -> None:
        route = canonical_route(key)
        spec = route_spec(route)

        if spec.owner == "home":
            self.stack.setCurrentWidget(self._architecture_page(route))
            self.status.set_status(
                "Project Data",
                f"{self.project.name} · model inventory and validation",
                units="ROTOR MODEL edits physics · ANALYSIS consumes the qualified ROSS Rotor",
            )
            return

        if spec.owner == "bearing":
            if spec.bearing_group is None:
                raise RuntimeError(f"Bearing route {route!r} has no family.")
            self._open_bearing_group(spec.bearing_group)
            if not spec.operational:
                self.status.set_status(
                    f"{spec.title} blocked",
                    spec.note,
                    units="Visible architecture route; Apply remains unavailable until scientific qualification",
                )
            return

        if spec.owner == "rotor":
            if spec.editor_key is None:
                raise RuntimeError(f"Rotor route {route!r} has no editor key.")
            self.stack.setCurrentWidget(self.rotor_page)
            self.rotor_page.select_editor(spec.editor_key)
            detail = (
                f"{self.project.physical_sections} physical sections → "
                f"{self.project.ross_shaft_elements} ROSS ShaftElements"
            )
            if spec.note:
                detail = f"{spec.title}: {spec.note}"
            self.status.set_status(
                spec.title,
                detail,
                units="Units: SI boundary · exact engineering coordinates; no nearest-node snapping",
            )
            return

        if spec.owner in {"foundation", "analysis"}:
            self.stack.setCurrentWidget(self._architecture_page(route))
            if route.startswith("analysis.static_modal."):
                detail = "Independent native ROSS Static and Modal/Campbell transactions with separate caches"
            elif route == "analysis.time_frequency":
                detail = (
                    "Independent native ROSS Frequency, Unbalance, Time, HBM, UCS and Clearance transactions "
                    "with per-analysis caches and plot-only post-processing"
                )
            else:
                detail = "Dedicated route owner established" if spec.operational else spec.note
            self.status.set_status(
                spec.title,
                detail,
                units=f"Scientific execution gate: {spec.implementation_phase}",
            )
            return

        raise KeyError(route)

    def run_analysis(self) -> None:
        """Preserve the historical all-in-one qualification pipeline for compatibility."""
        super().run_analysis()
        if self.results_page.result is not None:
            self.stack.setCurrentWidget(self.results_page)


def launch() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("ROSS Studio")
    app.setOrganizationName("ROSS Studio")
    app.setStyleSheet(APP_STYLESHEET)
    app.setFont(QFont("Segoe UI", 10))
    window = RossStudioWindow()
    window.show()
    return app.exec()


__all__ = ["RossStudioWindow", "TitleBar", "launch"]
