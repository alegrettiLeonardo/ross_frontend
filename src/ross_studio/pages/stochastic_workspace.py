from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import numpy as np
from PySide6.QtCore import QObject, QThread, Signal, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QDoubleSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..domain import EngineeringError
from ..models import ProjectModel
from ..project_io import project_fingerprint
from ..result_validity import ResultValidityGuard
from ..plotly_native_view import NativeRossFigureView
from ..stochastic_analysis import (
    RandomInputSpec,
    StochasticCampbellRequest,
    StochasticFrequencyRequest,
    StochasticRotorService,
    StochasticSamplingConfig,
    StochasticTarget,
    StochasticTimeRequest,
    StochasticUnbalanceRequest,
    StochasticVariableSpec,
)
from ..stochastic_native import (
    STOCHASTIC_PLOT_LABELS,
    StochasticCampbellCatalog,
    StochasticFrequencyCatalog,
    StochasticInputCatalog,
    StochasticTimeCatalog,
    StochasticUnbalanceCatalog,
)


class _CallableWorker(QObject):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, fn: Callable[[], Any]) -> None:
        super().__init__()
        self.fn = fn

    @Slot()
    def run(self) -> None:
        try:
            self.completed.emit(self.fn())
        except Exception as exc:  # pragma: no cover - exercised by Qt integration/frozen smoke
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class StochasticWorkspacePage(QWidget):
    """Native ROSS stochastic workspace.

    The workspace never implements a parallel Monte-Carlo solver. It builds native
    ``ross.stochastic.ST_*`` containers and executes the four ``ST_Rotor.run_*``
    analyses exposed by the pinned ROSS 2.3 stochastic API. Mean, percentile and
    confidence-band changes are plot-only post-processing of retained native results.
    """

    def __init__(self, project: ProjectModel, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.project = project
        self.service = StochasticRotorService()
        self._targets: dict[str, StochasticTarget] = {}
        self._variables: list[StochasticVariableSpec] = []
        self._results: dict[str, Any] = {}
        self._input_build: Any | None = None
        self._threads: list[QThread] = []
        self._busy = False

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        heading = QLabel("Stochastic ROSS · Native ST_* Analysis")
        heading.setObjectName("pageTitle")
        root.addWidget(heading)
        subtitle = QLabel(
            "Random variables are sampled at the engineering boundary, then passed to native ROSS "
            "ST_Material / ST_ShaftElement / ST_DiskElement / ST_BearingElement / ST_PointMass and ST_Rotor. "
            "Results remain native ROSS objects with mean, percentiles and confidence intervals."
        )
        subtitle.setWordWrap(True)
        subtitle.setObjectName("muted")
        root.addWidget(subtitle)

        root.addWidget(self._sampling_panel())
        self.tabs = QTabWidget()
        self.tabs.addTab(self._random_variables_tab(), "Random Variables")
        self.tabs.addTab(self._campbell_tab(), "Campbell")
        self.tabs.addTab(self._frequency_tab(), "Frequency Response")
        self.tabs.addTab(self._unbalance_tab(), "Unbalance Response")
        self.tabs.addTab(self._time_tab(), "Time Response")
        root.addWidget(self.tabs, 1)

        self._load_targets()
        self._update_variable_table()
        self._revision = 0
        self.validity_guard = ResultValidityGuard(self, self._invalidate_all)
        for name in ("samples", "seed", "camp_min", "camp_max", "camp_points", "camp_freqs", "fr_min", "fr_max", "fr_points", "ub_min", "ub_max", "ub_points", "ub_mag", "ub_phase", "ub_random_mag", "ub_random_phase", "tr_speed", "tr_duration", "tr_points", "tr_force", "tr_frequency", "tr_random_force"):
            widget = getattr(self, name)
            for signal_name in ("valueChanged", "currentIndexChanged", "textChanged"):
                signal = getattr(widget, signal_name, None)
                if signal is not None:
                    signal.connect(lambda *_: self._invalidate_all())
                    break

    @property
    def engineering(self):
        if self.project.engineering is None:
            raise EngineeringError("Stochastic analysis requires an engineering RotorProject.")
        return self.project.engineering

    def _sampling_panel(self) -> QWidget:
        box = QGroupBox("Sampling and statistical display")
        layout = QGridLayout(box)
        self.samples = QSpinBox()
        self.samples.setRange(2, 10000)
        self.samples.setValue(20)
        self.seed = QSpinBox()
        self.seed.setRange(0, 2_147_483_647)
        self.seed.setValue(12345)
        self.percentiles = QLineEdit("5, 50, 95")
        self.confidence = QLineEdit("90")
        layout.addWidget(QLabel("Samples"), 0, 0)
        layout.addWidget(self.samples, 0, 1)
        layout.addWidget(QLabel("Seed"), 0, 2)
        layout.addWidget(self.seed, 0, 3)
        layout.addWidget(QLabel("Percentiles [%]"), 1, 0)
        layout.addWidget(self.percentiles, 1, 1)
        layout.addWidget(QLabel("Confidence intervals [%]"), 1, 2)
        layout.addWidget(self.confidence, 1, 3)
        note = QLabel("All native ST_* random-variable arrays are generated with the same sample count, as required by ROSS.")
        note.setObjectName("muted")
        note.setWordWrap(True)
        layout.addWidget(note, 2, 0, 1, 4)
        return box

    def _random_variables_tab(self) -> QWidget:
        page = QWidget()
        root = QVBoxLayout(page)
        selector = QGridLayout()
        self.target_combo = QComboBox()
        self.target_combo.currentIndexChanged.connect(self._target_changed)
        self.distribution = QComboBox()
        self.distribution.addItem("Normal", "normal")
        self.distribution.addItem("Uniform", "uniform")
        self.distribution.currentIndexChanged.connect(self._sampling_rule_changed)
        self.scale_mode = QComboBox()
        self.scale_mode.addItem("Relative [%]", "relative")
        self.scale_mode.addItem("Absolute [SI]", "absolute")
        self.scale_mode.currentIndexChanged.connect(self._sampling_rule_changed)
        self.value_a = QLineEdit("0")
        self.value_b = QLineEdit("5")
        self.add_variable = QPushButton("Add Random Variable")
        self.add_variable.clicked.connect(self._add_variable)
        selector.addWidget(QLabel("ROSS target"), 0, 0)
        selector.addWidget(self.target_combo, 0, 1, 1, 3)
        selector.addWidget(QLabel("Distribution"), 1, 0)
        selector.addWidget(self.distribution, 1, 1)
        selector.addWidget(QLabel("Scale"), 1, 2)
        selector.addWidget(self.scale_mode, 1, 3)
        selector.addWidget(QLabel("A: mean / lower"), 2, 0)
        selector.addWidget(self.value_a, 2, 1)
        selector.addWidget(QLabel("B: std.dev. / upper"), 2, 2)
        selector.addWidget(self.value_b, 2, 3)
        selector.addWidget(self.add_variable, 3, 0, 1, 4)
        root.addLayout(selector)

        self.variable_table = QTableWidget(0, 7)
        self.variable_table.setHorizontalHeaderLabels(["Target", "Parameter", "Distribution", "Scale", "A", "B", "Unit"])
        self.variable_table.horizontalHeader().setStretchLastSection(True)
        root.addWidget(self.variable_table)
        row = QHBoxLayout()
        self.remove_variable = QPushButton("Remove Selected")
        self.remove_variable.clicked.connect(self._remove_variable)
        self.preview_inputs = QPushButton("Build ST_Rotor / Preview Samples")
        self.preview_inputs.clicked.connect(self._preview_random_variables)
        row.addWidget(self.remove_variable)
        row.addStretch(1)
        row.addWidget(self.preview_inputs)
        root.addLayout(row)

        result_row = QHBoxLayout()
        self.input_plot_combo = QComboBox()
        self.input_plot_combo.currentIndexChanged.connect(self._render_input_plot)
        result_row.addWidget(QLabel("Native input histogram/PDF"))
        result_row.addWidget(self.input_plot_combo, 1)
        self.export_samples = QPushButton("Export Samples NPZ")
        self.export_samples.clicked.connect(self._export_samples_npz)
        result_row.addWidget(self.export_samples)
        root.addLayout(result_row)
        self.input_view = NativeRossFigureView()
        root.addWidget(self.input_view, 1)
        return page

    def _analysis_shell(self, run_label: str, kind: str) -> tuple[QWidget, QFormLayout, QComboBox, NativeRossFigureView, QPushButton]:
        page = QWidget()
        root = QVBoxLayout(page)
        form_box = QGroupBox("Analysis request")
        form = QFormLayout(form_box)
        root.addWidget(form_box)
        action = QHBoxLayout()
        run = QPushButton(run_label)
        run.clicked.connect(lambda _checked=False, k=kind: self._run_analysis(k))
        action.addWidget(run)
        action.addStretch(1)
        output = QComboBox()
        for key, label in STOCHASTIC_PLOT_LABELS[kind].items():
            output.addItem(label, key)
        output.currentIndexChanged.connect(lambda _index, k=kind: self._render_analysis(k))
        action.addWidget(QLabel("Native ROSS output"))
        action.addWidget(output)
        export_html = QPushButton("Export HTML")
        export_html.clicked.connect(lambda _checked=False, k=kind: self._export_figure(k, "html"))
        export_png = QPushButton("Export PNG")
        export_png.clicked.connect(lambda _checked=False, k=kind: self._export_figure(k, "png"))
        export_native = QPushButton("Native JSON")
        export_native.clicked.connect(lambda _checked=False, k=kind: self._export_native_result(k))
        export_raw = QPushButton("Raw NPZ")
        export_raw.clicked.connect(lambda _checked=False, k=kind: self._export_raw(k))
        action.addWidget(export_html)
        action.addWidget(export_png)
        action.addWidget(export_native)
        action.addWidget(export_raw)
        root.addLayout(action)
        view = NativeRossFigureView()
        root.addWidget(view, 1)
        return page, form, output, view, run

    def _speed_box(self, value: float) -> QDoubleSpinBox:
        box = QDoubleSpinBox()
        box.setRange(0.0, 1_000_000.0)
        box.setDecimals(3)
        box.setValue(value)
        return box

    def _campbell_tab(self) -> QWidget:
        page, form, self.camp_output, self.camp_view, self.camp_run = self._analysis_shell("Run native ST_Rotor Campbell", "campbell")
        case = self.engineering.operating_cases[0]
        self.camp_min = self._speed_box(case.speed_min_rpm)
        self.camp_max = self._speed_box(case.speed_max_rpm)
        self.camp_points = QSpinBox(); self.camp_points.setRange(3, 401); self.camp_points.setValue(21)
        self.camp_freqs = QSpinBox(); self.camp_freqs.setRange(1, 32); self.camp_freqs.setValue(6)
        self.camp_harmonics = QLineEdit("1")
        form.addRow("Minimum speed [rpm]", self.camp_min)
        form.addRow("Maximum speed [rpm]", self.camp_max)
        form.addRow("Speed points", self.camp_points)
        form.addRow("Modes/frequencies", self.camp_freqs)
        form.addRow("Plot harmonics", self.camp_harmonics)
        self.camp_harmonics.editingFinished.connect(lambda: self._render_analysis("campbell"))
        return page

    def _node_combo(self) -> QComboBox:
        combo = QComboBox()
        for node in getattr(self, "_nodes", []):
            combo.addItem(str(node), int(node))
        return combo

    def _dof_combo(self) -> QComboBox:
        combo = QComboBox()
        for index, label in enumerate(("x", "y", "z", "alpha", "beta", "theta")):
            combo.addItem(label, index)
        return combo

    def _frequency_tab(self) -> QWidget:
        page, form, self.fr_output, self.fr_view, self.fr_run = self._analysis_shell("Run native ST_Rotor Frequency Response", "frequency_response")
        case = self.engineering.operating_cases[0]
        self.fr_min = self._speed_box(case.speed_min_rpm)
        self.fr_max = self._speed_box(case.speed_max_rpm)
        self.fr_points = QSpinBox(); self.fr_points.setRange(3, 2001); self.fr_points.setValue(101)
        self.fr_in_node = QComboBox(); self.fr_in_dof = self._dof_combo()
        self.fr_out_node = QComboBox(); self.fr_out_dof = self._dof_combo()
        self.fr_quantity = QComboBox()
        self.fr_quantity.addItem("Displacement", "m/N")
        self.fr_quantity.addItem("Velocity", "m/s/N")
        self.fr_quantity.addItem("Acceleration", "m/s**2/N")
        self.fr_quantity.currentIndexChanged.connect(lambda: self._render_analysis("frequency_response"))
        form.addRow("Minimum speed [rpm]", self.fr_min)
        form.addRow("Maximum speed [rpm]", self.fr_max)
        form.addRow("Frequency points", self.fr_points)
        form.addRow("Input node", self.fr_in_node)
        form.addRow("Input local DOF", self.fr_in_dof)
        form.addRow("Output node", self.fr_out_node)
        form.addRow("Output local DOF", self.fr_out_dof)
        form.addRow("Response quantity", self.fr_quantity)
        return page

    def _unbalance_tab(self) -> QWidget:
        page, form, self.ub_output, self.ub_view, self.ub_run = self._analysis_shell("Run native ST_Rotor Unbalance", "unbalance_response")
        case = self.engineering.operating_cases[0]
        self.ub_min = self._speed_box(case.speed_min_rpm)
        self.ub_max = self._speed_box(case.speed_max_rpm)
        self.ub_points = QSpinBox(); self.ub_points.setRange(3, 2001); self.ub_points.setValue(101)
        self.ub_node = QComboBox()
        self.ub_mag = QLineEdit("0.0001")
        self.ub_phase = QDoubleSpinBox(); self.ub_phase.setRange(-3600, 3600); self.ub_phase.setValue(0)
        self.ub_random_mag = QComboBox(); self.ub_random_mag.addItems(["Deterministic", "Normal ±5%", "Uniform ±5%"])
        self.ub_random_phase = QComboBox(); self.ub_random_phase.addItems(["Deterministic", "Normal σ=5°", "Uniform ±5°"])
        self.ub_quantity = QComboBox(); self.ub_quantity.addItem("Displacement", "m"); self.ub_quantity.addItem("Velocity", "m/s"); self.ub_quantity.addItem("Acceleration", "m/s**2")
        self.ub_quantity.currentIndexChanged.connect(lambda: self._render_analysis("unbalance_response"))
        form.addRow("Minimum speed [rpm]", self.ub_min)
        form.addRow("Maximum speed [rpm]", self.ub_max)
        form.addRow("Frequency points", self.ub_points)
        form.addRow("Unbalance node", self.ub_node)
        form.addRow("Magnitude [kg·m]", self.ub_mag)
        form.addRow("Phase [deg]", self.ub_phase)
        form.addRow("Magnitude uncertainty", self.ub_random_mag)
        form.addRow("Phase uncertainty", self.ub_random_phase)
        form.addRow("Response quantity", self.ub_quantity)
        return page

    def _time_tab(self) -> QWidget:
        page, form, self.tr_output, self.tr_view, self.tr_run = self._analysis_shell("Run native ST_Rotor Time Response", "time_response")
        case = self.engineering.operating_cases[0]
        self.tr_speed = self._speed_box(case.rated_speed_rpm)
        self.tr_duration = QDoubleSpinBox(); self.tr_duration.setRange(0.001, 10000); self.tr_duration.setDecimals(4); self.tr_duration.setValue(1.0)
        self.tr_points = QSpinBox(); self.tr_points.setRange(8, 200000); self.tr_points.setValue(201)
        self.tr_node = QComboBox()
        self.tr_force = QLineEdit("10")
        self.tr_frequency = QDoubleSpinBox(); self.tr_frequency.setRange(0, 1e6); self.tr_frequency.setValue(2.0)
        self.tr_random_force = QComboBox(); self.tr_random_force.addItems(["Deterministic", "Normal ±5%", "Uniform ±5%"])
        form.addRow("Rotor speed [rpm]", self.tr_speed)
        form.addRow("Duration [s]", self.tr_duration)
        form.addRow("Time points", self.tr_points)
        form.addRow("Force node", self.tr_node)
        form.addRow("Force amplitude [N]", self.tr_force)
        form.addRow("Force frequency [Hz]", self.tr_frequency)
        form.addRow("Force amplitude uncertainty", self.tr_random_force)
        return page

    def _load_targets(self) -> None:
        try:
            targets = self.service.available_targets(self.engineering)
            build = self.service.builder.build(self.engineering, strict=True)
            self._nodes = [int(value) for value in build.rotor.nodes]
        except Exception as exc:
            self.input_view.set_unavailable(f"Unable to build deterministic ROSS target inventory: {exc}")
            return
        self._targets = {target.key: target for target in targets}
        self.target_combo.clear()
        for target in targets:
            suffix = "" if target.randomizable else " · BLOCKED"
            self.target_combo.addItem(f"{target.label} · {target.parameter} = {target.nominal:.6g} {target.units}{suffix}", target.key)
        for combo in (self.fr_in_node, self.fr_out_node, self.ub_node, self.tr_node):
            combo.clear()
            for node in self._nodes:
                combo.addItem(str(node), node)
        if self._nodes:
            middle = len(self._nodes) // 2
            for combo in (self.fr_in_node, self.fr_out_node, self.ub_node, self.tr_node):
                combo.setCurrentIndex(middle)
        self._target_changed()

    def _target_changed(self) -> None:
        key = self.target_combo.currentData()
        target = self._targets.get(str(key))
        if target is None:
            return
        self.add_variable.setEnabled(target.randomizable)
        self.add_variable.setToolTip(target.reason)
        self._sampling_rule_changed()

    def _sampling_rule_changed(self) -> None:
        key = self.target_combo.currentData()
        target = self._targets.get(str(key))
        if target is None:
            return
        distribution = str(self.distribution.currentData())
        scale = str(self.scale_mode.currentData())
        if scale == "relative":
            a, b = ((0.0, 5.0) if distribution == "normal" else (-5.0, 5.0))
        else:
            nominal = target.nominal
            spread = abs(nominal) * 0.05 or 1.0
            a, b = ((nominal, spread) if distribution == "normal" else (nominal - spread, nominal + spread))
        self.value_a.setText(f"{a:.12g}")
        self.value_b.setText(f"{b:.12g}")

    def _add_variable(self) -> None:
        key = str(self.target_combo.currentData())
        target = self._targets.get(key)
        if target is None or not target.randomizable:
            QMessageBox.warning(self, "Stochastic target blocked", target.reason if target else "Unknown target")
            return
        try:
            rule = RandomInputSpec(
                distribution=str(self.distribution.currentData()),
                scale=str(self.scale_mode.currentData()),
                a=float(self.value_a.text()), b=float(self.value_b.text()),
            )
            variable = StochasticVariableSpec(target.family, target.index, target.parameter, rule)
            variable.validate()
        except Exception as exc:
            QMessageBox.warning(self, "Invalid random variable", str(exc))
            return
        self._variables = [item for item in self._variables if item.key != variable.key]
        self._variables.append(variable)
        self._invalidate_all()
        self._update_variable_table()

    def _remove_variable(self) -> None:
        row = self.variable_table.currentRow()
        if 0 <= row < len(self._variables):
            self._variables.pop(row)
            self._invalidate_all()
            self._update_variable_table()

    def _update_variable_table(self) -> None:
        self.variable_table.setRowCount(len(self._variables))
        for row, variable in enumerate(self._variables):
            target = self._targets.get(variable.key)
            values = [
                target.label if target else variable.family,
                variable.parameter,
                variable.sampling.distribution,
                variable.sampling.scale,
                f"{variable.sampling.a:.8g}",
                f"{variable.sampling.b:.8g}",
                target.units if target else "SI",
            ]
            for col, value in enumerate(values):
                self.variable_table.setItem(row, col, QTableWidgetItem(str(value)))

    def _sampling_config(self) -> StochasticSamplingConfig:
        config = StochasticSamplingConfig(self.samples.value(), self.seed.value(), tuple(self._variables))
        config.validate()
        return config

    @staticmethod
    def _parse_numbers(text: str) -> list[float]:
        if not text.strip():
            return []
        return [float(token.strip()) for token in text.replace(";", ",").split(",") if token.strip()]

    def _statistics(self) -> tuple[list[float], list[float]]:
        p = self._parse_numbers(self.percentiles.text())
        c = self._parse_numbers(self.confidence.text())
        if any(value < 0 or value > 100 for value in [*p, *c]):
            raise EngineeringError("Percentiles and confidence intervals must be inside [0, 100].")
        return p, c

    def _run_worker(self, label: str, fn: Callable[[], Any], done: Callable[[Any], None]) -> None:
        if self._busy:
            QMessageBox.information(self, "ROSS Stochastic", "Another stochastic transaction is still running.")
            return
        self._busy = True
        self._set_run_buttons(False)
        thread = QThread(self)
        worker = _CallableWorker(fn)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        snapshot = (project_fingerprint(self.project), self._revision)
        worker.completed.connect(lambda result: done(result) if snapshot == (project_fingerprint(self.project), self._revision) else self._invalidate_all())
        worker.failed.connect(lambda message: self._worker_failed(label, message))
        worker.completed.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(lambda: self._worker_finished(thread, worker))
        self._threads.append(thread)
        thread.start()

    def _worker_failed(self, label: str, message: str) -> None:
        QMessageBox.critical(self, f"{label} failed", message)

    def _worker_finished(self, thread: QThread, worker: QObject) -> None:
        self._busy = False
        self._set_run_buttons(True)
        if thread in self._threads:
            self._threads.remove(thread)
        worker.deleteLater()
        thread.deleteLater()

    def _set_run_buttons(self, enabled: bool) -> None:
        for button in (self.preview_inputs, self.camp_run, self.fr_run, self.ub_run, self.tr_run):
            button.setEnabled(enabled)

    def _preview_random_variables(self) -> None:
        try:
            config = self._sampling_config()
        except Exception as exc:
            QMessageBox.warning(self, "Invalid stochastic configuration", str(exc))
            return
        self._run_worker(
            "ST_Rotor build",
            lambda: self.service.build(self.engineering, config),
            self._input_build_complete,
        )

    def _input_build_complete(self, build: Any) -> None:
        self._input_build = build
        self.input_plot_combo.blockSignals(True)
        self.input_plot_combo.clear()
        for index, wrapper in enumerate(build.input_wrappers):
            if tuple(value for value in wrapper.variables if value != "material"):
                self.input_plot_combo.addItem(f"{wrapper.label} · {', '.join(wrapper.variables)}", index)
        self.input_plot_combo.blockSignals(False)
        if self.input_plot_combo.count():
            self.input_plot_combo.setCurrentIndex(0)
            self._render_input_plot()
        else:
            self.input_view.set_unavailable("Native ST_* inputs were built, but no direct plot_random_var output is available for the selected material-only wrapper.")

    def _render_input_plot(self) -> None:
        if self._input_build is None or self.input_plot_combo.count() == 0:
            return
        try:
            catalog = StochasticInputCatalog(self._input_build)
            figure = catalog.figure(int(self.input_plot_combo.currentData()))
            self.input_view.set_figure(figure, tooltip="Native ROSS ST_* plot_random_var()")
        except Exception as exc:
            self.input_view.set_unavailable(str(exc))

    def _run_analysis(self, kind: str) -> None:
        try:
            config = self._sampling_config()
            if kind == "campbell":
                request = StochasticCampbellRequest(self.camp_min.value(), self.camp_max.value(), self.camp_points.value(), self.camp_freqs.value())
                fn = lambda: self.service.run_campbell(self.engineering, config, request)
            elif kind == "frequency_response":
                request = StochasticFrequencyRequest(
                    self.fr_min.value(), self.fr_max.value(), self.fr_points.value(),
                    int(self.fr_in_node.currentData()), int(self.fr_in_dof.currentData()),
                    int(self.fr_out_node.currentData()), int(self.fr_out_dof.currentData()),
                )
                fn = lambda: self.service.run_frequency_response(self.engineering, config, request)
            elif kind == "unbalance_response":
                mag_random = None
                if self.ub_random_mag.currentIndex() == 1:
                    mag_random = RandomInputSpec("normal", "relative", 0.0, 5.0)
                elif self.ub_random_mag.currentIndex() == 2:
                    mag_random = RandomInputSpec("uniform", "relative", -5.0, 5.0)
                phase_random = None
                if self.ub_random_phase.currentIndex() == 1:
                    phase_random = RandomInputSpec("normal", "absolute", self.ub_phase.value(), 5.0)
                elif self.ub_random_phase.currentIndex() == 2:
                    phase_random = RandomInputSpec("uniform", "absolute", self.ub_phase.value() - 5.0, self.ub_phase.value() + 5.0)
                request = StochasticUnbalanceRequest(
                    self.ub_min.value(), self.ub_max.value(), self.ub_points.value(), int(self.ub_node.currentData()),
                    float(self.ub_mag.text()), self.ub_phase.value(), mag_random, phase_random,
                )
                fn = lambda: self.service.run_unbalance_response(self.engineering, config, request)
            elif kind == "time_response":
                force_random = None
                if self.tr_random_force.currentIndex() == 1:
                    force_random = RandomInputSpec("normal", "relative", 0.0, 5.0)
                elif self.tr_random_force.currentIndex() == 2:
                    force_random = RandomInputSpec("uniform", "relative", -5.0, 5.0)
                request = StochasticTimeRequest(
                    self.tr_speed.value(), self.tr_duration.value(), self.tr_points.value(), int(self.tr_node.currentData()),
                    float(self.tr_force.text()), self.tr_frequency.value(), force_random,
                )
                fn = lambda: self.service.run_time_response(self.engineering, config, request)
            else:
                raise KeyError(kind)
            request.validate()
        except Exception as exc:
            QMessageBox.warning(self, "Invalid stochastic request", str(exc))
            return
        self._run_worker(kind, fn, lambda result, k=kind: self._analysis_complete(k, result))

    def _analysis_complete(self, kind: str, result: Any) -> None:
        self._results[kind] = result
        self._input_build = result.build
        self._render_analysis(kind)

    def _catalog(self, kind: str):
        result = self._results[kind]
        if kind == "campbell":
            return StochasticCampbellCatalog(result)
        if kind == "frequency_response":
            return StochasticFrequencyCatalog(result)
        if kind == "unbalance_response":
            return StochasticUnbalanceCatalog(result)
        if kind == "time_response":
            return StochasticTimeCatalog(result)
        raise KeyError(kind)

    def _render_analysis(self, kind: str) -> None:
        if kind not in self._results:
            return
        try:
            percentile, confidence = self._statistics()
            catalog = self._catalog(kind)
            if kind == "campbell":
                key = str(self.camp_output.currentData())
                harmonics = self._parse_numbers(self.camp_harmonics.text()) or [1.0]
                figure = catalog.figure(key, percentile=percentile, conf_interval=confidence, harmonics=harmonics)
                view = self.camp_view
            elif kind == "frequency_response":
                key = str(self.fr_output.currentData())
                figure = catalog.figure(key, percentile=percentile, conf_interval=confidence, amplitude_units=str(self.fr_quantity.currentData()))
                view = self.fr_view
            elif kind == "unbalance_response":
                key = str(self.ub_output.currentData())
                figure = catalog.figure(key, percentile=percentile, conf_interval=confidence, amplitude_units=str(self.ub_quantity.currentData()))
                view = self.ub_view
            elif kind == "time_response":
                key = str(self.tr_output.currentData())
                figure = catalog.figure(key, node=int(self.tr_node.currentData()), percentile=percentile, conf_interval=confidence)
                view = self.tr_view
            else:
                return
            view.set_figure(figure, tooltip=f"Native ROSS stochastic {kind} output")
        except Exception as exc:
            getattr(self, {"campbell":"camp_view", "frequency_response":"fr_view", "unbalance_response":"ub_view", "time_response":"tr_view"}[kind]).set_unavailable(str(exc))

    def _view_for(self, kind: str) -> NativeRossFigureView:
        return {"campbell":self.camp_view, "frequency_response":self.fr_view, "unbalance_response":self.ub_view, "time_response":self.tr_view}[kind]

    def _export_figure(self, kind: str, fmt: str) -> None:
        if kind not in self._results:
            QMessageBox.information(self, "No stochastic result", "Run the analysis first.")
            return
        figure = self._view_for(kind).figure
        if figure is None:
            self._render_analysis(kind)
            figure = self._view_for(kind).figure
        if figure is None:
            return
        suffix = ".html" if fmt == "html" else ".png"
        path, _ = QFileDialog.getSaveFileName(self, "Export native ROSS stochastic figure", f"stochastic_{kind}{suffix}", f"*{suffix}")
        if not path:
            return
        try:
            catalog = self._catalog(kind)
            if fmt == "html":
                catalog.export_html(figure, path)
            else:
                catalog.export_png(figure, path)
        except Exception as exc:
            QMessageBox.critical(self, "Export failed", str(exc))

    def _export_native_result(self, kind: str) -> None:
        if kind not in self._results:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save native ROSS stochastic result", f"stochastic_{kind}.json", "JSON (*.json);;TOML (*.toml)")
        if not path:
            return
        try:
            self._catalog(kind).export_native_result(path)
        except Exception as exc:
            QMessageBox.critical(self, "Native result export failed", str(exc))

    def _export_raw(self, kind: str) -> None:
        if kind not in self._results:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export raw stochastic arrays", f"stochastic_{kind}.npz", "NumPy archive (*.npz)")
        if not path:
            return
        try:
            arrays = self._catalog(kind).raw_arrays()
            np.savez_compressed(path, **arrays)
        except Exception as exc:
            QMessageBox.critical(self, "Raw export failed", str(exc))

    def _export_samples_npz(self) -> None:
        if self._input_build is None:
            QMessageBox.information(self, "No samples", "Build the stochastic rotor or run an analysis first.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export sampled random variables", "stochastic_samples.npz", "NumPy archive (*.npz)")
        if not path:
            return
        np.savez_compressed(path, **{key.replace(":", "__"): value for key, value in self._input_build.sampled_values.items()})

    def _invalidate_all(self) -> None:
        self._revision = getattr(self, "_revision", 0) + 1
        self._results.clear()
        self._input_build = None
        for view in (self.input_view, self.camp_view, self.fr_view, self.ub_view, self.tr_view):
            view.set_unavailable("Stochastic inputs changed. Build/run again to obtain results for the current sample definition.")


__all__ = ["StochasticWorkspacePage"]
