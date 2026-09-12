from __future__ import annotations

from copy import deepcopy
from typing import Any

from PySide6.QtCore import QObject, QThread, Signal, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..domain import RotorProject
from ..models import ProjectModel
from ..page_registry import route_spec
from ..plotly_native_view import NativeRossFigureView
from ..project_io import project_fingerprint
from ..time_frequency_analysis import (
    ClearanceRequest,
    ClearanceService,
    FrequencyResponseRequest,
    FrequencyResponseService,
    HarmonicBalanceRequest,
    HarmonicBalanceService,
    TimeResponseRequest,
    TimeResponseService,
    UCSRequest,
    UCSService,
    UnbalanceResponseRequest,
    UnbalanceResponseService,
)
from ..time_frequency_native import (
    AMB_TIME_PLOT_LABELS,
    ClearanceNativeCatalog,
    FREQUENCY_PLOT_LABELS,
    FrequencyResponseNativeCatalog,
    HBM_PLOT_LABELS,
    HarmonicBalanceNativeCatalog,
    TIME_PLOT_LABELS,
    TimeResponseNativeCatalog,
    UCSNativeCatalog,
    UCS_PLOT_LABELS,
    UNBALANCE_PLOT_LABELS,
    UnbalanceResponseNativeCatalog,
)
from ..widgets import Card, SectionCard
from .architecture_workspaces import AnalysisRoutePage
from ..result_validity import ResultValidityGuard
from .faults_workspace import FaultsWorkspace
from .amb_sensitivity_workspace import AMBSensitivityWorkspace


_SERVICES = {
    "frequency": FrequencyResponseService,
    "unbalance": UnbalanceResponseService,
    "time": TimeResponseService,
    "hbm": HarmonicBalanceService,
    "ucs": UCSService,
    "clearance": ClearanceService,
}
_CATALOGS = {
    "frequency": FrequencyResponseNativeCatalog,
    "unbalance": UnbalanceResponseNativeCatalog,
    "time": TimeResponseNativeCatalog,
    "hbm": HarmonicBalanceNativeCatalog,
    "ucs": UCSNativeCatalog,
    "clearance": ClearanceNativeCatalog,
}


class _Worker(QObject):
    succeeded = Signal(str, object, str)
    failed = Signal(str, str, str)
    progress = Signal(str, str, str)
    finished = Signal(str)

    def __init__(self, kind: str, project: RotorProject, request: object, fingerprint: str) -> None:
        super().__init__()
        self.kind = kind
        self.project = project
        self.request = request
        self.fingerprint = fingerprint

    @Slot()
    def run(self) -> None:
        thread = QThread.currentThread()
        try:
            result = _SERVICES[self.kind]().run(
                self.project,
                self.request,
                progress=lambda stage, state: self.progress.emit(self.kind, stage, state),
                cancelled=thread.isInterruptionRequested,
            )
        except Exception as exc:
            self.failed.emit(self.kind, str(exc), self.fingerprint)
        else:
            self.succeeded.emit(self.kind, result, self.fingerprint)
        finally:
            self.finished.emit(self.kind)


class _Header(Card):
    def __init__(self) -> None:
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        title = QLabel("Time & Frequency · Native ROSS Results")
        title.setObjectName("cardHeader")
        root.addWidget(title)
        subtitle = QLabel(
            "ROSS Studio 0.21 executes Frequency Response, Unbalance Response, Time Response, "
            "Harmonic Balance, UCS, Clearance, Faults and AMB sensitivity as native ROSS 2.3.0 transactions. "
            "The native result object is cached; changing plot type, units, probe/orbit node or "
            "deflected-shape speed is post-processing only and never re-runs the scientific solve."
        )
        subtitle.setWordWrap(True)
        subtitle.setObjectName("muted")
        root.addWidget(subtitle)


class TimeFrequencyWorkspacePage(AnalysisRoutePage):
    """0.21 workspace exposing the native ROSS Time/Frequency result surface."""

    def __init__(self, project: ProjectModel, parent: QWidget | None = None) -> None:
        QWidget.__init__(self, parent)
        self.project = project
        self.spec = route_spec("analysis.time_frequency")
        self._results: dict[str, Any] = {}
        self._catalogs: dict[str, Any] = {}
        self._fingerprints: dict[str, str] = {}
        self._request_keys: dict[str, tuple[object, ...]] = {}
        self._threads: dict[str, QThread] = {}
        self._workers: dict[str, _Worker] = {}
        self._states: dict[str, QLabel] = {}
        self._buttons: dict[str, QPushButton] = {}
        self._views: dict[str, NativeRossFigureView] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)
        root.addWidget(_Header())
        self.tabs = QTabWidget()
        self.tabs.addTab(self._frequency_tab(), "Frequency Response")
        self.tabs.addTab(self._unbalance_tab(), "Unbalance Response")
        self.tabs.addTab(self._time_tab(), "Time Response")
        self.tabs.addTab(self._hbm_tab(), "Harmonic Balance")
        self.tabs.addTab(self._ucs_tab(), "UCS Map")
        self.tabs.addTab(self._clearance_tab(), "Clearance")
        self.tabs.addTab(FaultsWorkspace(self.project), "Faults")
        self.tabs.addTab(AMBSensitivityWorkspace(self.project), "AMB Sensitivity")
        self.validity_guard = ResultValidityGuard(self, self.invalidate_for_project_change)
        root.addWidget(self.tabs, 1)

    def _engineering(self) -> RotorProject | None:
        return self.project.engineering

    @staticmethod
    def _double(value: float, minimum: float = 0.0, maximum: float = 1e12, decimals: int = 4) -> QDoubleSpinBox:
        box = QDoubleSpinBox()
        box.setRange(minimum, maximum)
        box.setDecimals(decimals)
        box.setValue(float(value))
        return box

    @staticmethod
    def _spin(value: int, minimum: int, maximum: int, step: int = 1) -> QSpinBox:
        box = QSpinBox()
        box.setRange(minimum, maximum)
        box.setSingleStep(step)
        box.setValue(value)
        return box

    @staticmethod
    def _dof_combo(default: int = 0) -> QComboBox:
        combo = QComboBox()
        for index, name in enumerate(("x", "y", "z", "α", "β", "θ")):
            combo.addItem(f"{name} · local {index}", index)
        combo.setCurrentIndex(default)
        return combo

    def _default_position(self) -> float:
        engineering = self._engineering()
        if engineering is not None:
            if engineering.probes:
                return float(engineering.probes[0].position_mm)
            if engineering.bearings:
                return float(engineering.bearings[0].position_mm)
        return 0.0

    def _actions(self, kind: str, text: str) -> QVBoxLayout:
        layout = QVBoxLayout()
        button = QPushButton(text)
        button.setObjectName("primaryButton")
        button.clicked.connect(lambda _checked=False, k=kind: self._run(k))
        state = QLabel("Cache: empty")
        state.setWordWrap(True)
        state.setObjectName("muted")
        layout.addWidget(button)
        layout.addWidget(state)
        layout.addStretch(1)
        self._buttons[kind] = button
        self._states[kind] = state
        return layout

    def _result_panel(self, kind: str, controls: QHBoxLayout | None = None) -> QWidget:
        page = QWidget()
        root = QVBoxLayout(page)
        if controls is not None:
            root.addLayout(controls)
        export = QHBoxLayout()
        label = QLabel("Native ROSS figure · controls above do not trigger a re-solve")
        label.setObjectName("muted")
        export.addWidget(label)
        export.addStretch(1)
        html = QPushButton("Export HTML")
        png = QPushButton("Export PNG")
        html.clicked.connect(lambda _checked=False, k=kind: self._export(k, "html"))
        png.clicked.connect(lambda _checked=False, k=kind: self._export(k, "png"))
        export.addWidget(html)
        export.addWidget(png)
        root.addLayout(export)
        view = NativeRossFigureView()
        self._views[kind] = view
        root.addWidget(view, 1)
        return page

    def _invalidate_signal(self, kind: str, *widgets: QWidget) -> None:
        for widget in widgets:
            for name in ("valueChanged", "toggled", "currentIndexChanged", "textChanged"):
                signal = getattr(widget, name, None)
                if signal is not None:
                    signal.connect(lambda *_args, k=kind: self._invalidate(k, "analysis inputs changed"))
                    break

    @staticmethod
    def _refresh_signal(widget: QWidget, callback) -> None:
        for name in ("valueChanged", "toggled", "currentIndexChanged", "textChanged"):
            signal = getattr(widget, name, None)
            if signal is not None:
                signal.connect(lambda *_args: callback())
                return

    def _invalidate(self, kind: str, reason: str) -> None:
        if kind not in self._results:
            return
        self._results.pop(kind, None)
        self._catalogs.pop(kind, None)
        self._fingerprints.pop(kind, None)
        self._request_keys.pop(kind, None)
        self._states[kind].setText(f"Cache invalidated: {reason}")
        self._views[kind].set_unavailable(f"Native ROSS result invalidated: {reason}. Run this analysis again.")

    def invalidate_for_project_change(self) -> None:
        """Public hook used by the shell/model editor when rotor physics changes."""
        for kind in tuple(self._results):
            self._invalidate(kind, "ROTOR MODEL changed")

    def _invalidate_if_project_changed(self) -> None:
        fingerprint = project_fingerprint(self.project)
        for kind, saved in tuple(self._fingerprints.items()):
            if saved != fingerprint:
                self._invalidate(kind, "ROTOR MODEL changed")

    def _request(self, kind: str) -> object:
        return {
            "frequency": self._frequency_request,
            "unbalance": self._unbalance_request,
            "time": self._time_request,
            "hbm": self._hbm_request,
            "ucs": self._ucs_request,
            "clearance": self._clearance_request,
        }[kind]()

    def _run(self, kind: str) -> None:
        thread = self._threads.get(kind)
        if thread is not None and thread.isRunning():
            return
        engineering = self._engineering()
        if engineering is None:
            self._states[kind].setText("Analysis rejected: project has no engineering RotorProject.")
            return
        try:
            self._invalidate_if_project_changed()
            request = self._request(kind)
            request.validate()
            fingerprint = project_fingerprint(self.project)
            request_key = request.cache_key()
        except Exception as exc:
            self._states[kind].setText(f"Input rejected: {exc}")
            return
        if (
            kind in self._results
            and self._fingerprints.get(kind) == fingerprint
            and self._request_keys.get(kind) == request_key
        ):
            self._states[kind].setText("Cache hit · native ROSS result retained; no scientific re-solve.")
            self._refresh(kind)
            return

        self._buttons[kind].setEnabled(False)
        self._states[kind].setText("Building strict ROSS Rotor...")
        thread = QThread(self)
        worker = _Worker(kind, deepcopy(engineering), request, fingerprint)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._progress)
        worker.succeeded.connect(self._success)
        worker.failed.connect(self._failure)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(lambda k=kind: self._thread_finished(k))
        self._threads[kind] = thread
        self._workers[kind] = worker
        thread.start()

    @Slot(str, str, str)
    def _progress(self, kind: str, stage: str, state: str) -> None:
        self._states[kind].setText(f"{stage}: {state}")

    @Slot(str, object, str)
    def _success(self, kind: str, result: object, fingerprint: str) -> None:
        if project_fingerprint(self.project) != fingerprint:
            self._states[kind].setText("Result discarded: ROTOR MODEL changed while the analysis was running.")
            return
        self._results[kind] = result
        self._catalogs[kind] = _CATALOGS[kind](result)
        self._fingerprints[kind] = fingerprint
        self._request_keys[kind] = result.request.cache_key()
        self._states[kind].setText(f"Native ROSS result ready · {result.total_elapsed_s:.2f} s")
        if kind == "ucs":
            count = self._catalogs[kind].critical_mode_count
            self.ucs_critical_mode.setRange(0, max(0, count - 1))
            self.ucs_critical_mode.setEnabled(count > 0)
        if kind == "clearance":
            self._fill_clearance_table()
        self._refresh(kind)

    @Slot(str, str, str)
    def _failure(self, kind: str, message: str, fingerprint: str) -> None:
        prefix = "Stale analysis failed" if project_fingerprint(self.project) != fingerprint else "Analysis failed"
        self._states[kind].setText(f"{prefix}: {message}")

    def _thread_finished(self, kind: str) -> None:
        thread = self._threads.pop(kind, None)
        self._workers.pop(kind, None)
        self._buttons[kind].setEnabled(True)
        if thread is not None:
            thread.deleteLater()

    def _refresh(self, kind: str) -> None:
        {
            "frequency": self._refresh_frequency,
            "unbalance": self._refresh_unbalance,
            "time": self._refresh_time,
            "hbm": self._refresh_hbm,
            "ucs": self._refresh_ucs,
            "clearance": self._refresh_clearance,
        }[kind]()

    def _export(self, kind: str, fmt: str) -> None:
        catalog = self._catalogs.get(kind)
        view = self._views.get(kind)
        figure = None if view is None else view.figure
        if catalog is None or figure is None:
            self._states[kind].setText("Export rejected: run the analysis and select a native ROSS figure first.")
            return
        suffix = ".html" if fmt == "html" else ".png"
        filename, _ = QFileDialog.getSaveFileName(self, "Export native ROSS figure", f"{kind}{suffix}", f"*{suffix}")
        if not filename:
            return
        try:
            if fmt == "html":
                catalog.export_html(figure, filename)
            else:
                catalog.export_png(figure, filename)
            self._states[kind].setText(f"Native ROSS figure exported: {filename}")
        except Exception as exc:
            self._states[kind].setText(f"Export failed: {exc}")

    # Frequency Response -------------------------------------------------
    def _frequency_tab(self) -> QWidget:
        page = QWidget()
        root = QVBoxLayout(page)
        setup = SectionCard("Frequency Response · Rotor.run_freq_response()")
        row = QHBoxLayout()
        form = QFormLayout()
        self.fr_min = self._double(max(0, self.project.speed_min_rpm), maximum=1e7, decimals=2); self.fr_min.setSuffix(" rpm")
        self.fr_max = self._double(max(self.project.speed_max_rpm, self.project.speed_rpm), maximum=1e7, decimals=2); self.fr_max.setSuffix(" rpm")
        self.fr_points = self._spin(101, 3, 5001)
        p = self._default_position()
        self.fr_input_pos = self._double(p, maximum=max(self.project.total_length_mm, 1.0), decimals=3); self.fr_input_pos.setSuffix(" mm")
        self.fr_output_pos = self._double(p, maximum=max(self.project.total_length_mm, 1.0), decimals=3); self.fr_output_pos.setSuffix(" mm")
        self.fr_input_dof = self._dof_combo(1)
        self.fr_output_dof = self._dof_combo(1)
        self.fr_free_free = QCheckBox("Free-free transfer matrix")
        for label, widget in (
            ("Minimum", self.fr_min), ("Maximum", self.fr_max), ("Samples", self.fr_points),
            ("Input x", self.fr_input_pos), ("Input DOF", self.fr_input_dof),
            ("Output x", self.fr_output_pos), ("Output DOF", self.fr_output_dof),
            ("Boundary", self.fr_free_free),
        ):
            form.addRow(label, widget)
        row.addLayout(form, 1)
        row.addLayout(self._actions("frequency", "Run Frequency Response"))
        setup.root.addLayout(row)
        root.addWidget(setup)

        controls = QHBoxLayout()
        self.fr_output = QComboBox()
        for key, label in FREQUENCY_PLOT_LABELS.items(): self.fr_output.addItem(label, key)
        self.fr_freq_units = QComboBox(); self.fr_freq_units.addItems(["RPM", "rad/s", "Hz"])
        self.fr_amp_units = QComboBox(); self.fr_amp_units.addItems(["m/N", "um/N", "m/s/N", "mm/s/N", "m/s**2/N"])
        self.fr_phase_units = QComboBox(); self.fr_phase_units.addItems(["deg", "rad"])
        for label, widget in (("Output", self.fr_output), ("Frequency", self.fr_freq_units), ("Response", self.fr_amp_units), ("Phase", self.fr_phase_units)):
            controls.addWidget(QLabel(label)); controls.addWidget(widget); self._refresh_signal(widget, self._refresh_frequency)
        controls.addStretch(1)
        root.addWidget(self._result_panel("frequency", controls), 1)
        self._invalidate_signal("frequency", self.fr_min, self.fr_max, self.fr_points, self.fr_input_pos, self.fr_output_pos, self.fr_input_dof, self.fr_output_dof, self.fr_free_free)
        return page

    def _frequency_request(self) -> FrequencyResponseRequest:
        return FrequencyResponseRequest(
            self.fr_min.value(), self.fr_max.value(), self.fr_points.value(),
            self.fr_input_pos.value(), int(self.fr_input_dof.currentData()),
            self.fr_output_pos.value(), int(self.fr_output_dof.currentData()), free_free=self.fr_free_free.isChecked(),
        )

    def _refresh_frequency(self) -> None:
        catalog = self._catalogs.get("frequency")
        if catalog is None: return
        try:
            figure = catalog.figure(
                str(self.fr_output.currentData()), frequency_units=self.fr_freq_units.currentText(),
                amplitude_units=self.fr_amp_units.currentText(), phase_units=self.fr_phase_units.currentText(),
            )
            self._views["frequency"].set_figure(figure, tooltip="Native ROSS FrequencyResponseResults")
        except Exception as exc:
            self._views["frequency"].set_unavailable(f"Native ROSS frequency-response output unavailable: {exc}")

    # Unbalance Response -------------------------------------------------
    def _unbalance_tab(self) -> QWidget:
        page = QWidget(); root = QVBoxLayout(page)
        setup = SectionCard("Unbalance Response · Rotor.run_unbalance_response()")
        row = QHBoxLayout(); form = QFormLayout()
        self.ub_min = self._double(max(0, self.project.speed_min_rpm), maximum=1e7, decimals=2); self.ub_min.setSuffix(" rpm")
        self.ub_max = self._double(max(self.project.speed_max_rpm, self.project.speed_rpm), maximum=1e7, decimals=2); self.ub_max.setSuffix(" rpm")
        self.ub_points = self._spin(101, 3, 5001)
        for label, widget in (("Minimum", self.ub_min), ("Maximum", self.ub_max), ("Samples", self.ub_points)): form.addRow(label, widget)
        note = QLabel("Uses every project load with kind='unbalance' and the project probe definitions.")
        note.setWordWrap(True); note.setObjectName("muted"); form.addRow(note)
        row.addLayout(form, 1); row.addLayout(self._actions("unbalance", "Run Unbalance Response")); setup.root.addLayout(row)
        root.addWidget(setup)
        controls = QHBoxLayout()
        self.ub_output = QComboBox()
        for key, label in UNBALANCE_PLOT_LABELS.items(): self.ub_output.addItem(label, key)
        self.ub_speed = self._double(self.project.speed_rpm, maximum=1e7, decimals=2); self.ub_speed.setSuffix(" rpm")
        self.ub_freq_units = QComboBox(); self.ub_freq_units.addItems(["RPM", "rad/s", "Hz"])
        self.ub_amp_units = QComboBox(); self.ub_amp_units.addItems(["m", "um", "mm", "m/s", "mm/s", "m/s**2"])
        self.ub_phase_units = QComboBox(); self.ub_phase_units.addItems(["deg", "rad"])
        for label, widget in (("Output", self.ub_output), ("Shape speed", self.ub_speed), ("Frequency", self.ub_freq_units), ("Amplitude", self.ub_amp_units), ("Phase", self.ub_phase_units)):
            controls.addWidget(QLabel(label)); controls.addWidget(widget); self._refresh_signal(widget, self._refresh_unbalance)
        controls.addStretch(1)
        root.addWidget(self._result_panel("unbalance", controls), 1)
        self._invalidate_signal("unbalance", self.ub_min, self.ub_max, self.ub_points)
        return page

    def _unbalance_request(self) -> UnbalanceResponseRequest:
        return UnbalanceResponseRequest(self.ub_min.value(), self.ub_max.value(), self.ub_points.value())

    def _refresh_unbalance(self) -> None:
        catalog = self._catalogs.get("unbalance")
        if catalog is None: return
        try:
            figure = catalog.figure(
                str(self.ub_output.currentData()), speed_rpm=self.ub_speed.value(),
                frequency_units=self.ub_freq_units.currentText(), amplitude_units=self.ub_amp_units.currentText(),
                phase_units=self.ub_phase_units.currentText(),
            )
            self._views["unbalance"].set_figure(figure, tooltip="Native ROSS ForcedResponseResults")
        except Exception as exc:
            self._views["unbalance"].set_unavailable(f"Native ROSS unbalance output unavailable: {exc}")

    # Time Response ------------------------------------------------------
    def _time_tab(self) -> QWidget:
        page = QWidget(); root = QVBoxLayout(page)
        setup = SectionCard("Time Response · Rotor.run_time_response()")
        row = QHBoxLayout(); form = QFormLayout()
        self.tr_start = self._double(self.project.speed_rpm, maximum=1e7, decimals=2); self.tr_start.setSuffix(" rpm")
        self.tr_end = self._double(self.project.speed_rpm, maximum=1e7, decimals=2); self.tr_end.setSuffix(" rpm")
        self.tr_duration = self._double(1.0, 1e-6, 1e5, 4); self.tr_duration.setSuffix(" s")
        self.tr_samples = self._spin(1001, 5, 200000)
        self.tr_method = QComboBox(); self.tr_method.addItem("Newmark", "newmark"); self.tr_method.addItem("State-space / default", "default")
        self.tr_unbalance = QCheckBox("Project unbalance"); self.tr_unbalance.setChecked(True)
        self.tr_gravity = QCheckBox("Gravity")
        self.tr_harmonic_pos = self._double(self._default_position(), maximum=max(self.project.total_length_mm, 1.0), decimals=3); self.tr_harmonic_pos.setSuffix(" mm")
        self.tr_harmonic_omega = self._double(0.0, maximum=1e7); self.tr_harmonic_omega.setSuffix(" rad/s")
        self.tr_harmonic_x = self._double(0.0, -1e12, 1e12); self.tr_harmonic_x.setSuffix(" N")
        self.tr_harmonic_y = self._double(0.0, -1e12, 1e12); self.tr_harmonic_y.setSuffix(" N")
        self.tr_harmonic_phase = self._double(0.0, -3600, 3600, 2); self.tr_harmonic_phase.setSuffix(" deg")
        for label, widget in (
            ("Start speed", self.tr_start), ("End speed", self.tr_end), ("Duration", self.tr_duration),
            ("Samples", self.tr_samples), ("Integrator", self.tr_method), ("Forces", self.tr_unbalance),
            ("", self.tr_gravity), ("Harmonic x", self.tr_harmonic_pos), ("Harmonic ω", self.tr_harmonic_omega),
            ("Fx amplitude", self.tr_harmonic_x), ("Fy amplitude", self.tr_harmonic_y), ("Force phase", self.tr_harmonic_phase),
        ):
            form.addRow(label, widget)
        row.addLayout(form, 1); row.addLayout(self._actions("time", "Run Time Response")); setup.root.addLayout(row)
        root.addWidget(setup)
        controls = QHBoxLayout()
        self.tr_output = QComboBox()
        for key, label in TIME_PLOT_LABELS.items():
            self.tr_output.addItem(label, key)
        engineering = self._engineering()
        if engineering is not None and any(
            bearing.ross_class == "MagneticBearingElement" for bearing in engineering.bearings
        ):
            for key, label in AMB_TIME_PLOT_LABELS.items():
                self.tr_output.addItem(label, key)
        self.tr_node = self._spin(0, 0, 100000)
        self.tr_disp_units = QComboBox(); self.tr_disp_units.addItems(["m", "um", "mm"])
        self.tr_freq_units = QComboBox(); self.tr_freq_units.addItems(["Hz", "rad/s", "RPM"])
        for label, widget in (("Output", self.tr_output), ("Orbit node", self.tr_node), ("Displacement", self.tr_disp_units), ("DFFT frequency", self.tr_freq_units)):
            controls.addWidget(QLabel(label)); controls.addWidget(widget); self._refresh_signal(widget, self._refresh_time)
        controls.addStretch(1)
        root.addWidget(self._result_panel("time", controls), 1)
        self._invalidate_signal("time", self.tr_start, self.tr_end, self.tr_duration, self.tr_samples, self.tr_method, self.tr_unbalance, self.tr_gravity, self.tr_harmonic_pos, self.tr_harmonic_omega, self.tr_harmonic_x, self.tr_harmonic_y, self.tr_harmonic_phase)
        return page

    def _time_request(self) -> TimeResponseRequest:
        return TimeResponseRequest(
            self.tr_start.value(), self.tr_end.value(), self.tr_duration.value(), self.tr_samples.value(),
            str(self.tr_method.currentData()), self.tr_unbalance.isChecked(), self.tr_gravity.isChecked(),
            self.tr_harmonic_pos.value(), self.tr_harmonic_omega.value(), self.tr_harmonic_x.value(),
            self.tr_harmonic_y.value(), self.tr_harmonic_phase.value(),
        )

    def _refresh_time(self) -> None:
        catalog = self._catalogs.get("time")
        if catalog is None: return
        try:
            figure = catalog.figure(
                str(self.tr_output.currentData()), node=self.tr_node.value(),
                displacement_units=self.tr_disp_units.currentText(), frequency_units=self.tr_freq_units.currentText(),
            )
            self._views["time"].set_figure(figure, tooltip="Native ROSS TimeResponseResults")
        except Exception as exc:
            self._views["time"].set_unavailable(f"Native ROSS time-response output unavailable: {exc}")

    # Harmonic Balance ---------------------------------------------------
    def _hbm_tab(self) -> QWidget:
        page = QWidget(); root = QVBoxLayout(page)
        setup = SectionCard("Harmonic Balance · Rotor.run_harmonic_balance_response()")
        row = QHBoxLayout(); form = QFormLayout()
        self.hb_speed = self._double(self.project.speed_rpm, maximum=1e7, decimals=2); self.hb_speed.setSuffix(" rpm")
        self.hb_duration = self._double(1.0, 1e-6, 1e5, 4); self.hb_duration.setSuffix(" s")
        self.hb_samples = self._spin(1001, 9, 200000)
        self.hb_n = self._spin(3, 1, 32)
        self.hb_gravity = QCheckBox("Include gravity")
        self.hb_unbalance = QCheckBox("Project unbalance as 1X"); self.hb_unbalance.setChecked(True)
        self.hb_pos = self._double(self._default_position(), maximum=max(self.project.total_length_mm, 1.0), decimals=3); self.hb_pos.setSuffix(" mm")
        self.hb_mag = QLineEdit(""); self.hb_mag.setPlaceholderText("N, e.g. 1, 10, 5")
        self.hb_phase = QLineEdit(""); self.hb_phase.setPlaceholderText("deg, e.g. 0, 0, 0")
        self.hb_orders = QLineEdit(""); self.hb_orders.setPlaceholderText("e.g. 1, 2, 3")
        for label, widget in (
            ("Speed", self.hb_speed), ("Reconstruction duration", self.hb_duration), ("Samples", self.hb_samples),
            ("Harmonics retained", self.hb_n), ("Gravity", self.hb_gravity), ("Unbalance", self.hb_unbalance),
            ("Direct-force x", self.hb_pos), ("Direct magnitudes", self.hb_mag), ("Direct phases", self.hb_phase),
            ("Direct orders", self.hb_orders),
        ):
            form.addRow(label, widget)
        row.addLayout(form, 1); row.addLayout(self._actions("hbm", "Run Harmonic Balance")); setup.root.addLayout(row)
        root.addWidget(setup)
        controls = QHBoxLayout()
        self.hb_output = QComboBox()
        for key, label in HBM_PLOT_LABELS.items(): self.hb_output.addItem(label, key)
        self.hb_node = self._spin(0, 0, 100000)
        self.hb_amp_units = QComboBox(); self.hb_amp_units.addItems(["m", "um", "mm"])
        self.hb_freq_units = QComboBox(); self.hb_freq_units.addItems(["Hz", "rad/s", "RPM"])
        for label, widget in (("Output", self.hb_output), ("Orbit node", self.hb_node), ("Amplitude", self.hb_amp_units), ("Frequency", self.hb_freq_units)):
            controls.addWidget(QLabel(label)); controls.addWidget(widget); self._refresh_signal(widget, self._refresh_hbm)
        controls.addStretch(1)
        root.addWidget(self._result_panel("hbm", controls), 1)
        self._invalidate_signal("hbm", self.hb_speed, self.hb_duration, self.hb_samples, self.hb_n, self.hb_gravity, self.hb_unbalance, self.hb_pos, self.hb_mag, self.hb_phase, self.hb_orders)
        return page

    @staticmethod
    def _csv_floats(text: str) -> tuple[float, ...]:
        return tuple(float(v.strip()) for v in text.replace(";", ",").split(",") if v.strip())

    @staticmethod
    def _csv_ints(text: str) -> tuple[int, ...]:
        return tuple(int(v.strip()) for v in text.replace(";", ",").split(",") if v.strip())

    def _hbm_request(self) -> HarmonicBalanceRequest:
        magnitudes = self._csv_floats(self.hb_mag.text())
        phases = self._csv_floats(self.hb_phase.text())
        orders = self._csv_ints(self.hb_orders.text())
        if magnitudes and not phases: phases = tuple(0.0 for _ in magnitudes)
        if magnitudes and not orders: orders = tuple(range(1, len(magnitudes) + 1))
        return HarmonicBalanceRequest(
            self.hb_speed.value(), self.hb_duration.value(), self.hb_samples.value(), self.hb_n.value(),
            self.hb_gravity.isChecked(), self.hb_unbalance.isChecked(), self.hb_pos.value(), magnitudes, phases, orders,
        )

    def _refresh_hbm(self) -> None:
        catalog = self._catalogs.get("hbm")
        if catalog is None: return
        try:
            figure = catalog.figure(
                str(self.hb_output.currentData()), node=self.hb_node.value(),
                amplitude_units=self.hb_amp_units.currentText(), frequency_units=self.hb_freq_units.currentText(),
            )
            self._views["hbm"].set_figure(figure, tooltip="Native ROSS HarmonicBalanceResults")
        except Exception as exc:
            self._views["hbm"].set_unavailable(f"Native ROSS HBM output unavailable: {exc}")

    # UCS ---------------------------------------------------------------
    def _ucs_tab(self) -> QWidget:
        page = QWidget(); root = QVBoxLayout(page)
        setup = SectionCard("Undamped Critical Speed Map · Rotor.run_ucs()")
        row = QHBoxLayout(); form = QFormLayout()
        self.ucs_start = self._double(6.0, -12, 20, 2)
        self.ucs_end = self._double(11.0, -12, 20, 2)
        self.ucs_num = self._spin(20, 3, 200)
        self.ucs_modes = self._spin(16, 4, 128, 2)
        self.ucs_sync = QCheckBox("Synchronous")
        for label, widget in (("log10(K) start", self.ucs_start), ("log10(K) end", self.ucs_end), ("Stiffness samples", self.ucs_num), ("Eigenvalues", self.ucs_modes), ("Mode selection", self.ucs_sync)):
            form.addRow(label, widget)
        row.addLayout(form, 1); row.addLayout(self._actions("ucs", "Run UCS Map")); setup.root.addLayout(row)
        root.addWidget(setup)
        controls = QHBoxLayout()
        self.ucs_output = QComboBox()
        for key, label in UCS_PLOT_LABELS.items(): self.ucs_output.addItem(label, key)
        self.ucs_critical_mode = self._spin(0, 0, 0); self.ucs_critical_mode.setEnabled(False)
        self.ucs_freq_units = QComboBox(); self.ucs_freq_units.addItems(["rad/s", "RPM", "Hz"])
        for label, widget in (("Output", self.ucs_output), ("Critical intersection", self.ucs_critical_mode), ("Frequency", self.ucs_freq_units)):
            controls.addWidget(QLabel(label)); controls.addWidget(widget); self._refresh_signal(widget, self._refresh_ucs)
        controls.addStretch(1)
        root.addWidget(self._result_panel("ucs", controls), 1)
        self._invalidate_signal("ucs", self.ucs_start, self.ucs_end, self.ucs_num, self.ucs_modes, self.ucs_sync)
        return page

    def _ucs_request(self) -> UCSRequest:
        modes = self.ucs_modes.value()
        if modes % 2: modes += 1
        return UCSRequest(self.ucs_start.value(), self.ucs_end.value(), self.ucs_num.value(), modes, self.ucs_sync.isChecked())

    def _refresh_ucs(self) -> None:
        catalog = self._catalogs.get("ucs")
        if catalog is None: return
        try:
            figure = catalog.figure(
                str(self.ucs_output.currentData()), critical_mode=self.ucs_critical_mode.value(),
                frequency_units=self.ucs_freq_units.currentText(),
            )
            self._views["ucs"].set_figure(figure, tooltip="Native ROSS UCSResults")
        except Exception as exc:
            self._views["ucs"].set_unavailable(f"Native ROSS UCS output unavailable: {exc}")

    # Clearance ---------------------------------------------------------
    def _clearance_tab(self) -> QWidget:
        page = QWidget(); root = QVBoxLayout(page)
        setup = SectionCard("Clearance Analysis · Rotor.run_clearance_analysis()")
        row = QHBoxLayout(); form = QFormLayout()
        self.cl_speed = self._double(self.project.speed_rpm, 1e-6, 1e7, 2); self.cl_speed.setSuffix(" rpm")
        self.cl_band = self._double(10.0, 0.0, 100.0, 2); self.cl_band.setSuffix(" %")
        self.cl_points = self._spin(21, 1, 401)
        form.addRow("Operating speed", self.cl_speed); form.addRow("Frequency band ±", self.cl_band); form.addRow("Samples", self.cl_points)
        note = QLabel(
            "Requires explicit radial_clearance_m from Bearing Studio. Clearance is never inferred from K/C. "
            "ROSS 2.3 native clearance is blocked for auxiliary flexible-support BearingElements to avoid non-physical rows."
        )
        note.setWordWrap(True); note.setObjectName("muted"); form.addRow(note)
        row.addLayout(form, 1); row.addLayout(self._actions("clearance", "Run Clearance Analysis")); setup.root.addLayout(row)
        root.addWidget(setup)
        self.cl_table = QTableWidget(0, 4)
        self.cl_table.setHorizontalHeaderLabels(["Bearing node", "Vibration [µm pkpk]", "Clearance [µm]", "75% [µm]"])
        self.cl_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        root.addWidget(self.cl_table)
        root.addWidget(self._result_panel("clearance"), 1)
        self._invalidate_signal("clearance", self.cl_speed, self.cl_band, self.cl_points)
        return page

    def _clearance_request(self) -> ClearanceRequest:
        return ClearanceRequest(self.cl_speed.value(), self.cl_band.value(), self.cl_points.value())

    def _fill_clearance_table(self) -> None:
        catalog = self._catalogs.get("clearance")
        if catalog is None: return
        rows = catalog.rows()
        self.cl_table.setRowCount(len(rows))
        for r, values in enumerate(rows):
            for c, value in enumerate(values):
                self.cl_table.setItem(r, c, QTableWidgetItem(str(int(value)) if c == 0 else f"{value:.6g}"))
        self.cl_table.resizeColumnsToContents()

    def _refresh_clearance(self) -> None:
        catalog = self._catalogs.get("clearance")
        if catalog is None: return
        try:
            self._views["clearance"].set_figure(catalog.figure(), tooltip="Native ROSS ClearanceResults.plot")
        except Exception as exc:
            self._views["clearance"].set_unavailable(f"Native ROSS clearance output unavailable: {exc}")

    def closeEvent(self, event) -> None:  # noqa: N802
        for thread in tuple(self._threads.values()):
            if thread.isRunning():
                thread.requestInterruption()
                thread.quit()
                thread.wait(5000)
        super().closeEvent(event)


__all__ = ["TimeFrequencyWorkspacePage"]
