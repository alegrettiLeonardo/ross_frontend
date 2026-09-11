from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import plotly.graph_objects as go

from ross_studio.models import ProjectModel, load_reference_project_model
from ross_studio.project_io import project_fingerprint
from ross_studio.static_modal_analysis import StaticModalModeSummary
from ross_studio.static_modal_decoupled import (
    ModalAnalysisRequest,
    ModalAnalysisResult,
    ModalAnalysisService,
    StaticAnalysisResult,
    StaticAnalysisService,
)


class _Shape:
    def __init__(self, mode_type: str) -> None:
        self.mode_type = mode_type


class _FakeModal:
    wn = np.asarray([100.0, 200.0])
    wd = np.asarray([99.0, 198.0])
    damping_ratio = np.asarray([0.01, 0.02])
    log_dec = np.asarray([0.06, 0.12])
    shapes = (_Shape("Lateral"), _Shape("Torsional"))

    def whirl_direction(self):
        return np.asarray(["Forward", "None"])

    def plot_mode_2d(self, mode: int, orientation: str = "major"):
        return go.Figure(go.Scatter(x=[0, 1], y=[0, mode + 1], name=orientation))

    def plot_mode_3d(self, mode: int, animation: bool = False):
        figure = go.Figure(go.Scatter3d(x=[0, 1], y=[0, 0], z=[0, mode + 1]))
        if animation:
            figure.frames = [go.Frame(data=[go.Scatter3d(x=[0, 1], y=[0, 0], z=[0, mode + 1])])]
        return figure


class _FakeCampbell:
    wd = np.asarray([[100.0, 200.0], [105.0, 205.0]])

    def plot(self, harmonics=None):
        return go.Figure(go.Scatter(x=[0, 1], y=[100, 105], name=str(harmonics)))


class _FakeStatic:
    @staticmethod
    def _figure(name: str):
        return go.Figure(go.Scatter(x=[0, 1], y=[0, 1], name=name))

    def plot_free_body_diagram(self):
        return self._figure("free_body")

    def plot_deformation(self):
        return self._figure("deformation")

    def plot_shearing_force(self):
        return self._figure("shearing")

    def plot_bending_moment(self):
        return self._figure("moment")


class _CountingBackend:
    def __init__(self) -> None:
        self.calls = {"build": 0, "static": 0, "modal": 0, "campbell": 0}

    def build_rotor(self, project, strict=True):
        assert strict is True
        self.calls["build"] += 1
        return SimpleNamespace(unresolved_positions_mm=[])

    def run_static_build(self, build):
        self.calls["static"] += 1
        return _FakeStatic()

    def run_modal_build(self, build, speed_rpm, num_modes=24):
        self.calls["modal"] += 1
        return _FakeModal()

    def run_campbell_build(self, build, speed_rpm, frequencies=8):
        self.calls["campbell"] += 1
        return _FakeCampbell()


def _engineering_without_unbalance():
    model = load_reference_project_model()
    engineering = deepcopy(model.engineering)
    assert engineering is not None
    engineering.loads = [load for load in engineering.loads if load.kind.strip().casefold() != "unbalance"]
    return engineering


def test_static_020_transaction_does_not_execute_modal_or_campbell() -> None:
    engineering = _engineering_without_unbalance()
    backend = _CountingBackend()
    result = StaticAnalysisService(backend).run(engineering)
    assert result.static is not None
    assert backend.calls == {"build": 1, "static": 1, "modal": 0, "campbell": 0}
    assert result.build.unresolved_positions_mm == []
    assert any(audit.code == "ROSS_STATIC_NATIVE_020" for audit in result.audits)


def test_modal_020_transaction_does_not_execute_static() -> None:
    engineering = _engineering_without_unbalance()
    backend = _CountingBackend()
    request = ModalAnalysisRequest(
        speed_rpm=engineering.operating_cases[0].rated_speed_rpm,
        num_modes=8,
        campbell_points=7,
        campbell_frequencies=4,
    )
    result = ModalAnalysisService(backend).run(engineering, request)
    assert result.modal is not None and result.campbell is not None
    assert backend.calls == {"build": 1, "static": 0, "modal": 1, "campbell": 1}
    assert result.mode_indices("Lateral") == (0,)
    assert result.mode_indices("Torsional") == (1,)
    assert any(audit.code == "ROSS_MODAL_NATIVE_020" for audit in result.audits)


def test_static_and_modal_020_are_two_independent_strict_build_transactions() -> None:
    engineering = _engineering_without_unbalance()
    backend = _CountingBackend()
    StaticAnalysisService(backend).run(engineering)
    after_static = dict(backend.calls)
    ModalAnalysisService(backend).run(
        engineering,
        ModalAnalysisRequest(
            speed_rpm=engineering.operating_cases[0].rated_speed_rpm,
            num_modes=8,
            campbell_points=7,
            campbell_frequencies=4,
        ),
    )
    assert after_static == {"build": 1, "static": 1, "modal": 0, "campbell": 0}
    assert backend.calls == {"build": 2, "static": 1, "modal": 1, "campbell": 1}


def _fake_results(project: ProjectModel):
    engineering = project.engineering
    assert engineering is not None
    build = SimpleNamespace(unresolved_positions_mm=[])
    static = StaticAnalysisResult(
        project_name=engineering.name,
        build=build,
        static=_FakeStatic(),
    )
    request = ModalAnalysisRequest(
        speed_rpm=float(project.speed_rpm),
        num_modes=8,
        campbell_points=7,
        campbell_frequencies=4,
    )
    modal = ModalAnalysisResult(
        project_name=engineering.name,
        build=build,
        request=request,
        modal=_FakeModal(),
        campbell=_FakeCampbell(),
        campbell_speed_rpm=np.asarray([1000.0, 2000.0]),
        modal_modes=(
            StaticModalModeSummary(0, 1, "Lateral", 10.0, 9.9, 0.01, 0.06, "Forward"),
            StaticModalModeSummary(1, 2, "Torsional", 20.0, 19.8, 0.02, 0.12, "Torsional"),
        ),
    )
    return static, modal


def test_workspace_020_modal_input_change_invalidates_only_modal_cache(qtbot) -> None:
    from ross_studio.pages.static_modal_workspace import StaticModalWorkspacePage

    project = load_reference_project_model()
    page = StaticModalWorkspacePage(project, mode_filter="Lateral")
    qtbot.addWidget(page)
    static, modal = _fake_results(project)
    fp = project_fingerprint(project)
    page.set_static_result(static, fingerprint=fp)
    page.set_modal_result(modal, fingerprint=fp)
    assert page.static_result is static
    assert page.modal_result is modal
    assert page.static_view.figure is not None
    assert page.mode_view.figure is not None

    page.speed_rpm.setValue(page.speed_rpm.value() + 25.0)
    qtbot.wait(1)
    assert page.static_result is static
    assert page.static_catalog is not None
    assert page.modal_result is None
    assert page.modal_catalog is None
    assert "Static cache" in page.modal_state.text()


def test_workspace_020_project_change_invalidates_both_caches(qtbot) -> None:
    from ross_studio.pages.static_modal_workspace import StaticModalWorkspacePage

    project = load_reference_project_model()
    page = StaticModalWorkspacePage(project, mode_filter="Lateral")
    qtbot.addWidget(page)
    static, modal = _fake_results(project)
    fp = project_fingerprint(project)
    page.set_static_result(static, fingerprint=fp)
    page.set_modal_result(modal, fingerprint=fp)
    assert project.engineering is not None
    project.engineering.name = project.engineering.name + "-REV"
    page._invalidate_if_project_changed()
    assert page.static_result is None
    assert page.modal_result is None
    assert "ROTOR MODEL changed" in page.static_state.text()
    assert "ROTOR MODEL changed" in page.modal_state.text()


def test_workspace_020_exposes_dedicated_run_controls(qtbot) -> None:
    from ross_studio.pages.static_modal_workspace import StaticModalWorkspacePage
    from ross_studio.page_registry import route_spec

    project = load_reference_project_model()
    lateral = StaticModalWorkspacePage(project, mode_filter="Lateral")
    torsional = StaticModalWorkspacePage(project, mode_filter="Torsional")
    qtbot.addWidget(lateral)
    qtbot.addWidget(torsional)
    assert lateral.run_static_button.text() == "Run Static"
    assert lateral.run_modal_button.text() == "Run Modal & Campbell"
    assert not hasattr(torsional, "run_static_button")
    assert torsional.run_modal_button.text() == "Run Modal & Campbell"
    assert route_spec("analysis.static_modal.lateral").implementation_phase == "0.20.0"
    assert route_spec("analysis.static_modal.torsional").implementation_phase == "0.20.0"
