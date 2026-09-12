from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QThread, Signal, Slot, Qt
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
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..domain import EngineeringError, RotorProject
from ..result_validity import ResultValidityGuard
from ..models import ProjectModel
from ..page_registry import route_spec
from ..plotly_native_view import NativeRossFigureView
from ..project_io import project_fingerprint
from ..static_modal_analysis import StaticModalResult
from ..static_modal_decoupled import (
    ModalAnalysisRequest,
    ModalAnalysisResult,
    ModalAnalysisService,
    StaticAnalysisResult,
    StaticAnalysisService,
)
from ..static_modal_native import (
    STATIC_FIGURES,
    ModalNativeFigureCatalog,
    StaticNativeFigureCatalog,
)
from ..widgets import Card, SectionCard
from .architecture_workspaces import AnalysisRoutePage


class _StaticWorker(QObject):
    succeeded = Signal(object, str)
    failed = Signal(str, str)
    progress = Signal(str, str)
    finished = Signal()

    def __init__(self, project: RotorProject, fingerprint: str) -> None:
        super().__init__()
        self.project = project
        self.validity_guard = ResultValidityGuard(self, self._invalidate_if_project_changed)
        self.fingerprint = fingerprint

    @Slot()
    def run(self) -> None:
        thread = QThread.currentThread()
        try:
            result = StaticAnalysisService().run(
                self.project,
                progress=lambda stage, state: self.progress.emit(stage, state),
                cancelled=thread.isInterruptionRequested,
            )
        except Exception as exc:
            self.failed.emit(str(exc), self.fingerprint)
        else:
            self.succeeded.emit(result, self.fingerprint)
        finally:
            self.finished.emit()


class _ModalWorker(QObject):
    succeeded = Signal(object, str)
    failed = Signal(str, str)
    progress = Signal(str, str)
    finished = Signal()

    def __init__(self, project: RotorProject, request: ModalAnalysisRequest, fingerprint: str) -> None:
        super().__init__()
        self.project = project
        self.request = request
        self.fingerprint = fingerprint

    @Slot()
    def run(self) -> None:
        thread = QThread.currentThread()
        try:
            result = ModalAnalysisService().run(
                self.project,
                self.request,
                progress=lambda stage, state: self.progress.emit(stage, state),
                cancelled=thread.isInterruptionRequested,
            )
        except Exception as exc:
            self.failed.emit(str(exc), self.fingerprint)
        else:
            self.succeeded.emit(result, self.fingerprint)
        finally:
            self.finished.emit()


class _Header(Card):
    def __init__(self, title: str, subtitle: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(4)
        heading = QLabel(title)
        heading.setObjectName("cardHeader")
        root.addWidget(heading)
        text = QLabel(subtitle)
        text.setWordWrap(True)
        text.setObjectName("muted")
        root.addWidget(text)


class StaticModalWorkspacePage(AnalysisRoutePage):
    """0.20 workspace with independent Static and Modal/Campbell transactions.

    Static and Modal/Campbell own separate workers, caches, project fingerprints and
    invalidation rules. Modal input changes invalidate only Modal/Campbell; a valid
    Static result remains available. Any ROTOR MODEL change invalidates both caches.
    Native ROSS result objects continue to own every plotted curve and animation.
    """

    def __init__(
        self,
        project: ProjectModel,
        *,
        mode_filter: str = "Lateral",
        parent: QWidget | None = None,
    ) -> None:
        QWidget.__init__(self, parent)
        if mode_filter not in {"Lateral", "Torsional"}:
            raise ValueError(mode_filter)
        self.project = project
        self.mode_filter = mode_filter
        self.spec = route_spec(
            "analysis.static_modal.lateral" if mode_filter == "Lateral" else "analysis.static_modal.torsional"
        )

        self.static_result: StaticAnalysisResult | None = None
        self.modal_result: ModalAnalysisResult | None = None
        self.static_catalog: StaticNativeFigureCatalog | None = None
        self.modal_catalog: ModalNativeFigureCatalog | None = None
        self.static_fingerprint: str | None = None
        self.modal_fingerprint: str | None = None
        self.modal_request_key: tuple[object, ...] | None = None

        self._static_thread: QThread | None = None
        self._modal_thread: QThread | None = None
        self._static_worker: _StaticWorker | None = None
        self._modal_worker: _ModalWorker | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)
        title = "Lateral Static & Modal Analysis" if mode_filter == "Lateral" else "Torsional Modal Analysis"
        root.addWidget(
            _Header(
                title,
                "ROSS Studio 0.20 decoupled execution. Static uses its own Rotor.run_static() transaction; "
                "Modal/Campbell use a separate Rotor.run_modal()/run_campbell() transaction. Each cache is "
                "invalidated independently and native ROSS plots never trigger a scientific re-solve.",
            )
        )

        if self.mode_filter == "Lateral":
            root.addWidget(self._build_static_setup())
        root.addWidget(self._build_modal_setup())

        self.tabs = QTabWidget()
        self.static_tab: QWidget | None = None
        if self.mode_filter == "Lateral":
            self.static_tab = self._build_static_tab()
            self.tabs.addTab(self.static_tab, "Static Results")
        self.modal_tab = self._build_modal_tab()
        self.campbell_tab = self._build_campbell_tab()
        self.tabs.addTab(self.modal_tab, "Mode Shapes")
        self.tabs.addTab(self.campbell_tab, "Campbell")
        root.addWidget(self.tabs, 1)

        self._set_static_controls_enabled(False)
        self._set_modal_controls_enabled(False)

    def _build_static_setup(self) -> SectionCard:
        section = SectionCard("Static Analysis · independent transaction")
        row = QHBoxLayout()
        note = QLabel(
            "Runs only Rotor.run_static(). Modal and Campbell are not solved. The cached StaticResults object "
            "remains valid when only modal speed/eigenvalue settings are changed."
        )
        note.setWordWrap(True)
        note.setObjectName("muted")
        row.addWidget(note, 1)
        actions = QVBoxLayout()
        self.run_static_button = QPushButton("Run Static")
        self.run_static_button.setObjectName("primaryButton")
        self.run_static_button.clicked.connect(self.run_static)
        actions.addWidget(self.run_static_button)
        self.static_state = QLabel("Static cache: empty")
        self.static_state.setWordWrap(True)
        self.static_state.setObjectName("muted")
        actions.addWidget(self.static_state)
        row.addLayout(actions)
        section.root.addLayout(row)
        return section

    def _build_modal_setup(self) -> SectionCard:
        section = SectionCard("Modal & Campbell · independent transaction")
        row = QHBoxLayout()
        form = QFormLayout()
        self.speed_rpm = QDoubleSpinBox()
        self.speed_rpm.setRange(0.0, 1_000_000.0)
        self.speed_rpm.setDecimals(2)
        self.speed_rpm.setSuffix(" rpm")
        self.speed_rpm.setValue(float(self.project.speed_rpm))
        form.addRow("Modal speed", self.speed_rpm)

        self.num_modes = QSpinBox()
        self.num_modes.setRange(4, 128)
        self.num_modes.setSingleStep(2)
        self.num_modes.setValue(24)
        form.addRow("Eigenvalue count", self.num_modes)

        self.campbell_points = QSpinBox()
        self.campbell_points.setRange(5, 401)
        self.campbell_points.setValue(41)
        form.addRow("Campbell stations", self.campbell_points)

        self.campbell_frequencies = QSpinBox()
        self.campbell_frequencies.setRange(2, 32)
        self.campbell_frequencies.setValue(8)
        form.addRow("Campbell frequencies", self.campbell_frequencies)

        self.harmonics = QLineEdit("0.5, 1.0")
        self.harmonics.setToolTip("Plot-only harmonics. Changing this field does not re-run Rotor.run_campbell().")
        form.addRow("Plot harmonics", self.harmonics)
        row.addLayout(form, 1)

        actions = QVBoxLayout()
        self.run_modal_button = QPushButton("Run Modal & Campbell")
        self.run_modal_button.setObjectName("primaryButton")
        self.run_modal_button.clicked.connect(self.run_modal)
        actions.addWidget(self.run_modal_button)
        self.modal_state = QLabel("Modal/Campbell cache: empty")
        self.modal_state.setWordWrap(True)
        self.modal_state.setObjectName("muted")
        actions.addWidget(self.modal_state)
        actions.addStretch(1)
        row.addLayout(actions)
        section.root.addLayout(row)

        self.speed_rpm.valueChanged.connect(self._modal_inputs_changed)
        self.num_modes.valueChanged.connect(self._modal_inputs_changed)
        self.campbell_points.valueChanged.connect(self._modal_inputs_changed)
        self.campbell_frequencies.valueChanged.connect(self._modal_inputs_changed)

        # 0.19 compatibility aliases used by older UI smoke checks.
        self.run_button = self.run_modal_button
        self.run_state = self.modal_state
        return section

    def _build_static_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        controls = QHBoxLayout()
        self.static_selector = QComboBox()
        for key, spec in STATIC_FIGURES.items():
            self.static_selector.addItem(spec.title, key)
        self.static_selector.currentIndexChanged.connect(self._refresh_static_figure)
        controls.addWidget(QLabel("Native ROSS output"))
        controls.addWidget(self.static_selector)
        controls.addStretch(1)
        self.static_export_png_button = QPushButton("Export PNG")
        self.static_export_png_button.clicked.connect(self._choose_export_static_png)
        controls.addWidget(self.static_export_png_button)
        self.static_export_html_button = QPushButton("Export HTML")
        self.static_export_html_button.clicked.connect(self._choose_export_static_html)
        controls.addWidget(self.static_export_html_button)
        layout.addLayout(controls)
        self.static_view = NativeRossFigureView()
        layout.addWidget(self.static_view, 1)
        return page

    def _build_modal_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        controls = QHBoxLayout()
        self.mode_dimension = QComboBox()
        self.mode_dimension.addItems(["3D", "2D"])
        self.mode_dimension.currentTextChanged.connect(self._mode_dimension_changed)
        controls.addWidget(QLabel("View"))
        controls.addWidget(self.mode_dimension)

        self.mode_orientation = QComboBox()
        self.mode_orientation.addItem("Major axis", "major")
        self.mode_orientation.addItem("X", "x")
        self.mode_orientation.addItem("Y", "y")
        self.mode_orientation.currentIndexChanged.connect(self._refresh_mode_figure)
        self.mode_orientation.setEnabled(False)
        controls.addWidget(QLabel("2D orientation"))
        controls.addWidget(self.mode_orientation)

        self.animate = QCheckBox("Animate 3D")
        self.animate.setToolTip(
            "Uses ModalResults.plot_mode_3d(mode, animation=True). Plotly Play/Pause controls are supplied by ROSS."
        )
        self.animate.toggled.connect(self._refresh_mode_figure)
        controls.addWidget(self.animate)
        controls.addStretch(1)

        self.export_png_button = QPushButton("Export PNG")
        self.export_png_button.clicked.connect(self._choose_export_mode_png)
        controls.addWidget(self.export_png_button)
        self.export_html_button = QPushButton("Export HTML")
        self.export_html_button.setToolTip("HTML preserves the native Plotly animation and Play/Pause controls.")
        self.export_html_button.clicked.connect(self._choose_export_mode_html)
        controls.addWidget(self.export_html_button)
        layout.addLayout(controls)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.mode_table = QTableWidget(0, 7)
        self.mode_table.setHorizontalHeaderLabels(
            ["Mode", "Type", "wn [Hz]", "wd [Hz]", "Damping", "Log. Dec.", "Whirl"]
        )
        self.mode_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.mode_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.mode_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.mode_table.itemSelectionChanged.connect(self._refresh_mode_figure)
        self.mode_table.horizontalHeader().setStretchLastSection(True)
        splitter.addWidget(self.mode_table)
        self.mode_view = NativeRossFigureView()
        splitter.addWidget(self.mode_view)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([520, 980])
        layout.addWidget(splitter, 1)
        return page

    def _build_campbell_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        controls = QHBoxLayout()
        self.refresh_campbell_button = QPushButton("Refresh Native Campbell Plot")
        self.refresh_campbell_button.clicked.connect(self._refresh_campbell_figure)
        controls.addWidget(self.refresh_campbell_button)
        note = QLabel("Harmonics are plot-only; no scientific re-solve and no cache invalidation.")
        note.setObjectName("muted")
        controls.addWidget(note)
        controls.addStretch(1)
        layout.addLayout(controls)
        self.campbell_view = NativeRossFigureView()
        layout.addWidget(self.campbell_view, 1)
        return page

    def _set_static_controls_enabled(self, enabled: bool) -> None:
        if self.mode_filter != "Lateral":
            return
        self.static_selector.setEnabled(enabled)
        self.static_export_png_button.setEnabled(enabled)
        self.static_export_html_button.setEnabled(enabled)

    def _set_modal_controls_enabled(self, enabled: bool) -> None:
        self.mode_dimension.setEnabled(enabled)
        self.animate.setEnabled(enabled and self.mode_dimension.currentText() == "3D")
        self.mode_orientation.setEnabled(enabled and self.mode_dimension.currentText() == "2D")
        self.export_png_button.setEnabled(enabled)
        self.export_html_button.setEnabled(enabled)
        self.refresh_campbell_button.setEnabled(enabled)

    def _modal_request(self) -> ModalAnalysisRequest:
        value = int(self.num_modes.value())
        if value % 2:
            value += 1
        return ModalAnalysisRequest(
            speed_rpm=float(self.speed_rpm.value()),
            num_modes=value,
            campbell_points=int(self.campbell_points.value()),
            campbell_frequencies=int(self.campbell_frequencies.value()),
        )

    def _engineering_project(self) -> RotorProject | None:
        return self.project.engineering

    @Slot()
    def run_static(self) -> None:
        if self.mode_filter != "Lateral":
            return
        if self._static_thread is not None and self._static_thread.isRunning():
            return
        engineering = self._engineering_project()
        if engineering is None:
            self.static_state.setText("Static rejected: project has no engineering RotorProject.")
            return
        try:
            fingerprint = project_fingerprint(self.project)
        except Exception as exc:
            self.static_state.setText(f"Static input rejected: {exc}")
            return
        self._invalidate_if_project_changed()
        self.run_static_button.setEnabled(False)
        self.static_state.setText("Static transaction · building strict ROSS Rotor...")
        thread = QThread(self)
        worker = _StaticWorker(deepcopy(engineering), fingerprint)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._on_static_progress)
        worker.succeeded.connect(self._on_static_success)
        worker.failed.connect(self._on_static_failure)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(self._static_thread_finished)
        self._static_thread = thread
        self._static_worker = worker
        thread.start()

    @Slot()
    def run_modal(self) -> None:
        if self._modal_thread is not None and self._modal_thread.isRunning():
            return
        engineering = self._engineering_project()
        if engineering is None:
            self.modal_state.setText("Modal rejected: project has no engineering RotorProject.")
            return
        try:
            request = self._modal_request()
            request.validate()
            fingerprint = project_fingerprint(self.project)
        except Exception as exc:
            self.modal_state.setText(f"Modal input rejected: {exc}")
            return
        self._invalidate_if_project_changed()
        self.run_modal_button.setEnabled(False)
        self.modal_state.setText("Modal transaction · building strict ROSS Rotor...")
        thread = QThread(self)
        worker = _ModalWorker(deepcopy(engineering), request, fingerprint)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._on_modal_progress)
        worker.succeeded.connect(self._on_modal_success)
        worker.failed.connect(self._on_modal_failure)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(self._modal_thread_finished)
        self._modal_thread = thread
        self._modal_worker = worker
        thread.start()

    @Slot(str, str)
    def _on_static_progress(self, stage: str, state: str) -> None:
        self.static_state.setText(f"{stage}: {state}")

    @Slot(str, str)
    def _on_modal_progress(self, stage: str, state: str) -> None:
        self.modal_state.setText(f"{stage}: {state}")

    @Slot(object, str)
    def _on_static_success(self, result: StaticAnalysisResult, fingerprint: str) -> None:
        if project_fingerprint(self.project) != fingerprint:
            self.static_state.setText("Static result discarded: ROTOR MODEL changed while the transaction was running.")
            return
        self.set_static_result(result, fingerprint=fingerprint)
        self.static_state.setText(f"Static cache ready · independent Rotor.run_static() · {result.total_elapsed_s:.2f} s")

    @Slot(object, str)
    def _on_modal_success(self, result: ModalAnalysisResult, fingerprint: str) -> None:
        if project_fingerprint(self.project) != fingerprint:
            self.modal_state.setText("Modal result discarded: ROTOR MODEL changed while the transaction was running.")
            return
        try:
            current_key = self._modal_request().cache_key()
        except Exception:
            current_key = None
        if current_key != result.request.cache_key():
            self.modal_state.setText("Modal result discarded: modal inputs changed while the transaction was running.")
            return
        self.set_modal_result(result, fingerprint=fingerprint)
        self.modal_state.setText(
            f"Modal/Campbell cache ready · {len(result.modal_modes)} modes · {result.total_elapsed_s:.2f} s"
        )

    @Slot(str, str)
    def _on_static_failure(self, message: str, fingerprint: str) -> None:
        stale = project_fingerprint(self.project) != fingerprint
        self.static_state.setText(("Stale Static failed: " if stale else "Static failed: ") + message)

    @Slot(str, str)
    def _on_modal_failure(self, message: str, fingerprint: str) -> None:
        stale = project_fingerprint(self.project) != fingerprint
        self.modal_state.setText(("Stale Modal failed: " if stale else "Modal failed: ") + message)

    @Slot()
    def _static_thread_finished(self) -> None:
        thread = self._static_thread
        self._static_thread = None
        self._static_worker = None
        if self.mode_filter == "Lateral":
            self.run_static_button.setEnabled(True)
        self._invalidate_if_project_changed()
        if thread is not None:
            thread.deleteLater()

    @Slot()
    def _modal_thread_finished(self) -> None:
        thread = self._modal_thread
        self._modal_thread = None
        self._modal_worker = None
        self.run_modal_button.setEnabled(True)
        self._invalidate_if_project_changed()
        if thread is not None:
            thread.deleteLater()

    def set_static_result(self, result: StaticAnalysisResult, *, fingerprint: str | None = None) -> None:
        self.static_result = result
        self.static_catalog = StaticNativeFigureCatalog(result)
        self.static_fingerprint = fingerprint or project_fingerprint(self.project)
        self._set_static_controls_enabled(True)
        self._refresh_static_figure()

    def set_modal_result(self, result: ModalAnalysisResult, *, fingerprint: str | None = None) -> None:
        self.modal_result = result
        self.modal_catalog = ModalNativeFigureCatalog(result)
        self.modal_fingerprint = fingerprint or project_fingerprint(self.project)
        self.modal_request_key = result.request.cache_key()
        self._populate_mode_table()
        self._set_modal_controls_enabled(True)
        self._refresh_mode_figure()
        self._refresh_campbell_figure()

    def set_result(self, result: StaticModalResult, *, fingerprint: str | None = None) -> None:
        """0.19 compatibility adapter used only by historical tests/importers."""
        fp = fingerprint or project_fingerprint(self.project)
        if self.mode_filter == "Lateral" and result.static is not None:
            self.set_static_result(
                StaticAnalysisResult(
                    project_name=result.project_name,
                    build=result.build,
                    static=result.static,
                    audits=list(result.audits),
                    stage_elapsed_s={
                        key: value for key, value in result.stage_elapsed_s.items() if key in {"Strict Rotor", "Static"}
                    },
                ),
                fingerprint=fp,
            )
        self.set_modal_result(
            ModalAnalysisResult(
                project_name=result.project_name,
                build=result.build,
                request=ModalAnalysisRequest(
                    speed_rpm=result.request.speed_rpm,
                    num_modes=result.request.num_modes,
                    campbell_min_rpm=result.request.campbell_min_rpm,
                    campbell_max_rpm=result.request.campbell_max_rpm,
                    campbell_points=result.request.campbell_points,
                    campbell_frequencies=result.request.campbell_frequencies,
                ),
                modal=result.modal,
                campbell=result.campbell,
                campbell_speed_rpm=result.campbell_speed_rpm,
                modal_modes=result.modal_modes,
                audits=list(result.audits),
                stage_elapsed_s={
                    key: value for key, value in result.stage_elapsed_s.items() if key in {"Strict Rotor", "Modal", "Campbell"}
                },
            ),
            fingerprint=fp,
        )

    def _invalidate_static_cache(self, reason: str) -> None:
        if self.mode_filter != "Lateral":
            return
        self.static_result = None
        self.static_catalog = None
        self.static_fingerprint = None
        self._set_static_controls_enabled(False)
        self.static_view.set_unavailable(reason)
        self.static_state.setText(reason)

    def _invalidate_modal_cache(self, reason: str) -> None:
        self.modal_result = None
        self.modal_catalog = None
        self.modal_fingerprint = None
        self.modal_request_key = None
        self.mode_table.setRowCount(0)
        self._set_modal_controls_enabled(False)
        self.mode_view.set_unavailable(reason)
        self.campbell_view.set_unavailable(reason)
        self.modal_state.setText(reason)

    def _invalidate_if_project_changed(self) -> None:
        current = project_fingerprint(self.project)
        if self.static_result is not None and self.static_fingerprint != current:
            self._invalidate_static_cache("Static cache invalidated: ROTOR MODEL changed. Run Static again.")
        if self.modal_result is not None and self.modal_fingerprint != current:
            self._invalidate_modal_cache("Modal/Campbell cache invalidated: ROTOR MODEL changed. Run Modal & Campbell again.")

    @Slot()
    def _modal_inputs_changed(self, *_args) -> None:
        if self.modal_result is None:
            return
        try:
            current_key = self._modal_request().cache_key()
        except Exception:
            current_key = None
        if current_key != self.modal_request_key:
            self._invalidate_modal_cache(
                "Modal/Campbell cache invalidated: modal numerical inputs changed. Static cache, if present, remains valid."
            )

    def _filtered_modes(self):
        if self.modal_result is None:
            return ()
        return tuple(item for item in self.modal_result.modal_modes if item.mode_type == self.mode_filter)

    def _populate_mode_table(self) -> None:
        modes = self._filtered_modes()
        self.mode_table.setRowCount(len(modes))
        for row, item in enumerate(modes):
            values = (
                item.mode_number,
                item.mode_type,
                f"{item.wn_hz:.6g}",
                f"{item.wd_hz:.6g}",
                f"{item.damping_ratio:.6g}",
                f"{item.log_dec:.6g}",
                item.whirl,
            )
            for col, value in enumerate(values):
                cell = QTableWidgetItem(str(value))
                if col == 0:
                    cell.setData(Qt.ItemDataRole.UserRole, item.mode_index)
                self.mode_table.setItem(row, col, cell)
        self.mode_table.resizeColumnsToContents()
        if modes:
            self.mode_table.selectRow(0)
        else:
            self.mode_view.set_unavailable(
                f"No {self.mode_filter} modes were returned among the requested eigenvalues. Increase Eigenvalue count and run Modal again."
            )

    def _selected_mode_index(self) -> int | None:
        row = self.mode_table.currentRow()
        if row < 0:
            return None
        cell = self.mode_table.item(row, 0)
        if cell is None:
            return None
        value = cell.data(Qt.ItemDataRole.UserRole)
        return None if value is None else int(value)

    def _mode_dimension_changed(self, text: str) -> None:
        is_2d = text == "2D"
        available = self.modal_result is not None
        self.mode_orientation.setEnabled(is_2d and available)
        self.animate.setEnabled((not is_2d) and available)
        if is_2d and self.animate.isChecked():
            self.animate.blockSignals(True)
            self.animate.setChecked(False)
            self.animate.blockSignals(False)
        self._refresh_mode_figure()

    def _refresh_static_figure(self) -> None:
        self._invalidate_if_project_changed()
        if self.static_catalog is None or self.mode_filter != "Lateral":
            return
        key = str(self.static_selector.currentData())
        try:
            figure = self.static_catalog.static_figure(key)
            spec = self.static_catalog.static_spec(key)
        except Exception as exc:
            self.static_view.set_unavailable(f"Native ROSS static output unavailable: {exc}")
            return
        self.static_view.set_figure(figure, tooltip=f"{spec.source_method} · {spec.tutorial_basis}")

    def _refresh_mode_figure(self) -> None:
        self._invalidate_if_project_changed()
        if self.modal_catalog is None:
            return
        mode_index = self._selected_mode_index()
        if mode_index is None:
            return
        dimension = self.mode_dimension.currentText().casefold()
        try:
            figure = self.modal_catalog.mode_figure(
                mode_index,
                dimension=dimension,
                animation=bool(self.animate.isChecked()),
                orientation=str(self.mode_orientation.currentData()),
            )
        except Exception as exc:
            self.mode_view.set_unavailable(f"Native ROSS mode shape unavailable: {exc}")
            return
        source = "ModalResults.plot_mode_3d" if dimension == "3d" else "ModalResults.plot_mode_2d"
        suffix = " · animation=True" if self.animate.isChecked() else ""
        self.mode_view.set_figure(figure, tooltip=f"{source}{suffix} · native ROSS result")

    def _parse_harmonics(self) -> tuple[float, ...]:
        raw = self.harmonics.text().replace(";", ",")
        values = tuple(float(item.strip()) for item in raw.split(",") if item.strip())
        if not values or any(value <= 0 for value in values):
            raise EngineeringError(f"Campbell harmonics must be positive; received {raw!r}.")
        return values

    def _refresh_campbell_figure(self) -> None:
        self._invalidate_if_project_changed()
        if self.modal_catalog is None:
            return
        try:
            values = self._parse_harmonics()
            figure = self.modal_catalog.campbell_figure(values)
        except Exception as exc:
            self.campbell_view.set_unavailable(f"Native ROSS Campbell output unavailable: {exc}")
            return
        self.campbell_view.set_figure(
            figure,
            tooltip=f"CampbellResults.plot(harmonics={list(values)!r}) · native ROSS result · plot-only",
        )

    def current_figure(self) -> Any | None:
        current = self.tabs.currentWidget()
        if self.mode_filter == "Lateral" and current is self.static_tab:
            return self.static_view.figure
        if current is self.modal_tab:
            return self.mode_view.figure
        if current is self.campbell_tab:
            return self.campbell_view.figure
        return None

    def export_figure_html(self, path: str | Path, figure: Any | None = None) -> Path:
        target_figure = figure or self.current_figure()
        if target_figure is None:
            raise EngineeringError("No native ROSS figure is selected for export.")
        return ModalNativeFigureCatalog.export_html(target_figure, path)

    def export_figure_png(self, path: str | Path, figure: Any | None = None) -> Path:
        target_figure = figure or self.current_figure()
        if target_figure is None:
            raise EngineeringError("No native ROSS figure is selected for export.")
        return ModalNativeFigureCatalog.export_png(target_figure, path)

    def _choose_export_static_html(self) -> None:
        filename, _ = QFileDialog.getSaveFileName(self, "Export native ROSS Static HTML", "static_result.html", "HTML (*.html)")
        if not filename:
            return
        try:
            self.export_figure_html(filename, self.static_view.figure)
            self.static_state.setText(f"Native ROSS Static HTML exported: {filename}")
        except Exception as exc:
            self.static_state.setText(f"Static HTML export failed: {exc}")

    def _choose_export_static_png(self) -> None:
        filename, _ = QFileDialog.getSaveFileName(self, "Export native ROSS Static PNG", "static_result.png", "PNG (*.png)")
        if not filename:
            return
        try:
            self.export_figure_png(filename, self.static_view.figure)
            self.static_state.setText(f"Native ROSS Static PNG exported: {filename}")
        except Exception as exc:
            self.static_state.setText(f"Static PNG export failed: {exc}")

    def _choose_export_mode_html(self) -> None:
        filename, _ = QFileDialog.getSaveFileName(self, "Export native ROSS mode HTML", "mode_shape.html", "HTML (*.html)")
        if not filename:
            return
        try:
            self.export_figure_html(filename, self.mode_view.figure)
            self.modal_state.setText(f"Native ROSS mode HTML exported: {filename}")
        except Exception as exc:
            self.modal_state.setText(f"Mode HTML export failed: {exc}")

    def _choose_export_mode_png(self) -> None:
        filename, _ = QFileDialog.getSaveFileName(self, "Export native ROSS mode PNG", "mode_shape.png", "PNG (*.png)")
        if not filename:
            return
        try:
            self.export_figure_png(filename, self.mode_view.figure)
            self.modal_state.setText(f"Native ROSS mode PNG exported: {filename}")
        except Exception as exc:
            self.modal_state.setText(f"Mode PNG export failed: {exc}")

    # 0.19 method names retained for callers that did not know the decoupled labels.
    _choose_export_html = _choose_export_mode_html
    _choose_export_png = _choose_export_mode_png

    def showEvent(self, event) -> None:
        self._invalidate_if_project_changed()
        super().showEvent(event)

    def closeEvent(self, event) -> None:
        for thread in (self._static_thread, self._modal_thread):
            if thread is not None and thread.isRunning():
                thread.requestInterruption()
                thread.quit()
                thread.wait(5000)
        super().closeEvent(event)


__all__ = ["StaticModalWorkspacePage"]
