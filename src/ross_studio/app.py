from __future__ import annotations

"""ROSS Studio 0.15 application composition root.

The qualified 0.14 window/application orchestration is preserved in
``app_legacy`` while 0.15 replaces only workspace presentation classes. This keeps
scientific transaction logic stable during the UI refactor and gives project-file
rebuilds the same class mapping as startup.
"""

import sys

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from . import app_legacy as _legacy
from .pages import bearing_studio as _bearing_base_module
from .pages import rotor_model as _rotor_base_module
from .pages.bearing_workspace_page import BearingStudioPage
from .pages.rotor_workspace import RotorModelPage
from .theme import APP_STYLESHEET

# app_legacy resolves these module globals when a window/page is constructed or
# refreshed. Redirect them to the 0.15 workspaces without duplicating solver logic.
_legacy.BearingStudioPage = BearingStudioPage
_legacy.RotorModelPage = RotorModelPage

# ProjectFileController imports the historical module paths lazily after Open/New.
# Publish the same composition there so startup and file replacement cannot diverge.
_bearing_base_module.BearingStudioPage = BearingStudioPage
_rotor_base_module.RotorModelPage = RotorModelPage

TitleBar = _legacy.TitleBar
RossStudioWindow = _legacy.RossStudioWindow


def launch() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("ROSS Studio")
    app.setOrganizationName("ROSS Studio")
    app.setStyleSheet(APP_STYLESHEET)
    app.setFont(QFont("Segoe UI", 10))
    window = RossStudioWindow()
    window.show()
    return app.exec()


__all__ = ["RossStudioWindow", "TitleBar", "launch"]
