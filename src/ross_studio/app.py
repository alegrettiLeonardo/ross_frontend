from __future__ import annotations

"""ROSS Studio 0.18 application composition root.

The qualified 0.15 scientific transaction logic remains in ``app_legacy`` while
0.17 replaces flat navigation ownership with stable architecture routes. 0.18 adds
Engineering Outputs as a local analysis-result capability; it does not introduce a
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
from .theme import APP_STYLESHEET

# Install the bounded landscape-A4 report composer before any GUI export is invoked.
# This changes presentation only; the report still consumes the exact retained
# EngineeringOutputsSnapshot and native ROSS image exports.
install_engineering_report_export()

# app_legacy resolves these module globals when a window/page is constructed or
# refreshed. Redirect them to the qualified workspaces without duplicating solver logic.
_legacy.BearingStudioPage = BearingStudioPage
_legacy.RotorModelPage = RotorModelPage
_legacy.AnalysisResultsPage = EngineeringAnalysisResultsPage

# ProjectFileController imports the historical module paths lazily after Open/New.
# Publish the same composition there so startup and file replacement cannot diverge.
_bearing_base_module.BearingStudioPage = BearingStudioPage
_rotor_base_module.RotorModelPage = RotorModelPage

TitleBar = _legacy.TitleBar


class RossStudioWindow(_legacy.RossStudioWindow):
    """0.18 shell with registry-driven navigation and local Engineering Outputs."""

    def __init__(self) -> None:
        # ``app_legacy.__init__`` emits its initial navigation signal. Prepare the
        # cache first so the overridden virtual _navigate() is safe during super().
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
        elif spec.owner == "analysis":
            page = AnalysisRoutePage(self.project, spec)
        else:  # pragma: no cover - guarded by callers/page registry
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
            self.status.set_status(
                spec.title,
                "Dedicated route owner established" if spec.operational else spec.note,
                units=f"Scientific execution gate: {spec.implementation_phase}",
            )
            return

        raise KeyError(route)

    def run_analysis(self) -> None:
        """Preserve the qualified pipeline and expose its local Engineering Outputs."""
        super().run_analysis()
        # The historical method activates the compatibility alias ``results``.
        # There is intentionally no public global Results route in 0.18. Keep the
        # real result page visible; its local Engineering Outputs button owns export.
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
