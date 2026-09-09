from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from .icons import app_icon
from .main_window import RossStudioWindow


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("ROSS STUDIO")
    app.setOrganizationName("ROSS Studio")
    app.setWindowIcon(app_icon(32))
    window = RossStudioWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
