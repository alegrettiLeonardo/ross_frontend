"""PyInstaller entry point for ROSS Studio release binaries.

Normal execution preloads the pinned ROSS runtime before importing the desktop
application. Setting ROSS_STUDIO_SMOKE_TEST=1 performs a deterministic headless
startup and scientific-runtime test, then exits without entering the Qt event
loop. The smoke test validates the same BearingCatalogService instance used by
the GUI, preventing a frozen executable from passing with a separately-created
registry while the visible Bearing Studio remains blocked.
"""
from __future__ import annotations

import json
import os
import sys


def _load_ross():
    """Load the pinned scientific runtime before any desktop-module import."""
    import ross as rs

    version = str(getattr(rs, "__version__", "unknown"))
    if version != "2.3.0":
        raise RuntimeError(f"ROSS Studio 0.11.0 requires ROSS 2.3.0; found {version}.")
    return rs


def _smoke_test() -> int:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    import numpy as np

    # Match the normal packaged startup order: ROSS is loaded before app.py.
    rs = _load_ross()
    import ross_studio
    from PySide6.QtWidgets import QApplication

    from ross_studio.analysis_backend import RossAnalysisBackend
    from ross_studio.app import RossStudioWindow
    from ross_studio.domain import AdapterStatus, BearingGroup
    from ross_studio.ross_backend import RossModelBuilder

    app = QApplication.instance() or QApplication([])
    window = RossStudioWindow()

    # Validate the actual registry/catalog bound to the visible Bearing Studio.
    general = window.catalog.entries(BearingGroup.GENERAL)
    thd = window.catalog.entries(BearingGroup.THD)
    amb = window.catalog.entries(BearingGroup.AMB)
    thrust_status, thrust_reason = window.catalog.registry.effective_status("ThrustPad")

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
        "general_executable": sum(bool(row["can_execute"]) for row in general),
        "general_total": len(general),
        "thd_executable": sum(bool(row["can_execute"]) for row in thd),
        "thd_total": len(thd),
        "amb_executable": sum(bool(row["can_execute"]) for row in amb),
        "amb_total": len(amb),
        "thrust_pad_status": thrust_status.value,
        "thrust_pad_reason": thrust_reason,
        "general_classes": {str(row["class"]): str(row["status"]) for row in general},
        "thd_classes": {str(row["class"]): str(row["status"]) for row in thd},
        "amb_classes": {str(row["class"]): str(row["status"]) for row in amb},
    }

    assert ross_studio.__version__ == "0.11.0", checks
    assert getattr(rs, "__version__", None) == "2.3.0", checks
    assert window.project.name == "OP-W60-500-60Hz-IC611-P3", checks
    assert len(build.rotor.shaft_elements) == 27, checks
    assert build.unresolved_positions_mm == [], checks
    assert checks["modal_finite"], checks
    assert checks["general_executable"] == 4 and checks["general_total"] == 4, checks
    assert checks["thd_executable"] == 4 and checks["thd_total"] == 4, checks
    assert checks["amb_executable"] == 0 and checks["amb_total"] == 1, checks
    assert thrust_status == AdapterStatus.VALIDATED, checks

    window.close()
    app.processEvents()
    # --windowed executables on Windows intentionally have sys.stdout=None.
    if sys.stdout is not None:
        print(json.dumps(checks, ensure_ascii=False))
    return 0


def main() -> int:
    if os.environ.get("ROSS_STUDIO_SMOKE_TEST") == "1":
        return _smoke_test()

    # Normal GUI launch uses the same import order qualified by the smoke test.
    _load_ross()
    from ross_studio.app import launch

    return launch()


if __name__ == "__main__":
    raise SystemExit(main())
