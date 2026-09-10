from __future__ import annotations

from PySide6.QtCore import QObject, Signal


class WorkspaceCommandBus(QObject):
    """Application-level presentation commands shared by toolbar and workspaces."""

    fit_view_requested = Signal()
    zoom_in_requested = Signal()
    zoom_out_requested = Signal()
    view_mode_requested = Signal(str)
    navigate_requested = Signal(str)


WORKSPACE_COMMANDS = WorkspaceCommandBus()


__all__ = ["WorkspaceCommandBus", "WORKSPACE_COMMANDS"]
