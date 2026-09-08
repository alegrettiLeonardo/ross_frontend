from __future__ import annotations

import sys

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .icons import engineering_icon
from .models import BearingModel, ProjectModel
from .pages.bearing_studio import BearingStudioPage
from .pages.results import AnalysisResultsPage
from .pages.rotor_model import RotorModelPage
from .solver_console import SolverConsole
from .theme import APP_STYLESHEET
from .widgets import AppToolbar, Sidebar, StatusBar


class TitleBar(QFrame):
    def __init__(self, window: QMainWindow, project: ProjectModel) -> None:
        super().__init__(window)
        self.window = window
        self.setObjectName("titleBar")
        self.setFixedHeight(55)
        self._drag_position: QPoint | None = None
        layout=QHBoxLayout(self); layout.setContentsMargins(16,6,8,6); layout.setSpacing(10)
        brand_icon=QLabel(); brand_icon.setPixmap(engineering_icon("brand",27).pixmap(27,27)); layout.addWidget(brand_icon)
        brand=QLabel("ROSS STUDIO"); brand.setObjectName("brandLabel"); layout.addWidget(brand)
        sep=QLabel("|"); sep.setStyleSheet("color:#9eb9cf;font-size:20px;"); layout.addWidget(sep)
        proj=QLabel(project.name); proj.setObjectName("projectTitle"); layout.addWidget(proj)
        layout.addStretch(1)
        minimize=QPushButton("—"); minimize.setObjectName("windowButton"); minimize.clicked.connect(window.showMinimized); layout.addWidget(minimize)
        maximize=QPushButton("□"); maximize.setObjectName("windowButton"); maximize.clicked.connect(self._toggle_max); layout.addWidget(maximize)
        close=QPushButton("×"); close.setObjectName("windowCloseButton"); close.clicked.connect(window.close); layout.addWidget(close)

    def _toggle_max(self)->None:
        self.window.showNormal() if self.window.isMaximized() else self.window.showMaximized()

    def mousePressEvent(self,event) -> None:  # noqa: N802
        if event.button()==Qt.MouseButton.LeftButton:
            self._drag_position=event.globalPosition().toPoint()-self.window.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self,event) -> None:  # noqa: N802
        if self._drag_position is not None and event.buttons() & Qt.MouseButton.LeftButton and not self.window.isMaximized():
            self.window.move(event.globalPosition().toPoint()-self._drag_position)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self,event) -> None:  # noqa: N802
        self._drag_position=None; super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self,event) -> None:  # noqa: N802
        if event.button()==Qt.MouseButton.LeftButton: self._toggle_max()
        super().mouseDoubleClickEvent(event)


class RossStudioWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.project=ProjectModel(); self.bearing=BearingModel()
        self.setWindowTitle("ROSS STUDIO | WGM20")
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.resize(1672,941)
        self.setMinimumSize(1280,760)
        root=QWidget(); root.setObjectName("appRoot"); self.setCentralWidget(root)
        outer=QVBoxLayout(root); outer.setContentsMargins(0,0,0,0); outer.setSpacing(0)
        outer.addWidget(TitleBar(self,self.project))
        body=QHBoxLayout(); body.setContentsMargins(0,0,0,0); body.setSpacing(0); holder=QWidget(); holder.setLayout(body); outer.addWidget(holder,1)
        self.sidebar=Sidebar(); body.addWidget(self.sidebar)
        work=QVBoxLayout(); work.setContentsMargins(0,0,0,0); work.setSpacing(0); work_holder=QWidget(); work_holder.setLayout(work); body.addWidget(work_holder,1)
        self.toolbar=AppToolbar(); work.addWidget(self.toolbar)
        self.stack=QStackedWidget(); work.addWidget(self.stack,1)
        self.status=StatusBar(self.project); outer.addWidget(self.status)

        self.rotor_page=RotorModelPage(self.project)
        self.bearing_page=BearingStudioPage(self.project,self.bearing)
        self.results_page=AnalysisResultsPage(self.project)
        self.stack.addWidget(self.rotor_page); self.stack.addWidget(self.bearing_page); self.stack.addWidget(self.results_page)
        self.page_index={"rotor":0,"shaft":0,"disks":0,"seals":0,"supports":0,"couplings":0,"loads":0,"bearings":1,"rotor_dynamics":2,"response":2,"stability":2,"transient":2,"faults":2,"stochastic":2,"results":2,"home":0}
        self.sidebar.page_requested.connect(self._navigate)
        self.rotor_page.run_requested.connect(self.run_analysis)
        self.rotor_page.validate_requested.connect(self.validate_model)
        self.bearing_page.status_message.connect(lambda text:self.status.set_status(text))
        self.sidebar.set_active("rotor")

    def _navigate(self,key:str)->None:
        self.stack.setCurrentIndex(self.page_index.get(key,0))
        if key=="bearings": self.status.set_status("Bearing solution converged")
        elif key in {"rotor_dynamics","response","stability","transient","faults","stochastic","results"}: self.status.set_status("Campbell analysis completed successfully",units="Units: SI (mm, kg, N, Hz, rpm)")
        else: self.status.set_status("Model validated",units="Units: SI (mm, kg, N)")

    def validate_model(self)->None:
        self.status.set_status("Model validated","No issues found")

    def run_analysis(self)->None:
        dlg=SolverConsole(self.project,self)
        dlg.exec()
        if dlg.status.text()=="Completed":
            self.status.set_status("Analysis completed","No issues found")


def launch() -> int:
    app=QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("ROSS Studio")
    app.setOrganizationName("ROSS Studio")
    app.setStyleSheet(APP_STYLESHEET)
    font=QFont("Segoe UI",10); app.setFont(font)
    window=RossStudioWindow(); window.show()
    return app.exec()
