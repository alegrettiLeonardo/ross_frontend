from __future__ import annotations

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
from ross_studio.thd_results import UNAVAILABLE, native_field
from ross_studio.thrust_pad_input_dialog import ThrustPadInputDialog
from ross_studio.thrust_pad_service import ThrustPadCalculationResult


ROOT = Path(__file__).resolve().parents[1]


def test_pre_promotion_registry_keeps_thrust_pad_gated():
    window = RossStudioWindow()
    try:
        status, _reason = window.catalog.registry.effective_status("ThrustPad")
        assert status == AdapterStatus.PLANNED
        window._open_bearing_group("THD")
        window.bearing_page._select_type("thrust", announce=False)
        assert not window.bearing_page.calculate_button.isEnabled()
        assert not window.bearing_page.apply_button.isEnabled()
    finally:
        window.close()


def test_real_qt_thrust_pad_calculate_preview_apply_strict_modal(qtbot, monkeypatch):
    """Exercise the complete desktop wiring while the production capability is gated.

    The button is enabled only inside this coordination test. The calculation itself is
    the real ROSS 2.3 ThrustPad solve; no scientific result is mocked. Promotion occurs
    only after this test and all independent scientific gates are green.
    """
    assert rs.__version__ == "2.3.0"
    window = RossStudioWindow()
    qtbot.addWidget(window)
    window.show()
    window._open_bearing_group("THD")
    qtbot.mouseClick(window.bearing_page.type_buttons["thrust"], Qt.MouseButton.LeftButton)
    assert window._selected_bearing_class() == "ThrustPad"
    assert not window.bearing_page.calculate_button.isEnabled()

    # Pre-promotion execution is deliberately test-local. No registry status is changed.
    window.bearing_page.calculate_button.setEnabled(True)
    original = deepcopy(window.project.engineering)
    calls: list[tuple[str, str]] = []
    calculate = window.thrust_pad_service.calculate
    apply = window.thrust_pad_service.apply

    def calculate_real(*args):
        calls.append(("calculate", args[2]))
        return calculate(*args)

    def apply_real(*args):
        calls.append(("apply", args[2].source_model))
        return apply(*args)

    def wrong_service(*_args, **_kwargs):
        pytest.fail("ThrustPad was routed to a lateral or General bearing service")

    monkeypatch.setattr(window.thrust_pad_service, "calculate", calculate_real)
    monkeypatch.setattr(window.thrust_pad_service, "apply", apply_real)
    monkeypatch.setattr(window.thd_bearing_service, "calculate", wrong_service)
    monkeypatch.setattr(window.thd_bearing_service, "apply", wrong_service)
    monkeypatch.setattr(window.bearing_service, "calculate", wrong_service)
    monkeypatch.setattr(window.bearing_service, "apply", wrong_service)

    entered: dict[str, object] = {}

    def fill_dialog():
        dialog = QApplication.activeModalWidget()
        assert isinstance(dialog, ThrustPadInputDialog)
        # One canonical ROSS 2.3 speed station keeps this E2E deterministic.
        dialog.fields["speed_rpm"].setText("90")
        entered.update(dialog.values())
        dialog.accept()

    QTimer.singleShot(0, fill_dialog)
    qtbot.mouseClick(window.bearing_page.calculate_button, Qt.MouseButton.LeftButton)

    result = window.bearing_calculation
    assert isinstance(result, ThrustPadCalculationResult)
    assert calls == [("calculate", "ThrustPad")]
    assert result.source_model == "ThrustPad"
    assert result.application_class == "BearingElement"
    assert result.native_element.__class__.__name__ == "ThrustPad"
    assert result.metadata["engineering_input"] == entered
    assert result.metadata["ross_api_contract"] == "2.3.0"
    assert result.metadata["solved_axial_kc_cache"] == 1
    assert not hasattr(result, "coefficients")
    assert len(result.axial_coefficients) == 1
    assert np.isfinite(result.axial_coefficients[0].kzz)
    assert np.isfinite(result.axial_coefficients[0].czz)
    assert window.project.engineering == original  # Calculate is preview-only.

    # Preview is an explicit axial table; no Kzz/Czz is inserted in lateral columns.
    assert window.bearing_page.kc_table.rowCount() == 1
    assert window.bearing_page.kc_table.columnCount() == 3
    assert "Kzz" in window.bearing_page.kc_table.horizontalHeaderItem(1).text()
    assert "Czz" in window.bearing_page.kc_table.horizontalHeaderItem(2).text()
    assert float(window.bearing_page.kc_table.item(0, 1).text()) == pytest.approx(
        result.axial_coefficients[0].kzz, rel=1e-6
    )
    assert float(window.bearing_page.kc_table.item(0, 2).text()) == pytest.approx(
        result.axial_coefficients[0].czz, rel=1e-6
    )
    assert not window.bearing_page.chart_card.isVisible()
    assert window.bearing_page.apply_button.isEnabled()

    pressure_tab = window.bearing_page.result_tabs["Pressure"]
    temperature_tab = window.bearing_page.result_tabs["Temperature"]
    film_tab = window.bearing_page.result_tabs["Film Thickness"]
    journal_tab = window.bearing_page.result_tabs["Journal Position"]
    for tab in (pressure_tab, temperature_tab, film_tab, journal_tab):
        assert tab.result is result
        tab.speed.setCurrentIndex(0)

    pressure = native_field(result, "Pressure", 0)
    temperature = native_field(result, "Temperature", 0)
    assert pressure is not None and pressure_tab.table.rowCount() == pressure.shape[0]
    assert temperature is not None and temperature_tab.table.rowCount() == temperature.shape[0]
    assert "h_min" in film_tab.summary.text()
    assert "h_pivot" in film_tab.summary.text()
    assert "h_max" in film_tab.summary.text()
    assert UNAVAILABLE in journal_tab.summary.text()

    qtbot.mouseClick(window.bearing_page.apply_button, Qt.MouseButton.LeftButton)
    assert calls == [("calculate", "ThrustPad"), ("apply", "ThrustPad")]
    engineering = window.project.engineering
    assert len(engineering.bearings) == len(original.bearings) + 1
    assert engineering.bearings[0] == original.bearings[0]
    assert engineering.bearings[1] == original.bearings[1]
    applied = engineering.bearings[-1]
    assert applied.metadata["source_model"] == "ThrustPad"
    assert applied.metadata["application_mode"] == "independent_axial_bearing_same_shaft_node"
    assert applied.metadata["lateral_coefficients_forced_zero"] == 1
    assert applied.coefficients == []
    assert window.bearing_field_result is result
    assert window.bearing_calculation is None

    build = RossModelBuilder(rs).build(engineering, strict=True)
    radial_de = next(e for e in build.rotor.bearing_elements if e.tag == original.bearings[0].name)
    radial_nde = next(e for e in build.rotor.bearing_elements if e.tag == original.bearings[1].name)
    thrust = next(e for e in build.rotor.bearing_elements if e.tag == applied.name)
    assert radial_de.n_link == 28
    assert radial_nde.n_link == 29
    assert thrust.n_link is None
    assert len(build.rotor.shaft_elements) == 27

    local_k = np.asarray(thrust.K(90.0 * 2.0 * np.pi / 60.0), dtype=float)
    local_c = np.asarray(thrust.C(90.0 * 2.0 * np.pi / 60.0), dtype=float)
    assert np.allclose(local_k[:2, :], 0.0) and np.allclose(local_k[:, :2], 0.0)
    assert np.allclose(local_c[:2, :], 0.0) and np.allclose(local_c[:, :2], 0.0)
    assert local_k[2, 2] == pytest.approx(result.axial_coefficients[0].kzz)
    assert local_c[2, 2] == pytest.approx(result.axial_coefficients[0].czz)

    modal = RossAnalysisBackend(rs).run_modal_build(build, 90.0, num_modes=12)
    assert len(modal.wn) > 0 and np.all(np.isfinite(np.asarray(modal.wn, dtype=float)))
    assert calls == [("calculate", "ThrustPad"), ("apply", "ThrustPad")]  # no THD re-solve

    payload = {
        "status": "PASS",
        "ross_version": rs.__version__,
        "source_model": result.source_model,
        "engineering_input": entered,
        "metadata": result.metadata,
        "axial_coefficients": [
            {"rpm": p.rpm, "kzz": p.kzz, "czz": p.czz}
            for p in result.axial_coefficients
        ],
        "application_class": applied.ross_class,
        "application_mode": applied.metadata["application_mode"],
        "radial_n_links": [radial_de.n_link, radial_nde.n_link],
        "thrust_n_link": thrust.n_link,
        "shaft_elements": len(build.rotor.shaft_elements),
        "modal_wn_rad_s": [float(v) for v in modal.wn],
        "native_fields_retained_after_apply": window.bearing_field_result is result,
        "capability_status_during_gate": "PLANNED",
    }
    out = ROOT / "artifacts" / "thrust_pad_desktop_qualification.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    window.close()
