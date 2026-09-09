from __future__ import annotations

from PySide6.QtCore import QObject, QThread, Signal, Slot
from PySide6.QtWidgets import QHeaderView, QPushButton, QStackedWidget, QTableWidgetItem

from ..backends.ross.response_calculator import RotorResponseResult
from ..domain import RotorProject
from .response_view import ResponseCurveView
from .results_page import ResultsPage


class ResponseWorker(QObject):
    progress = Signal(str)
    completed = Signal(object)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, project: RotorProject, kind: str):
        super().__init__()
        self.project = project
        self.kind = kind

    @Slot()
    def run(self):
        try:
            from ..backends.ross.response_calculator import RossResponseCalculator

            calculator = RossResponseCalculator()
            if self.kind == "unbalance":
                result = calculator.project_unbalance_response(self.project, progress=self.progress.emit)
            elif self.kind == "frequency":
                result = calculator.project_frequency_response(self.project, progress=self.progress.emit)
            else:
                raise ValueError(f"Unsupported response worker kind: {self.kind}")
            self.completed.emit(result)
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")
        finally:
            self.finished.emit()


class EnhancedResultsPage(ResultsPage):
    """Approved Results workspace with native engineering response bindings."""

    statusMessage = Signal(str, str, bool)

    def __init__(self, project: RotorProject):
        super().__init__(project)
        self._response_thread: QThread | None = None
        self._response_worker: ResponseWorker | None = None
        self.response_result: RotorResponseResult | None = None
        self._active_response_kind = ""

        chart_card = self.chart.parentWidget()
        chart_layout = chart_card.layout
        chart_layout.removeWidget(self.chart)
        self.analysis_stack = QStackedWidget()
        self.analysis_stack.addWidget(self.chart)
        self.response_chart = ResponseCurveView()
        self.analysis_stack.addWidget(self.response_chart)
        chart_layout.addWidget(self.analysis_stack)
        self.analysis_stack.setCurrentWidget(self.chart)

    def _select_analysis(self, selected: QPushButton, host):
        super()._select_analysis(selected, host)
        if not selected.isChecked():
            return
        text = selected.text()
        if text in {"Modal", "Critical Speed", "Campbell"}:
            self.analysis_stack.setCurrentWidget(self.chart)
            self._restore_rotor_table()
            return
        if text == "Frequency Response":
            self._start_response("frequency")
            return
        if text == "Unbalance Response":
            self._start_response("unbalance")
            return
        if text == "Time Response":
            self.analysis_stack.setCurrentWidget(self.response_chart)
            self.response_chart.set_message(
                "Time Response backend is available. Define a transient force/load case before running this analysis."
            )
            self._set_message_table("Time response requires an explicit transient force definition.")
            self.statusMessage.emit("Time Response", "Transient load definition required", False)

    def _start_response(self, kind: str):
        if self._response_thread is not None and self._response_thread.isRunning():
            self.statusMessage.emit("Response analysis busy", "Wait for the current ROSS response solve to finish", False)
            return
        if kind == "unbalance" and (not self.project.unbalances or not self.project.probes):
            self.analysis_stack.setCurrentWidget(self.response_chart)
            self.response_chart.set_message("Define at least one unbalance plane and one response probe.")
            self._set_message_table("Unbalance Response requires project unbalances and probes.")
            self.statusMessage.emit("Unbalance Response unavailable", "Define unbalance planes and probes", False)
            return
        if kind == "frequency" and not self.project.probes:
            self.analysis_stack.setCurrentWidget(self.response_chart)
            self.response_chart.set_message("Define physical response probes to run the oriented FRF.")
            self._set_message_table("Frequency Response requires at least one physical probe.")
            self.statusMessage.emit("Frequency Response unavailable", "Define a response probe", False)
            return

        self._active_response_kind = kind
        label = "Unbalance Response" if kind == "unbalance" else "Frequency Response"
        self.analysis_stack.setCurrentWidget(self.response_chart)
        self.response_chart.set_message(f"Running native ROSS {label}...")
        self._set_message_table("ROSS response calculation running...")
        self.statusMessage.emit(f"{label} running", "ROSS solver active", True)

        self._response_thread = QThread(self)
        self._response_worker = ResponseWorker(self.project, kind)
        self._response_worker.moveToThread(self._response_thread)
        self._response_thread.started.connect(self._response_worker.run)
        self._response_worker.progress.connect(self._on_response_progress)
        self._response_worker.completed.connect(self._on_response_completed)
        self._response_worker.failed.connect(self._on_response_failed)
        self._response_worker.finished.connect(self._response_thread.quit)
        self._response_thread.finished.connect(self._on_response_finished)
        self._response_thread.start()

    @Slot(str)
    def _on_response_progress(self, message: str):
        label = "Unbalance Response" if self._active_response_kind == "unbalance" else "Frequency Response"
        self.statusMessage.emit(f"{label} running", message, True)

    @Slot(object)
    def _on_response_completed(self, result: RotorResponseResult):
        self.response_result = result
        self.analysis_stack.setCurrentWidget(self.response_chart)
        self.response_chart.set_result(result, "magnitude")
        self._fill_response_table(result)
        label = "Unbalance Response" if result.kind == "project_unbalance_response" else "Frequency Response"
        self.statusMessage.emit(f"{label} completed", f"{len(result.curves)} response curve(s)", True)

    @Slot(str)
    def _on_response_failed(self, message: str):
        self.analysis_stack.setCurrentWidget(self.response_chart)
        self.response_chart.set_message(message)
        self._set_message_table(message)
        self.statusMessage.emit("Response analysis failed", message, False)

    def _on_response_finished(self):
        if self._response_worker is not None:
            self._response_worker.deleteLater()
        if self._response_thread is not None:
            self._response_thread.deleteLater()
        self._response_worker = None
        self._response_thread = None

    def _fill_response_table(self, result: RotorResponseResult):
        self.table.clear()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Probe / Transfer", "Peak", "Speed (rpm)", "Phase (deg)", "Unit"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setRowCount(len(result.curves))
        for row, curve in enumerate(result.curves):
            if curve.magnitude:
                index = max(range(len(curve.magnitude)), key=lambda i: curve.magnitude[i])
                peak = curve.magnitude[index]
                speed = curve.x[index]
                phase = curve.phase_deg[index]
            else:
                peak = speed = phase = 0.0
            if curve.magnitude_unit == "m":
                peak_text = f"{peak * 1e6:.3f}"
                unit = "µm"
            elif curve.magnitude_unit == "m/N":
                peak_text = f"{peak:.4e}"
                unit = "m/N"
            else:
                peak_text = f"{peak:.4e}"
                unit = curve.magnitude_unit
            values = [curve.label, peak_text, f"{speed:,.0f}", f"{phase:.2f}", unit]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                self.table.setItem(row, col, item)

    def _set_message_table(self, message: str):
        self.table.clear()
        self.table.setColumnCount(1)
        self.table.setHorizontalHeaderLabels(["Status"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setRowCount(1)
        self.table.setItem(0, 0, QTableWidgetItem(message))

    def _restore_rotor_table(self):
        self.table.clear()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Mode", "Speed\n(rpm)", "Freq\n(Hz)", "Damping\n(%)", "Whirl"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        if self.last_result is not None and self.last_result.critical_speeds:
            result = self.last_result
            self.table.setRowCount(len(result.critical_speeds))
            for row, point in enumerate(result.critical_speeds):
                values = [row + 1, f"{point.rpm:,.0f}", f"{point.hz:.2f}", f"{(point.damping_ratio or 0) * 100:.2f}", point.whirl]
                for col, value in enumerate(values):
                    self.table.setItem(row, col, QTableWidgetItem(str(value)))
        else:
            self._fill_demo_table()


__all__ = ["EnhancedResultsPage"]
