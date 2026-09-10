"""PyInstaller entry point for ROSS Studio release binaries.

Normal execution launches the desktop application. Setting
ROSS_STUDIO_SMOKE_TEST=1 performs a deterministic headless startup and
scientific-runtime test, then exits without entering the Qt event loop. This is
used by native Linux and Windows release runners after packaging.
"""
from __future__ import annotations

import json
import os
import sys


def _smoke_test() -> int:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    import numpy as np
    import ross as rs
    import ross_studio
    from PySide6.QtWidgets import QApplication

    from ross_studio.analysis_backend import RossAnalysisBackend
    from ross_studio.app import RossStudioWindow
    from ross_studio.domain import AdapterStatus
    from ross_studio.ross_backend import RossModelBuilder
    from ross_studio.services import RossCapabilityRegistry

    app = QApplication.instance() or QApplication([])
    window = RossStudioWindow()
    status, reason = RossCapabilityRegistry(rs).effective_status("ThrustPad")

    assert window.project.engineering is not None
    build = RossModelBuilder(rs).build(window.project.engineering, strict=True)
    rated_speed_rpm = float(window.project.engineering.operating_cases[0].rated_speed_rpm)
    modal = RossAnalysisBackend(rs).run_modal_build(build, rated_speed_rpm, num_modes=6)
    modal_wn = np.asarray(modal.wn, dtype=float)

    checks = {
        "ross_studio_version": ross_studio.__version__,
        "ross_version": getattr(rs, "__version__", "unknown"),
        "project": window.project.name,
        "shaft_elements": len(build.rotor.shaft_elements),
        "unresolved_positions": list(build.unresolved_positions_mm),
        "modal_modes": int(modal_wn.size),
        "modal_finite": bool(modal_wn.size and np.all(np.isfinite(modal_wn))),
        "thrust_pad_status": status.value,
        "thrust_pad_reason": reason,
    }

    assert ross_studio.__version__ == "0.11.0", checks
    assert getattr(rs, "__version__", None) == "2.3.0", checks
    assert window.project.name == "OP-W60-500-60Hz-IC611-P3", checks
    assert len(build.rotor.shaft_elements) == 27, checks
    assert build.unresolved_positions_mm == [], checks
    assert checks["modal_finite"], checks
    assert status == AdapterStatus.VALIDATED, checks

    window.close()
    app.processEvents()
    # --windowed executables on Windows intentionally have sys.stdout=None.
    if sys.stdout is not None:
        print(json.dumps(checks, ensure_ascii=False))
    return 0


def main() -> int:
    if os.environ.get("ROSS_STUDIO_SMOKE_TEST") == "1":
        return _smoke_test()

    from ross_studio.app import launch

    return launch()


if __name__ == "__main__":
    raise SystemExit(main())
