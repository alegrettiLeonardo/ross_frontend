from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QObject, Signal


@dataclass(slots=True, frozen=True)
class RotorEntityRef:
    """Stable presentation reference for one engineering entity.

    The reference deliberately stores domain identity (kind/index/physical position)
    rather than a table row or painter object. This keeps sketch, editor and future
    3D/native ROSS views synchronized without coupling their widgets together.
    """

    kind: str
    index: int
    label: str
    position_mm: float | None = None


class RotorSelectionModel(QObject):
    selection_changed = Signal(object)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._current: RotorEntityRef | None = None

    @property
    def current(self) -> RotorEntityRef | None:
        return self._current

    def select(self, ref: RotorEntityRef | None) -> None:
        if ref == self._current:
            return
        self._current = ref
        self.selection_changed.emit(ref)

    def clear(self) -> None:
        self.select(None)


WORKSPACE_SELECTION = RotorSelectionModel()


__all__ = ["RotorEntityRef", "RotorSelectionModel", "WORKSPACE_SELECTION"]
