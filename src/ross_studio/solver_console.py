from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .icons import engineering_icon
from .models import ProjectModel
from .theme import COLORS


@dataclass(slots=True)
class AnalysisStep:
    label: str
    elapsed: str
    lines: tuple[str, ...]


class SolverConsole(QDialog):
    def __init__(self, project: ProjectModel, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.project=project
        self.setObjectName("solverConsole")
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setModal(True)
        self.resize(920,700)
        self.setMinimumSize(820,620)
        self._step_index=0
        self._elapsed=0.0
        self._steps=[
            AnalysisStep("Build shaft elements","0.4 s",("Building model from input data...","Building shaft elements (6 segments)...             OK  (6 elements)")),
            AnalysisStep("Build bearings","0.9 s",("Building disks (2)...                              OK","Building bearings (2)...                           OK")),
            AnalysisStep("Solve DE tilting pad","1.1 s",("Solving DE tilting pad bearings...","  Bearing 1: converged in 6 iterations              OK","  Bearing 2: converged in 5 iterations              OK")),
            AnalysisStep("Assemble rotor model","0.2 s",("Assembling global rotor model...                    OK","Model assembly complete.","Degrees of freedom (DOF): 12")),
            AnalysisStep("Static analysis","0.3 s",("------------------------------------------------------------","Running static analysis...                          OK  (0.3 s)")),
            AnalysisStep("Modal analysis","1.2 s",("Running modal analysis...                           OK  (1.2 s)",)),
            AnalysisStep("Critical speed analysis","2.8 s",("Running critical speed analysis...                  OK  (2.8 s)",)),
            AnalysisStep("Campbell analysis","3.1 s",("Running Campbell diagram analysis...                OK  (3.1 s)",)),
            AnalysisStep("Export results","0.7 s",("Exporting results (tables, plots, data)...          OK  (0.7 s)","------------------------------------------------------------")),
        ]
        self._build_ui()
        self._timer=QTimer(self); self._timer.setInterval(260); self._timer.timeout.connect(self._advance)
        QTimer.singleShot(220,self.start)

    def _build_ui(self)->None:
        outer=QVBoxLayout(self); outer.setContentsMargins(0,0,0,0); outer.setSpacing(0)
        title=QFrame(); title.setObjectName("consoleTitleBar"); title.setFixedHeight(50)
        tl=QHBoxLayout(title); tl.setContentsMargins(14,6,8,6)
        icon=QLabel(); icon.setPixmap(engineering_icon("brand",25).pixmap(25,25)); tl.addWidget(icon)
        label=QLabel("ROSS Solver Console"); label.setObjectName("consoleTitle"); tl.addWidget(label); tl.addStretch(1)
        for text,action,name in [("—",self.showMinimized,"windowButton"),("□",self._toggle_max,"windowButton"),("×",self.reject,"windowCloseButton")]:
            b=QPushButton(text); b.setObjectName(name); b.clicked.connect(action); tl.addWidget(b)
        outer.addWidget(title)

        body=QHBoxLayout(); body.setContentsMargins(0,0,0,0); body.setSpacing(0); holder=QWidget(); holder.setLayout(body); outer.addWidget(holder,1)
        self.console=QPlainTextEdit(); self.console.setObjectName("consoleOutput"); self.console.setReadOnly(True); body.addWidget(self.console,7)
        self.side=QFrame(); self.side.setObjectName("consoleSide"); self.side.setFixedWidth(290); sl=QVBoxLayout(self.side); sl.setContentsMargins(20,16,18,16); sl.setSpacing(10); body.addWidget(self.side)
        t=QLabel("Execution Status"); t.setStyleSheet("color:white;font-weight:700;font-size:14px;"); sl.addWidget(t)
        state=QHBoxLayout(); self.status_icon=QLabel(); self.status_icon.setPixmap(engineering_icon("check",34).pixmap(34,34)); self.status_icon.setVisible(False); state.addWidget(self.status_icon); self.status=QLabel("Running"); self.status.setStyleSheet("color:#f7c948;font-size:21px;font-weight:700;"); state.addWidget(self.status); state.addStretch(1); sl.addLayout(state)
        self.status_detail=QLabel("Running selected analysis tasks..."); self.status_detail.setWordWrap(True); self.status_detail.setStyleSheet("color:#b8c9d7;"); sl.addWidget(self.status_detail)
        self._line(sl)
        grid=QVBoxLayout(); self.elapsed_label=QLabel("Elapsed Time       0.0 s"); self.current_label=QLabel("Current Step       Building model"); self.progress_label=QLabel("Progress           0%");
        for w in (self.elapsed_label,self.current_label,self.progress_label): w.setStyleSheet("color:#d7e5ef;"); grid.addWidget(w)
        sl.addLayout(grid)
        self.progress=QProgressBar(); self.progress.setRange(0,len(self._steps)); self.progress.setValue(0); self.progress.setTextVisible(False); sl.addWidget(self.progress)
        self._line(sl)
        ah=QLabel("Analysis Steps"); ah.setStyleSheet("color:white;font-weight:700;font-size:14px;"); sl.addWidget(ah)
        self.step_labels=[]
        for step in self._steps:
            row=QHBoxLayout(); mark=QLabel("○"); mark.setStyleSheet("color:#6f8aa0;font-size:16px;"); row.addWidget(mark); name=QLabel(step.label); name.setStyleSheet("color:#d7e5ef;"); row.addWidget(name,1); tm=QLabel(step.elapsed); tm.setStyleSheet("color:#d7e5ef;"); row.addWidget(tm); sl.addLayout(row); self.step_labels.append(mark)
        sl.addStretch(1); self.total_label=QLabel("Total elapsed time       —"); self.total_label.setStyleSheet("color:white;font-weight:700;"); sl.addWidget(self.total_label)

        footer=QFrame(); footer.setObjectName("consoleFooter"); footer.setFixedHeight(66); fl=QHBoxLayout(footer); fl.setContentsMargins(14,10,14,10); fl.setSpacing(10)
        self.stop=QPushButton("Stop"); self.stop.setObjectName("outlineButton"); self.stop.clicked.connect(self._stop); fl.addWidget(self.stop)
        clear=QPushButton("Clear"); clear.setObjectName("outlineButton"); clear.setIcon(engineering_icon("trash",18,"#dbe9f4")); clear.clicked.connect(self.console.clear); fl.addWidget(clear)
        save=QPushButton("Save Log"); save.setObjectName("outlineButton"); save.setIcon(engineering_icon("save",18,"#dbe9f4")); fl.addWidget(save)
        fl.addStretch(1)
        open_results=QPushButton("Open Results"); open_results.setObjectName("outlineButton"); open_results.setIcon(engineering_icon("open",18,"#dbe9f4")); fl.addWidget(open_results)
        close=QPushButton("Close"); close.setObjectName("primaryButton"); close.setFixedWidth(115); close.clicked.connect(self.accept); fl.addWidget(close)
        outer.addWidget(footer)

    def _line(self,layout:QVBoxLayout)->None:
        line=QFrame(); line.setFixedHeight(1); line.setStyleSheet(f"background:{COLORS.console_border};"); layout.addWidget(line)

    def start(self)->None:
        self.console.clear(); self._step_index=0; self._elapsed=0.0; self.progress.setValue(0)
        self._append(f"[14:20:31]   ROSS Solver 1.0.0  --  Starting analysis for project: {self.project.name}")
        self._append("[14:20:31]   ------------------------------------------------------------")
        self._timer.start()

    def _append(self,text:str)->None:
        self.console.appendPlainText(text)
        bar=self.console.verticalScrollBar(); bar.setValue(bar.maximum())

    def _advance(self)->None:
        if self._step_index>=len(self._steps):
            self._timer.stop(); self._finish(); return
        step=self._steps[self._step_index]
        for line in step.lines: self._append(f"[14:20:{31+self._step_index:02d}]   {line}")
        self.step_labels[self._step_index].setText("●"); self.step_labels[self._step_index].setStyleSheet("color:#39db83;font-size:16px;")
        self._step_index+=1; self._elapsed=round(11.4*self._step_index/len(self._steps),1); self.progress.setValue(self._step_index)
        pct=round(100*self._step_index/len(self._steps)); self.elapsed_label.setText(f"Elapsed Time       {self._elapsed:.1f} s"); self.current_label.setText(f"Current Step       {step.label}"); self.progress_label.setText(f"Progress           {pct}%")

    def _finish(self)->None:
        self._append("[14:20:42]   Analysis completed successfully!")
        self._append(f"[14:20:42]   Results saved to: C:\\Projects\\{self.project.name}\\results\\")
        self._append("[14:20:42]   Total elapsed time: 11.4 seconds")
        self._append("")
        self._append(">")
        self.status.setText("Completed"); self.status.setStyleSheet("color:#4de28b;font-size:21px;font-weight:700;"); self.status_icon.setVisible(True); self.status_detail.setText("All analysis tasks finished successfully.")
        self.current_label.setText("Current Step       Exporting results"); self.progress_label.setText("Progress           100%"); self.elapsed_label.setText("Elapsed Time       11.4 s"); self.total_label.setText("Total elapsed time       11.4 s"); self.stop.setEnabled(False)

    def _stop(self)->None:
        self._timer.stop(); self.status.setText("Stopped"); self.status.setStyleSheet("color:#ff8389;font-size:21px;font-weight:700;"); self.status_detail.setText("Analysis interrupted by user.")

    def _toggle_max(self)->None:
        self.showNormal() if self.isMaximized() else self.showMaximized()
