from __future__ import annotations

import sys

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QDialog, QFrame, QHBoxLayout, QLabel, QMainWindow, QPushButton, QStackedWidget, QVBoxLayout, QWidget

from .bearing_input_dialog import BearingInputDialog
from .bearing_studio_service import BearingCalculationResult, BearingStudioService
from .icons import engineering_icon
from .models import BearingCoefficientRow, BearingModel, ProjectModel, load_reference_project_model
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
        self.bearing_service = BearingStudioService(self.catalog.registry.ross_module)
        self.bearing_calculation: BearingCalculationResult | None = None
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
        self.bearing_page = BearingStudioPage(self.project, self.bearing, catalog=self.catalog)
        self.results_page = AnalysisResultsPage(self.project)
        self.stack.addWidget(self.rotor_page)
        self.stack.addWidget(self.bearing_groups_page)
        self.stack.addWidget(self.bearing_page)
        self.stack.addWidget(self.results_page)

        self.sidebar.page_requested.connect(self._navigate)
        self.bearing_groups_page.group_selected.connect(self._open_bearing_group)
        self.rotor_page.run_requested.connect(self.run_analysis)
        self.rotor_page.validate_requested.connect(self.validate_model)
        self._wire_bearing_page()
        self.sidebar.set_active("rotor")

    def _wire_bearing_page(self) -> None:
        self.bearing_page.status_message.connect(lambda text: self.status.set_status(text))
        self.bearing_page.calculate_button.clicked.connect(self._calculate_bearing)
        self.bearing_page.apply_button.clicked.connect(self._apply_bearing)
        for button in self.bearing_page.type_buttons.values():
            button.clicked.connect(self._bearing_type_changed)
        self.bearing_page.apply_button.setEnabled(self.bearing_calculation is not None)

    def _bearing_type_changed(self) -> None:
        # A calculation is valid only for the exact class/input state that created it.
        self.bearing_calculation = None
        self.bearing_page.apply_button.setEnabled(False)

    def _selected_bearing_class(self) -> str | None:
        for key, button in self.bearing_page.type_buttons.items():
            if button.isChecked():
                return self.bearing_page.type_metadata[key][1]
        return None

    @staticmethod
    def _bearing_key_for_class(page: BearingStudioPage, ross_class: str) -> str | None:
        for key, (_title, candidate, _group) in page.type_metadata.items():
            if candidate == ross_class:
                return key
        return None

    def _refresh_bearing_page(self, *, selected_class: str | None = None, keep_result: bool = False) -> None:
        old = self.bearing_page
        was_current = self.stack.currentWidget() is old
        index = self.stack.indexOf(old)
        group = old.current_group.value
        self.stack.removeWidget(old)
        old.deleteLater()
        self.bearing_page = BearingStudioPage(self.project, self.bearing, catalog=self.catalog)
        self.stack.insertWidget(index, self.bearing_page)
        self._wire_bearing_page()
        self.bearing_page.set_group(group, announce=False)
        if selected_class is not None:
            key = self._bearing_key_for_class(self.bearing_page, selected_class)
            if key is not None:
                self.bearing_page._select_type(key, announce=False)
        if keep_result and self.bearing_calculation is not None:
            self.bearing_page.apply_button.setEnabled(True)
        if was_current:
            self.stack.setCurrentWidget(self.bearing_page)

    def _preview_bearing_result(self, result: BearingCalculationResult) -> None:
        if self.project.engineering is None:
            return
        base = BearingModel.from_project(self.project.engineering, 0)
        base.ross_class = result.source_model
        titles = {
            "BearingElement": "Coefficient K/C",
            "BallBearingElement": "Ball Bearing",
            "RollerBearingElement": "Roller Bearing",
            "CylindricalBearing": "Cylindrical Bearing",
        }
        base.bearing_type = titles.get(result.source_model, result.source_model)
        if result.coefficients:
            base.coefficients = [BearingCoefficientRow.from_point(point) for point in result.coefficients]
            base.speed_min_rpm = round(result.coefficients[0].rpm)
            base.speed_max_rpm = round(result.coefficients[-1].rpm)
        else:
            kxx, kxy, kyx, kyy, cxx, cxy, cyx, cyy = result.scalar_kc
            base.coefficients = [BearingCoefficientRow(
                rpm=self.project.speed_rpm,
                kxx=kxx,
                kxy=kxy,
                kyx=kyx,
                kyy=kyy,
                cxx=cxx,
                cxy=cxy,
                cyx=cyx,
                cyy=cyy,
            )]
            base.speed_min_rpm = self.project.speed_rpm
            base.speed_max_rpm = self.project.speed_rpm
        self.bearing = base

    def _calculate_bearing(self) -> None:
        engineering = self.project.engineering
        if engineering is None:
            self.status.set_status("Bearing calculation failed", "Engineering domain is not loaded")
            return
        ross_class = self._selected_bearing_class()
        if ross_class is None:
            self.status.set_status("Bearing calculation failed", "No bearing class is selected")
            return

        inputs = {}
        if ross_class != "BearingElement":
            dialog = BearingInputDialog(engineering, 0, ross_class, self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                self.status.set_status("Bearing calculation cancelled", ross_class)
                return
            inputs = dialog.values()

        try:
            result = self.bearing_service.calculate(engineering, 0, ross_class, inputs)
        except Exception as exc:
            self.bearing_calculation = None
            self.bearing_page.apply_button.setEnabled(False)
            self.status.set_status("Bearing calculation failed", str(exc))
            return

        self.bearing_calculation = result
        self._preview_bearing_result(result)
        self._refresh_bearing_page(selected_class=result.source_model, keep_result=True)
        kxx, _kxy, _kyx, kyy, cxx, _cxy, _cyx, cyy = result.scalar_kc
        self.status.set_status(
            f"{result.source_model} calculated",
            f"Kxx={kxx:.4e} N/m · Kyy={kyy:.4e} N/m · Cxx={cxx:.4e} N·s/m · Cyy={cyy:.4e} N·s/m",
            units="Preview only — Apply to Rotor commits the bearing model",
        )

    def _apply_bearing(self) -> None:
        engineering = self.project.engineering
        result = self.bearing_calculation
        if engineering is None or result is None:
            self.status.set_status("Bearing not applied", "Calculate the selected bearing model first")
            return
        try:
            applied = self.bearing_service.apply(engineering, 0, result)
            issues = self.validation_service.validate(engineering)
            errors = [issue for issue in issues if issue.severity == "error"]
            if errors:
                raise ValueError(errors[0].message)
        except Exception as exc:
            self.status.set_status("Bearing apply failed", str(exc))
            return

        note = result.note
        source_model = result.source_model
        application_class = applied.ross_class
        self.project.touch()
        self.bearing = BearingModel.from_project(engineering, 0)
        self.bearing_calculation = None
        self._refresh_bearing_page(selected_class=source_model, keep_result=False)
        self.status.set_status(
            "Bearing applied to rotor",
            f"{source_model} → {application_class}. {note}",
            units="Engineering model updated; rerun analyses to refresh rotor results",
        )

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
