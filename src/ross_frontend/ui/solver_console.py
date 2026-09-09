from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QElapsedTimer, QThread, QTimer, Qt, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel, QPlainTextEdit, QProgressBar, QPushButton, QToolButton, QVBoxLayout

from ..backends.base import AnalysisResult
from ..domain import RotorProject
from .icons import app_icon, studio_icon
from .theme import P


class SolverWorker(QObject):
    progress = Signal(str)
    completed = Signal(object)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, project: RotorProject):
        super().__init__(); self.project=project

    @Slot()
    def run(self):
        try:
            from ..backends.ross.backend import RossBackend
            result=RossBackend().run(self.project, progress=self.progress.emit)
            self.completed.emit(result)
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")
        finally:
            self.finished.emit()


class SolverConsoleDialog(QDialog):
    resultReady = Signal(object)

    def __init__(self, project: RotorProject, parent=None):
        super().__init__(parent); self.project=project; self.result: AnalysisResult | None=None; self.thread=None; self.worker=None
        self.setWindowFlags(Qt.WindowType.Dialog|Qt.WindowType.FramelessWindowHint); self.setModal(False); self.resize(920,610); self.setMinimumSize(820,560)
        self.setStyleSheet(f"QDialog{{background:{P.terminal_panel};border:1px solid #24485F;border-radius:8px;}} QLabel{{color:#D7E6F2;}} QPushButton{{background:#132E42;color:#DDEAF4;border:1px solid #49677C;border-radius:4px;padding:7px 12px;}} QPushButton:hover{{background:#1A3A51;}}")
        root=QVBoxLayout(self); root.setContentsMargins(0,0,0,0); root.setSpacing(0)
        title=QFrame(); title.setFixedHeight(52); title.setStyleSheet(f"background:{P.navy};border-top-left-radius:8px;border-top-right-radius:8px;"); tl=QHBoxLayout(title); tl.setContentsMargins(16,0,8,0); icon=QLabel(); icon.setPixmap(app_icon(22).pixmap(22,22)); tl.addWidget(icon); lab=QLabel("ROSS Solver Console"); lab.setStyleSheet("color:white;font-size:16px;font-weight:700;"); tl.addWidget(lab); tl.addStretch(1)
        mini=QToolButton(); mini.setText("—"); mini.setStyleSheet("color:white;border:none;"); mini.clicked.connect(self.showMinimized); tl.addWidget(mini); close=QToolButton(); close.setText("×"); close.setStyleSheet("color:white;border:none;font-size:18px;"); close.clicked.connect(self.close); tl.addWidget(close); root.addWidget(title)
        body=QHBoxLayout(); body.setContentsMargins(12,0,12,10); body.setSpacing(0); root.addLayout(body,1)
        self.console=QPlainTextEdit(); self.console.setReadOnly(True); font=QFont("Cascadia Mono"); font.setStyleHint(QFont.StyleHint.Monospace); font.setPointSize(10); self.console.setFont(font); self.console.setStyleSheet(f"QPlainTextEdit{{background:{P.terminal};color:{P.terminal_text};border:none;padding:12px;selection-background-color:#245477;}}"); body.addWidget(self.console,1)
        panel=QFrame(); panel.setFixedWidth(275); panel.setStyleSheet(f"background:{P.terminal_panel};border-left:1px solid {P.terminal_line};"); pr=QVBoxLayout(panel); pr.setContentsMargins(16,14,16,12); pr.setSpacing(8); body.addWidget(panel)
        head=QLabel("Execution Status"); head.setStyleSheet("font-weight:700;color:white;"); pr.addWidget(head)
        state=QHBoxLayout(); self.state_icon=QLabel("●"); self.state_icon.setStyleSheet("color:#26D985;font-size:26px;"); state.addWidget(self.state_icon); self.state_label=QLabel("Running"); self.state_label.setStyleSheet("color:#26D985;font-size:18px;font-weight:700;"); state.addWidget(self.state_label); state.addStretch(1); pr.addLayout(state)
        self.state_detail=QLabel("ROSS analysis is running."); self.state_detail.setWordWrap(True); self.state_detail.setStyleSheet("color:#AFC2D0;"); pr.addWidget(self.state_detail)
        line=QFrame(); line.setFixedHeight(1); line.setStyleSheet(f"background:{P.terminal_line};"); pr.addWidget(line)
        self.elapsed_label=QLabel("Elapsed Time        0.0 s"); self.step_label=QLabel("Current Step        Building model"); pr.addWidget(self.elapsed_label); pr.addWidget(self.step_label)
        prog_lab=QHBoxLayout(); prog_lab.addWidget(QLabel("Progress")); prog_lab.addStretch(1); self.percent=QLabel("0%"); prog_lab.addWidget(self.percent); pr.addLayout(prog_lab); self.progressbar=QProgressBar(); self.progressbar.setRange(0,100); self.progressbar.setValue(0); pr.addWidget(self.progressbar)
        line2=QFrame(); line2.setFixedHeight(1); line2.setStyleSheet(f"background:{P.terminal_line};"); pr.addWidget(line2); ah=QLabel("Analysis Steps"); ah.setStyleSheet("font-weight:700;color:white;"); pr.addWidget(ah)
        self.steps=[]
        for text in ("Build shaft elements","Build bearings","Solve DE tilting pad","Assemble rotor model","Static analysis","Modal analysis","Critical speed analysis","Campbell analysis","Export results"):
            row=QHBoxLayout(); icon=QLabel("○"); icon.setStyleSheet("color:#7E9BAD;"); label=QLabel(text); label.setStyleSheet("color:#C6D6E0;"); tm=QLabel(""); tm.setStyleSheet("color:#A4BAC9;"); row.addWidget(icon); row.addWidget(label,1); row.addWidget(tm); pr.addLayout(row); self.steps.append((icon,label,tm))
        pr.addStretch(1); self.total=QLabel("Total elapsed time     —"); self.total.setStyleSheet("font-weight:600;color:white;"); pr.addWidget(self.total)
        footer=QFrame(); footer.setFixedHeight(60); footer.setStyleSheet(f"background:{P.terminal_panel};border-top:1px solid {P.terminal_line};"); fl=QHBoxLayout(footer); fl.setContentsMargins(14,9,14,9); fl.setSpacing(10); root.addWidget(footer)
        self.stop=QPushButton("■  Stop"); self.stop.setEnabled(False); fl.addWidget(self.stop); clear=QPushButton("Clear"); clear.setIcon(studio_icon("trash","#DDEAF4",16)); clear.clicked.connect(self.console.clear); fl.addWidget(clear); save=QPushButton("Save Log"); save.setIcon(studio_icon("save","#DDEAF4",16)); save.clicked.connect(self.save_log); fl.addWidget(save); fl.addStretch(1); self.open_results=QPushButton("Open Results"); self.open_results.setIcon(studio_icon("open","#DDEAF4",16)); self.open_results.setEnabled(False); self.open_results.clicked.connect(self.open_result_folder); fl.addWidget(self.open_results); closeb=QPushButton("Close"); closeb.setStyleSheet(f"background:{P.blue};color:white;border-color:{P.blue};"); closeb.clicked.connect(self.close); fl.addWidget(closeb)
        self.timer=QElapsedTimer(); self.ui_timer=QTimer(self); self.ui_timer.timeout.connect(self._tick); self._step_index=0

    def start(self):
        self.console.clear(); self._append(f"ROSS Solver -- Starting analysis for project: {self.project.reference or 'Untitled'}"); self._append("------------------------------------------------------------"); self.timer.start(); self.ui_timer.start(100); self.thread=QThread(self); self.worker=SolverWorker(self.project); self.worker.moveToThread(self.thread); self.thread.started.connect(self.worker.run); self.worker.progress.connect(self.on_progress); self.worker.completed.connect(self.on_completed); self.worker.failed.connect(self.on_failed); self.worker.finished.connect(self.thread.quit); self.thread.finished.connect(self._thread_finished); self.thread.start()

    def _append(self, text: str):
        seconds=self.timer.elapsed()/1000 if self.timer.isValid() else 0; self.console.appendPlainText(f"[{seconds:07.2f}]  {text}")

    @Slot(str)
    def on_progress(self, msg: str):
        self._append(msg); low=msg.lower(); mapping=[("building rotor",0),("model built",3),("static",4),("modal",5),("critical",6),("campbell",7),("completed",8)]
        for token,idx in mapping:
            if token in low:
                self._mark_through(idx); self.step_label.setText(f"Current Step        {self.steps[idx][1].text()}"); break

    def _mark_through(self, idx: int):
        self._step_index=max(self._step_index,idx)
        for i,(icon,label,tm) in enumerate(self.steps):
            if i<=idx: icon.setText("●"); icon.setStyleSheet("color:#27D883;"); tm.setText("OK")
        val=min(95,int((idx+1)/len(self.steps)*100)); self.progressbar.setValue(val); self.percent.setText(f"{val}%")

    @Slot(object)
    def on_completed(self, result: AnalysisResult):
        self.result=result; self._mark_through(len(self.steps)-1); self.progressbar.setValue(100); self.percent.setText("100%"); self.state_label.setText("Completed"); self.state_label.setStyleSheet("color:#26D985;font-size:18px;font-weight:700;"); self.state_detail.setText("All analysis tasks finished successfully."); self._append("Analysis completed successfully!"); self._append(f"Results saved to: {result.run_dir}"); self.open_results.setEnabled(True); self.resultReady.emit(result)

    @Slot(str)
    def on_failed(self, message: str):
        self.state_icon.setStyleSheet(f"color:{P.danger};font-size:26px;"); self.state_label.setText("Failed"); self.state_label.setStyleSheet(f"color:{P.danger};font-size:18px;font-weight:700;"); self.state_detail.setText(message); self._append(f"ERROR: {message}")

    def _thread_finished(self):
        self.ui_timer.stop(); elapsed=self.timer.elapsed()/1000; self.elapsed_label.setText(f"Elapsed Time        {elapsed:.1f} s"); self.total.setText(f"Total elapsed time     {elapsed:.1f} s")

    def _tick(self): self.elapsed_label.setText(f"Elapsed Time        {self.timer.elapsed()/1000:.1f} s")

    def save_log(self):
        path,_=QFileDialog.getSaveFileName(self,"Save solver log","ross_solver.log","Log files (*.log);;Text files (*.txt)")
        if path: Path(path).write_text(self.console.toPlainText(),encoding="utf-8")

    def open_result_folder(self):
        if self.result: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.result.run_dir)))
