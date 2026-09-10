"""PyInstaller entry point for ROSS Studio release binaries.

Normal execution launches the desktop application. Setting
ROSS_STUDIO_SMOKE_TEST=1 performs a deterministic headless startup test and
exits without entering the Qt event loop. This is used by native Linux and
Windows release runners after packaging.
"""
from __future__ import annotations

import json
import os


def _smoke_test() -> int:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    import ross as rs
    import ross_studio
    from PySide6.QtWidgets import QApplication

    from ross_studio.app import RossStudioWindow
    from ross_studio.domain import AdapterStatus
    from ross_studio.services import RossCapabilityRegistry

    app = QApplication.instance() or QApplication([])
    window = RossStudioWindow()
    status, reason = RossCapabilityRegistry(rs).effective_status("ThrustPad")

    checks = {
        "ross_studio_version": ross_studio.__version__,
        "ross_version": getattr(rs, "__version__", "unknown"),
        "project": window.project.name,
        "thrust_pad_status": status.value,
        "thrust_pad_reason": reason,
    }

    assert ross_studio.__version__ == "0.11.0", checks
    assert getattr(rs, "__version__", None) == "2.3.0", checks
    assert window.project.engineering is not None, checks
    assert window.project.name == "OP-W60-500-60Hz-IC611-P3", checks
    assert status == AdapterStatus.VALIDATED, checks

    window.close()
    app.processEvents()
    print(json.dumps(checks, ensure_ascii=False))
    return 0


def main() -> int:
    if os.environ.get("ROSS_STUDIO_SMOKE_TEST") == "1":
        return _smoke_test()

    from ross_studio.app import launch

    return launch()


if __name__ == "__main__":
    raise SystemExit(main())
