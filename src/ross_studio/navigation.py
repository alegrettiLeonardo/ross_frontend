from __future__ import annotations

from PySide6.QtWidgets import QWidget

from .ui_shell import Sidebar as _LegacySidebar


class Sidebar(_LegacySidebar):
    """Single-source model navigation for the engineering workspace.

    ``Rotor`` and ``Shaft`` previously pointed to the same ``RotorModelPage`` and
    the same shaft editor.  Keeping both buttons made a single editor look like two
    independent models.  The visible navigation now exposes one ``Rotor Model``
    entry.  The internal ``shaft`` route remains accepted by the editor as a
    backwards-compatible command alias, but is not user state and has no button.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        rotor = self.buttons.get("rotor")
        if rotor is not None:
            rotor.setText("Rotor Model")
            rotor.setToolTip("Physical rotor model, shaft sections and attached engineering entities")

        shaft = self.buttons.pop("shaft", None)
        if shaft is not None:
            layout = self.layout()
            if layout is not None:
                layout.removeWidget(shaft)
            shaft.hide()
            shaft.deleteLater()

        bearings = self.buttons.get("bearings")
        if bearings is not None:
            bearings.setText("Bearing Studio")
            bearings.setToolTip("Configure, solve and apply bearings to qualified rotor stations/nodes")

    def set_active(self, key: str) -> None:
        # ``shaft`` is an internal editor alias only; it must never recreate a
        # duplicate navigation state.
        super().set_active("rotor" if key == "shaft" else key)


__all__ = ["Sidebar"]
