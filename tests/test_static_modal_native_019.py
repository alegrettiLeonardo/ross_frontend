from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from ross_studio.models import ProjectModel, load_reference_project_model
from ross_studio.static_modal_analysis import StaticModalAnalysisService, StaticModalRequest
from ross_studio.static_modal_native import STATIC_FIGURES, StaticModalNativeFigureCatalog


@pytest.fixture(scope="module")
def native_result():
    pytest.importorskip("ross")
    project = load_reference_project_model()
    engineering = deepcopy(project.engineering)
    assert engineering is not None
    engineering.loads = [load for load in engineering.loads if load.kind.strip().casefold() != "unbalance"]
    model = ProjectModel.from_engineering(engineering)
    case = engineering.operating_cases[0]
    request = StaticModalRequest(
        speed_rpm=case.rated_speed_rpm,
        num_modes=32,
        campbell_points=13,
        campbell_frequencies=8,
        include_static=True,
    )
    result = StaticModalAnalysisService().run(engineering, request)
    return model, result


def test_static_modal_019_runs_without_unbalance(native_result) -> None:
    project, result = native_result
    assert project.engineering is not None
    assert not any(load.kind.strip().casefold() == "unbalance" for load in project.engineering.loads)
    assert result.static is not None
    assert result.modal is not None
    assert result.campbell is not None
    assert result.build.unresolved_positions_mm == []
    assert result.modal_modes


def test_static_019_uses_four_native_ross_plots(native_result) -> None:
    _project, result = native_result
    catalog = StaticModalNativeFigureCatalog(result)
    assert tuple(STATIC_FIGURES) == ("free_body", "deformation", "shearing_force", "bending_moment")
    for key, spec in STATIC_FIGURES.items():
        figure = catalog.static_figure(key)
        assert len(getattr(figure, "data", ())) > 0
        assert spec.source_method.startswith("StaticResults.plot_")
        assert catalog.static_figure(key) is figure
    assert catalog.scientific_recompute is False


def test_modal_019_uses_native_2d_3d_and_animation(native_result) -> None:
    _project, result = native_result
    catalog = StaticModalNativeFigureCatalog(result)
    lateral = catalog.mode_indices("Lateral")
    assert lateral
    mode = lateral[0]
    fig_2d = catalog.mode_figure(mode, dimension="2d")
    fig_3d = catalog.mode_figure(mode, dimension="3d")
    fig_anim = catalog.mode_figure(mode, dimension="3d", animation=True)
    assert len(getattr(fig_2d, "data", ())) > 0
    assert len(getattr(fig_3d, "data", ())) > 0
    assert len(getattr(fig_anim, "frames", ())) > 0
    assert catalog.mode_figure(mode, dimension="3d", animation=True) is fig_anim


def test_torsional_019_uses_ross_mode_classification_and_animation(native_result) -> None:
    _project, result = native_result
    catalog = StaticModalNativeFigureCatalog(result)
    torsional = catalog.mode_indices("Torsional")
    assert torsional, "ROSS did not return a torsional mode among the requested eigenvalues"
    mode = torsional[0]
    summary = next(item for item in result.modal_modes if item.mode_index == mode)
    assert summary.mode_type == "Torsional"
    fig = catalog.mode_figure(mode, dimension="3d", animation=True)
    assert len(getattr(fig, "data", ())) > 0
    assert len(getattr(fig, "frames", ())) > 0


def test_campbell_019_uses_native_ross_plot_and_plot_only_harmonics(native_result) -> None:
    _project, result = native_result
    catalog = StaticModalNativeFigureCatalog(result)
    before = dict(result.stage_elapsed_s)
    figure = catalog.campbell_figure((0.5, 1.0))
    assert len(getattr(figure, "data", ())) > 0
    assert result.stage_elapsed_s == before
    assert catalog.campbell_figure((0.5, 1.0)) is figure


def test_static_modal_019_routes_are_operational_native_workspaces(qtbot, native_result) -> None:
    from ross_studio.app import RossStudioWindow
    from ross_studio.pages.static_modal_workspace import StaticModalWorkspacePage
    from ross_studio.page_registry import route_spec

    project, result = native_result
    assert route_spec("analysis.static_modal.lateral").operational is True
    assert route_spec("analysis.static_modal.torsional").operational is True
    assert route_spec("analysis.static_modal.lateral").implementation_phase == "0.19.0"

    window = RossStudioWindow()
    qtbot.addWidget(window)
    window.project = project

    window._navigate("analysis.static_modal.lateral")
    lateral = window.stack.currentWidget()
    assert isinstance(lateral, StaticModalWorkspacePage)
    assert lateral.mode_filter == "Lateral"
    lateral.set_result(result)
    assert lateral.mode_table.rowCount() > 0
    assert lateral.static_view.figure is not None
    assert lateral.mode_view.figure is not None
    assert lateral.campbell_view.figure is not None

    window._navigate("analysis.static_modal.torsional")
    torsional = window.stack.currentWidget()
    assert isinstance(torsional, StaticModalWorkspacePage)
    assert torsional.mode_filter == "Torsional"
    torsional.set_result(result)
    assert torsional.mode_table.rowCount() > 0
    torsional.animate.setChecked(True)
    qtbot.wait(1)
    assert torsional.mode_view.figure is not None
    assert len(getattr(torsional.mode_view.figure, "frames", ())) > 0


def test_static_modal_019_animation_html_export_preserves_frames(native_result, tmp_path: Path) -> None:
    _project, result = native_result
    catalog = StaticModalNativeFigureCatalog(result)
    mode = catalog.mode_indices("Torsional")[0]
    figure = catalog.mode_figure(mode, dimension="3d", animation=True)
    target = catalog.export_html(figure, tmp_path / "torsional_mode_animated.html")
    assert target.is_file() and target.stat().st_size > 0
    text = target.read_text(encoding="utf-8")
    assert "Plotly" in text
    assert "frames" in text or "addFrames" in text
