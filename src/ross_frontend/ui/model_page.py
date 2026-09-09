from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QComboBox, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTableWidget, QTableWidgetItem, QTabWidget, QTextEdit, QVBoxLayout, QWidget, QHeaderView

from ..domain import RotorProject, ShaftSectionSpec
from .drawing import RotorSketch
from .icons import studio_icon
from .theme import P
from .widgets import Card


def _field_row(label: str, value: str, unit: str = "") -> QWidget:
    w=QWidget(); lay=QHBoxLayout(w); lay.setContentsMargins(0,0,0,0); lay.setSpacing(8)
    lab=QLabel(label); lab.setMinimumWidth(124); lay.addWidget(lab)
    val=QLabel(value); val.setStyleSheet(f"color:{P.text_dark};font-weight:500;"); lay.addWidget(val,1)
    if unit:
        u=QLabel(unit); u.setObjectName("Muted"); lay.addWidget(u)
    return w


class ModelPage(QWidget):
    runRequested = Signal()
    validateRequested = Signal()
    projectChanged = Signal(object)

    def __init__(self, project: RotorProject):
        super().__init__(); self.project=project
        root=QHBoxLayout(self); root.setContentsMargins(14,0,12,12); root.setSpacing(12)
        left=QVBoxLayout(); left.setSpacing(10); root.addLayout(left,1)
        rotor_card=Card("Rotor Model", margins=(0,10,0,0)); self.sketch=RotorSketch(project); rotor_card.layout.addWidget(self.sketch,1); left.addWidget(rotor_card,5)
        editor=Card(margins=(0,0,0,0)); left.addWidget(editor,5)
        self.tabs=QTabWidget(); self.tabs.setDocumentMode(True); editor.layout.addWidget(self.tabs)
        shaft_tab=QWidget(); s_lay=QVBoxLayout(shaft_tab); s_lay.setContentsMargins(14,8,14,12); s_lay.setSpacing(8)
        head=QHBoxLayout(); title=QLabel("Shaft Segments"); title.setObjectName("SectionTitle"); head.addWidget(title); head.addStretch(1)
        for text,icon,slot in (("Add Segment","new",self.add_segment),("Delete","trash",self.delete_segment),("Import...","export",self.import_placeholder)):
            b=QPushButton(text); b.setIcon(studio_icon(icon,P.text,17)); b.clicked.connect(slot); head.addWidget(b)
        s_lay.addLayout(head)
        self.table=QTableWidget(0,7); self.table.setAlternatingRowColors(True); self.table.setHorizontalHeaderLabels(["Section","Length (mm)","OD Left (mm)","OD Right (mm)","ID Left (mm)","ID Right (mm)","Material"])
        self.table.verticalHeader().setVisible(False); self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch); self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows); self.table.itemChanged.connect(self._sync_table)
        s_lay.addWidget(self.table,1); self.tabs.addTab(shaft_tab,"Shaft Segments")
        for name in ("Disks","Bearings","Supports","Couplings"):
            stub=QWidget(); v=QVBoxLayout(stub); lbl=QLabel(f"{name} editor"); lbl.setObjectName("SectionTitle"); v.addWidget(lbl); v.addStretch(1); self.tabs.addTab(stub,name)
        self._populate_table()

        right_host=QWidget(); right_host.setFixedWidth(320); right=QVBoxLayout(right_host); right.setContentsMargins(0,0,0,0); right.setSpacing(10); root.addWidget(right_host)
        info=Card("Project Information"); right.addWidget(info)
        grid=QGridLayout(); grid.setHorizontalSpacing(8); grid.setVerticalSpacing(8)
        grid.addWidget(QLabel("Project Name"),0,0); self.project_name=QLineEdit(project.reference or "WGM20"); grid.addWidget(self.project_name,0,1)
        grid.addWidget(QLabel("Description"),1,0,Qt.AlignmentFlag.AlignTop); self.description=QTextEdit(); self.description.setPlainText(str(project.metadata.get("description",""))); self.description.setFixedHeight(68); grid.addWidget(self.description,1,1)
        grid.addWidget(QLabel("Created"),2,0); grid.addWidget(QLabel(str(project.metadata.get("created","Apr 25, 2025  10:24"))),2,1)
        grid.addWidget(QLabel("Last Modified"),3,0); grid.addWidget(QLabel(str(project.metadata.get("last_modified","Apr 25, 2025  14:17"))),3,1); info.layout.addLayout(grid)

        summary=Card("Model Summary"); right.addWidget(summary)
        speed_row=QWidget(); sl=QHBoxLayout(speed_row); sl.setContentsMargins(0,0,0,0); sl.addWidget(QLabel("Rotor Speed")); self.speed=QLineEdit(f"{float(project.metadata.get('rotor_speed_rpm',1800)):,.0f}"); self.speed.setFixedWidth(118); sl.addStretch(1); sl.addWidget(self.speed); sl.addWidget(QLabel("rpm")); summary.layout.addWidget(speed_row)
        matrow=QWidget(); ml=QHBoxLayout(matrow); ml.setContentsMargins(0,0,0,0); ml.addWidget(QLabel("Material")); ml.addStretch(1); self.material=QComboBox(); self.material.addItems([m.name for m in project.materials]); self.material.setMinimumWidth(160); ml.addWidget(self.material); summary.layout.addWidget(matrow)
        summary.layout.addWidget(_field_row("Total Mass",f"{float(project.metadata.get('display_total_mass_kg',286.4)):.1f}","kg"))
        summary.layout.addWidget(_field_row("Total Length",f"{project.shaft_length_mm:,.0f}","mm"))
        summary.layout.addWidget(_field_row("Degrees of Freedom (DOF)","12"))
        summary.layout.addWidget(_field_row("Shaft Segments",str(len(project.shaft))))
        summary.layout.addWidget(_field_row("Disks",str(len(project.disks))))
        summary.layout.addWidget(_field_row("Bearings",str(len(project.bearings))))
        summary.layout.addWidget(_field_row("Supports","2"))

        quick=Card("Quick Actions"); right.addWidget(quick)
        save=QPushButton("Save Project"); save.setIcon(studio_icon("save",P.text,19)); quick.layout.addWidget(save)
        validate=QPushButton("Validate Model"); validate.setObjectName("SuccessButton"); validate.setIcon(studio_icon("check",P.success,19)); validate.clicked.connect(self.validateRequested.emit); quick.layout.addWidget(validate)
        run=QPushButton("Run Analysis"); run.setObjectName("PrimaryButton"); run.setMinimumHeight(46); run.setIcon(studio_icon("play","#FFFFFF",21)); run.clicked.connect(self.runRequested.emit); quick.layout.addWidget(run); right.addStretch(1)
        self.project_name.editingFinished.connect(self._sync_header_fields); self.speed.editingFinished.connect(self._sync_header_fields); self.description.textChanged.connect(self._sync_header_fields)

    def _populate_table(self):
        self.table.blockSignals(True); self.table.setRowCount(len(self.project.shaft))
        for r,s in enumerate(self.project.shaft):
            vals=[str(r+1),f"{s.length_mm:g}",f"{s.outer_diameter_left_mm:g}",f"{s.odr_mm:g}",f"{s.inner_diameter_left_mm:g}",f"{s.idr_mm:g}",s.material]
            for c,v in enumerate(vals):
                item=QTableWidgetItem(v); item.setTextAlignment(Qt.AlignmentFlag.AlignCenter if c<6 else Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter); self.table.setItem(r,c,item)
        if self.table.rowCount(): self.table.selectRow(0)
        self.table.blockSignals(False)

    def _sync_table(self, item):
        try:
            shaft=[]
            for r in range(self.table.rowCount()):
                get=lambda c:self.table.item(r,c).text().strip()
                shaft.append(ShaftSectionSpec(float(get(1)),float(get(2)),float(get(4)),float(get(3)),float(get(5)),get(6) or self.project.materials[0].name,tag=str(r+1)))
            for s in shaft: s.validate()
        except Exception:
            return
        self.project.shaft=shaft; self.sketch.update(); self.projectChanged.emit(self.project)

    def _sync_header_fields(self):
        self.project.reference=self.project_name.text().strip() or "WGM20"; self.project.metadata["description"]=self.description.toPlainText()
        try: self.project.metadata["rotor_speed_rpm"]=float(self.speed.text().replace(",",""))
        except ValueError: pass
        self.projectChanged.emit(self.project)

    def add_segment(self):
        material=self.project.materials[0].name if self.project.materials else "Steel"; self.project.shaft.append(ShaftSectionSpec(100,50,0,50,0,material,tag=str(len(self.project.shaft)+1))); self._populate_table(); self.sketch.update(); self.projectChanged.emit(self.project)

    def delete_segment(self):
        row=self.table.currentRow()
        if row>=0 and len(self.project.shaft)>1: self.project.shaft.pop(row); self._populate_table(); self.sketch.update(); self.projectChanged.emit(self.project)

    def import_placeholder(self): pass

    def set_project(self, project: RotorProject): self.project=project; self.sketch.set_project(project); self._populate_table()
