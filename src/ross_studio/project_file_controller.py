from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PySide6.QtWidgets import QApplication, QFileDialog, QLabel, QMessageBox

from .models import BearingModel, ProjectModel
from .project_file_service import ProjectFileService, ProjectOpenResult
from .project_io import new_project_model, project_fingerprint
from .rotor_selection import WORKSPACE_SELECTION


@dataclass(slots=True)
class ProjectFileState:
    native_path: Path | None
    source_path: Path | None
    source_format: str
    clean_fingerprint: str


class ProjectFileController:
    """Own New/Open/Import/Save/Save-As without contaminating scientific services.

    External formats are imports, never persistence targets. A RotorDin/iRdin or
    DyRoBeS source therefore has ``native_path=None`` and Ctrl+S intentionally
    falls through to Save As, preventing ROSS Studio from overwriting vendor or
    legacy inputs with a different schema.
    """

    def __init__(self, window: Any, service: ProjectFileService | None = None) -> None:
        self.window = window
        self.service = service or ProjectFileService()
        self.state = ProjectFileState(
            native_path=None,
            source_path=None,
            source_format="Session baseline",
            clean_fingerprint=project_fingerprint(window.project),
        )

    @property
    def dirty(self) -> bool:
        return project_fingerprint(self.window.project) != self.state.clean_fingerprint

    def _set_status(self, message: str, detail: str, units: str | None = None) -> None:
        self.window.status.set_status(message, detail, units=units)

    def _error(self, title: str, exc: Exception | str) -> None:
        message = str(exc)
        self._set_status(title, message)
        QMessageBox.critical(self.window, title, message)

    def _confirm_destructive_action(self) -> bool:
        if not self.dirty:
            return True
        choice = QMessageBox.warning(
            self.window,
            "Unsaved project changes",
            "The current engineering model has unsaved changes. Save them before continuing?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if choice == QMessageBox.StandardButton.Cancel:
            return False
        if choice == QMessageBox.StandardButton.Discard:
            return True
        return self.save()

    def new(self) -> bool:
        if not self._confirm_destructive_action():
            return False
        model = new_project_model()
        self._replace_project(
            ProjectOpenResult(model, Path("Untitled"), None, "ROSS Studio / new", False),
            clean=False,
        )
        self._set_status(
            "New project",
            "Untitled project created; no rotor geometry, mass, support or bearing was invented.",
            units="Define/import the engineering model, then Save As (.rossproj)",
        )
        return True

    def open(self) -> bool:
        if not self._confirm_destructive_action():
            return False
        filename, _ = QFileDialog.getOpenFileName(
            self.window, "Open ROSS Studio project", "", self.service.OPEN_FILTER
        )
        if not filename:
            return False
        return self.open_path(filename)

    def open_path(self, path: str | Path) -> bool:
        try:
            result = self.service.open_path(path)
        except Exception as exc:
            self._error("Project open failed", exc)
            return False
        self._replace_project(result, clean=True)
        action = "Imported" if result.imported else "Opened"
        save_note = "Save creates a .rossproj copy" if result.imported else "Native project persistence active"
        self._set_status(
            f"{action} {result.source_format} project",
            f"{result.source_path.name} · {result.model.physical_sections} physical sections · "
            f"{result.model.ross_shaft_elements} ROSS ShaftElements",
            units=save_note,
        )
        return True

    def import_legacy(self) -> bool:
        if not self._confirm_destructive_action():
            return False
        filename, _ = QFileDialog.getOpenFileName(
            self.window, "Import legacy rotor calculation", "", self.service.LEGACY_FILTER
        )
        if not filename:
            return False
        try:
            result = self.service.import_legacy_path(filename)
        except Exception as exc:
            self._error("Legacy import failed", exc)
            return False
        self._replace_project(result, clean=True)
        self._set_status(
            f"Imported {result.source_format}",
            f"{result.source_path.name} loaded into the engineering domain",
            units="Source remains read-only; Save writes .rossproj",
        )
        return True

    def save(self) -> bool:
        if self.state.native_path is None:
            return self.save_as()
        return self._write(self.state.native_path)

    def save_as(self) -> bool:
        initial = self.window.project.name.strip() or "Untitled"
        filename, _ = QFileDialog.getSaveFileName(
            self.window,
            "Save ROSS Studio project as",
            f"{initial}.rossproj",
            self.service.SAVE_FILTER,
        )
        if not filename:
            return False
        return self._write(Path(filename))

    def _write(self, path: str | Path) -> bool:
        try:
            self.window.project.touch()
            target = self.service.save_native(self.window.project, path)
        except Exception as exc:
            self._error("Project save failed", exc)
            return False
        self.state.native_path = target
        self.state.source_path = target
        self.state.source_format = "ROSS Studio"
        self.state.clean_fingerprint = project_fingerprint(self.window.project)
        self._update_identity()
        self._set_status(
            "Project saved",
            str(target),
            units="ROSS Studio schema v1 · atomic write",
        )
        return True

    def _replace_project(self, result: ProjectOpenResult, *, clean: bool) -> None:
        from .pages.bearing_studio import BearingStudioPage
        from .pages.empty_bearing_studio import EmptyBearingStudioPage
        from .pages.results import AnalysisResultsPage
        from .pages.rotor_model import RotorModelPage

        window = self.window
        WORKSPACE_SELECTION.clear()
        old_pages = []
        for page_name in ("rotor_page", "bearing_page", "results_page"):
            page = getattr(window, page_name, None)
            if page is not None:
                window.stack.removeWidget(page)
                page.close()
                old_pages.append(page)

        window.project = result.model
        window.bearing_index = 0
        engineering = result.model.engineering
        has_bearing_station = bool(engineering is not None and engineering.bearings)
        window.bearing = (
            BearingModel.from_project(engineering, 0)
            if has_bearing_station
            else BearingModel(name="No bearing station")
        )
        window.bearing_context = None
        window.bearing_field_result = None
        window.bearing_calculation = None

        window.rotor_page = RotorModelPage(result.model)
        if has_bearing_station:
            window.bearing_page = BearingStudioPage(
                result.model,
                window.bearing,
                catalog=window.catalog,
                bearing_index=window.bearing_index,
            )
        else:
            window.bearing_page = EmptyBearingStudioPage(result.model)
        window.results_page = AnalysisResultsPage(result.model)
        window.stack.addWidget(window.rotor_page)
        window.stack.addWidget(window.bearing_page)
        window.stack.addWidget(window.results_page)
        window.rotor_page.run_requested.connect(window.run_analysis)
        window.rotor_page.validate_requested.connect(window.validate_model)
        window._wire_bearing_page()

        # Defer destruction only after the new page graph and signal connections are
        # complete. Bound QObject slots then disconnect automatically and no global
        # selection signal can observe a half-rebuilt workspace.
        for page in old_pages:
            page.deleteLater()

        self.state.native_path = result.native_path
        self.state.source_path = result.source_path
        self.state.source_format = result.source_format
        self.state.clean_fingerprint = project_fingerprint(result.model) if clean else ""
        self._update_identity()
        window.sidebar.set_active("rotor")
        window.stack.setCurrentWidget(window.rotor_page)

    def _update_identity(self) -> None:
        window = self.window
        window.setWindowTitle(f"ROSS STUDIO | {window.project.name}")
        title_labels = window.findChildren(QLabel, "projectTitle")
        for label in title_labels:
            label.setText(window.project.name)
        window.status.project = window.project
        window.status.project_label.setText(window.project.name)


def controller_for_window(window: Any | None = None) -> ProjectFileController | None:
    if window is None:
        app = QApplication.instance()
        window = app.activeWindow() if app is not None else None
    if window is None or not hasattr(window, "project") or not hasattr(window, "stack"):
        return None
    controller = getattr(window, "_project_file_controller", None)
    if controller is None:
        controller = ProjectFileController(window)
        setattr(window, "_project_file_controller", controller)
    return controller


def dispatch_project_command(command: str, window: Any | None = None) -> bool:
    controller = controller_for_window(window)
    if controller is None:
        return False
    handler = {
        "new": controller.new,
        "open": controller.open,
        "import": controller.import_legacy,
        "save": controller.save,
        "save_as": controller.save_as,
    }.get(command)
    if handler is None:
        raise KeyError(command)
    return bool(handler())


__all__ = [
    "ProjectFileController", "ProjectFileState", "controller_for_window", "dispatch_project_command",
]
