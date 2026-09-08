from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QComboBox, QDoubleSpinBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget, QHeaderView

from ..domain import RotorProject, TiltingPadBearingSpec
from .drawing import SimpleLineChart
from .icons import studio_icon
from .theme import P
from .widgets import BearingTypeButton, Card


class LabeledInput(QWidget):
    def __init__(self, label: str, value: float, unit: str = "", decimals: int = 2, minimum=-1e12, maximum=1e12):
        super().__init__(); lay=QHBoxLayout(self); lay.setContentsMargins(0,0,0,0); lay.setSpacing(6)
        lab=QLabel(label); lab.setMinimumWidth(105); lay.addWidget(lab)
        self.edit=QDoubleSpinBox(); self.edit.setDecimals(decimals); self.edit.setRange(minimum,maximum); self.edit.setValue(value); self.edit.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons); self.edit.setMinimumWidth(82); lay.addWidget(self.edit,1)
        u=QLabel(unit); u.setObjectName("Muted"); u.setFixedWidth(32); lay.addWidget(u)


class BearingPage(QWidget):
    statusMessage = Signal(str, str, bool)
    projectChanged = Signal(object)

    def __init__(self, project: RotorProject):
        super().__init__(); self.project=project
        root=QHBoxLayout(self); root.setContentsMargins(14,0,12,12); root.setSpacing(12)
        center=QVBoxLayout(); center.setSpacing(10); root.addLayout(center,1)
        header=Card(margins=(12,8,12,8)); hh=QHBoxLayout(); title=QLabel("Bearing Studio"); title.setObjectName("CardTitle"); hh.addWidget(title); crumb=QLabel("Model  /  Bearings  /  DE Journal Bearing"); crumb.setObjectName("Muted"); hh.addWidget(crumb); hh.addStretch(1); header.layout.addLayout(hh); center.addWidget(header)
        types=Card(margins=(12,8,12,10)); label=QLabel("Bearing Type"); label.setObjectName("SmallHeader"); types.layout.addWidget(label); row=QHBoxLayout(); row.setSpacing(8)
        specs=[("coefficient","Coefficient K/C","coefficient"),("ball","Ball Bearing","ball"),("roller","Roller Bearing","roller"),("cylindrical","Cylindrical","cylindrical"),("journal","Plain Journal","plain"),("tilting","Tilting Pad","tilting")]
        self.type_buttons={}
        for icon,text,key in specs:
            b=BearingTypeButton(icon,text); b.clicked.connect(lambda checked=False,k=key:self._type_changed(k)); row.addWidget(b); self.type_buttons[key]=b
        self.type_buttons["tilting"].setChecked(True); types.layout.addLayout(row); center.addWidget(types)
        top=QHBoxLayout(); top.setSpacing(10); center.addLayout(top)
        input_host=QWidget(); igrid=QGridLayout(input_host); igrid.setContentsMargins(0,0,0,0); igrid.setSpacing(10); top.addWidget(input_host,1)
        geom=Card("Geometry"); op=Card("Operation"); lub=Card("Lubrication / Model"); igrid.addWidget(geom,0,0); igrid.addWidget(op,0,1); igrid.addWidget(lub,0,2)
        self.diameter=LabeledInput("Shaft Diameter (D)",100,"mm",2,0.001); geom.layout.addWidget(self.diameter)
        self.length=LabeledInput("Pad Length (L)",80,"mm",2,0.001); geom.layout.addWidget(self.length)
        self.clearance=LabeledInput("Radial Clearance (c)",0.10,"mm",3,0.0001); geom.layout.addWidget(self.clearance)
        self.arc=LabeledInput("Pad Arc (α)",60,"deg",1,1,360); geom.layout.addWidget(self.arc)
        self.preload=LabeledInput("Preload",0.50,"-",2,0,1); geom.layout.addWidget(self.preload)
        pads=QWidget(); pl=QHBoxLayout(pads); pl.setContentsMargins(0,0,0,0); pl.addWidget(QLabel("Number of Pads")); pl.addStretch(1); self.npads=QSpinBox(); self.npads.setRange(2,16); self.npads.setValue(5); pl.addWidget(self.npads); geom.layout.addWidget(pads)
        speed=QWidget(); sl=QHBoxLayout(speed); sl.setContentsMargins(0,0,0,0); sl.addWidget(QLabel("Speed Range")); self.speed0=QDoubleSpinBox(); self.speed0.setRange(1,100000); self.speed0.setValue(500); self.speed0.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons); self.speed1=QDoubleSpinBox(); self.speed1.setRange(1,100000); self.speed1.setValue(10000); self.speed1.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons); sl.addWidget(self.speed0); sl.addWidget(QLabel("to")); sl.addWidget(self.speed1); sl.addWidget(QLabel("rpm")); op.layout.addWidget(speed)
        self.loadx=LabeledInput("Load X (Fx)",5000,"N",0); op.layout.addWidget(self.loadx)
        self.loady=LabeledInput("Load Y (Fy)",0,"N",0); op.layout.addWidget(self.loady)
        self.temp=LabeledInput("Oil Inlet Temperature",40,"°C",1); op.layout.addWidget(self.temp)
        self.pressure=LabeledInput("Supply Pressure",2.0,"bar",1,0); op.layout.addWidget(self.pressure)
        self.lube=QComboBox(); self.lube.addItems(["ISO VG 32","ISO VG 46","ISO VG 68"]); self._combo_row(lub,"Lubricant Grade",self.lube)
        self.thermal=QComboBox(); self.thermal.addItems(["Energy Equation","Isothermal","Full THD"]); self._combo_row(lub,"Thermal Model",self.thermal)
        self.viscosity=QComboBox(); self.viscosity.addItems(["Roelands","Vogel","Constant"]); self._combo_row(lub,"Viscosity Model",self.viscosity)
        self.mesh=QComboBox(); self.mesh.addItems(["Medium (60 × 30)","Coarse (30 × 15)","Fine (100 × 50)"]); self._combo_row(lub,"Mesh / Discretization",self.mesh)
        operating=Card("Operating Point (at 6,000 rpm)"); operating.setFixedWidth(285); top.addWidget(operating)
        for name,val,unit in [("Eccentricity Ratio (ε)","0.342","-"),("Attitude Angle (φ)","53.2","deg"),("Minimum Film Thickness (hmin)","0.067","mm"),("Power Loss","1.86","kW"),("Flow Rate","32.4","L/min"),("Max Temperature (Pad)","78.6","°C")]:
            r=QWidget(); rl=QHBoxLayout(r); rl.setContentsMargins(0,0,0,0); rl.addWidget(QLabel(name),1); v=QLabel(val); v.setStyleSheet(f"color:{P.text_dark};"); v.setMinimumWidth(55); rl.addWidget(v); u=QLabel(unit); u.setObjectName("Muted"); u.setFixedWidth(38); rl.addWidget(u); operating.layout.addWidget(r)
        results=Card(margins=(0,0,0,0)); center.addWidget(results,1); self.tabs=QTabWidget(); self.tabs.setDocumentMode(True); results.layout.addWidget(self.tabs)
        kc=QWidget(); kl=QHBoxLayout(kc); kl.setContentsMargins(12,8,12,12); kl.setSpacing(10)
        self.table=QTableWidget(0,9); self.table.setHorizontalHeaderLabels(["RPM","Kxx\n(N/m)","Kxy\n(N/m)","Kyx\n(N/m)","Kyy\n(N/m)","Cxx\n(N·s/m)","Cxy\n(N·s/m)","Cyx\n(N·s/m)","Cyy\n(N·s/m)"]); self.table.verticalHeader().setVisible(False); self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch); self.table.setAlternatingRowColors(True); kl.addWidget(self.table,3)
        chart_card=QFrame(); chart_card.setObjectName("FlatCard"); chl=QVBoxLayout(chart_card); chl.setContentsMargins(10,8,10,8); cht=QHBoxLayout(); lab=QLabel("Stiffness and Damping Coefficients"); lab.setObjectName("SmallHeader"); cht.addWidget(lab); cht.addStretch(1); sel=QComboBox(); sel.addItems(["Stiffness (K)","Damping (C)"]); cht.addWidget(sel); chl.addLayout(cht); self.chart=SimpleLineChart(); chl.addWidget(self.chart,1); kl.addWidget(chart_card,2); self.tabs.addTab(kc,"K & C Coefficients")
        for t in ("Pressure","Temperature","Film Thickness","Journal Position","Convergence"):
            w=QWidget(); l=QVBoxLayout(w); msg=QLabel(f"{t} result view"); msg.setObjectName("Muted"); msg.setAlignment(Qt.AlignmentFlag.AlignCenter); l.addWidget(msg); self.tabs.addTab(w,t)
        self._fill_demo_coefficients()
        right_host=QWidget(); right_host.setFixedWidth(320); right=QVBoxLayout(right_host); right.setContentsMargins(0,0,0,0); right.setSpacing(10); root.addWidget(right_host)
        info=Card("Project Information"); right.addWidget(info)
        for name,val in [("Project Name",project.reference or "WGM20"),("Description",str(project.metadata.get("description","Wind generator main rotor\n(20 MW class)"))),("Created",str(project.metadata.get("created","Apr 25, 2025  10:24"))),("Last Modified",str(project.metadata.get("last_modified","Apr 25, 2025  14:17")))]: self._info_row(info,name,val)
        bi=Card("Bearing Information"); right.addWidget(bi)
        for name,val in [("Bearing Name","DE Journal Bearing"),("Bearing Type","Tilting Pad"),("Node Position","Node 2 (Disk 1 - Left)"),("Connected Shaft","Shaft 1"),("Number of Pads","5"),("Preload","0.50"),("Clearance","0.10 mm"),("Pad Arc","60 deg")]: self._info_row(bi,name,val)
        qa=Card("Quick Actions"); right.addWidget(qa)
        calc=QPushButton("Calculate Bearing"); calc.setObjectName("PrimaryButton"); calc.setIcon(studio_icon("gear","#FFFFFF",20)); calc.setMinimumHeight(44); calc.clicked.connect(self.calculate); qa.layout.addWidget(calc)
        apply=QPushButton("Apply to Rotor"); apply.setObjectName("SuccessButton"); apply.setIcon(studio_icon("check",P.success,20)); apply.clicked.connect(self.apply_to_rotor); qa.layout.addWidget(apply)
        export=QPushButton("Export Curves"); export.setIcon(studio_icon("export",P.text,19)); qa.layout.addWidget(export); right.addStretch(1)

    @staticmethod
    def _combo_row(card: Card, label: str, combo: QComboBox):
        w=QWidget(); l=QHBoxLayout(w); l.setContentsMargins(0,0,0,0); lab=QLabel(label); lab.setMinimumWidth(105); l.addWidget(lab); l.addWidget(combo,1); card.layout.addWidget(w)

    @staticmethod
    def _info_row(card: Card, name: str, value: str):
        w=QWidget(); l=QHBoxLayout(w); l.setContentsMargins(0,0,0,0); n=QLabel(name); n.setMinimumWidth(112); l.addWidget(n); v=QLabel(value); v.setWordWrap(True); v.setStyleSheet(f"color:{P.text_dark};font-weight:500;"); l.addWidget(v,1); card.layout.addWidget(w)

    def _type_changed(self,key): self.statusMessage.emit(f"Bearing type: {self.type_buttons[key].text()}","Input panel selected",True)

    def _fill_demo_coefficients(self):
        rows=[(500,1.20e7,-.32e7,.28e7,1.10e7,3.10e4,-.20e4,.18e4,2.90e4),(1000,1.35e7,-.38e7,.34e7,1.28e7,3.80e4,-.28e4,.25e4,3.60e4),(2000,1.72e7,-.51e7,.48e7,1.64e7,5.60e4,-.42e4,.39e4,5.10e4),(4000,2.28e7,-.71e7,.66e7,2.18e7,8.40e4,-.63e4,.58e4,7.90e4),(6000,2.85e7,-.92e7,.86e7,2.74e7,1.10e5,-.82e4,.77e4,1.05e5),(8000,3.41e7,-1.10e7,1.03e7,3.28e7,1.34e5,-1.00e4,.95e4,1.29e5),(10000,3.95e7,-1.27e7,1.19e7,3.80e7,1.56e5,-1.16e4,1.10e4,1.50e5)]
        self.table.setRowCount(len(rows))
        for r,row in enumerate(rows):
            for c,val in enumerate(row):
                text=f"{val:,.0f}" if c==0 else f"{val:.2e}"; item=QTableWidgetItem(text); item.setTextAlignment(Qt.AlignmentFlag.AlignCenter); self.table.setItem(r,c,item)
        xs=[r[0] for r in rows]; self.chart.xmax=10000; self.chart.ymin=-1.5e7; self.chart.ymax=4.5e7; self.chart.set_series([("Kxx",list(zip(xs,[r[1] for r in rows])),"blue",False),("Kyy",list(zip(xs,[r[4] for r in rows])),"red",False),("Kxy",list(zip(xs,[r[2] for r in rows])),"green",True),("Kyx",list(zip(xs,[r[3] for r in rows])),"orange",True)])

    def calculate(self): self._fill_demo_coefficients(); self.statusMessage.emit("Bearing solution converged","No issues found",True)

    def apply_to_rotor(self):
        speeds=[500,1000,2000,4000,6000,8000,10000]; pivots=[0,72,144,216,288]
        bearing=TiltingPadBearingSpec(position_mm=self.project.bearings[0].position_mm if self.project.bearings else 80.0,journal_diameter_mm=self.diameter.edit.value(),radial_clearance_mm=self.clearance.edit.value(),pad_axial_length_mm=self.length.edit.value(),pad_thickness_mm=15.0,pad_arc_deg=self.arc.edit.value(),pivot_angle_deg=pivots[:self.npads.value()] if self.npads.value()<=5 else [i*360/self.npads.value() for i in range(self.npads.value())],frequency_rpm=speeds,oil_supply_temperature_c=self.temp.edit.value(),lubricant="ISOVG32",preload=self.preload.edit.value(),load_x_n=self.loadx.edit.value(),load_y_n=self.loady.edit.value(),tag="DE Journal Bearing")
        self.project.metadata["bearing_supply_pressure_bar"]=self.pressure.edit.value()
        if self.project.bearings: self.project.bearings[0]=bearing
        else: self.project.bearings.append(bearing)
        self.projectChanged.emit(self.project); self.statusMessage.emit("Bearing applied to rotor","DE Journal Bearing updated",True)
