from __future__ import annotations

from copy import deepcopy

from PySide6.QtCore import QObject, QThread, Signal, Slot
from PySide6.QtWidgets import QDoubleSpinBox, QFormLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ..amb_analysis import AMBSensitivityRequest, AMBSensitivityService
from ..models import ProjectModel
from ..project_io import project_fingerprint
from ..result_validity import ResultValidityGuard
from ..plotly_native_view import NativeRossFigureView
from ..widgets import SectionCard


class _Worker(QObject):
    succeeded = Signal(object)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, project, request) -> None:
        super().__init__()
        self.project = project
        self.request = request

    @Slot()
    def run(self) -> None:
        try:
            self.succeeded.emit(AMBSensitivityService().run(self.project, self.request))
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            self.finished.emit()


class AMBSensitivityWorkspace(QWidget):
    """ISO 14839-style native ROSS AMB sensitivity workspace."""

    def __init__(self, project: ProjectModel, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.project = project
        self.result = None
        self.thread = None
        self.worker = None
        root = QVBoxLayout(self)
        note = QLabel(
            "Native Rotor.run_amb_sensitivity(): logarithmic chirp injected at the AMB sensor loop, Newmark time integration, sensitivity FRF and peak Smax."
        )
        note.setWordWrap(True)
        note.setObjectName("muted")
        root.addWidget(note)
        setup = SectionCard("AMB sensitivity · ISO 14839")
        form = QFormLayout()
        self.speed = self._box(max(0.0, project.speed_rpm), 0, 1e7, 3)
        self.speed.setSuffix(" rpm")
        self.tmax = self._box(45.0, 0.01, 1000.0, 4)
        self.tmax.setSuffix(" s")
        self.dt = self._box(1e-3, 1e-6, 10.0, 6)
        self.dt.setSuffix(" s")
        self.amp = self._box(1e-5, 1e-12, 1.0, 9)
        self.amp.setSuffix(" m")
        self.fmin = self._box(0.001, 1e-6, 1e6, 6)
        self.fmin.setSuffix(" Hz")
        self.fmax = self._box(150.0, 1e-6, 1e6, 3)
        self.fmax.setSuffix(" Hz")
        for label, widget in (
            ("Rotor speed", self.speed), ("t max", self.tmax), ("dt", self.dt),
            ("Disturbance amplitude", self.amp), ("Minimum frequency", self.fmin), ("Maximum frequency", self.fmax),
        ):
            form.addRow(label, widget)
        setup.root.addLayout(form)
        row = QHBoxLayout()
        self.run_button = QPushButton("Run native AMB sensitivity")
        self.run_button.setObjectName("primaryButton")
        row.addWidget(self.run_button)
        self.state = QLabel("Result: empty")
        self.state.setObjectName("muted")
        row.addWidget(self.state, 1)
        setup.root.addLayout(row)
        root.addWidget(setup)
        self.bode = NativeRossFigureView()
        self.time = NativeRossFigureView()
        root.addWidget(self.bode, 2)
        root.addWidget(self.time, 2)
        self.run_button.clicked.connect(self._run)
        self.validity_guard = ResultValidityGuard(self, self._invalidate)
        self._request_revision = 0
        self._running_revision = None
        for box in (self.speed, self.tmax, self.dt, self.amp, self.fmin, self.fmax):
            box.valueChanged.connect(self._invalidate)

    def _invalidate(self, *_args):
        self._request_revision += 1
        self.result = None
        self.state.setText("Result invalidated: model or inputs changed; run again.")
        self.bode.set_unavailable("Result invalidated; run again.")
        self.time.set_unavailable("Result invalidated; run again.")

    @staticmethod
    def _box(value, minimum, maximum, decimals):
        box = QDoubleSpinBox()
        box.setRange(minimum, maximum)
        box.setDecimals(decimals)
        box.setValue(value)
        return box

    def _run(self) -> None:
        if self.project.engineering is None:
            self.state.setText("No RotorProject loaded")
            return
        if self.thread is not None and self.thread.isRunning():
            return
        request = AMBSensitivityRequest(
            speed_rpm=self.speed.value(), t_max_s=self.tmax.value(), dt_s=self.dt.value(),
            disturbance_amplitude_m=self.amp.value(), min_frequency_hz=self.fmin.value(), max_frequency_hz=self.fmax.value(),
        )
        try:
            request.validate()
        except Exception as exc:
            self.state.setText(f"Input rejected: {exc}")
            return
        self._running_revision = (project_fingerprint(self.project), self._request_revision)
        self.run_button.setEnabled(False)
        self.state.setText("Running native ROSS AMB sensitivity...")
        self.thread = QThread(self)
        self.worker = _Worker(deepcopy(self.project.engineering), request)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.succeeded.connect(self._success)
        self.worker.failed.connect(self._failure)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self._finished)
        self.thread.start()

    @Slot(object)
    def _success(self, result) -> None:
        if self._running_revision != (project_fingerprint(self.project), self._request_revision):
            self._invalidate()
            return
        self.result = result
        peaks = []
        for tag, axes in getattr(result.native, "max_abs_sensitivities", {}).items():
            for axis, value in axes.items():
                peaks.append(f"{tag}/{axis}: Smax={float(value):.3f}")
        self.state.setText(f"Ready · {result.elapsed_s:.2f} s · " + (" · ".join(peaks) if peaks else "SensitivityResults"))
        try:
            self.bode.set_figure(result.native.plot(frequency_units="Hz", magnitude_scale="decibel", xaxis_type="log"))
        except Exception as exc:
            self.bode.set_unavailable(str(exc))
        try:
            self.time.set_figure(result.native.plot_time_results())
        except Exception as exc:
            self.time.set_unavailable(str(exc))

    @Slot(str)
    def _failure(self, message: str) -> None:
        self.result = None
        self.state.setText(f"AMB sensitivity failed: {message}")
        self.bode.set_unavailable(message)
        self.time.set_unavailable(message)

    def _finished(self) -> None:
        self.run_button.setEnabled(True)
        if self.thread is not None:
            self.thread.deleteLater()
        self.thread = None
        self.worker = None


__all__ = ["AMBSensitivityWorkspace"]
