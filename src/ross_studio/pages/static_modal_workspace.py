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
from ..models import ProjectModel
from ..page_registry import route_spec
from ..plotly_native_view import NativeRossFigureView
from ..project_io import project_fingerprint
from ..static_modal_analysis import StaticModalAnalysisService, StaticModalRequest, StaticModalResult
from ..static_modal_native import STATIC_FIGURES, StaticModalNativeFigureCatalog
from ..widgets import Card, SectionCard
from .architecture_workspaces import AnalysisRoutePage


class _StaticModalWorker(QObject):
    succeeded = Signal(object, str)
    failed = Signal(str, str)
    progress = Signal(str, str)
    finished = Signal()

    def __init__(self, project: RotorProject, request: StaticModalRequest, fingerprint: str) -> None:
        super().__init__()
        self.project = project
        self.request = request
        self.fingerprint = fingerprint

    @Slot()
    def run(self) -> None:
        thread = QThread.currentThread()
        try:
            result = StaticModalAnalysisService().run(
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
    """Dedicated 0.19 Static & Modal workspace using native ROSS results and plots."""

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
        self.result: StaticModalResult | None = None
        self.figure_catalog: StaticModalNativeFigureCatalog | None = None
        self.result_fingerprint: str | None = None
        self._thread: QThread | None = None
        self._worker: _StaticModalWorker | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)
        title = "Lateral Static & Modal Analysis" if mode_filter == "Lateral" else "Torsional Modal Analysis"
        root.addWidget(
            _Header(
                title,
                "Native ROSS workflow. StaticResults, ModalResults and CampbellResults stay retained in memory; "
                "changing result tabs, mode, 2D/3D view or animation does not re-run the solver.",
            )
        )

        setup = SectionCard("Analysis Setup")
        setup_row = QHBoxLayout()
        form = QFormLayout()
        self.speed_rpm = QDoubleSpinBox()
        self.speed_rpm.setRange(0.0, 1_000_000.0)
        self.speed_rpm.setDecimals(2)
        self.speed_rpm.setSuffix(" rpm")
        self.speed_rpm.setValue(float(project.speed_rpm))
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

        self.harmonics = QLineEdit("0.5, 1.0")
        self.harmonics.setToolTip("Plot-only harmonics. Changing this field does not re-run Rotor.run_campbell().")
        form.addRow("Campbell harmonics", self.harmonics)
        setup_row.addLayout(form, 1)

        actions = QVBoxLayout()
        self.run_button = QPushButton("Run Static & Modal" if mode_filter == "Lateral" else "Run Modal & Campbell")
        self.run_button.setObjectName("primaryButton")
        self.run_button.clicked.connect(self.run_analysis)
        actions.addWidget(self.run_button)
        self.run_state = QLabel("Ready")
        self.run_state.setWordWrap(True)
        self.run_state.setObjectName("muted")
        actions.addWidget(self.run_state)
        actions.addStretch(1)
        setup_row.addLayout(actions)
        setup.root.addLayout(setup_row)
        root.addWidget(setup)

        self.tabs = QTabWidget()
        if self.mode_filter == "Lateral":
            self.tabs.addTab(self._build_static_tab(), "Static")
        self.tabs.addTab(self._build_modal_tab(), "Mode Shapes")
        self.tabs.addTab(self._build_campbell_tab(), "Campbell")
        root.addWidget(self.tabs, 1)
        self._set_result_controls_enabled(False)

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
        self.export_png_button.clicked.connect(self._choose_export_png)
        controls.addWidget(self.export_png_button)
        self.export_html_button = QPushButton("Export HTML")
        self.export_html_button.setToolTip("HTML preserves the native Plotly animation and Play/Pause controls.")
        self.export_html_button.clicked.connect(self._choose_export_html)
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
        self.campbell_note = QLabel("Harmonics are plot-only; no scientific re-solve.")
        self.campbell_note.setObjectName("muted")
        controls.addWidget(self.campbell_note)
        controls.addStretch(1)
        layout.addLayout(controls)
        self.campbell_view = NativeRossFigureView()
        layout.addWidget(self.campbell_view, 1)
        return page

    def _set_result_controls_enabled(self, enabled: bool) -> None:
        if self.mode_filter == "Lateral":
            self.static_selector.setEnabled(enabled)
        self.mode_dimension.setEnabled(enabled)
        self.animate.setEnabled(enabled)
        self.export_png_button.setEnabled(enabled)
        self.export_html_button.setEnabled(enabled)
        self.refresh_campbell_button.setEnabled(enabled)

    def _request(self) -> StaticModalRequest:
        value = int(self.num_modes.value())
        if value % 2:
            value += 1
        return StaticModalRequest(
            speed_rpm=float(self.speed_rpm.value()),
            num_modes=value,
            campbell_points=int(self.campbell_points.value()),
            include_static=self.mode_filter == "Lateral",
        )

    def run_analysis(self) -> None:
        if self._thread is not None and self._thread.isRunning():
            return
        engineering = self.project.engineering
        if engineering is None:
            self.run_state.setText("Analysis rejected: project has no engineering RotorProject.")
            return
        try:
            request = self._request()
            request.validate()
            fingerprint = project_fingerprint(self.project)
        except Exception as exc:
            self.run_state.setText(f"Analysis input rejected: {exc}")
            return

        self.run_button.setEnabled(False)
        self._set_result_controls_enabled(False)
        self.run_state.setText("Building strict ROSS Rotor...")

        thread = QThread(self)
        worker = _StaticModalWorker(deepcopy(engineering), request, fingerprint)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._on_progress)
        worker.succeeded.connect(self._on_success)
        worker.failed.connect(self._on_failure)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(self._thread_finished)
        self._thread = thread
        self._worker = worker
        thread.start()

    @Slot(str, str)
    def _on_progress(self, stage: str, state: str) -> None:
        self.run_state.setText(f"{stage}: {state}")

    @Slot(object, str)
    def _on_success(self, result: StaticModalResult, fingerprint: str) -> None:
        if project_fingerprint(self.project) != fingerprint:
            self.run_state.setText(
                "Result discarded: ROTOR MODEL changed while Static & Modal was running. Run the analysis again."
            )
            return
        self.set_result(result, fingerprint=fingerprint)
        self.run_state.setText(
            f"ROSS native result ready · {len(result.modal_modes)} modes · {result.total_elapsed_s:.2f} s"
        )

    @Slot(str, str)
    def _on_failure(self, message: str, fingerprint: str) -> None:
        stale = project_fingerprint(self.project) != fingerprint
        prefix = "Stale analysis failed" if stale else "Analysis failed"
        self.run_state.setText(f"{prefix}: {message}")

    @Slot()
    def _thread_finished(self) -> None:
        thread = self._thread
        self._thread = None
        self._worker = None
        self.run_button.setEnabled(True)
        if self.result is not None and self.result_fingerprint == project_fingerprint(self.project):
            self._set_result_controls_enabled(True)
        if thread is not None:
            thread.deleteLater()

    def set_result(self, result: StaticModalResult, *, fingerprint: str | None = None) -> None:
        self.result = result
        self.figure_catalog = StaticModalNativeFigureCatalog(result)
        self.result_fingerprint = fingerprint or project_fingerprint(self.project)
        self._populate_mode_table()
        self._set_result_controls_enabled(True)
        if self.mode_filter == "Lateral":
            self._refresh_static_figure()
        self._refresh_mode_figure()
        self._refresh_campbell_figure()

    def _filtered_modes(self):
        if self.result is None:
            return ()
        return tuple(item for item in self.result.modal_modes if item.mode_type == self.mode_filter)

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
                f"No {self.mode_filter} modes were returned among the requested eigenvalues. Increase Eigenvalue count and run again."
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
        self.mode_orientation.setEnabled(is_2d and self.result is not None)
        self.animate.setEnabled((not is_2d) and self.result is not None)
        if is_2d and self.animate.isChecked():
            self.animate.blockSignals(True)
            self.animate.setChecked(False)
            self.animate.blockSignals(False)
        self._refresh_mode_figure()

    def _refresh_static_figure(self) -> None:
        if self.figure_catalog is None or self.mode_filter != "Lateral":
            return
        key = str(self.static_selector.currentData())
        try:
            figure = self.figure_catalog.static_figure(key)
            spec = self.figure_catalog.static_spec(key)
        except Exception as exc:
            self.static_view.set_unavailable(f"Native ROSS static output unavailable: {exc}")
            return
        self.static_view.set_figure(figure, tooltip=f"{spec.source_method} · {spec.tutorial_basis}")

    def _refresh_mode_figure(self) -> None:
        if self.figure_catalog is None:
            return
        mode_index = self._selected_mode_index()
        if mode_index is None:
            return
        dimension = self.mode_dimension.currentText().casefold()
        try:
            figure = self.figure_catalog.mode_figure(
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
        if self.figure_catalog is None:
            return
        try:
            values = self._parse_harmonics()
            figure = self.figure_catalog.campbell_figure(values)
        except Exception as exc:
            self.campbell_view.set_unavailable(f"Native ROSS Campbell output unavailable: {exc}")
            return
        self.campbell_view.set_figure(
            figure,
            tooltip=f"CampbellResults.plot(harmonics={list(values)!r}) · native ROSS result",
        )

    def current_figure(self) -> Any | None:
        current = self.tabs.currentWidget()
        if self.mode_filter == "Lateral" and current is self.static_view.parentWidget():
            return self.static_view.figure
        if current is self.mode_view.parentWidget():
            return self.mode_view.figure
        if current is self.campbell_view.parentWidget():
            return self.campbell_view.figure
        if self.mode_filter == "Lateral" and self.static_view.isVisible():
            return self.static_view.figure
        if self.mode_view.isVisible():
            return self.mode_view.figure
        if self.campbell_view.isVisible():
            return self.campbell_view.figure
        return self.mode_view.figure

    def export_figure_html(self, path: str | Path, figure: Any | None = None) -> Path:
        if self.figure_catalog is None:
            raise EngineeringError("Run Static & Modal before exporting a figure.")
        target_figure = figure or self.current_figure()
        if target_figure is None:
            raise EngineeringError("No native ROSS figure is selected for export.")
        return self.figure_catalog.export_html(target_figure, path)

    def export_figure_png(self, path: str | Path, figure: Any | None = None) -> Path:
        if self.figure_catalog is None:
            raise EngineeringError("Run Static & Modal before exporting a figure.")
        target_figure = figure or self.current_figure()
        if target_figure is None:
            raise EngineeringError("No native ROSS figure is selected for export.")
        return self.figure_catalog.export_png(target_figure, path)

    def _choose_export_html(self) -> None:
        filename, _ = QFileDialog.getSaveFileName(self, "Export native ROSS HTML", "mode_shape.html", "HTML (*.html)")
        if not filename:
            return
        try:
            self.export_figure_html(filename, self.mode_view.figure)
            self.run_state.setText(f"Native ROSS HTML exported: {filename}")
        except Exception as exc:
            self.run_state.setText(f"HTML export failed: {exc}")

    def _choose_export_png(self) -> None:
        filename, _ = QFileDialog.getSaveFileName(self, "Export native ROSS PNG", "mode_shape.png", "PNG (*.png)")
        if not filename:
            return
        try:
            self.export_figure_png(filename, self.mode_view.figure)
            self.run_state.setText(f"Native ROSS PNG exported: {filename}")
        except Exception as exc:
            self.run_state.setText(f"PNG export failed: {exc}")

    def closeEvent(self, event) -> None:
        thread = self._thread
        if thread is not None and thread.isRunning():
            thread.requestInterruption()
            thread.quit()
            thread.wait(5000)
        super().closeEvent(event)


__all__ = ["StaticModalWorkspacePage"]
