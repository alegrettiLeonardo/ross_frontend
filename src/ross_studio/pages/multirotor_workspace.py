from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..domain import EngineeringError
from ..models import ProjectModel
from ..multirotor.analysis import (
    CampbellRequest,
    FrequencyResponseRequest,
    HarmonicBalanceRequest,
    ModalRequest,
    MultiRotorAnalysisService,
    TimeResponseRequest,
)
from ..multirotor.builder import MultiRotorBuilder
from ..multirotor.domain import GearConnection, GearModel, GearSpec, METHOD_QUALIFICATION, MultiRotorProject
from ..multirotor.io import load_multirotor_project, save_multirotor_project
from ..multirotor.native_results import MultiRotorNativeCatalog
from ..page_registry import route_spec
from ..plotly_native_view import NativeRossFigureView
from ..project_io import load_project
from ..widgets import Card
from .architecture_workspaces import AnalysisRoutePage


class _AnalysisWorker(QObject):
    done = Signal(object)
    failed = Signal(str)
    progress = Signal(str, str)
    finished = Signal()

    def __init__(self, project: MultiRotorProject, kind: str, request: object) -> None:
        super().__init__()
        self.project = project
        self.kind = kind
        self.request = request

    @Slot()
    def run(self) -> None:
        service = MultiRotorAnalysisService()
        try:
            fn = {
                "Modal": service.run_modal,
                "Campbell": service.run_campbell,
                "Frequency Response": service.run_frequency_response,
                "Time Response": service.run_time_response,
                "Harmonic Balance": service.run_harmonic_balance,
            }[self.kind]
            self.done.emit(fn(self.project, self.request, progress=self.progress.emit))
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")
        finally:
            self.finished.emit()


class MultiRotorWorkspacePage(AnalysisRoutePage):
    """Native ROSS 2.3 geared multi-shaft workspace with exact-node gear placement.

    It remains an ``AnalysisRoutePage`` subtype so the navigation ownership
    contract introduced in 0.17 stays intact while 0.23 supplies the executable
    scientific implementation.
    """

    def __init__(self, project: ProjectModel, parent: QWidget | None = None) -> None:
        # Do not call AnalysisRoutePage.__init__ because 0.23 replaces its planned
        # placeholder layout with the qualified executable workspace. QWidget is
        # still initialized exactly once through the inherited Qt base.
        QWidget.__init__(self, parent)
        self.project = project
        self.spec = route_spec("analysis.multirotor")
        self.multirotor = MultiRotorProject(
            f"{project.name} · MultiRotor",
            rotors=[deepcopy(project.engineering)] if project.engineering is not None else [],
        )
        self._thread = None
        self._worker = None
        self._result = None
        self._catalog = None

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        header = Card()
        header_layout = QVBoxLayout(header)
        title = QLabel("MultiRotor System · ROSS 2.3 native")
        title.setObjectName("cardHeader")
        note = QLabel(
            "Each shaft remains an independent RotorProject and is strict-built before native "
            "GearElement/GearElementTVMS and MultiRotor assembly. All requested speeds are driving-rotor "
            "speeds; driven speed/sign stays owned by ROSS check_speed(). Static, UCS and Level 1 remain blocked."
        )
        note.setWordWrap(True)
        note.setObjectName("muted")
        header_layout.addWidget(title)
        header_layout.addWidget(note)
        root.addWidget(header)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._system_tab(), "System")
        self.tabs.addTab(self._gear_tab(), "Gears")
        self.tabs.addTab(self._connection_tab(), "Gear Mesh")
        self.tabs.addTab(self._analysis_tab(), "Analysis")
        self.tabs.addTab(self._qualification_tab(), "Qualification")
        root.addWidget(self.tabs, 1)
        self._refresh_tables()

    def _system_tab(self):
        page = QWidget()
        root = QVBoxLayout(page)
        row = QHBoxLayout()
        add = QPushButton("Add RotorProject…")
        add.clicked.connect(self._add_rotor)
        open_mr = QPushButton("Open .rossmulti…")
        open_mr.clicked.connect(self._open_multirotor)
        save_mr = QPushButton("Save .rossmulti…")
        save_mr.clicked.connect(self._save_multirotor)
        build = QPushButton("Validate / Build native MultiRotor")
        build.setObjectName("primaryButton")
        build.clicked.connect(self._build)
        for widget in (add, open_mr, save_mr, build):
            row.addWidget(widget)
        row.addStretch(1)
        root.addLayout(row)
        self.rotor_table = QTableWidget(0, 4)
        self.rotor_table.setHorizontalHeaderLabels(["#", "RotorProject", "Length [mm]", "Strict shaft elements"])
        self.rotor_table.horizontalHeader().setStretchLastSection(True)
        root.addWidget(self.rotor_table)
        self.build_state = QLabel("Add at least two rotor projects, gears and N-1 ordered connections.")
        self.build_state.setWordWrap(True)
        self.build_state.setObjectName("muted")
        root.addWidget(self.build_state)
        return page

    def _gear_tab(self):
        page = QWidget()
        root = QVBoxLayout(page)
        form = QFormLayout()
        self.gear_rotor = QSpinBox()
        self.gear_rotor.setRange(0, 99)
        self.gear_position = QDoubleSpinBox()
        self.gear_position.setRange(0, 1e7)
        self.gear_position.setSuffix(" mm")
        self.gear_type = QComboBox()
        self.gear_type.addItems([GearModel.SIMPLE.value, GearModel.TVMS.value])
        self.gear_teeth = QSpinBox()
        self.gear_teeth.setRange(1, 10000)
        self.gear_teeth.setValue(20)
        self.gear_pitch = QDoubleSpinBox()
        self.gear_pitch.setRange(1e-6, 100)
        self.gear_pitch.setDecimals(6)
        self.gear_pitch.setValue(0.1)
        self.gear_pitch.setSuffix(" m")
        for label, widget in (
            ("Rotor index", self.gear_rotor),
            ("Exact x", self.gear_position),
            ("ROSS gear class", self.gear_type),
            ("Teeth", self.gear_teeth),
            ("Pitch diameter", self.gear_pitch),
        ):
            form.addRow(label, widget)
        root.addLayout(form)
        add = QPushButton("Add native gear")
        add.clicked.connect(self._add_gear)
        root.addWidget(add)
        self.gear_table = QTableWidget(0, 5)
        self.gear_table.setHorizontalHeaderLabels(["#", "Name", "Rotor", "x [mm]", "ROSS class"])
        self.gear_table.horizontalHeader().setStretchLastSection(True)
        root.addWidget(self.gear_table, 1)
        return page

    def _connection_tab(self):
        page = QWidget()
        root = QVBoxLayout(page)
        form = QFormLayout()
        self.drive_rotor = QSpinBox()
        self.drive_rotor.setRange(0, 99)
        self.driven_rotor = QSpinBox()
        self.driven_rotor.setRange(0, 99)
        self.driven_rotor.setValue(1)
        self.drive_gear = QSpinBox()
        self.drive_gear.setRange(0, 999)
        self.driven_gear = QSpinBox()
        self.driven_gear.setRange(0, 999)
        self.driven_gear.setValue(1)
        self.mesh_k = QDoubleSpinBox()
        self.mesh_k.setRange(0, 1e15)
        self.mesh_k.setValue(1e8)
        self.mesh_k.setSuffix(" N/m")
        self.orientation = QDoubleSpinBox()
        self.orientation.setRange(-360, 360)
        self.orientation.setSuffix(" deg")
        self.position = QComboBox()
        self.position.addItems(["above", "below"])
        for label, widget in (
            ("Driving rotor", self.drive_rotor),
            ("Driven rotor", self.driven_rotor),
            ("Driving gear index", self.drive_gear),
            ("Driven gear index", self.driven_gear),
            ("Mesh stiffness (0 = automatic TVMS)", self.mesh_k),
            ("Orientation", self.orientation),
            ("Relative position", self.position),
        ):
            form.addRow(label, widget)
        root.addLayout(form)
        add = QPushButton("Add ordered gear connection")
        add.clicked.connect(self._add_connection)
        root.addWidget(add)
        self.connection_table = QTableWidget(0, 6)
        self.connection_table.setHorizontalHeaderLabels(["#", "Driving", "Driven", "Gear pair", "Kmesh", "Orientation"])
        self.connection_table.horizontalHeader().setStretchLastSection(True)
        root.addWidget(self.connection_table, 1)
        return page

    def _analysis_tab(self):
        page = QWidget()
        root = QVBoxLayout(page)
        controls = QHBoxLayout()
        self.analysis_kind = QComboBox()
        self.analysis_kind.addItems(["Modal", "Campbell", "Frequency Response", "Time Response", "Harmonic Balance"])
        self.speed = QDoubleSpinBox()
        self.speed.setRange(0, 1e6)
        self.speed.setValue(max(0, self.project.speed_rpm))
        self.speed.setSuffix(" rpm")
        self.run_button = QPushButton("Run native ROSS analysis")
        self.run_button.setObjectName("primaryButton")
        self.run_button.clicked.connect(self._run_analysis)
        for widget in (QLabel("Analysis"), self.analysis_kind, QLabel("Driving speed"), self.speed, self.run_button):
            controls.addWidget(widget)
        controls.addStretch(1)
        root.addLayout(controls)
        self.analysis_state = QLabel("No MultiRotor result cached.")
        self.analysis_state.setObjectName("muted")
        self.analysis_state.setWordWrap(True)
        root.addWidget(self.analysis_state)
        self.plot_selector = QComboBox()
        self.plot_selector.currentIndexChanged.connect(self._render_plot)
        root.addWidget(self.plot_selector)
        self.result_view = NativeRossFigureView()
        root.addWidget(self.result_view, 1)
        return page

    def _qualification_tab(self):
        page = QWidget()
        root = QVBoxLayout(page)
        table = QTableWidget(len(METHOD_QUALIFICATION), 2)
        table.setHorizontalHeaderLabels(["ROSS MultiRotor method", "Status"])
        for row, (name, status) in enumerate(METHOD_QUALIFICATION.items()):
            table.setItem(row, 0, QTableWidgetItem(name))
            table.setItem(row, 1, QTableWidgetItem(status.value))
        table.horizontalHeader().setStretchLastSection(True)
        root.addWidget(table)
        msg = QLabel(
            "BLOCKED: run_static(), run_ucs(), run_level1(). EXPERIMENTAL: run_critical_speed(). "
            "Backlash options not present in the public ROSS 2.3.0 MultiRotor constructor are also blocked, never ignored."
        )
        msg.setWordWrap(True)
        root.addWidget(msg)
        return page

    def _refresh_tables(self):
        self.rotor_table.setRowCount(len(self.multirotor.rotors))
        for index, rotor in enumerate(self.multirotor.rotors):
            for column, value in enumerate((index, rotor.name, f"{rotor.total_length_mm:g}", rotor.ross_shaft_element_count)):
                self.rotor_table.setItem(index, column, QTableWidgetItem(str(value)))
        self.gear_table.setRowCount(len(self.multirotor.gears))
        for index, gear in enumerate(self.multirotor.gears):
            for column, value in enumerate((index, gear.name, gear.rotor_index, f"{gear.position_mm:g}", gear.model.value)):
                self.gear_table.setItem(index, column, QTableWidgetItem(str(value)))
        self.connection_table.setRowCount(len(self.multirotor.connections))
        for index, connection in enumerate(self.multirotor.connections):
            km = "AUTO" if connection.gear_mesh_stiffness is None else f"{connection.gear_mesh_stiffness:g}"
            values = (
                index,
                connection.driving_rotor_index,
                connection.driven_rotor_index,
                f"{connection.driving_gear_index} → {connection.driven_gear_index}",
                km,
                f"{connection.orientation_angle_deg:g}°",
            )
            for column, value in enumerate(values):
                self.connection_table.setItem(index, column, QTableWidgetItem(str(value)))

    def _add_rotor(self):
        path, _ = QFileDialog.getOpenFileName(self, "Add ROSS Studio rotor project", str(Path.home()), "ROSS Studio (*.rossproj)")
        if not path:
            return
        model = load_project(path)
        if model.engineering is None:
            self.build_state.setText("Rejected: selected project has no RotorProject engineering domain.")
            return
        self.multirotor.rotors.append(deepcopy(model.engineering))
        self._refresh_tables()

    def _add_gear(self):
        model = GearModel(self.gear_type.currentText())
        pitch = None if model == GearModel.TVMS else float(self.gear_pitch.value())
        spec = GearSpec(
            f"G{len(self.multirotor.gears)}",
            int(self.gear_rotor.value()),
            float(self.gear_position.value()),
            model=model,
            n_teeth=int(self.gear_teeth.value()),
            pitch_diameter_m=pitch,
        )
        try:
            spec.validate(len(self.multirotor.rotors))
        except Exception as exc:
            self.build_state.setText(str(exc))
            return
        self.multirotor.gears.append(spec)
        self._refresh_tables()

    def _add_connection(self):
        stiffness = float(self.mesh_k.value())
        self.multirotor.connections.append(
            GearConnection(
                int(self.drive_rotor.value()),
                int(self.driven_rotor.value()),
                int(self.drive_gear.value()),
                int(self.driven_gear.value()),
                gear_mesh_stiffness=None if stiffness == 0 else stiffness,
                orientation_angle_deg=float(self.orientation.value()),
                position=self.position.currentText(),
            )
        )
        self._refresh_tables()

    def _build(self):
        try:
            build = MultiRotorBuilder().build(self.multirotor)
            self.build_state.setText(
                f"PASS · native {build.rotor.__class__.__name__} · {len(self.multirotor.rotors)} shafts · ratios "
                + ", ".join(f"{ratio:.6g}" for ratio in build.connection_ratios)
            )
        except Exception as exc:
            self.build_state.setText(f"BLOCKED · {type(exc).__name__}: {exc}")

    def _save_multirotor(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save MultiRotor project", str(Path.home() / "system.rossmulti"), "ROSS MultiRotor (*.rossmulti)")
        if path:
            try:
                save_multirotor_project(self.multirotor, path)
                self.build_state.setText(f"Saved {path}")
            except Exception as exc:
                self.build_state.setText(str(exc))

    def _open_multirotor(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open MultiRotor project", str(Path.home()), "ROSS MultiRotor (*.rossmulti)")
        if path:
            try:
                self.multirotor = load_multirotor_project(path)
                self._refresh_tables()
                self.build_state.setText(f"Loaded {path}")
            except Exception as exc:
                self.build_state.setText(str(exc))

    def _request(self):
        kind = self.analysis_kind.currentText()
        speed = float(self.speed.value())
        if kind == "Modal":
            return ModalRequest(speed, 26)
        if kind == "Campbell":
            return CampbellRequest(0.0, max(speed, 100.0), 51, 13)
        if kind == "Frequency Response":
            return FrequencyResponseRequest(0.0, max(speed, 100.0), 101)
        if kind == "Time Response":
            return TimeResponseRequest(speed, 0.2, 1001)
        if kind == "Harmonic Balance":
            return HarmonicBalanceRequest(speed, 0.2, 501)
        raise EngineeringError(kind)

    def _run_analysis(self):
        if self._thread is not None and self._thread.isRunning():
            return
        try:
            self.multirotor.validate()
            request = self._request()
        except Exception as exc:
            self.analysis_state.setText(f"Input rejected: {exc}")
            return
        self.run_button.setEnabled(False)
        self.analysis_state.setText("Building strict native MultiRotor…")
        thread = QThread(self)
        worker = _AnalysisWorker(deepcopy(self.multirotor), self.analysis_kind.currentText(), request)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(lambda stage, state: self.analysis_state.setText(f"{stage}: {state}"))
        worker.done.connect(self._analysis_done)
        worker.failed.connect(self._analysis_failed)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(lambda: self.run_button.setEnabled(True))
        thread.finished.connect(thread.deleteLater)
        self._thread = thread
        self._worker = worker
        thread.start()

    @Slot(object)
    def _analysis_done(self, result):
        self._result = result
        self._catalog = MultiRotorNativeCatalog(result)
        self.analysis_state.setText(f"PASS · {result.kind} · {result.elapsed_s:.3f} s · native ROSS result retained")
        self.plot_selector.blockSignals(True)
        self.plot_selector.clear()
        self.plot_selector.addItems(self._catalog.available())
        self.plot_selector.blockSignals(False)
        self._render_plot()

    @Slot(str)
    def _analysis_failed(self, message):
        self.analysis_state.setText(f"FAILED · {message}")
        self.result_view.set_unavailable(message)

    def _render_plot(self):
        if self._catalog is None or self.plot_selector.count() == 0:
            return
        try:
            figure = self._catalog.figure(self.plot_selector.currentText())
        except Exception as exc:
            self.result_view.set_unavailable(f"Native plot requires additional probe/DOF selection: {exc}")
            return
        self.result_view.set_figure(figure, tooltip="Native ROSS MultiRotor result")


__all__ = ["MultiRotorWorkspacePage"]
