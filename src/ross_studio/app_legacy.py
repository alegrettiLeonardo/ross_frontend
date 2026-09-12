from __future__ import annotations

from copy import deepcopy
import sys

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .bearing_dispatch import BearingCalculationContext, BearingServiceDispatcher
from .bearing_studio_service import BearingCalculationResult, BearingStudioService
from .bearing_workspace import BearingWorkspaceService
from .icons import engineering_icon
from .models import BearingCoefficientRow, BearingModel, ProjectModel, load_reference_project_model
from .pages.bearing_studio import BearingStudioPage
from .pages.results import AnalysisResultsPage
from .pages.rotor_model import RotorModelPage
from .services import BearingCatalogService, EngineeringValidationService
from .solver_console import SolverConsole
from .thd_bearing_service import THDBearingCalculationResult, THDBearingStudioService
from .thd_calculation_dialog import THDCalculationDialog
from .theme import APP_STYLESHEET
from .thrust_pad_service import ThrustPadCalculationResult, ThrustPadStudioService
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
        sep.setStyleSheet("color:#c8dceb;font-size:20px;")
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
        self.bearing_workspace = BearingWorkspaceService()
        self.bearing_index = 0
        self.bearing = (
            BearingModel.from_project(self.project.engineering, self.bearing_index)
            if self.project.engineering
            else BearingModel()
        )
        self.catalog = BearingCatalogService()
        self.bearing_service = BearingStudioService(self.catalog.registry.ross_module)
        self.thd_bearing_service = THDBearingStudioService(self.catalog.registry.ross_module)
        self.thrust_pad_service = ThrustPadStudioService(self.catalog.registry.ross_module)
        self.bearing_dispatcher = BearingServiceDispatcher(
            self.bearing_service,
            self.thd_bearing_service,
            self.thrust_pad_service,
        )
        self.bearing_context: BearingCalculationContext | None = None
        self.bearing_field_result: THDBearingCalculationResult | ThrustPadCalculationResult | None = None
        self.bearing_calculation: BearingCalculationResult | THDBearingCalculationResult | ThrustPadCalculationResult | None = None
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
        self.bearing_page = BearingStudioPage(
            self.project,
            self.bearing,
            catalog=self.catalog,
            bearing_index=self.bearing_index,
        )
        self.results_page = AnalysisResultsPage(self.project)
        self.stack.addWidget(self.rotor_page)
        self.stack.addWidget(self.bearing_page)
        self.stack.addWidget(self.results_page)

        self.sidebar.page_requested.connect(self._navigate)
        self.rotor_page.run_requested.connect(self.run_analysis)
        self.rotor_page.validate_requested.connect(self.validate_model)
        self._wire_bearing_page()
        self.sidebar.set_active("rotor")

    def _wire_bearing_page(self) -> None:
        self.bearing_page.status_message.connect(lambda text: self.status.set_status(text))
        self.bearing_page.bearing_selected.connect(self._select_bearing)
        self.bearing_page.calculate_button.clicked.connect(self._calculate_bearing)
        self.bearing_page.apply_button.clicked.connect(self._apply_bearing)
        self.bearing_page.group_selector.currentTextChanged.connect(lambda _text: self._bearing_type_changed())
        for button in self.bearing_page.type_buttons.values():
            button.clicked.connect(self._bearing_type_changed)
        self.bearing_page.apply_button.setEnabled(self.bearing_calculation is not None)

    def _bearing_type_changed(self) -> None:
        self.bearing_calculation = None
        self.bearing_context = None
        self.bearing_field_result = None
        self.bearing_page.apply_button.setEnabled(False)
        self.bearing_page.set_results_available(False)

    def _select_bearing(self, index: int) -> None:
        engineering = self.project.engineering
        if engineering is None:
            self.status.set_status("Bearing selection failed", "Engineering domain is not loaded")
            return
        try:
            resolved = self.bearing_workspace.resolve_index(engineering, index)
            station = self.bearing_workspace.station(engineering, resolved)
        except Exception as exc:
            self.status.set_status("Bearing selection failed", str(exc))
            return
        if resolved == self.bearing_index:
            return

        self.bearing_calculation = None
        self.bearing_context = None
        self.bearing_field_result = None
        self.bearing_index = resolved
        self.bearing = BearingModel.from_project(engineering, resolved)
        self._refresh_bearing_page(
            selected_class=self.bearing.ross_class,
            keep_result=False,
            group=self.bearing.group,
        )
        self.stack.setCurrentWidget(self.bearing_page)
        support = f" · support {', '.join(station.support_names)}" if station.support_names else ""
        self.status.set_status(
            "Bearing station selected",
            f"#{resolved + 1} {station.name} · x={station.position_mm:g} mm · ROSS node {station.ross_node}{support}",
            units="Edit visible inputs → Calculate preview → Apply this station",
        )

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

    def _refresh_bearing_page(
        self,
        *,
        selected_class: str | None = None,
        keep_result: bool = False,
        group: str | None = None,
    ) -> None:
        old = self.bearing_page
        was_current = self.stack.currentWidget() is old
        index = self.stack.indexOf(old)
        selected_group = group or old.current_group.value
        self.stack.removeWidget(old)
        old.deleteLater()
        self.bearing_page = BearingStudioPage(
            self.project,
            self.bearing,
            catalog=self.catalog,
            bearing_index=self.bearing_index,
        )
        self.stack.insertWidget(index, self.bearing_page)
        self._wire_bearing_page()
        self.bearing_page.set_group(selected_group, announce=False)
        if selected_class is not None:
            key = self._bearing_key_for_class(self.bearing_page, selected_class)
            if key is not None:
                target_group = self.bearing_page.type_metadata[key][2].value
                if self.bearing_page.current_group.value != target_group:
                    self.bearing_page.set_group(target_group, announce=False)
                self.bearing_page._select_type(key, announce=False)
        self.bearing_page.apply_button.setEnabled(bool(keep_result and self.bearing_calculation is not None))
        if self.bearing.coefficients:
            self.bearing_page.set_bearing_preview(self.bearing)
        if self.bearing_field_result is not None and self.bearing_field_result.source_model == selected_class:
            if isinstance(self.bearing_field_result, ThrustPadCalculationResult):
                self.bearing_page.set_thrust_result(self.bearing_field_result)
            else:
                self.bearing_page.set_thd_result(self.bearing_field_result)
        if was_current:
            self.stack.setCurrentWidget(self.bearing_page)

    def _preview_bearing_result(
        self,
        result: BearingCalculationResult | THDBearingCalculationResult | ThrustPadCalculationResult,
        bearing_index: int,
    ) -> None:
        if self.project.engineering is None:
            return
        base = BearingModel.from_project(self.project.engineering, bearing_index)
        base.ross_class = result.source_model
        titles = {
            "BearingElement": "Coefficient K/C",
            "BallBearingElement": "Ball Bearing",
            "RollerBearingElement": "Roller Bearing",
            "CylindricalBearing": "Cylindrical Bearing",
            "PlainJournal": "Plain Journal",
            "TiltingPad": "Tilting Pad",
            "SqueezeFilmDamper": "Squeeze Film Damper",
            "ThrustPad": "Axial Thrust Pad",
            "MagneticBearingElement": "Active Magnetic Bearing",
        }
        base.bearing_type = titles.get(result.source_model, result.source_model)

        if isinstance(result, ThrustPadCalculationResult):
            base.coefficients = []
            base.speed_min_rpm = round(result.axial_coefficients[0].rpm)
            base.speed_max_rpm = round(result.axial_coefficients[-1].rpm)
            self.bearing = base
            return

        if result.coefficients:
            base.coefficients = [BearingCoefficientRow.from_point(point) for point in result.coefficients]
            base.speed_min_rpm = round(result.coefficients[0].rpm)
            base.speed_max_rpm = round(result.coefficients[-1].rpm)
        else:
            if not isinstance(result, BearingCalculationResult):
                raise ValueError("THD preview requires a solved coefficient table.")
            kxx, kxy, kyx, kyy, cxx, cxy, cyx, cyy = result.scalar_kc
            base.coefficients = [
                BearingCoefficientRow(
                    rpm=self.project.speed_rpm,
                    kxx=kxx,
                    kxy=kxy,
                    kyx=kyx,
                    kyy=kyy,
                    cxx=cxx,
                    cxy=cxy,
                    cyx=cyx,
                    cyy=cyy,
                )
            ]
            base.speed_min_rpm = self.project.speed_rpm
            base.speed_max_rpm = self.project.speed_rpm
        self.bearing = base

    def _calculate_bearing(self) -> None:
        """Calculate from the visible inline editor without opening an input dialog."""
        engineering = self.project.engineering
        if engineering is None:
            self.status.set_status("Bearing calculation failed", "Engineering domain is not loaded")
            return
        ross_class = self._selected_bearing_class()
        if ross_class is None:
            self.status.set_status("Bearing calculation failed", "No bearing class is selected")
            return

        try:
            bearing_index = self.bearing_workspace.resolve_index(engineering, self.bearing_index)
            station = self.bearing_workspace.station(engineering, bearing_index)
        except Exception as exc:
            self.status.set_status("Bearing calculation failed", str(exc))
            return

        self.bearing_calculation = None
        self.bearing_context = None
        self.bearing_field_result = None
        self.bearing_page.apply_button.setEnabled(False)
        self.bearing_page.set_results_available(False)
        try:
            service = self.bearing_dispatcher.for_class(ross_class)
            inputs = self.bearing_page.input_values()
            snapshot = deepcopy(engineering)
            if ross_class in THDBearingStudioService.SUPPORTED_CLASSES | ThrustPadStudioService.SUPPORTED_CLASSES:
                result = THDCalculationDialog(
                    service,
                    snapshot,
                    bearing_index,
                    ross_class,
                    inputs,
                    self,
                ).calculate()
            else:
                result = service.calculate(snapshot, bearing_index, ross_class, inputs)
            self._preview_bearing_result(result, bearing_index)
        except Exception as exc:
            self.status.set_status("Bearing calculation failed", str(exc))
            return

        self.bearing_calculation = result
        self.bearing_context = BearingCalculationContext(service, result, bearing_index, snapshot)
        self.bearing_field_result = result if isinstance(result, (THDBearingCalculationResult, ThrustPadCalculationResult)) else None

        # Update only result widgets. Rebuilding the complete page here would erase
        # the inline engineering values the user has just entered.
        self.bearing_page.set_bearing_preview(self.bearing)
        if isinstance(result, ThrustPadCalculationResult):
            self.bearing_page.set_thrust_result(result)
        elif isinstance(result, THDBearingCalculationResult):
            self.bearing_page.set_thd_result(result)
        else:
            self.bearing_page.set_results_available(True)
        self.bearing_page.apply_button.setEnabled(True)

        count = (
            len(result.axial_coefficients)
            if isinstance(result, ThrustPadCalculationResult)
            else len(result.coefficients)
        )
        self.status.set_status(
            f"{result.source_model} calculated for {station.name}",
            f"{count} solved speed station(s)" if count else "Scalar K/C calculated",
            units=f"Preview only — use View Results or scroll; Apply commits bearing #{bearing_index + 1}",
        )

    def _apply_bearing(self) -> None:
        engineering = self.project.engineering
        result = self.bearing_calculation
        context = self.bearing_context
        if engineering is None or result is None or context is None:
            self.status.set_status("Bearing not applied", "Calculate the selected bearing model first")
            return
        try:
            if context.bearing_index != self.bearing_index:
                raise ValueError("The selected bearing station has changed; calculate again before Apply.")
            if result is not context.result or self._selected_bearing_class() != result.source_model:
                raise ValueError("The selected class has changed; calculate again before Apply.")
            if engineering != context.project_snapshot:
                raise ValueError("The rotor inputs have changed since Calculate; calculate again before Apply.")
            candidate = deepcopy(engineering)
            applied = context.service.apply(candidate, context.bearing_index, result)
            issues = self.validation_service.validate(candidate)
            errors = [issue for issue in issues if issue.severity == "error"]
            if errors:
                raise ValueError(errors[0].message)
        except Exception as exc:
            self.status.set_status("Bearing apply failed", str(exc))
            return

        if isinstance(result, ThrustPadCalculationResult):
            engineering.bearings = candidate.bearings
            applied_index = next(
                i
                for i, bearing in enumerate(engineering.bearings)
                if bearing.metadata.get("source_model") == "ThrustPad"
                and abs(float(bearing.position_mm) - float(applied.position_mm)) <= 1e-9
            )
            selected_index = context.bearing_index
        else:
            engineering.bearings[context.bearing_index] = applied
            applied_index = context.bearing_index
            selected_index = context.bearing_index

        self.bearing_context = None
        note = result.note
        source_model = result.source_model
        application_class = applied.ross_class
        self.project.touch()
        self.bearing_index = selected_index
        self.bearing = BearingModel.from_project(engineering, selected_index)
        self.bearing_calculation = None
        self._refresh_bearing_page(
            selected_class=source_model,
            keep_result=False,
            group=self.bearing.group,
        )
        target = (
            f"station #{selected_index + 1} {self.bearing.name}; axial element #{applied_index + 1}"
            if isinstance(result, ThrustPadCalculationResult)
            else f"bearing #{applied_index + 1} {self.bearing.name}"
        )
        self.status.set_status(
            "Bearing applied to rotor",
            f"{target}: {source_model} → {application_class}. {note}",
            units="Only the selected bearing transaction was committed; rerun analyses to refresh rotor results",
        )

    def _navigate(self, key: str) -> None:
        if key == "bearings":
            self.stack.setCurrentWidget(self.bearing_page)
            self.status.set_status(
                "Bearing Studio 2.0 ready",
                f"Selected bearing #{self.bearing_index + 1}: {self.bearing.name}",
                units="Select station → model icon → edit inputs → Calculate → Results → Apply",
            )
            return
        if key in self.RESULT_KEYS:
            self.stack.setCurrentWidget(self.results_page)
            state = "Real ROSS results loaded" if self.results_page.result is not None else "No real analysis executed"
            self.status.set_status("Results workspace", state, units="Units: SI (mm, kg, N, Hz, rpm)")
            return
        self.stack.setCurrentWidget(self.rotor_page)
        self.rotor_page.select_editor(key)
        self.status.set_status(
            "Engineering model loaded",
            f"{self.project.physical_sections} physical sections → {self.project.ross_shaft_elements} ROSS ShaftElements",
            units="Units: SI (mm, kg, N)",
        )

    def _open_bearing_group(self, group: str) -> None:
        """Compatibility entry point for automated qualification and older callers."""
        requested = str(group)
        if self.bearing_page.current_group.value != requested:
            self.bearing_calculation = None
            self.bearing_context = None
            self.bearing_field_result = None
        self.bearing_page.set_group(group)
        self.bearing_page.apply_button.setEnabled(self.bearing_calculation is not None)
        self.stack.setCurrentWidget(self.bearing_page)
        self.status.set_status(
            f"Bearing family: {group}",
            f"Target #{self.bearing_index + 1}: {self.bearing.name}",
        )

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
            self.status.set_status(
                "Model valid with engineering gates",
                f"{len(warnings)} readiness warning(s); first: {warnings[0].code}",
            )
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
