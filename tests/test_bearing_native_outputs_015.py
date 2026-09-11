from __future__ import annotations

from copy import deepcopy

import numpy as np
import pytest
from plotly import graph_objects as go

from ross_studio.app import RossStudioWindow
from ross_studio.bearing_node_inspector import THD_SOURCE_MODELS
from ross_studio.domain import BearingCoefficientPoint
from ross_studio.ross_native_plots import RossBearingNativePlotService
from ross_studio.rotor_selection import RotorEntityRef, WORKSPACE_SELECTION


class PlainJournal:
    """Small API-faithful fixture proving Studio delegates output ownership to ROSS."""

    def __init__(self) -> None:
        self.frequency = np.asarray([100.0])

    def plot(self, **_kwargs):
        return go.Figure(go.Scatter(x=[900, 1200], y=[1.0, 2.0], name="native K/C"))

    def plot_results(self, show_plots=False, freq_index=0):
        assert show_plots is False
        assert freq_index == 0
        return {
            "pressure_2d": go.Figure(go.Contour(z=[[0.0, 1.0], [0.2, 0.8]])),
            "pressure_3d": go.Figure(go.Surface(z=[[0.0, 1.0], [0.2, 0.8]])),
            "temperature_2d": go.Figure(go.Contour(z=[[40.0, 50.0], [45.0, 55.0]])),
            "temperature_3d": go.Figure(go.Surface(z=[[40.0, 50.0], [45.0, 55.0]])),
        }

    def plot_bearing_representation(self):
        return go.Figure(go.Scatter(x=[0, 1], y=[0, 1], name="bearing geometry"))

    def plot_pressure_distribution(self):
        return go.Figure(go.Scatter(x=[0, 1], y=[0, 1], name="pressure distribution"))

    def show_results(self):
        print("PLAIN JOURNAL RESULTS - NATIVE ROSS")

    def show_coefficients_comparison(self):
        print("DYNAMIC COEFFICIENTS COMPARISON TABLE")

    def show_execution_time(self):
        print("Execution time: 1.234 seconds")

    def show_optimization_convergence(self, by="index", show_plots=False):
        assert by == "value"
        assert show_plots is False
        print("OPTIMIZATION CONVERGENCE - NATIVE ROSS")


def test_native_bearing_output_adapter_keeps_ross_figures_and_show_outputs() -> None:
    native = PlainJournal()
    service = RossBearingNativePlotService()

    kc = service.kc_figure(native)
    assert isinstance(kc, go.Figure)
    assert kc.data[0].name == "native K/C"

    output = service.dimensional_outputs(native, freq_index=0)
    assert output.source == "PlainJournal"
    assert {
        "Pressure 2D", "Pressure 3D", "Temperature 2D", "Temperature 3D",
        "Bearing Representation", "Pressure Distribution",
    }.issubset(output.figures)
    assert output.text_outputs["Results Summary"] == "PLAIN JOURNAL RESULTS - NATIVE ROSS"
    assert "DYNAMIC COEFFICIENTS" in output.text_outputs["K/C Comparison"]
    assert "Execution time" in output.text_outputs["Execution Time"]
    assert "OPTIMIZATION CONVERGENCE" in output.text_outputs["Optimization Convergence"]


def test_production_app_is_composed_with_015_workspaces(qtbot) -> None:
    window = RossStudioWindow()
    qtbot.addWidget(window)
    assert window.rotor_page.__class__.__module__.endswith("rotor_workspace")
    assert window.bearing_page.__class__.__module__.endswith("bearing_workspace_page")
    assert not hasattr(window.toolbar, "view_combo")


def test_bearing_node_inspector_shows_nominal_kc_and_curves_only_for_thd(qtbot) -> None:
    WORKSPACE_SELECTION.clear()
    window = RossStudioWindow()
    qtbot.addWidget(window)
    window.show()
    window._navigate("rotor")
    engineering = window.project.engineering
    assert engineering is not None
    inspector = window.rotor_page.bearing_node_inspector

    spec = engineering.bearings[0]
    ref = RotorEntityRef("bearings", 0, spec.name, spec.position_mm)
    WORKSPACE_SELECTION.select(ref)
    qtbot.waitUntil(lambda: inspector.station_index == 0)

    assert inspector.value_labels["Node"].text().startswith("ROSS n")
    assert inspector.value_labels["Model"].text() == "BearingElement"
    assert "N/m" in inspector.value_labels["Kxx"].text()
    assert "N·s/m" in inspector.value_labels["Cxx"].text()
    assert inspector.curves_button.isHidden()  # General/imported K/C has no curve action.

    # Mark a deterministic solved table as a committed THD result. The inspector
    # must read/interpolate that cache only; no bearing solver is invoked here.
    spec.metadata["source_model"] = "PlainJournal"
    assert spec.metadata["source_model"] in THD_SOURCE_MODELS
    spec.coefficients = [
        BearingCoefficientPoint(3000.0, 1.0e8, 1.0e7, -2.0e7, 1.1e8, 1.0e5, 1.0e4, -2.0e4, 1.1e5),
        BearingCoefficientPoint(4000.0, 2.0e8, 2.0e7, -3.0e7, 2.1e8, 2.0e5, 2.0e4, -3.0e4, 2.1e5),
    ]
    inspector.set_selection(ref)

    # Rated OP-W60 speed is 3600 rpm: linear interpolation is 60% through the
    # solved THD table, and extrapolation is intentionally not used.
    assert inspector.value_labels["Model"].text() == "PlainJournal"
    assert "1.6000e+08" in inspector.value_labels["Kxx"].text()
    assert "1.6000e+05" in inspector.value_labels["Cxx"].text()
    assert not inspector.curves_button.isHidden()

    # Activating the bearing in the physical sketch keeps the user in the model
    # flow; Bearing Studio opens only from the explicit inspector action.
    window.stack.setCurrentWidget(window.rotor_page)
    window.rotor_page._sketch_entity_activated("bearings", 0)
    assert window.stack.currentWidget() is window.rotor_page
    WORKSPACE_SELECTION.clear()


def test_thd_curve_visibility_is_cache_driven_not_native_solver_rerun(qtbot, monkeypatch) -> None:
    WORKSPACE_SELECTION.clear()
    window = RossStudioWindow()
    qtbot.addWidget(window)
    engineering = window.project.engineering
    assert engineering is not None
    spec = engineering.bearings[0]
    original = deepcopy(spec.coefficients)
    spec.metadata["source_model"] = "SqueezeFilmDamper"
    assert original

    def forbidden(*_args, **_kwargs):
        pytest.fail("Opening model-flow THD K/C curves must not rerun a native bearing solver")

    monkeypatch.setattr(window.thd_bearing_service, "calculate", forbidden)
    inspector = window.rotor_page.bearing_node_inspector
    inspector.set_selection(RotorEntityRef("bearings", 0, spec.name, spec.position_mm))
    assert not inspector.curves_button.isHidden()
    # Building the dialog reads only stored points.
    from ross_studio.bearing_node_inspector import THDCoefficientCurvesDialog
    dialog = THDCoefficientCurvesDialog(window.project, 0)
    qtbot.addWidget(dialog)
    assert dialog is not None
    assert spec.coefficients == original
