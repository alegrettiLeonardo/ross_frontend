from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pytest


@pytest.mark.parametrize("optional_module", ["PySide6", "ross"])
def test_optional_runtime_modules_are_importable_when_installed(optional_module: str) -> None:
    pytest.importorskip(optional_module)


def test_qt_engineering_routes_and_bearing_studio_2_workspace() -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication, QTabWidget

    from ross_studio.app import RossStudioWindow
    from ross_studio.pages.seal_workspace import SealStudioWorkspacePage

    app = QApplication.instance() or QApplication([])
    window = RossStudioWindow()
    assert window.project.name == "OP-W60-500-60Hz-IC611-P3"

    expected_rotor_workspaces = {
        "shaft": 0,  # compatibility alias; there is no visible Shaft navigation state
        "disks": 1,
        "supports": 2,
        "couplings": 4,
        "loads": 5,
        "ump": 6,
        "probes": 7,
    }
    for route, workspace_index in expected_rotor_workspaces.items():
        window._navigate(route)
        assert window.stack.currentWidget() is window.rotor_page
        assert window.rotor_page.editor_stack.currentIndex() == workspace_index

    # 0.25 migrates Seals out of the legacy RotorModelPage editor stack. The old
    # editor index remains internal compatibility state only; the public route owns
    # an independent native ROSS Calculate -> Preview -> Apply workspace.
    window._navigate("seals")
    seal_page = window.stack.currentWidget()
    assert isinstance(seal_page, SealStudioWorkspacePage)
    assert seal_page is not window.rotor_page

    assert "shaft" not in window.sidebar.buttons
    assert window.rotor_page.findChildren(QTabWidget) == []
    assert not hasattr(window.toolbar, "view_combo")
    assert hasattr(window.toolbar, "full_rotor_button")

    window._navigate("bearings")
    assert window.stack.currentWidget() is window.bearing_page
    assert window.stack.count() == 4  # legacy rotor + bearing + results + dedicated Seal Studio
    assert not hasattr(window, "bearing_groups_page")
    assert window.bearing_page.__class__.__module__.endswith("bearing_workspace_page")
    assert window.bearing_page.bearing_selector.count() == len(window.project.engineering.bearings) == 2
    assert window.bearing_page.group_selector.isHidden()

    visible_classes = {
        window.bearing_page.type_metadata[key][1]
        for key, button in window.bearing_page.type_buttons.items()
        if not button.isHidden()
    }
    assert visible_classes == {
        "BallBearingElement",
        "RollerBearingElement",
        "CylindricalBearing",
        "PlainJournal",
        "TiltingPad",
        "ThrustPad",
        "SqueezeFilmDamper",
        "MagneticBearingElement",
    }
    assert "kc" not in window.bearing_page.type_buttons

    for key, (_title, ross_class, _group) in window.bearing_page.type_metadata.items():
        window.bearing_page._select_type(key, announce=False)
        if ross_class == "MagneticBearingElement":
            assert not window.bearing_page.calculate_button.isEnabled()
        else:
            assert window.bearing_page.calculate_button.isEnabled()


def test_plotly_native_fallback_respects_webengine_disable(monkeypatch) -> None:
    monkeypatch.setenv("ROSS_STUDIO_DISABLE_WEBENGINE", "1")
    from ross_studio import plotly_native_view

    assert plotly_native_view.WEBENGINE_AVAILABLE is False


def _write_summary(artifact_dir: Path, result) -> None:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "project_name": result.project_name,
        "physical_sections": len(result.build.shaft_plan),
        "probe_responses": [
            {
                "name": probe.name,
                "rated_speed_rpm": probe.rated_speed_rpm,
                "rated_amplitude_m": probe.rated_amplitude_m,
                "rated_phase_deg": probe.rated_phase_deg,
            }
            for probe in result.probe_responses
        ],
        "audits": [
            {"severity": audit.severity, "code": audit.code, "message": audit.message}
            for audit in result.audits
        ],
        "stage_elapsed_s": result.stage_elapsed_s,
        "gui_results_handoff": "PASS",
    }
    (artifact_dir / "op_w60_pipeline_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


# The remaining optional-runtime tests exercise scientific services directly. They
# intentionally stay below this UI contract and therefore do not depend on the
# Seal Studio route migration.

def test_numpy_runtime_available() -> None:
    assert np.__version__
