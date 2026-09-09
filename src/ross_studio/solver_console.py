from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, QThread, QTimer, Qt, Signal, Slot
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .analysis_pipeline import AnalysisPipelineResult, AnalysisPipelineService, PipelineEvent
from .icons import engineering_icon
from .models import ProjectModel
from .theme import COLORS


class PipelineWorker(QObject):
    event = Signal(object)
    completed = Signal(object)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, project: ProjectModel, service: AnalysisPipelineService) -> None:
        super().__init__()
        self.project = project
        self.service = service
        self.cancel_requested = False

    def request_cancel(self) -> None:
        self.cancel_requested = True

    @Slot()
    def run(self) -> None:
        try:
            if self.project.engineering is None:
                raise RuntimeError("Engineering domain is not loaded.")
            result = self.service.run(
                self.project.engineering,
                progress=self.event.emit,
                cancelled=lambda: self.cancel_requested,
            )
        except Exception as exc:  # displayed verbatim in engineering console
            self.failed.emit(str(exc))
        else:
            self.completed.emit(result)
        finally:
            self.finished.emit()


class SolverConsole(QDialog):
    """Live terminal-style execution window backed by the real ROSS pipeline."""

    def __init__(
        self,
        project: ProjectModel,
        parent: QWidget | None = None,
        *,
        service: AnalysisPipelineService | None = None,
        autostart: bool = True,
    ) -> None:
        super().__init__(parent)
        self.project = project
        self.service = service or AnalysisPipelineService()
        self.analysis_result: AnalysisPipelineResult | None = None
        self._thread: QThread | None = None
        self._worker: PipelineWorker | None = None
        self._running = False
        self._stage_elapsed: dict[str, float] = {}

        self.setObjectName("solverConsole")
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setModal(True)
        self.resize(980, 720)
        self.setMinimumSize(860, 640)
        self._build_ui()
        if autostart:
            QTimer.singleShot(0, self.start)

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        title = QFrame()
        title.setObjectName("consoleTitleBar")
        title.setFixedHeight(50)
        tl = QHBoxLayout(title)
        tl.setContentsMargins(14, 6, 8, 6)
        icon = QLabel()
        icon.setPixmap(engineering_icon("brand", 25).pixmap(25, 25))
        tl.addWidget(icon)
        label = QLabel("ROSS Solver Console")
        label.setObjectName("consoleTitle")
        tl.addWidget(label)
        tl.addStretch(1)
        minimize = QPushButton("—")
        minimize.setObjectName("windowButton")
        minimize.clicked.connect(self.showMinimized)
        tl.addWidget(minimize)
        maximize = QPushButton("□")
        maximize.setObjectName("windowButton")
        maximize.clicked.connect(self._toggle_max)
        tl.addWidget(maximize)
        close_title = QPushButton("×")
        close_title.setObjectName("windowCloseButton")
        close_title.clicked.connect(self._request_close)
        tl.addWidget(close_title)
        outer.addWidget(title)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        holder = QWidget()
        holder.setLayout(body)
        outer.addWidget(holder, 1)

        self.console = QPlainTextEdit()
        self.console.setObjectName("consoleOutput")
        self.console.setReadOnly(True)
        body.addWidget(self.console, 7)

        self.side = QFrame()
        self.side.setObjectName("consoleSide")
        self.side.setFixedWidth(315)
        sl = QVBoxLayout(self.side)
        sl.setContentsMargins(20, 16, 18, 16)
        sl.setSpacing(10)
        body.addWidget(self.side)

        title_status = QLabel("Execution Status")
        title_status.setStyleSheet("color:white;font-weight:700;font-size:14px;")
        sl.addWidget(title_status)
        state = QHBoxLayout()
        self.status_icon = QLabel()
        self.status_icon.setPixmap(engineering_icon("check", 34).pixmap(34, 34))
        self.status_icon.setVisible(False)
        state.addWidget(self.status_icon)
        self.status = QLabel("Ready")
        self.status.setStyleSheet("color:#d7e5ef;font-size:21px;font-weight:700;")
        state.addWidget(self.status)
        state.addStretch(1)
        sl.addLayout(state)
        self.status_detail = QLabel("Strict OP-W60 ROSS pipeline is ready.")
        self.status_detail.setWordWrap(True)
        self.status_detail.setStyleSheet("color:#b8c9d7;")
        sl.addWidget(self.status_detail)
        self._line(sl)

        self.elapsed_label = QLabel("Elapsed Time       0.0 s")
        self.current_label = QLabel("Current Step       —")
        self.progress_label = QLabel("Progress           0%")
        for widget in (self.elapsed_label, self.current_label, self.progress_label):
            widget.setStyleSheet("color:#d7e5ef;")
            sl.addWidget(widget)

        self.progress = QProgressBar()
        self.progress.setRange(0, len(self.service.STAGES))
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        sl.addWidget(self.progress)
        self._line(sl)

        ah = QLabel("Analysis Steps")
        ah.setStyleSheet("color:white;font-weight:700;font-size:14px;")
        sl.addWidget(ah)
        self.step_labels: dict[str, QLabel] = {}
        self.step_times: dict[str, QLabel] = {}
        for stage in self.service.STAGES:
            row = QHBoxLayout()
            mark = QLabel("○")
            mark.setStyleSheet("color:#6f8aa0;font-size:16px;")
            row.addWidget(mark)
            name = QLabel(stage)
            name.setStyleSheet("color:#d7e5ef;")
            row.addWidget(name, 1)
            tm = QLabel("—")
            tm.setStyleSheet("color:#9fb6c8;")
            row.addWidget(tm)
            sl.addLayout(row)
            self.step_labels[stage] = mark
            self.step_times[stage] = tm
        sl.addStretch(1)
        self.total_label = QLabel("Total elapsed time       —")
        self.total_label.setStyleSheet("color:white;font-weight:700;")
        sl.addWidget(self.total_label)

        footer = QFrame()
        footer.setObjectName("consoleFooter")
        footer.setFixedHeight(66)
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(14, 10, 14, 10)
        fl.setSpacing(10)
        self.stop = QPushButton("Stop after current stage")
        self.stop.setObjectName("outlineButton")
        self.stop.clicked.connect(self._stop)
        self.stop.setEnabled(False)
        fl.addWidget(self.stop)
        clear = QPushButton("Clear")
        clear.setObjectName("outlineButton")
        clear.setIcon(engineering_icon("trash", 18, "#dbe9f4"))
        clear.clicked.connect(self.console.clear)
        fl.addWidget(clear)
        save = QPushButton("Save Log")
        save.setObjectName("outlineButton")
        save.setIcon(engineering_icon("save", 18, "#dbe9f4"))
        save.clicked.connect(self._save_log)
        fl.addWidget(save)
        fl.addStretch(1)
        self.open_results = QPushButton("Open Results")
        self.open_results.setObjectName("outlineButton")
        self.open_results.setIcon(engineering_icon("open", 18, "#dbe9f4"))
        self.open_results.setEnabled(False)
        self.open_results.clicked.connect(self.accept)
        fl.addWidget(self.open_results)
        self.close_button = QPushButton("Close")
        self.close_button.setObjectName("primaryButton")
        self.close_button.setFixedWidth(115)
        self.close_button.clicked.connect(self._request_close)
        fl.addWidget(self.close_button)
        outer.addWidget(footer)

    def _line(self, layout: QVBoxLayout) -> None:
        line = QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet(f"background:{COLORS.console_border};")
        layout.addWidget(line)

    def _timestamp(self) -> str:
        return datetime.now().strftime("%H:%M:%S")

    def _append(self, text: str) -> None:
        self.console.appendPlainText(f"[{self._timestamp()}]   {text}")
        bar = self.console.verticalScrollBar()
        bar.setValue(bar.maximum())

    def start(self) -> None:
        if self._running:
            return
        self.console.clear()
        self.analysis_result = None
        self._stage_elapsed.clear()
        self.progress.setValue(0)
        self.open_results.setEnabled(False)
        self.stop.setEnabled(True)
        self.status_icon.setVisible(False)
        self.status.setText("Running")
        self.status.setStyleSheet("color:#f7c948;font-size:21px;font-weight:700;")
        self.status_detail.setText("Executing the real ROSS 2.3 scientific pipeline...")
        self._append(f"ROSS Studio 0.8.0 -- Starting real analysis for project: {self.project.name}")
        self._append("Pipeline: strict Rotor -> Static -> Modal -> Critical -> Campbell -> Unbalance -> Probes -> Results")
        self._append("No simulated timing or mock solver output is used.")
        self._running = True

        self._thread = QThread(self)
        self._worker = PipelineWorker(self.project, self.service)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.event.connect(self._on_event)
        self._worker.completed.connect(self._on_completed)
        self._worker.failed.connect(self._on_failed)
        self._worker.finished.connect(self._thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.finished.connect(self._on_thread_finished)
        self._thread.start()

    @Slot(object)
    def _on_event(self, event: PipelineEvent) -> None:
        mark = self.step_labels.get(event.stage)
        tm = self.step_times.get(event.stage)
        if event.state == "running":
            if mark is not None:
                mark.setText("▶")
                mark.setStyleSheet("color:#f7c948;font-size:16px;")
            self.current_label.setText(f"Current Step       {event.stage}")
            self.progress.setValue(max(0, event.index - 1))
            self._append(f"BEGIN {event.stage}: {event.message}")
        elif event.state == "completed":
            if mark is not None:
                mark.setText("●")
                mark.setStyleSheet("color:#39db83;font-size:16px;")
            if tm is not None:
                tm.setText(f"{event.elapsed_s:.2f} s")
            self._stage_elapsed[event.stage] = event.elapsed_s
            self.progress.setValue(event.index)
            pct = round(100 * event.index / event.total)
            self.progress_label.setText(f"Progress           {pct}%")
            elapsed = sum(self._stage_elapsed.values())
            self.elapsed_label.setText(f"Elapsed Time       {elapsed:.2f} s")
            self._append(f"PASS  {event.stage} ({event.elapsed_s:.3f} s): {event.message}")
        else:
            if mark is not None:
                mark.setText("×")
                mark.setStyleSheet("color:#ff8389;font-size:16px;")
            self._append(f"FAIL  {event.stage}: {event.message}")

    @Slot(object)
    def _on_completed(self, result: AnalysisPipelineResult) -> None:
        self.analysis_result = result
        self._running = False
        self.stop.setEnabled(False)
        self.open_results.setEnabled(True)
        self.status.setText("Completed")
        self.status.setStyleSheet("color:#4de28b;font-size:21px;font-weight:700;")
        self.status_icon.setVisible(True)
        self.status_detail.setText("All real ROSS analysis stages completed successfully.")
        self.progress.setValue(len(self.service.STAGES))
        self.progress_label.setText("Progress           100%")
        self.elapsed_label.setText(f"Elapsed Time       {result.total_elapsed_s:.2f} s")
        self.total_label.setText(f"Total elapsed time       {result.total_elapsed_s:.2f} s")
        self._append("------------------------------------------------------------")
        self._append(f"Strict shaft topology: {len(result.build.shaft_plan)} ShaftElements / {len(result.build.node_positions_mm)} shaft nodes")
        self._append(f"Modal modes returned: {len(result.modal_modes)}")
        self._append(f"Critical speeds in qualified K/C envelope: {len(result.critical_speeds)}")
        self._append(f"Unbalance response stations: {len(result.speed_rpm)}")
        self._append(f"Probe channels: {len(result.probe_responses)}")
        for probe in result.probe_responses:
            self._append(
                f"  {probe.name}: peak={probe.peak_amplitude_um:.6g} um at {probe.peak_speed_rpm:.1f} rpm; "
                f"rated={probe.rated_amplitude_um:.6g} um at {probe.rated_speed_rpm:.1f} rpm"
            )
        for audit in result.audits:
            self._append(f"AUDIT [{audit.severity.upper()}] {audit.code}: {audit.message}")
        self._append("Analysis completed successfully.")

    @Slot(str)
    def _on_failed(self, message: str) -> None:
        self._running = False
        self.stop.setEnabled(False)
        self.open_results.setEnabled(False)
        self.status.setText("Failed")
        self.status.setStyleSheet("color:#ff8389;font-size:21px;font-weight:700;")
        self.status_detail.setText(message)
        self._append(f"ANALYSIS FAILED: {message}")

    @Slot()
    def _on_thread_finished(self) -> None:
        self._thread = None
        self._worker = None

    def _stop(self) -> None:
        if self._worker is not None and self._running:
            self._worker.request_cancel()
            self.stop.setEnabled(False)
            self.status_detail.setText("Cancellation requested; the active ROSS solve will finish before stopping.")
            self._append("Cancellation requested. ROSS will stop between analysis stages; the active numerical solve is not force-killed.")

    def _request_close(self) -> None:
        if self._running:
            self._stop()
            return
        self.accept() if self.analysis_result is not None else self.reject()

    def _save_log(self) -> None:
        default = str(Path.home() / f"{self.project.name}_ross_pipeline.log")
        path, _ = QFileDialog.getSaveFileName(self, "Save ROSS pipeline log", default, "Log files (*.log *.txt)")
        if path:
            Path(path).write_text(self.console.toPlainText(), encoding="utf-8")

    def _toggle_max(self) -> None:
        self.showNormal() if self.isMaximized() else self.showMaximized()

    def reject(self) -> None:
        if self._running:
            self._stop()
            return
        super().reject()
