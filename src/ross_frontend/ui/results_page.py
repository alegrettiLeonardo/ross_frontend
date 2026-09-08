from __future__ import annotations

import csv

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget, QHeaderView

from ..backends.base import AnalysisResult
from ..domain import RotorProject
from .drawing import CampbellChart
from .icons import studio_icon
from .theme import P
from .widgets import Card


class KpiCard(QFrame):
    def __init__(self, label: str, value: str, unit: str, icon_name: str):
        super().__init__(); self.setObjectName("Card"); self.setMinimumHeight(80)
        l=QHBoxLayout(self); l.setContentsMargins(16,10,16,10); icon=QLabel(); icon.setPixmap(studio_icon(icon_name,P.text_dark,34).pixmap(34,34)); l.addWidget(icon)
        v=QVBoxLayout(); lab=QLabel(label); lab.setObjectName("KpiLabel"); v.addWidget(lab); row=QHBoxLayout(); self.value=QLabel(value); self.value.setObjectName("KpiValue"); row.addWidget(self.value); u=QLabel(unit); u.setObjectName("Muted"); row.addWidget(u); row.addStretch(1); v.addLayout(row); l.addLayout(v,1)


class ResultsPage(QWidget):
    def __init__(self, project: RotorProject):
        super().__init__(); self.project=project; self.last_result: AnalysisResult | None=None
        root=QHBoxLayout(self); root.setContentsMargins(14,0,12,12); root.setSpacing(12)
        center=QVBoxLayout(); center.setSpacing(10); root.addLayout(center,1)
        head=Card(margins=(12,8,12,8)); h=QHBoxLayout(); title=QLabel("Analysis Results"); title.setObjectName("CardTitle"); h.addWidget(title); ref=QLabel(project.reference or "WGM20"); ref.setStyleSheet(f"color:{P.text};font-size:15px;"); h.addWidget(ref); h.addStretch(1); head.layout.addLayout(h); center.addWidget(head)
        selector=QWidget(); sl=QHBoxLayout(selector); sl.setContentsMargins(0,0,0,0); sl.setSpacing(8)
        for text in ("Modal","Critical Speed","Campbell","Frequency Response","Unbalance Response","Time Response"):
            b=QPushButton(text); b.setCheckable(True); b.setAutoExclusive(True); b.setMinimumHeight(38)
            if text=="Campbell": b.setChecked(True); b.setObjectName("PrimaryButton")
            b.clicked.connect(lambda checked=False, btn=b:self._select_analysis(btn,selector)); sl.addWidget(b)
        sl.addStretch(1); center.addWidget(selector)
        krow=QHBoxLayout(); self.k1=KpiCard("First Critical Speed","2,840","rpm","wave"); self.k2=KpiCard("Second Critical Speed","6,520","rpm","wave"); self.k3=KpiCard("Max Amplification","8.4","-","transient"); self.k4=KpiCard("Stability Margin","0.26","-","shield")
        for k in (self.k1,self.k2,self.k3,self.k4): krow.addWidget(k,1)
        center.addLayout(krow)
        body=QHBoxLayout(); body.setSpacing(10); center.addLayout(body,1)
        chart_card=Card(margins=(0,0,0,0)); self.chart=CampbellChart(); chart_card.layout.addWidget(self.chart); body.addWidget(chart_card,7)
        table_card=Card("Mode Table"); body.addWidget(table_card,3); self.table=QTableWidget(0,5); self.table.setHorizontalHeaderLabels(["Mode","Speed\n(rpm)","Freq\n(Hz)","Damping\n(%)","Whirl"]); self.table.verticalHeader().setVisible(False); self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch); self.table.setAlternatingRowColors(True); table_card.layout.addWidget(self.table,1); self._fill_demo_table()
        tabs=Card(margins=(8,0,8,0)); tl=QHBoxLayout()
        for text in ("Mode Shapes","Critical Speeds","Orbit","FRF","Campbell"):
            b=QPushButton(text); b.setFlat(True); b.setCheckable(True); b.setAutoExclusive(True); b.setStyleSheet(f"QPushButton{{border:none;background:transparent;padding:10px 18px;}} QPushButton:checked{{color:{P.blue};border-bottom:3px solid {P.blue};}}")
            if text=="Campbell": b.setChecked(True)
            tl.addWidget(b)
        tl.addStretch(1); tabs.layout.addLayout(tl); center.addWidget(tabs)
        right_host=QWidget(); right_host.setFixedWidth(320); right=QVBoxLayout(right_host); right.setContentsMargins(0,0,0,0); right.setSpacing(10); root.addWidget(right_host)
        pi=Card("Project Information"); right.addWidget(pi)
        for n,v in [("Project Name",project.reference or "WGM20"),("Description",str(project.metadata.get("description","Wind generator main rotor\n(20 MW class)"))),("Created",str(project.metadata.get("created","Apr 25, 2025  10:24"))),("Last Modified",str(project.metadata.get("last_modified","Apr 25, 2025  14:17")))]: self._info_row(pi,n,v)
        settings=Card("Analysis Settings"); right.addWidget(settings)
        rng=QWidget(); rl=QHBoxLayout(rng); rl.setContentsMargins(0,0,0,0); rl.addWidget(QLabel("Speed Range (rpm)")); rl.addStretch(1); self.r0=QLineEdit("0"); self.r0.setFixedWidth(78); self.r1=QLineEdit("10,000"); self.r1.setFixedWidth(92); rl.addWidget(self.r0); rl.addWidget(QLabel("–")); rl.addWidget(self.r1); settings.layout.addWidget(rng)
        self.modes=QComboBox(); self.modes.addItems(["All Modes","Forward Whirl","Backward Whirl"]); self._combo(settings,"Modes Shown",self.modes)
        self.units=QComboBox(); self.units.addItems(["Hz","rad/s","CPM"]); self._combo(settings,"Frequency Units",self.units)
        self.sync=QCheckBox("Show Synchronous Line (1X)"); self.sync.setChecked(True); settings.layout.addWidget(self.sync); self.showcrit=QCheckBox("Show Critical Speeds"); settings.layout.addWidget(self.showcrit); self.grid=QCheckBox("Show Grid"); settings.layout.addWidget(self.grid)
        export=Card("Export & Report"); right.addWidget(export)
        png=QPushButton("Export PNG"); png.setIcon(studio_icon("export",P.text,18)); png.clicked.connect(self.export_png); export.layout.addWidget(png)
        csvb=QPushButton("Export CSV"); csvb.setIcon(studio_icon("results",P.text,18)); csvb.clicked.connect(self.export_csv); export.layout.addWidget(csvb)
        report=QPushButton("Generate Report"); report.setIcon(studio_icon("new",P.text,18)); export.layout.addWidget(report); right.addStretch(1)

    def _select_analysis(self, selected, host):
        for b in host.findChildren(QPushButton):
            b.setObjectName("PrimaryButton" if b is selected and b.isChecked() else ""); b.style().unpolish(b); b.style().polish(b)

    @staticmethod
    def _info_row(card: Card, name: str, value: str):
        w=QWidget(); l=QHBoxLayout(w); l.setContentsMargins(0,0,0,0); n=QLabel(name); n.setMinimumWidth(106); l.addWidget(n); v=QLabel(value); v.setWordWrap(True); v.setStyleSheet(f"color:{P.text_dark};font-weight:500;"); l.addWidget(v,1); card.layout.addWidget(w)

    @staticmethod
    def _combo(card: Card, label: str, combo: QComboBox):
        w=QWidget(); l=QHBoxLayout(w); l.setContentsMargins(0,0,0,0); l.addWidget(QLabel(label)); l.addStretch(1); combo.setMinimumWidth(145); l.addWidget(combo); card.layout.addWidget(w)

    def _fill_demo_table(self):
        rows=[(1,1050,62.3,.42,"BW"),(2,2840,153.6,.31,"FW"),(3,3120,176.4,.28,"BW"),(4,4310,238.7,.35,"FW"),(5,5020,281.9,.33,"BW"),(6,6520,332.8,.27,"FW"),(7,7140,366.1,.29,"BW"),(8,7980,401.5,.31,"FW"),(9,8760,438.2,.36,"BW"),(10,9240,468.9,.38,"FW"),(11,9680,495.3,.41,"BW"),(12,10000,520.7,.45,"FW")]
        self.table.setRowCount(len(rows))
        for r,row in enumerate(rows):
            for c,val in enumerate(row):
                txt=f"{val:,.0f}" if c in (0,1) else (f"{val:.1f}" if c==2 else (f"{val:.2f}" if c==3 else str(val))); item=QTableWidgetItem(txt); item.setTextAlignment(Qt.AlignmentFlag.AlignCenter); self.table.setItem(r,c,item)

    def set_result(self, result: AnalysisResult):
        self.last_result=result; crit=[p.rpm for p in result.critical_speeds]
        if crit:
            self.k1.value.setText(f"{crit[0]:,.0f}")
            if len(crit)>1: self.k2.value.setText(f"{crit[1]:,.0f}")
        camp=result.data.get("campbell",{}) if result.data else {}; self.chart.set_data(camp.get("speed_rpm",[]),camp.get("damped_frequency_hz"),crit)
        if result.critical_speeds:
            self.table.setRowCount(len(result.critical_speeds))
            for r,p in enumerate(result.critical_speeds):
                vals=[r+1,p.rpm,p.hz,(p.damping_ratio or 0)*100,p.whirl]
                for c,val in enumerate(vals):
                    txt=str(val) if c in (0,4) else (f"{val:,.0f}" if c==1 else f"{val:.2f}"); item=QTableWidgetItem(txt); item.setTextAlignment(Qt.AlignmentFlag.AlignCenter); self.table.setItem(r,c,item)

    def export_png(self):
        path,_=QFileDialog.getSaveFileName(self,"Export Campbell diagram","campbell.png","PNG image (*.png)")
        if path: self.chart.grab().save(path,"PNG")

    def export_csv(self):
        path,_=QFileDialog.getSaveFileName(self,"Export Campbell data","campbell.csv","CSV (*.csv)")
        if not path: return
        with open(path,"w",newline="",encoding="utf-8") as f:
            writer=csv.writer(f); writer.writerow([self.table.horizontalHeaderItem(c).text().replace("\n"," ") for c in range(self.table.columnCount())])
            for r in range(self.table.rowCount()): writer.writerow([self.table.item(r,c).text() if self.table.item(r,c) else "" for c in range(self.table.columnCount())])
