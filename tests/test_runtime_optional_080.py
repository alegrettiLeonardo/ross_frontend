from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pytest

from ross_studio.analysis_backend import RossAnalysisBackend
from ross_studio.analysis_pipeline import AnalysisPipelineService, AnalysisPolicy
from ross_studio.legacy_import import load_irdin_project
from ross_studio.models import ProjectModel, load_reference_project_model
from ross_studio.ross_backend import RossModelBuilder


FIXTURE = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "src",
    "ross_studio",
    "resources",
    "OP-W60-500-60Hz-IC611-P3.txt",
)


def test_real_ross_23_strict_builds_op_w60_with_inserted_nodes_and_legacy_masses() -> None:
    rs = pytest.importorskip("ross")
    project = load_irdin_project(FIXTURE)
    result = RossModelBuilder(rs).build(project, strict=True)

    assert len(result.rotor.shaft_elements) == 27
    assert len(result.node_positions_mm) == 28
    assert result.unresolved_positions_mm == []
    assert result.support_link_nodes == {"Support 1": 28, "Support 2": 29}
    assert len(result.rotor.bearing_elements) == 4
    assert len(result.rotor.disk_elements) == 5
    assert len(result.rotor.point_mass_elements) == 2
    assert len(result.equivalent_disks) == 4
    assert len(result.equivalent_point_masses) == 1

    bearings_by_tag = {bearing.tag: bearing for bearing in result.rotor.bearing_elements}
    assert bearings_by_tag["dianteiro -quente"].n_link == 28
    assert bearings_by_tag["traseiro -quente"].n_link == 29
    assert bearings_by_tag["Support 1 / ground"].n == 28
    assert bearings_by_tag["Support 2 / ground"].n == 29

    disk_by_tag = {disk.tag: disk for disk in result.rotor.disk_elements}
    assert disk_by_tag["Rotor mass 2 / legacy equivalent"].m == pytest.approx(723.19)
    assert disk_by_tag["Rotor mass 2 / legacy equivalent"].Id == pytest.approx(43.397426583333335)
    assert disk_by_tag["Rotor mass 2 / legacy equivalent"].Ip == pytest.approx(25.176051875)

    shaft_point_mass = disk_by_tag["Point mass 1 / shaft point mass"]
    assert shaft_point_mass.m == pytest.approx(34.0)
    assert shaft_point_mass.Id == 0.0
    assert shaft_point_mass.Ip == 0.0
    np.testing.assert_allclose(
        shaft_point_mass.M(),
        np.diag([34.0, 34.0, 34.0, 0.0, 0.0, 0.0]),
    )

    support_mass_by_tag = {mass.tag: mass for mass in result.rotor.point_mass_elements}
    assert set(support_mass_by_tag) == {"Support 1 mass", "Support 2 mass"}


def test_real_ross_23_runs_complete_op_w60_scientific_pipeline() -> None:
    rs = pytest.importorskip("ross")
    project = load_irdin_project(FIXTURE)
    backend = RossAnalysisBackend(rs)
    service = AnalysisPipelineService(
        backend=backend,
        policy=AnalysisPolicy(
            modal_num_modes=12,
            campbell_frequencies=6,
            campbell_points=13,
            response_points=13,
        ),
    )
    events = []
    result = service.run(project, progress=events.append)

    assert result.build.unresolved_positions_mm == []
    assert len(result.build.rotor.shaft_elements) == 27
    assert result.static is not None
    assert result.modal is not None
    assert result.campbell is not None
    assert result.unbalance is not None
    assert len(result.modal_modes) == 6
    assert len(result.probe_responses) == 4
    assert len(result.speed_rpm) >= 13
    assert result.speed_rpm[0] == pytest.approx(900.0)
    assert result.speed_rpm[-1] == pytest.approx(4500.0)
    assert np.any(np.isclose(result.speed_rpm, 3600.0))

    assert np.all(np.isfinite(np.asarray(result.static.deformation, dtype=float)))
    assert np.all(np.isfinite(np.asarray(result.modal.wd, dtype=float)))
    assert np.all(np.isfinite(np.asarray(result.campbell.wd, dtype=float)))
    assert np.all(np.isfinite(np.abs(np.asarray(result.unbalance.forced_resp))))

    assert {row.position_mm for row in result.probe_responses} == {467.8, 2202.2}
    assert all(row.node in result.build.rotor.nodes for row in result.probe_responses)
    assert all(np.isfinite(row.peak_amplitude_m) for row in result.probe_responses)
    assert all(np.isfinite(row.rated_amplitude_m) for row in result.probe_responses)

    audit_codes = {audit.code for audit in result.audits}
    assert "BEARING_KC_ENVELOPE" in audit_codes
    assert "CRITICAL_METHOD" in audit_codes
    assert "UNBALANCE_INPUT_UNITS" in audit_codes
    assert any(note.code == "ROSS_230_ORBIT_COMPAT" for note in backend.compatibility_notes)
    completed = [event.stage for event in events if event.state == "completed"]
    assert completed == list(AnalysisPipelineService.STAGES)

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    from ross_studio.pages.results import AnalysisResultsPage

    app = QApplication.instance() or QApplication([])
    result_page = AnalysisResultsPage(ProjectModel.from_engineering(project))
    result_page.set_results(result)
    assert result_page.result is result
    assert "ROSS pipeline PASS" in result_page.result_state.text()
    for result_key in ("static", "modal", "critical", "campbell", "unbalance"):
        result_page._select_analysis(result_key)
        assert result_page.table.rowCount() >= 1
    result_page.close()
    app.processEvents()

    artifact_dir = Path("artifacts")
    artifact_dir.mkdir(exist_ok=True)
    summary = {
        "project": project.name,
        "ross_version": getattr(rs, "__version__", "unknown"),
        "ross_compatibility": [
            {"code": note.code, "message": note.message}
            for note in backend.compatibility_notes
        ],
        "topology": {
            "physical_sections": project.physical_section_count,
            "shaft_elements": len(result.build.shaft_plan),
            "shaft_nodes": len(result.build.node_positions_mm),
            "support_link_nodes": result.build.support_link_nodes,
        },
        "speed_envelope_rpm": [float(result.speed_rpm[0]), float(result.speed_rpm[-1])],
        "static": {
            "max_abs_deformation_m": float(np.max(np.abs(np.asarray(result.static.deformation, dtype=float)))),
        },
        "modal_rated": [
            {
                "mode": mode.mode,
                "wn_hz": mode.wn_hz,
                "wd_hz": mode.wd_hz,
                "damping_ratio": mode.damping_ratio,
                "log_dec": mode.log_dec,
                "whirl": mode.whirl,
            }
            for mode in result.modal_modes
        ],
        "critical_speeds": [
            {
                "mode": critical.mode,
                "speed_rpm": critical.speed_rpm,
                "frequency_hz": critical.frequency_hz,
                "damping_ratio": critical.damping_ratio,
                "log_dec": critical.log_dec,
                "whirl": critical.whirl,
                "method": critical.method,
            }
            for critical in result.critical_speeds
        ],
        "probes": [
            {
                "name": probe.name,
                "node": probe.node,
                "position_mm": probe.position_mm,
                "coordinate": probe.coordinate,
                "orientation_deg": probe.orientation_deg,
                "peak_speed_rpm": probe.peak_speed_rpm,
                "peak_amplitude_m": probe.peak_amplitude_m,
                "peak_phase_deg": probe.peak_phase_deg,
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


def test_qt_engineering_routes_and_bearing_studio_2_workspace() -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication, QTabWidget

    from ross_studio.app import RossStudioWindow

    app = QApplication.instance() or QApplication([])
    window = RossStudioWindow()
    assert window.project.name == "OP-W60-500-60Hz-IC611-P3"

    expected_workspaces = {
        "shaft": 0,  # compatibility alias; there is no visible Shaft navigation state
        "disks": 1,
        "supports": 2,
        "couplings": 4,
        "loads": 5,
        "ump": 6,
        "probes": 7,
    }
    for route, workspace_index in expected_workspaces.items():
        window._navigate(route)
        assert window.stack.currentWidget() is window.rotor_page
        assert window.rotor_page.editor_stack.currentIndex() == workspace_index

    assert "shaft" not in window.sidebar.buttons
    assert window.rotor_page.findChildren(QTabWidget) == []
    assert not hasattr(window.toolbar, "view_combo")
    assert hasattr(window.toolbar, "full_rotor_button")

    window._navigate("bearings")
    assert window.stack.currentWidget() is window.bearing_page
    assert window.stack.count() == 3
    assert not hasattr(window, "bearing_groups_page")

    window._navigate("seals")
    assert window.stack.currentWidget().__class__.__module__.endswith("seal_workspace")
    assert window.stack.count() == 4
    window._navigate("bearings")
    assert window.stack.currentWidget() is window.bearing_page
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

    for key, (_title, _ross_class, _group) in window.bearing_page.type_metadata.items():
        window.bearing_page._select_type(key, announce=False)
        assert window.bearing_page.calculate_button.isEnabled()
        assert not window.bearing_page.apply_button.isEnabled()

    window.close()
    app.processEvents()


def test_reference_model_is_loaded_without_hardcoded_ui_geometry() -> None:
    project = load_reference_project_model()
    assert project.engineering is not None
    assert project.physical_sections == project.engineering.physical_section_count == 15
    assert project.ross_shaft_elements == project.engineering.ross_shaft_element_count == 27
