from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from ..icons import engineering_icon
from ..models import CAMPBELL_MODES, ProjectModel
from ..theme import COLORS
from ..widgets import CampbellChart, Card, ProjectInfoCard, SectionCard, configure_table, item


class KpiCard(Card):
    def __init__(self, title: str, value: str, unit: str, icon_name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent, object_name="kpiCard")
        layout=QHBoxLayout(self); layout.setContentsMargins(16,10,14,10); layout.setSpacing(12)
        icon=QLabel(); icon.setPixmap(engineering_icon(icon_name,42,"#0f4f89").pixmap(42,42)); layout.addWidget(icon)
        text=QVBoxLayout(); text.setSpacing(0); t=QLabel(title); t.setObjectName("kpiTitle"); text.addWidget(t)
        row=QHBoxLayout(); v=QLabel(value); v.setObjectName("kpiValue"); row.addWidget(v); u=QLabel(unit); u.setObjectName("muted"); row.addWidget(u,0,Qt.AlignmentFlag.AlignBottom); row.addStretch(1); text.addLayout(row); layout.addLayout(text,1)


class AnalysisResultsPage(QWidget):
    def __init__(self, project: ProjectModel, parent: QWidget | None = None) -> None:
        super().__init__(parent); self.project=project
        root=QHBoxLayout(self); root.setContentsMargins(12,12,12,12); root.setSpacing(12)
        center=QVBoxLayout(); center.setContentsMargins(0,0,0,0); center.setSpacing(10); root.addLayout(center,1)

        head=Card(); hl=QVBoxLayout(head); hl.setContentsMargins(14,10,14,10); hl.setSpacing(8)
        title_row=QHBoxLayout(); title=QLabel("Analysis Results"); title.setObjectName("cardHeader"); title_row.addWidget(title); title_row.addWidget(QLabel(project.name)); title_row.addStretch(1); hl.addLayout(title_row)
        tabs=QHBoxLayout(); self.analysis_buttons={}
        for key,text in [("modal","Modal"),("critical","Critical Speed"),("campbell","Campbell"),("frf","Frequency Response"),("unbalance","Unbalance Response"),("time","Time Response")]:
            b=QPushButton(text); b.setCheckable(True); b.setObjectName("primaryButton" if key=="campbell" else "outlineButton"); b.setMinimumHeight(36); b.clicked.connect(lambda checked=False,k=key:self._select_analysis(k)); tabs.addWidget(b); self.analysis_buttons[key]=b
        self.analysis_buttons["campbell"].setChecked(True); tabs.addStretch(1); hl.addLayout(tabs)
        center.addWidget(head)

        kpis=QHBoxLayout(); kpis.setSpacing(10)
        for args in [("First Critical Speed","2,840","rpm","speed"),("Second Critical Speed","6,520","rpm","speed"),("Max Amplification","8.4","-","amplification"),("Stability Margin","0.26","-","shield")]: kpis.addWidget(KpiCard(*args),1)
        center.addLayout(kpis)

        main=QHBoxLayout(); main.setSpacing(10)
        chart_card=Card(); cl=QVBoxLayout(chart_card); cl.setContentsMargins(12,10,12,10); h=QLabel("Campbell Diagram"); h.setObjectName("cardHeader"); cl.addWidget(h); cl.addWidget(CampbellChart(),1); main.addWidget(chart_card,3)
        mode_card=Card(); ml=QVBoxLayout(mode_card); ml.setContentsMargins(8,10,8,8); mh=QLabel("Mode Table"); mh.setObjectName("cardHeader"); ml.addWidget(mh)
        headers=["Mode","Speed\n(rpm)","Freq\n(Hz)","Damping\n(%)","Whirl"]
        table=QTableWidget(len(CAMPBELL_MODES),len(headers)); table.setHorizontalHeaderLabels(headers); configure_table(table,row_height=30); table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        for r,m in enumerate(CAMPBELL_MODES):
            vals=[m.mode,f"{m.speed_rpm:,}",f"{m.freq_hz:.1f}",f"{m.damping_pct:.2f}",m.whirl]
            for c,v in enumerate(vals): table.setItem(r,c,item(v))
        table.resizeColumnsToContents(); table.horizontalHeader().setStretchLastSection(True); ml.addWidget(table,1); main.addWidget(mode_card,1)
        center.addLayout(main,1)

        footer=Card(); fl=QHBoxLayout(footer); fl.setContentsMargins(10,0,10,0); fl.setSpacing(18)
        self.footer_buttons={}
        for text in ("Mode Shapes","Critical Speeds","Orbit","FRF","Campbell"):
            b=QPushButton(text); b.setObjectName("toolButton"); b.setCheckable(True); if_active = text=="Campbell"; b.setChecked(if_active); fl.addWidget(b); self.footer_buttons[text]=b
        fl.addStretch(1); center.addWidget(footer)

        right_l=QVBoxLayout(); right_l.setContentsMargins(0,0,0,0); right_l.setSpacing(10); right=QWidget(); right.setFixedWidth(326); right.setLayout(right_l); root.addWidget(right)
        right_l.addWidget(ProjectInfoCard(project))
        right_l.addWidget(self._settings_card(),1)
        right_l.addWidget(self._export_card())

    def _select_analysis(self,key:str)->None:
        for name,b in self.analysis_buttons.items():
            active=name==key; b.setChecked(active); b.setObjectName("primaryButton" if active else "outlineButton"); b.style().unpolish(b); b.style().polish(b)

    def _settings_card(self)->QWidget:
        card=SectionCard("Analysis Settings"); g=QGridLayout(); g.setHorizontalSpacing(8); g.setVerticalSpacing(10)
        g.addWidget(QLabel("Speed Range (rpm)"),0,0,1,3)
        a=QSpinBox(); a.setRange(0,200000); a.setValue(0); b=QSpinBox(); b.setRange(0,200000); b.setValue(10000); g.addWidget(a,1,0); g.addWidget(QLabel("–"),1,1,Qt.AlignmentFlag.AlignCenter); g.addWidget(b,1,2)
        g.addWidget(QLabel("Modes Shown"),2,0); modes=QComboBox(); modes.addItems(["All Modes","Forward Whirl","Backward Whirl"]); g.addWidget(modes,2,1,1,2)
        g.addWidget(QLabel("Frequency Units"),3,0); units=QComboBox(); units.addItems(["Hz","rad/s","CPM"]); g.addWidget(units,3,1,1,2)
        checks=[("Show Synchronous Line (1X)",True),("Show Critical Speeds",False),("Show Grid",False)]
        for r,(text,checked) in enumerate(checks,4): c=QCheckBox(text); c.setChecked(checked); g.addWidget(c,r,0,1,3)
        card.root.addLayout(g); return card

    def _export_card(self)->QWidget:
        card=SectionCard("Export & Report")
        for text,icon in [("Export PNG","image"),("Export CSV","table"),("Generate Report","report")]:
            b=QPushButton(text); b.setObjectName("softButton"); b.setIcon(engineering_icon(icon,20)); card.root.addWidget(b)
        return card
