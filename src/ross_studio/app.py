from __future__ import annotations

import sys

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QMainWindow, QPushButton, QStackedWidget, QVBoxLayout, QWidget

from .icons import engineering_icon
from .models import BearingModel, ProjectModel, load_reference_project_model
from .pages.bearing_groups import BearingGroupsPage
from .pages.bearing_studio import BearingStudioPage
from .pages.results import AnalysisResultsPage
from .pages.rotor_model import RotorModelPage
from .services import BearingCatalogService, EngineeringValidationService
from .solver_console import SolverConsole
from .theme import APP_STYLESHEET
from .widgets import AppToolbar, Sidebar, StatusBar


class TitleBar(QFrame):
    def __init__(self, window: QMainWindow, project: ProjectModel) -> None:
        super().__init__(window)
        self.window = window
        self.setObjectName("titleBar")
        self.setFixedHeight(55)
        self._drag_position: QPoint | None = None
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 6, 8, 6)
        layout.setSpacing(10)
        brand_icon = QLabel()
        brand_icon.setPixmap(engineering_icon("brand", 27).pixmap(27, 27))
        layout.addWidget(brand_icon)
        brand = QLabel("ROSS STUDIO")
        brand.setObjectName("brandLabel")
        layout.addWidget(brand)
        sep = QLabel("|")
        sep.setStyleSheet("color:#9eb9cf;font-size:20px;")
        layout.addWidget(sep)
        proj = QLabel(project.name)
        proj.setObjectName("projectTitle")
        layout.addWidget(proj)
        layout.addStretch(1)
        minimize = QPushButton("—")
        minimize.setObjectName("windowButton")
        minimize.clicked.connect(window.showMinimized)
        layout.addWidget(minimize)
        maximize = QPushButton("□")
        maximize.setObjectName("windowButton")
        maximize.clicked.connect(self._toggle_max)
        layout.addWidget(maximize)
        close = QPushButton("×")
        close.setObjectName("windowCloseButton")
        close.clicked.connect(window.close)
        layout.addWidget(close)

    def _toggle_max(self) -> None:
        self.window.showNormal() if self.window.isMaximized() else self.window.showMaximized()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_position = event.globalPosition().toPoint() - self.window.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag_position is not None and event.buttons() & Qt.MouseButton.LeftButton and not self.window.isMaximized():
            self.window.move(event.globalPosition().toPoint() - self._drag_position)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._drag_position = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._toggle_max()
        super().mouseDoubleClickEvent(event)


class RossStudioWindow(QMainWindow):
    MODEL_EDITOR_KEYS = {"rotor", "shaft", "disks", "seals", "supports", "couplings", "loads", "probes", "home"}
    RESULT_KEYS = {"rotor_dynamics", "response", "stability", "transient", "faults", "stochastic", "results"}

    def __init__(self) -> None:
        super().__init__()
        self.project = load_reference_project_model()
        self.bearing = BearingModel.from_project(self.project.engineering) if self.project.engineering else BearingModel()
        self.catalog = BearingCatalogService()
        self.validation_service = EngineeringValidationService()
        self.setWindowTitle(f"ROSS STUDIO | {self.project.name}")
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.resize(1672, 941)
        self.setMinimumSize(1280, 760)

        root = QWidget()
        root.setObjectName("appRoot")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(TitleBar(self, self.project))
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        holder = QWidget()
        holder.setLayout(body)
        outer.addWidget(holder, 1)
        self.sidebar = Sidebar()
        body.addWidget(self.sidebar)
        work = QVBoxLayout()
        work.setContentsMargins(0, 0, 0, 0)
        work.setSpacing(0)
        work_holder = QWidget()
        work_holder.setLayout(work)
        body.addWidget(work_holder, 1)
        self.toolbar = AppToolbar()
        work.addWidget(self.toolbar)
        self.stack = QStackedWidget()
        work.addWidget(self.stack, 1)
        self.status = StatusBar(self.project)
        outer.addWidget(self.status)

        self.rotor_page = RotorModelPage(self.project)
        self.bearing_groups_page = BearingGroupsPage(self.project, self.catalog)
        self.bearing_page = BearingStudioPage(self.project, self.bearing)
        self.results_page = AnalysisResultsPage(self.project)
        self.stack.addWidget(self.rotor_page)
        self.stack.addWidget(self.bearing_groups_page)
        self.stack.addWidget(self.bearing_page)
        self.stack.addWidget(self.results_page)

        self.sidebar.page_requested.connect(self._navigate)
        self.bearing_groups_page.group_selected.connect(self._open_bearing_group)
        self.rotor_page.run_requested.connect(self.run_analysis)
        self.rotor_page.validate_requested.connect(self.validate_model)
        self.bearing_page.status_message.connect(lambda text: self.status.set_status(text))
        self.sidebar.set_active("rotor")

    def _navigate(self, key: str) -> None:
        if key == "bearings":
            self.stack.setCurrentWidget(self.bearing_groups_page)
            self.status.set_status("Bearing catalog ready", "Select General / Parametric, THD or AMB")
            return
        if key in self.RESULT_KEYS:
            self.stack.setCurrentWidget(self.results_page)
            state = "Real ROSS results loaded" if self.results_page.result is not None else "No real analysis executed"
            self.status.set_status("Results workspace", state, units="Units: SI (mm, kg, N, Hz, rpm)")
            return
        self.stack.setCurrentWidget(self.rotor_page)
        self.rotor_page.select_editor(key)
        self.status.set_status("Engineering model loaded", f"{self.project.physical_sections} physical sections → {self.project.ross_shaft_elements} ROSS ShaftElements", units="Units: SI (mm, kg, N)")

    def _open_bearing_group(self, group: str) -> None:
        if hasattr(self.bearing_page, "set_group"):
            self.bearing_page.set_group(group)
        self.stack.setCurrentWidget(self.bearing_page)
        self.status.set_status(f"Bearing group: {group}", "Class capability gating active")

    def validate_model(self) -> None:
        if self.project.engineering is None:
            self.status.set_status("Validation failed", "Engineering domain is not loaded")
            return
        issues = self.validation_service.validate(self.project.engineering)
        errors = [issue for issue in issues if issue.severity == "error"]
        warnings = [issue for issue in issues if issue.severity == "warning"]
        if errors:
            self.status.set_status("Model validation failed", errors[0].message)
        elif warnings:
            self.status.set_status("Model valid with engineering gates", f"{len(warnings)} readiness warning(s); first: {warnings[0].code}")
        else:
            self.status.set_status("Model validated", "No issues found")

    def run_analysis(self) -> None:
        dlg = SolverConsole(self.project, self)
        dlg.exec()
        result = dlg.analysis_result
        if result is not None:
            self.results_page.set_results(result)
            self.stack.setCurrentWidget(self.results_page)
            try:
                self.sidebar.set_active("results")
            except Exception:
                pass
            critical_text = (
                f"first critical {result.first_critical_rpm:,.1f} rpm"
                if result.first_critical_rpm is not None
                else "no 1X critical inside qualified K/C envelope"
            )
            self.status.set_status(
                "Real ROSS analysis completed",
                f"{len(result.modal_modes)} modal modes · {critical_text} · {len(result.probe_responses)} probe channels",
                units="Units: Hz, rpm, µm",
            )
        elif dlg.status.text() == "Failed":
            self.status.set_status("Analysis failed", dlg.status_detail.text())
        elif dlg.status.text() == "Stopped":
            self.status.set_status("Analysis stopped", "Cancelled between ROSS analysis stages")


def launch() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("ROSS Studio")
    app.setOrganizationName("ROSS Studio")
    app.setStyleSheet(APP_STYLESHEET)
    app.setFont(QFont("Segoe UI", 10))
    window = RossStudioWindow()
    window.show()
    return app.exec()
