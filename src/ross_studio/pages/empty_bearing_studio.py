from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..domain import BearingGroup
from ..models import ProjectModel
from ..widgets import Card


class EmptyBearingStudioPage(QWidget):
    """Non-fictional Bearing Studio state for a newly created empty project.

    New must not invent a shaft station or a placeholder physical bearing merely to
    satisfy a widget constructor. This page preserves the same application-facing
    interface as BearingStudioPage while all physics-dependent actions stay disabled
    until the user defines/imports an engineering rotor with a bearing station.
    """

    status_message = Signal(str)
    bearing_selected = Signal(int)

    def __init__(self, project: ProjectModel, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.project = project
        self.current_group = BearingGroup.GENERAL
        self.type_buttons: dict[str, QPushButton] = {}
        self.type_metadata: dict[str, tuple] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)

        card = Card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(24, 24, 24, 24)
        title = QLabel("Bearing Studio")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        message = QLabel(
            "No bearing station exists in this project yet. Define/import the rotor geometry and physical "
            "bearing stations first; ROSS Studio will not create a fictitious support or K/C entry for a new file."
        )
        message.setObjectName("muted")
        message.setWordWrap(True)
        layout.addWidget(message)

        self.bearing_selector = QComboBox()
        self.bearing_selector.setObjectName("bearingStationSelector")
        self.bearing_selector.setEnabled(False)
        layout.addWidget(self.bearing_selector)

        self.group_selector = QComboBox()
        self.group_selector.setObjectName("bearingFamilySelector")
        for group in (BearingGroup.GENERAL, BearingGroup.THD, BearingGroup.AMB):
            self.group_selector.addItem(group.value, group.value)
        self.group_selector.hide()
        layout.addWidget(self.group_selector)

        self.calculate_button = QPushButton("Calculate Bearing")
        self.calculate_button.setEnabled(False)
        self.apply_button = QPushButton("Apply to Rotor")
        self.apply_button.setEnabled(False)
        layout.addWidget(self.calculate_button)
        layout.addWidget(self.apply_button)
        layout.addStretch(1)
        root.addWidget(card, 1)

    def set_group(self, group: str, *, announce: bool = True) -> None:
        self.current_group = BearingGroup(group)
        row = self.group_selector.findData(self.current_group.value)
        if row >= 0:
            self.group_selector.setCurrentIndex(row)
        if announce:
            self.status_message.emit(
                f"{self.current_group.value}: define a physical bearing station before selecting a bearing model"
            )

    def set_results_available(self, _available: bool, *, show: bool = False) -> None:
        del show

    def input_values(self) -> dict:
        return {}


__all__ = ["EmptyBearingStudioPage"]
