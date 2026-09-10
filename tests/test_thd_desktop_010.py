"""Production THD desktop qualification uses real Qt, native ROSS and strict modal.

The three lateral THD capabilities are enabled by the production registry and are
qualified here through their dedicated lateral service. ThrustPad is also promoted
in the registry, but its scientific and desktop execution remain covered by the
separate axial ThrustPad qualification; it is never routed through this lateral service.
"""
from copy import deepcopy
import json
from pathlib import Path

import numpy as np
import pytest
import ross as rs
from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QApplication

from ross_studio.app import RossStudioWindow
from ross_studio.analysis_backend import RossAnalysisBackend
from ross_studio.domain import AdapterStatus
from ross_studio.ross_backend import RossModelBuilder
from ross_studio.services import RossCapabilityRegistry
from ross_studio.thd_bearing_service import THDBearingStudioService
from ross_studio.thd_input_dialog import THDBearingInputDialog
from ross_studio.thd_results import UNAVAILABLE, convergence, native_field


def test_production_registry_promotes_qualified_thd_and_blocks_amb():
    registry = RossCapabilityRegistry(rs)
    for model in THDBearingStudioService.SUPPORTED_CLASSES:
        status, _reason = registry.effective_status(model)
        assert status == AdapterStatus.VALIDATED
    assert registry.effective_status("ThrustPad")[0] == AdapterStatus.VALIDATED
    assert registry.effective_status("MagneticBearingElement")[0] == AdapterStatus.BLOCKED


@pytest.mark.parametrize("model,speeds", [
    ("PlainJournal", [900., 1000.]),
    ("TiltingPad", [3000., 3600.]),
    ("SqueezeFilmDamper", [900., 3600.]),
])
def test_real_qt_thd_calculate_preview_apply_strict_modal(qtbot, monkeypatch, model, speeds):
    window = RossStudioWindow()
    qtbot.addWidget(window)
    window.show()
    window._open_bearing_group("THD")
    key = window._bearing_key_for_class(window.bearing_page, model)
    qtbot.mouseClick(window.bearing_page.type_buttons[key], Qt.MouseButton.LeftButton)
    assert window._selected_bearing_class() == model
    assert window.bearing_page.calculate_button.isEnabled()
    original = deepcopy(window.project.engineering)
    calls = []
    calculate = window.thd_bearing_service.calculate
    apply = window.thd_bearing_service.apply

    def scientific(*args):
        calls.append(("calculate", args[2]))
        return calculate(*args)

    def apply_real(*args):
        calls.append(("apply", args[2].source_model))
        return apply(*args)

    def wrong_service(*args):
        pytest.fail("THD routed to the General service")

    monkeypatch.setattr(window.thd_bearing_service, "calculate", scientific)
    monkeypatch.setattr(window.thd_bearing_service, "apply", apply_real)
    monkeypatch.setattr(window.bearing_service, "calculate", wrong_service)
    monkeypatch.setattr(window.bearing_service, "apply", wrong_service)
    entered = {}

    def fill_real_dialog():
        dialog = QApplication.activeModalWidget()
        assert isinstance(dialog, THDBearingInputDialog)
        dialog.fields["speed_rpm"].setText(", ".join(map(str, speeds)))
        entered.update(dialog.values())
        dialog.accept()

    QTimer.singleShot(0, fill_real_dialog)
    qtbot.mouseClick(window.bearing_page.calculate_button, Qt.MouseButton.LeftButton)
    result = window.bearing_calculation
    assert result is not None, window.status
    assert calls == [("calculate", model)]
    assert result.source_model == model
    assert result.native_element.__class__.__name__ == model
    assert result.metadata["engineering_input"] == entered
    assert result.metadata["ross_api_contract"] == "2.3.0"
    assert result.metadata["solved_kc_cache"] == 1
    assert result.metadata["normalized_input"]["journal_diameter_m"] == pytest.approx(entered["journal_diameter_mm"] * 1e-3)
    assert result.metadata["speed_rpm"] == speeds
    assert len(result.coefficients) == len(speeds)
    assert np.all(np.isfinite([[getattr(p, k) for k in ("kxx","kxy","kyx","kyy","cxx","cxy","cyx","cyy")] for p in result.coefficients]))
    assert window.project.engineering == original  # Preview must not mutate rotor.
    assert window.bearing_page.kc_table.rowCount() == len(speeds)
    assert [p.rpm for p in window.bearing.coefficients] == speeds
    assert window.bearing_page.nominal_index == len(speeds)-1
    assert window.bearing_page.apply_button.isEnabled()
    for name, tab in window.bearing_page.result_tabs.items():
        assert tab.result is result
        tab.speed.setCurrentIndex(0)
        field = native_field(result, name, 0)
        if field is not None:
            expected = field[:, :, 0] if field.ndim == 3 else field
            assert tab.table.rowCount() == expected.shape[0]
            scale = 1e-6 if name == "Pressure" else 1
            assert float(tab.table.item(0, 0).text()) == pytest.approx(expected[0,0]*scale, rel=1e-7)
        if model == "SqueezeFilmDamper" and name in {"Pressure", "Temperature"}:
            assert UNAVAILABLE in tab.summary.text()
    qtbot.mouseClick(window.bearing_page.apply_button, Qt.MouseButton.LeftButton)
    assert calls == [("calculate", model), ("apply", model)]
    spec = window.project.engineering.bearings[0]
    assert spec.ross_class == "BearingElement"
    assert spec.metadata["source_model"] == model
    assert spec.metadata == result.metadata
    assert spec.coefficients == list(result.coefficients)
    assert window.bearing_field_result is result  # native evidence survives Apply
    assert window.bearing_calculation is None
    build = RossModelBuilder(rs).build(window.project.engineering, strict=True)
    assert build.rotor.bearing_elements[0].n_link == 28
    assert build.rotor.bearing_elements[1].n_link == 29
    assert len(build.rotor.shaft_elements) == 27
    modal = RossAnalysisBackend(rs).run_modal_build(build, speeds[0], num_modes=12)
    assert np.all(np.isfinite(modal.wn)) and len(modal.wn) > 0
    assert calls == [("calculate", model), ("apply", model)]  # no THD re-solve
    window.bearing_page._select_type("thrust", announce=False)
    assert window.bearing_page.calculate_button.isEnabled()
    assert not window.bearing_page.apply_button.isEnabled()
    window._open_bearing_group("AMB")
    assert not window.bearing_page.calculate_button.isEnabled()
    out = Path(__file__).parents[1] / "artifacts" / "thd_desktop_qualification.json"
    out.parent.mkdir(exist_ok=True)
    payload = json.loads(out.read_text()) if out.exists() else {}
    payload[model] = {
        "status": "PASS", "ross_version": rs.__version__, "engineering_input": entered,
        "metadata": result.metadata, "speed_rpm": speeds, "application_class": spec.ross_class,
        "n_link": 28, "modal_wn_rad_s": modal.wn.tolist(),
        "convergence": [convergence(result, i) for i in range(len(speeds))],
        "native_fields_retained_after_apply": window.bearing_field_result is result,
    }
    out.write_text(json.dumps(payload, indent=2))
    window.close()


def test_general_preview_rejects_stale_project_and_preserves_rotor(qtbot):
    window = RossStudioWindow()
    qtbot.addWidget(window)
    window._calculate_bearing()
    window.project.engineering.bearings[0].name += " changed"
    before = deepcopy(window.project.engineering)
    window._apply_bearing()
    assert window.project.engineering == before
    assert window.bearing_calculation is not None


def test_input_units_and_all_fields_reach_scientific_boundary(qtbot):
    window = RossStudioWindow()
    qtbot.addWidget(window)
    for model in THDBearingStudioService.SUPPORTED_CLASSES:
        dialog = THDBearingInputDialog(window.project.engineering, 0, model)
        qtbot.addWidget(dialog)
        engineering = dialog.values()
        normalized = THDBearingStudioService.normalize_inputs(engineering)
        assert normalized["journal_diameter_m"] == pytest.approx(engineering["journal_diameter_mm"] * 1e-3)
        assert normalized["radial_clearance_m"] == pytest.approx(engineering["radial_clearance_um"] * 1e-6)
        assert "journal_diameter_mm" not in normalized
        if model == "PlainJournal":
            assert normalized["initial_guess"] == pytest.approx([0.1, -0.1])
            assert normalized["oil_supply_pressure_pa"] == engineering["oil_supply_pressure_bar"] * 1e5