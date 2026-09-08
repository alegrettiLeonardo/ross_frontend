from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from ..icons import engineering_icon
from ..models import BearingModel, ProjectModel
from ..widgets import BearingCoefficientChart, Card, ProjectInfoCard, SectionCard, configure_table, item


class BearingStudioPage(QWidget):
    status_message = Signal(str)

    def __init__(self, project: ProjectModel, bearing: BearingModel, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.project = project
        self.bearing = bearing
        root = QHBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        center = QVBoxLayout(); center.setContentsMargins(0,0,0,0); center.setSpacing(10)
        root.addLayout(center, 1)

        page_card = Card()
        page_layout = QVBoxLayout(page_card); page_layout.setContentsMargins(14,10,14,10); page_layout.setSpacing(8)
        header_row = QHBoxLayout()
        title = QLabel("Bearing Studio"); title.setObjectName("cardHeader"); header_row.addWidget(title)
        crumb = QLabel("Model  /  Bearings  /  DE Journal Bearing"); crumb.setObjectName("muted"); header_row.addWidget(crumb)
        header_row.addStretch(1)
        page_layout.addLayout(header_row)

        lab = QLabel("Bearing Type"); lab.setObjectName("subHeader"); page_layout.addWidget(lab)
        types = QHBoxLayout(); types.setSpacing(8)
        self.type_buttons = {}
        for key, text, icon in [
            ("kc","Coefficient K/C","wave"),
            ("ball","Ball Bearing","bearing"),
            ("roller","Roller Bearing","bearing"),
            ("cyl","Cylindrical","bearing"),
            ("plain","Plain Journal","seal"),
            ("tilting","Tilting Pad","disk"),
        ]:
            b = QPushButton(text); b.setObjectName("bearingType"); b.setCheckable(True); b.setIcon(engineering_icon(icon, 30)); b.setIconSize(QSize(30, 30));
            b.clicked.connect(lambda checked=False, k=key: self._select_type(k))
            self.type_buttons[key]=b; types.addWidget(b,1)
        self.type_buttons["tilting"].setChecked(True)
        page_layout.addLayout(types)

        input_row = QHBoxLayout(); input_row.setSpacing(10)
        input_row.addWidget(self._geometry_box(),1)
        input_row.addWidget(self._operation_box(),1)
        input_row.addWidget(self._lubrication_box(),1)
        input_row.addWidget(self._operating_point_box(),1)
        page_layout.addLayout(input_row)
        center.addWidget(page_card, 5)

        result_card = Card(); result_layout = QVBoxLayout(result_card); result_layout.setContentsMargins(10,0,10,10)
        tabs = QTabWidget(); tabs.setDocumentMode(True); result_layout.addWidget(tabs,1)
        tabs.addTab(self._kc_tab(), "K & C Coefficients")
        for name in ("Pressure","Temperature","Film Thickness","Journal Position","Convergence"):
            holder=QWidget(); l=QVBoxLayout(holder); q=QLabel(f"{name} field visualization"); q.setObjectName("muted"); q.setAlignment(Qt.AlignmentFlag.AlignCenter); l.addWidget(q); tabs.addTab(holder,name)
        center.addWidget(result_card,5)

        right_layout=QVBoxLayout(); right_layout.setContentsMargins(0,0,0,0); right_layout.setSpacing(10)
        right=QWidget(); right.setFixedWidth(326); right.setLayout(right_layout); root.addWidget(right)
        right_layout.addWidget(ProjectInfoCard(project))
        right_layout.addWidget(self._bearing_info_card(),1)
        right_layout.addWidget(self._actions_card())

    def _select_type(self, key: str) -> None:
        for name, button in self.type_buttons.items(): button.setChecked(name==key)

    def _spin(self, value: float, decimals: int = 2) -> QDoubleSpinBox:
        w=QDoubleSpinBox(); w.setDecimals(decimals); w.setRange(-1e12,1e12); w.setValue(value); w.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons); return w

    def _geometry_box(self) -> QWidget:
        card=Card(); lay=QVBoxLayout(card); lay.setContentsMargins(12,10,12,10); title=QLabel("Geometry"); title.setObjectName("subHeader"); lay.addWidget(title)
        grid=QGridLayout(); grid.setHorizontalSpacing(6); grid.setVerticalSpacing(7)
        rows=[
            ("Shaft Diameter (D)",self._spin(self.bearing.shaft_diameter_mm,0),"mm"),
            ("Pad Length (L)",self._spin(self.bearing.pad_length_mm,0),"mm"),
            ("Radial Clearance (c)",self._spin(self.bearing.radial_clearance_mm,2),"mm"),
            ("Pad Arc (α)",self._spin(self.bearing.pad_arc_deg,0),"deg"),
            ("Preload",self._spin(self.bearing.preload,2),"-"),
        ]
        pads=QSpinBox(); pads.setRange(1,20); pads.setValue(self.bearing.number_of_pads)
        rows.append(("Number of Pads",pads,""))
        for r,(text,w,unit) in enumerate(rows):
            grid.addWidget(QLabel(text),r,0); grid.addWidget(w,r,1); u=QLabel(unit); u.setObjectName("muted"); grid.addWidget(u,r,2)
        grid.setColumnStretch(1,1); lay.addLayout(grid); lay.addStretch(1); return card

    def _operation_box(self) -> QWidget:
        card=Card(); lay=QVBoxLayout(card); lay.setContentsMargins(12,10,12,10); title=QLabel("Operation"); title.setObjectName("subHeader"); lay.addWidget(title)
        grid=QGridLayout(); grid.setHorizontalSpacing(6); grid.setVerticalSpacing(7)
        grid.addWidget(QLabel("Speed Range"),0,0)
        sr=QHBoxLayout(); a=QSpinBox(); a.setRange(0,999999); a.setValue(self.bearing.speed_min_rpm); b=QSpinBox(); b.setRange(0,999999); b.setValue(self.bearing.speed_max_rpm); sr.addWidget(a); sr.addWidget(QLabel("to")); sr.addWidget(b); box=QWidget(); box.setLayout(sr); grid.addWidget(box,0,1,1,2); grid.addWidget(QLabel("rpm"),0,3)
        rows=[("Load X (Fx)",self._spin(self.bearing.load_x_n,0),"N"),("Load Y (Fy)",self._spin(self.bearing.load_y_n,0),"N"),("Oil Inlet\nTemperature",self._spin(self.bearing.oil_inlet_temperature_c,0),"°C"),("Supply Pressure",self._spin(self.bearing.supply_pressure_bar,1),"bar")]
        for i,(text,w,unit) in enumerate(rows,1): grid.addWidget(QLabel(text),i,0); grid.addWidget(w,i,1,1,2); grid.addWidget(QLabel(unit),i,3)
        grid.setColumnStretch(1,1); lay.addLayout(grid); lay.addStretch(1); return card

    def _lubrication_box(self) -> QWidget:
        card=Card(); lay=QVBoxLayout(card); lay.setContentsMargins(12,10,12,10); title=QLabel("Lubrication / Model"); title.setObjectName("subHeader"); lay.addWidget(title)
        grid=QGridLayout(); grid.setHorizontalSpacing(6); grid.setVerticalSpacing(10)
        data=[("Lubricant Grade",["ISO VG 32","ISO VG 46","ISO VG 68"],self.bearing.lubricant_grade),("Thermal Model",["Energy Equation","Isothermal"],self.bearing.thermal_model),("Viscosity Model",["Roelands","Walther"],self.bearing.viscosity_model),("Mesh /\nDiscretization",["Medium (60 × 30)","Coarse (30 × 15)","Fine (120 × 60)"],self.bearing.mesh)]
        for r,(label,opts,cur) in enumerate(data):
            grid.addWidget(QLabel(label),r,0); combo=QComboBox(); combo.addItems(opts); combo.setCurrentText(cur); grid.addWidget(combo,r,1)
        grid.setColumnStretch(1,1); lay.addLayout(grid); lay.addStretch(1); return card

    def _operating_point_box(self) -> QWidget:
        card=Card(); lay=QVBoxLayout(card); lay.setContentsMargins(0,0,0,0); h=QLabel(f"Operating Point (at {self.bearing.operating_rpm:,} rpm)"); h.setObjectName("subHeader"); h.setContentsMargins(12,10,0,6); lay.addWidget(h)
        table=QTableWidget(6,3); table.setHorizontalHeaderLabels(["","",""]); table.horizontalHeader().hide(); configure_table(table,row_height=30); table.verticalHeader().hide(); table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        rows=[("Eccentricity Ratio (ε)",f"{self.bearing.eccentricity_ratio:.3f}","-"),("Attitude Angle (φ)",f"{self.bearing.attitude_angle_deg:.1f}","deg"),("Minimum Film Thickness (hmin)",f"{self.bearing.min_film_thickness_mm:.3f}","mm"),("Power Loss",f"{self.bearing.power_loss_kw:.2f}","kW"),("Flow Rate",f"{self.bearing.flow_rate_l_min:.1f}","L/min"),("Max Temperature (Pad)",f"{self.bearing.max_temperature_c:.1f}","°C")]
        for r,row in enumerate(rows):
            for c,v in enumerate(row): table.setItem(r,c,item(v,center=c>0))
        table.setColumnWidth(0,165); table.horizontalHeader().setStretchLastSection(True); lay.addWidget(table,1); return card

    def _kc_tab(self) -> QWidget:
        page=QWidget(); lay=QHBoxLayout(page); lay.setContentsMargins(0,8,0,0); lay.setSpacing(10)
        headers=["RPM","Kxx\n(N/m)","Kxy\n(N/m)","Kyx\n(N/m)","Kyy\n(N/m)","Cxx\n(N·s/m)","Cxy\n(N·s/m)","Cyx\n(N·s/m)","Cyy\n(N·s/m)"]
        table=QTableWidget(len(self.bearing.coefficients),len(headers)); table.setHorizontalHeaderLabels(headers); configure_table(table,row_height=30); table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        for r,x in enumerate(self.bearing.coefficients):
            vals=[f"{x.rpm:,}",f"{x.kxx:.2e}",f"{x.kxy:.2e}",f"{x.kyx:.2e}",f"{x.kyy:.2e}",f"{x.cxx:.2e}",f"{x.cxy:.2e}",f"{x.cyx:.2e}",f"{x.cyy:.2e}"]
            for c,v in enumerate(vals): table.setItem(r,c,item(v))
        table.selectRow(4); table.resizeColumnsToContents(); lay.addWidget(table,3)
        chart_card=Card(); cl=QVBoxLayout(chart_card); cl.setContentsMargins(10,8,10,8); top=QHBoxLayout(); t=QLabel("Stiffness and Damping Coefficients"); t.setObjectName("subHeader"); top.addWidget(t); top.addStretch(1); combo=QComboBox(); combo.addItems(["Stiffness (K)","Damping (C)"]); top.addWidget(combo); cl.addLayout(top); cl.addWidget(BearingCoefficientChart(self.bearing),1); lay.addWidget(chart_card,2)
        return page

    def _bearing_info_card(self) -> QWidget:
        card=SectionCard("Bearing Information"); grid=QGridLayout(); grid.setHorizontalSpacing(10); grid.setVerticalSpacing(9)
        rows=[("Bearing Name",self.bearing.name),("Bearing Type",self.bearing.bearing_type),("Node Position",self.bearing.node_position),("Connected Shaft",self.bearing.connected_shaft),("Number of Pads",str(self.bearing.number_of_pads)),("Preload",f"{self.bearing.preload:.2f}"),("Clearance",f"{self.bearing.radial_clearance_mm:.2f} mm"),("Pad Arc",f"{self.bearing.pad_arc_deg:.0f} deg")]
        for r,(k,v) in enumerate(rows): a=QLabel(k); a.setObjectName("muted"); grid.addWidget(a,r,0); grid.addWidget(QLabel(v),r,1)
        grid.setColumnStretch(1,1); card.root.addLayout(grid); return card

    def _actions_card(self) -> QWidget:
        card=SectionCard("Quick Actions")
        calc=QPushButton("Calculate Bearing"); calc.setObjectName("primaryButton"); calc.setIcon(engineering_icon("gear",20,"#ffffff")); calc.clicked.connect(lambda: self.status_message.emit("Bearing solution converged")); card.root.addWidget(calc)
        apply=QPushButton("Apply to Rotor"); apply.setObjectName("successButton"); apply.setIcon(engineering_icon("check",20)); card.root.addWidget(apply)
        export=QPushButton("Export Curves"); export.setObjectName("softButton"); export.setIcon(engineering_icon("export",20)); card.root.addWidget(export)
        return card
