from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from ..icons import engineering_icon
from ..models import ProjectModel
from ..widgets import (
    Card,
    ModelSummaryCard,
    ProjectInfoCard,
    QuickActionsCard,
    RotorSketch,
    configure_table,
    item,
)


class RotorModelPage(QWidget):
    run_requested = Signal()
    validate_requested = Signal()

    def __init__(self, project: ProjectModel, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.project = project
        root = QHBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        center = QVBoxLayout()
        center.setSpacing(10)
        center.setContentsMargins(0, 0, 0, 0)
        root.addLayout(center, 1)

        rotor_card = Card()
        rotor_layout = QVBoxLayout(rotor_card)
        rotor_layout.setContentsMargins(0, 0, 0, 0)
        rotor_layout.setSpacing(0)
        header = QLabel("Rotor Model")
        header.setObjectName("cardHeader")
        header.setContentsMargins(18, 12, 0, 8)
        rotor_layout.addWidget(header)
        line = QFrame(); line.setFixedHeight(1); line.setStyleSheet("background:#dbe6f0;")
        rotor_layout.addWidget(line)
        self.sketch = RotorSketch(project)
        rotor_layout.addWidget(self.sketch, 1)
        center.addWidget(rotor_card, 6)

        data_card = Card()
        data_layout = QVBoxLayout(data_card)
        data_layout.setContentsMargins(10, 0, 10, 10)
        data_layout.setSpacing(8)
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        data_layout.addWidget(self.tabs, 1)
        self.tabs.addTab(self._segments_tab(), "Shaft Segments")
        self.tabs.addTab(self._placeholder("Disk element editor"), "Disks")
        self.tabs.addTab(self._placeholder("Bearing element editor"), "Bearings")
        self.tabs.addTab(self._placeholder("Support element editor"), "Supports")
        self.tabs.addTab(self._placeholder("Coupling element editor"), "Couplings")
        center.addWidget(data_card, 7)

        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(10)
        right_panel = QWidget(); right_panel.setFixedWidth(326); right_panel.setLayout(right)
        root.addWidget(right_panel)
        right.addWidget(ProjectInfoCard(project))
        right.addWidget(ModelSummaryCard(project), 1)
        actions = QuickActionsCard()
        actions.run_requested.connect(self.run_requested.emit)
        actions.validate_requested.connect(self.validate_requested.emit)
        right.addWidget(actions)

    def _segments_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 9, 0, 0)
        layout.setSpacing(8)
        top = QHBoxLayout()
        title = QLabel("Shaft Segments"); title.setObjectName("cardHeader"); top.addWidget(title)
        top.addStretch(1)
        for text, icon_name in [("Add Segment", "plus"), ("Delete", "trash"), ("Import...", "import")]:
            b = QPushButton(text); b.setObjectName("outlineButton"); b.setIcon(engineering_icon(icon_name, 18)); top.addWidget(b)
        layout.addLayout(top)

        headers = ["Section", "Length (mm)", "OD Left (mm)", "OD Right (mm)", "ID Left (mm)", "ID Right (mm)", "Material"]
        table = QTableWidget(len(self.project.segments), len(headers))
        table.setHorizontalHeaderLabels(headers)
        configure_table(table, row_height=34)
        for r, seg in enumerate(self.project.segments):
            values = [seg.section, f"{seg.length_mm:.0f}", f"{seg.od_left_mm:.0f}", f"{seg.od_right_mm:.0f}", f"{seg.id_left_mm:.0f}", f"{seg.id_right_mm:.0f}", seg.material]
            for c, value in enumerate(values):
                table.setItem(r, c, item(value, center=c != 6))
        table.selectRow(0)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(table, 1)
        self.segment_table = table
        return page

    @staticmethod
    def _placeholder(text: str) -> QWidget:
        page = QWidget(); layout = QVBoxLayout(page); label = QLabel(text); label.setAlignment(Qt.AlignmentFlag.AlignCenter); label.setObjectName("muted"); layout.addWidget(label); return page
