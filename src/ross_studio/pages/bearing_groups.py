from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ..domain import BearingGroup
from ..icons import engineering_icon
from ..models import ProjectModel
from ..services import BearingCatalogService
from ..widgets import Card, ProjectInfoCard


class BearingGroupsPage(QWidget):
    group_selected = Signal(str)

    def __init__(self, project: ProjectModel, catalog: BearingCatalogService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.project = project
        self.catalog = catalog
        root = QHBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)
        center = QVBoxLayout()
        center.setSpacing(12)
        root.addLayout(center, 1)

        title_card = Card()
        title_layout = QVBoxLayout(title_card)
        title_layout.setContentsMargins(18, 16, 18, 16)
        title = QLabel("Bearing Studio")
        title.setObjectName("cardHeader")
        title_layout.addWidget(title)
        sub = QLabel("Select a bearing family. ROSS class availability and ROSS Studio adapter readiness are evaluated separately.")
        sub.setObjectName("muted")
        title_layout.addWidget(sub)
        center.addWidget(title_card)

        cards = QHBoxLayout()
        cards.setSpacing(12)
        descriptors = {
            BearingGroup.GENERAL: ("bearing", "General / Parametric", "Direct K/C plus analytical rolling and cylindrical bearing models."),
            BearingGroup.THD: ("seal", "Thermo-Hydro-Dynamic (THD)", "Reynolds / thermal fluid-film bearing models."),
            BearingGroup.AMB: ("wave", "Active Magnetic Bearings (AMB)", "Electromagnetic bearing with explicit actuator / sensor / controller domain."),
        }
        for group in self.catalog.groups():
            icon, heading, description = descriptors[group]
            card = Card()
            lay = QVBoxLayout(card)
            lay.setContentsMargins(18, 18, 18, 18)
            lay.setSpacing(9)
            icon_label = QLabel()
            icon_label.setPixmap(engineering_icon(icon, 36).pixmap(36, 36))
            lay.addWidget(icon_label)
            h = QLabel(heading)
            h.setObjectName("subHeader")
            lay.addWidget(h)
            d = QLabel(description)
            d.setObjectName("muted")
            d.setWordWrap(True)
            lay.addWidget(d)
            entries = self.catalog.entries(group)
            available = sum(1 for row in entries if row["can_execute"])
            summary = QLabel(f"{len(entries)} classes  •  {available} executable adapters")
            summary.setObjectName("muted")
            lay.addWidget(summary)
            for entry in entries:
                state = "Ready" if entry["can_execute"] else entry["status"]
                row = QLabel(f"{entry['title']}  —  {state}")
                row.setObjectName("muted")
                lay.addWidget(row)
            lay.addStretch(1)
            button = QPushButton("Open Group")
            button.setObjectName("primaryButton")
            button.clicked.connect(lambda checked=False, value=group.value: self.group_selected.emit(value))
            lay.addWidget(button)
            cards.addWidget(card, 1)
        center.addLayout(cards, 1)

        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right_panel = QWidget()
        right_panel.setFixedWidth(326)
        right_panel.setLayout(right)
        root.addWidget(right_panel)
        right.addWidget(ProjectInfoCard(project))
        right.addStretch(1)
