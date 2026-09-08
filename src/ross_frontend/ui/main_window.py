from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QMainWindow, QMessageBox, QStackedWidget, QVBoxLayout, QWidget

from ..domain import RotorProject
from ..legacy_import import load_irdin_project
from .enhanced_bearing_page import EnhancedBearingPage
from .enhanced_results_page import EnhancedResultsPage
from .industrial_model_page import IndustrialModelPage
from .sample_project import sample_project
from .solver_console import SolverConsoleDialog
from .theme import application_stylesheet
from .widgets import Sidebar, StatusStrip, TitleBar, TopToolbar


class RossStudioWindow(QMainWindow):
    def __init__(self, project: RotorProject | None = None):
        super().__init__(); self.project=project or sample_project(); self.console_dialog=None
        self.setWindowTitle("ROSS STUDIO"); self.setMinimumSize(1280,760); self.resize(1660,930); self.setWindowFlags(self.windowFlags() | Qt.WindowType.FramelessWindowHint)
        root=QWidget(); root.setObjectName("AppRoot"); self.setCentralWidget(root); outer=QVBoxLayout(root); outer.setContentsMargins(0,0,0,0); outer.setSpacing(0)
        self.titlebar=TitleBar(self,self.project.reference or "WGM20"); outer.addWidget(self.titlebar)
        content=QHBoxLayout(); content.setContentsMargins(0,0,0,0); content.setSpacing(0); outer.addLayout(content,1)
        self.sidebar=Sidebar(); self.sidebar.pageRequested.connect(self.navigate); content.addWidget(self.sidebar)
        main=QWidget(); main.setObjectName("ContentHost"); ml=QVBoxLayout(main); ml.setContentsMargins(0,0,0,0); ml.setSpacing(0); content.addWidget(main,1)
        self.toolbar=TopToolbar(); self.toolbar.actionTriggered.connect(self.toolbar_action); ml.addWidget(self.toolbar)
        self.stack=QStackedWidget(); ml.addWidget(self.stack,1)
        self.model_page=IndustrialModelPage(self.project); self.bearing_page=EnhancedBearingPage(self.project); self.results_page=EnhancedResultsPage(self.project)
        self.stack.addWidget(self.model_page); self.stack.addWidget(self.bearing_page); self.stack.addWidget(self.results_page)
        self.status=StatusStrip(); ml.addWidget(self.status)
        self.model_page.runRequested.connect(self.run_analysis); self.model_page.validateRequested.connect(self.validate_model); self.model_page.projectChanged.connect(self.on_project_changed)
        self.bearing_page.projectChanged.connect(self.on_project_changed); self.bearing_page.statusMessage.connect(self.status.set_state)
        self.results_page.statusMessage.connect(self.status.set_state)
        self.setStyleSheet(application_stylesheet()); self.navigate("rotor")

    def navigate(self, key: str):
        if key in {"rotor","shaft","disks","supports","couplings","loads","home"}:
            self.stack.setCurrentWidget(self.model_page); self.sidebar.set_active("rotor" if key=="home" else key if key in self.sidebar.buttons else "rotor")
            if key=="shaft": self.model_page.tabs.setCurrentIndex(0)
            elif key=="disks": self.model_page.tabs.setCurrentIndex(1)
            elif key=="supports": self.model_page.tabs.setCurrentIndex(3)
            elif key=="couplings": self.model_page.tabs.setCurrentIndex(4)
            elif key=="loads": self.model_page.tabs.setCurrentIndex(5)
        elif key=="bearings":
            self.stack.setCurrentWidget(self.bearing_page); self.sidebar.set_active("bearings")
        elif key in {"rotor_dynamics","response","stability","transient","faults","stochastic","results"}:
            self.stack.setCurrentWidget(self.results_page); self.sidebar.set_active(key)
        else:
            self.status.set_state("Module selected",key.replace("_"," ").title(),True)

    def _set_project(self, project: RotorProject):
        self.project=project
        self.model_page.set_project(project)
        self.bearing_page.project=project
        self.results_page.project=project
        self.on_project_changed(project)

    def on_project_changed(self, project: RotorProject):
        self.project=project; self.titlebar.project_label.setText(project.reference or "Untitled"); self.status.project.setText(project.reference or "Untitled"); self.results_page.project=project

    def validate_model(self):
        try:
            self.project.validate(); self.status.set_state("Model validated","No issues found",True)
        except Exception as exc:
            self.status.set_state("Validation failed",str(exc),False); QMessageBox.warning(self,"Model validation",str(exc))

    def run_analysis(self):
        try:
            self.project.validate()
        except Exception as exc:
            self.status.set_state("Validation failed",str(exc),False); QMessageBox.warning(self,"Cannot run analysis",str(exc)); return
        self.status.set_state("Analysis running","ROSS solver active",True)
        self.console_dialog=SolverConsoleDialog(self.project,self); self.console_dialog.resultReady.connect(self.on_analysis_result); self.console_dialog.show(); self.console_dialog.start()

    def on_analysis_result(self, result):
        self.results_page.set_result(result); self.status.set_state("Analysis completed","No issues found",True)

    def toolbar_action(self, action: str):
        if action=="save": self.save_project()
        elif action=="new": self.reset_project()
        elif action=="open": self.open_project()
        elif action in {"fit","zoom_in","zoom_out"}: self.status.set_state("Rotor view",action.replace("_"," ").title(),True)

    def open_project(self):
        path,_=QFileDialog.getOpenFileName(
            self,
            "Open RotorDin / ROSS Studio project",
            "",
            "RotorDin legacy (*.txt *.irdin *.ini);;All files (*)",
        )
        if not path:
            return
        try:
            project=load_irdin_project(path)
        except Exception as exc:
            self.status.set_state("Import failed",str(exc),False)
            QMessageBox.warning(self,"Cannot import project",str(exc))
            return
        self._set_project(project)
        warnings=project.metadata.get("legacy_import",{}).get("warnings",[])
        detail=f"{len(project.shaft)} shaft sections, {len(project.disks)} disks, {len(project.bearings)} bearings"
        if warnings:
            detail += f" | {len(warnings)} migration warning(s)"
        self.status.set_state("RotorDin project imported",detail,True)
        self.navigate("rotor")

    def save_project(self):
        default=f"{self.project.reference or 'project'}.json"; path,_=QFileDialog.getSaveFileName(self,"Save ROSS Studio project",default,"ROSS project (*.json)")
        if not path: return
        Path(path).write_text(json.dumps(self.project.to_dict(),indent=2,ensure_ascii=False,default=str),encoding="utf-8"); self.status.set_state("Project saved",Path(path).name,True)

    def reset_project(self):
        answer=QMessageBox.question(self,"New project","Replace the current project with the approved WGM20 starter model?")
        if answer!=QMessageBox.StandardButton.Yes: return
        self._set_project(sample_project()); self.navigate("rotor"); self.status.set_state("New project","WGM20 starter model loaded",True)
