from __future__ import annotations

from copy import deepcopy
from math import pi
from typing import Any

from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QHBoxLayout, QLabel,
    QPushButton, QSpinBox, QTabWidget, QVBoxLayout, QWidget,
)

from ..fault_analysis import CrackRequest, FaultAnalysisResult, FaultAnalysisService, MisalignmentRequest, RubbingRequest
from ..models import ProjectModel
from ..result_validity import ResultValidityGuard
from ..plotly_native_view import NativeRossFigureView
from ..widgets import SectionCard


class FaultsWorkspace(QWidget):
    """Native ROSS fault tabs embedded in Time & Frequency."""

    def __init__(self, project: ProjectModel, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.project = project
        self.service = FaultAnalysisService()
        self.result: FaultAnalysisResult | None = None
        self.figures: dict[str, Any] = {}

        root = QVBoxLayout(self)
        note = QLabel(
            "Faults are transient native ROSS analyses. Misalignment is a fault excitation and remains distinct from the physical two-node CouplingElement in ROTOR MODEL."
        )
        note.setObjectName("muted")
        note.setWordWrap(True)
        root.addWidget(note)
        self.tabs = QTabWidget()
        self.tabs.addTab(self._misalignment_tab(), "Misalignment")
        self.tabs.addTab(self._rubbing_tab(), "Rubbing")
        self.tabs.addTab(self._crack_tab(), "Crack")
        root.addWidget(self.tabs, 1)

        output = SectionCard("Native ROSS fault result")
        row = QHBoxLayout()
        row.addWidget(QLabel("Plot"))
        self.plot_choice = QComboBox()
        row.addWidget(self.plot_choice, 1)
        self.state = QLabel("Result: empty")
        self.state.setObjectName("muted")
        row.addWidget(self.state)
        output.root.addLayout(row)
        self.view = NativeRossFigureView()
        output.root.addWidget(self.view)
        root.addWidget(output, 2)
        self.plot_choice.currentIndexChanged.connect(self._show_plot)
        self.validity_guard = ResultValidityGuard(self, self._invalidate)
        for widget in self.tabs.findChildren(QWidget):
            for name in ("valueChanged", "currentIndexChanged", "toggled"):
                signal = getattr(widget, name, None)
                if signal is not None:
                    signal.connect(self._invalidate)
                    break

    def _invalidate(self, *_args):
        self.result = None
        self.figures.clear()
        self.plot_choice.clear()
        self.state.setText("Result invalidated: model or inputs changed; run again.")
        self.view.set_unavailable("Result invalidated; run again.")

    @staticmethod
    def _double(value: float, minimum: float = -1e12, maximum: float = 1e12, decimals: int = 8) -> QDoubleSpinBox:
        box = QDoubleSpinBox()
        box.setRange(minimum, maximum)
        box.setDecimals(decimals)
        box.setValue(value)
        return box

    @staticmethod
    def _spin(value: int, minimum: int = 0, maximum: int = 200000) -> QSpinBox:
        box = QSpinBox()
        box.setRange(minimum, maximum)
        box.setValue(value)
        return box

    def _base_form(self, form: QFormLayout) -> tuple[QDoubleSpinBox, QDoubleSpinBox, QSpinBox, QSpinBox]:
        speed = self._double(max(1.0, self.project.speed_rpm), 1e-6, 1e7, 3)
        speed.setSuffix(" rpm")
        duration = self._double(2.0, 1e-6, 1000.0, 4)
        duration.setSuffix(" s")
        samples = self._spin(4001, 101, 200000)
        element = self._spin(0, 0, 100000)
        form.addRow("Speed", speed)
        form.addRow("Duration", duration)
        form.addRow("Samples", samples)
        form.addRow("ROSS shaft element n", element)
        return speed, duration, samples, element

    def _misalignment_tab(self) -> QWidget:
        page = QWidget()
        root = QVBoxLayout(page)
        card = SectionCard("Rotor.run_misalignment()")
        form = QFormLayout()
        self.mis_speed, self.mis_duration, self.mis_samples, self.mis_n = self._base_form(form)
        self.mis_coupling = QComboBox()
        self.mis_coupling.addItems(["flex", "rigid"])
        form.addRow("Fault coupling model", self.mis_coupling)
        self.mis_type = QComboBox()
        self.mis_type.addItems(["parallel", "angular", "combined"])
        form.addRow("Flexible misalignment", self.mis_type)
        self.mis_dx = self._double(0.2, 0, 1e6)
        self.mis_dx.setSuffix(" mm")
        form.addRow("Δx", self.mis_dx)
        self.mis_dy = self._double(0.2, 0, 1e6)
        self.mis_dy.setSuffix(" mm")
        form.addRow("Δy", self.mis_dy)
        self.mis_angle = self._double(0.0, -360, 360)
        self.mis_angle.setSuffix(" deg")
        form.addRow("Angle", self.mis_angle)
        self.mis_kr = self._double(40e3, 0)
        form.addRow("Radial stiffness (N/m)", self.mis_kr)
        self.mis_kb = self._double(38e3, 0)
        form.addRow("Bending stiffness (N/m)", self.mis_kb)
        card.root.addLayout(form)
        run = QPushButton("Run native misalignment")
        run.setObjectName("primaryButton")
        run.clicked.connect(self._run_misalignment)
        card.root.addWidget(run)
        root.addWidget(card)
        root.addStretch(1)
        return page

    def _rubbing_tab(self) -> QWidget:
        page = QWidget()
        root = QVBoxLayout(page)
        card = SectionCard("Rotor.run_rubbing()")
        form = QFormLayout()
        self.rub_speed, self.rub_duration, self.rub_samples, self.rub_n = self._base_form(form)
        self.rub_distance = self._double(0.1, 1e-9, 1e6)
        self.rub_distance.setSuffix(" mm")
        form.addRow("Rotor-stator clearance", self.rub_distance)
        self.rub_k = self._double(1e6, 0)
        form.addRow("Contact stiffness (N/m)", self.rub_k)
        self.rub_c = self._double(10.0, 0)
        form.addRow("Contact damping (N·s/m)", self.rub_c)
        self.rub_mu = self._double(0.1, 0, 10)
        form.addRow("Friction coefficient", self.rub_mu)
        self.rub_torque = QCheckBox("Include friction torque")
        form.addRow("Torque", self.rub_torque)
        card.root.addLayout(form)
        run = QPushButton("Run native rubbing")
        run.setObjectName("primaryButton")
        run.clicked.connect(self._run_rubbing)
        card.root.addWidget(run)
        root.addWidget(card)
        root.addStretch(1)
        return page

    def _crack_tab(self) -> QWidget:
        page = QWidget()
        root = QVBoxLayout(page)
        card = SectionCard("Rotor.run_crack()")
        form = QFormLayout()
        self.crack_speed, self.crack_duration, self.crack_samples, self.crack_n = self._base_form(form)
        self.crack_depth = self._double(0.2, 1e-6, 0.999999)
        form.addRow("Depth ratio", self.crack_depth)
        self.crack_model = QComboBox()
        self.crack_model.addItems(["Mayes", "Gasch"])
        form.addRow("Crack model", self.crack_model)
        self.crack_cross = self._spin(0, 0, 10000)
        self.crack_cross.setSpecialValueText("ROSS default")
        form.addRow("Cross divisions", self.crack_cross)
        card.root.addLayout(form)
        run = QPushButton("Run native crack")
        run.setObjectName("primaryButton")
        run.clicked.connect(self._run_crack)
        card.root.addWidget(run)
        root.addWidget(card)
        root.addStretch(1)
        return page

    def _engineering(self):
        if self.project.engineering is None:
            raise RuntimeError("Fault analysis requires a loaded RotorProject.")
        return self.project.engineering

    def _run_misalignment(self) -> None:
        request = MisalignmentRequest(
            speed_rpm=self.mis_speed.value(), duration_s=self.mis_duration.value(), samples=self.mis_samples.value(), element_n=self.mis_n.value(),
            coupling=self.mis_coupling.currentText(), mis_type=self.mis_type.currentText(),
            mis_distance_x_m=self.mis_dx.value() / 1000.0, mis_distance_y_m=self.mis_dy.value() / 1000.0,
            mis_angle_rad=self.mis_angle.value() * pi / 180.0, radial_stiffness_n_m=self.mis_kr.value(), bending_stiffness_n_m=self.mis_kb.value(),
            rigid_mis_distance_m=self.mis_dx.value() / 1000.0,
        )
        self._run(request)

    def _run_rubbing(self) -> None:
        self._run(RubbingRequest(
            speed_rpm=self.rub_speed.value(), duration_s=self.rub_duration.value(), samples=self.rub_samples.value(), element_n=self.rub_n.value(),
            distance_m=self.rub_distance.value() / 1000.0, contact_stiffness_n_m=self.rub_k.value(), contact_damping_n_s_m=self.rub_c.value(),
            friction_coeff=self.rub_mu.value(), torque=self.rub_torque.isChecked(),
        ))

    def _run_crack(self) -> None:
        cross = self.crack_cross.value()
        self._run(CrackRequest(
            speed_rpm=self.crack_speed.value(), duration_s=self.crack_duration.value(), samples=self.crack_samples.value(), element_n=self.crack_n.value(),
            depth_ratio=self.crack_depth.value(), crack_model=self.crack_model.currentText(), cross_divisions=None if cross == 0 else cross,
        ))

    def _run(self, request) -> None:
        self.state.setText("Running native ROSS fault solve...")
        try:
            result = self.service.run(deepcopy(self._engineering()), request)
        except Exception as exc:
            self._invalidate()
            self.state.setText(f"Fault solve failed: {exc}")
            self.view.set_unavailable(str(exc))
            return
        self.result = result
        self.state.setText(f"{result.kind} ready · {result.elapsed_s:.2f} s")
        self._collect_figures(result)

    def _collect_figures(self, result: FaultAnalysisResult) -> None:
        self.figures.clear()
        self.plot_choice.clear()
        rs = self.service.backend.rs if getattr(self.service.backend, "rs", None) is not None else __import__("ross")
        probes = [rs.Probe(node=probe.node, angle=probe.orientation_deg * pi / 180.0, tag=probe.tag) for probe in result.probes]
        if not probes:
            probes = [rs.Probe(node=0, angle=0.0, tag="Node 0")]
        errors = []
        for label, method in (("Time response", result.native.plot_1d), ("DFFT", result.native.plot_dfft)):
            try:
                self.figures[label] = method(probe=probes)
            except Exception as exc:
                errors.append(f"{label}: {exc}")
        if errors:
            self.state.setText("Fault solve completed; native plot failures: " + "; ".join(errors))
            self.view.set_unavailable("; ".join(errors))
        self.plot_choice.addItems(list(self.figures))
        self._show_plot()

    def _show_plot(self) -> None:
        figure = self.figures.get(self.plot_choice.currentText())
        if figure is not None:
            self.view.set_figure(figure)


__all__ = ["FaultsWorkspace"]
