from __future__ import annotations

from plotly import graph_objects as go
from PySide6.QtCore import Qt

from ross_studio.app import RossStudioWindow
from ross_studio.bearing_native_inventory import inventory_native_outputs
from ross_studio.bearing_parity import BearingAnalysisFormulation, BearingCoordinateConvention
from ross_studio.plotly_native_view import NativeRossFigureView


class _NativeFixture:
    def plot(self):
        return go.Figure()

    def plot_results(self, show_plots=False, freq_index=0):
        return {}

    def plot_bearing_representation(self):
        return go.Figure()

    def plot_pressure_distribution(self):
        return go.Figure()

    def show_results(self):
        return None

    def show_coefficients_comparison(self):
        return None

    def show_execution_time(self):
        return None

    def show_optimization_convergence(self, by="value", show_plots=False):
        return None


def test_native_output_inventory_covers_adapter_contract():
    inventory = inventory_native_outputs(_NativeFixture())
    assert inventory.fully_covered
    assert not inventory.uncovered
    assert {method.name for method in inventory.methods} == {
        "plot",
        "plot_results",
        "plot_bearing_representation",
        "plot_pressure_distribution",
        "show_results",
        "show_coefficients_comparison",
        "show_execution_time",
        "show_optimization_convergence",
    }


def test_headless_native_plot_retains_ross_figure_without_webengine(qtbot, monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    view = NativeRossFigureView()
    qtbot.addWidget(view)
    figure = go.Figure(go.Scatter(x=[0, 1], y=[1, 2]))
    assert view.set_figure(figure)
    assert view.figure is figure
    assert not view.webengine_active


def test_plain_and_tilting_default_to_executable_thd_contract_without_timer_race(qtbot):
    window = RossStudioWindow()
    qtbot.addWidget(window)
    window.show()
    window._open_bearing_group("THD")

    assert window.bearing_page.analysis_formulation.currentData() == BearingAnalysisFormulation.DIMENSIONAL_HEAT_BALANCE.value
    assert window.bearing_page.coordinate_convention.currentData() == BearingCoordinateConvention.STANDARD_XY.value

    for model in ("PlainJournal", "TiltingPad"):
        key = window._bearing_key_for_class(window.bearing_page, model)
        qtbot.mouseClick(window.bearing_page.type_buttons[key], Qt.MouseButton.LeftButton)
        # Do not process an extra event-loop turn here. This is the regression gate:
        # Calculate must be valid immediately after the model click.
        values = window.bearing_page.input_values()
        assert values["studio_analysis_formulation"] == BearingAnalysisFormulation.DIMENSIONAL_HEAT_BALANCE.value
        assert values["studio_coordinate_convention"] == BearingCoordinateConvention.STANDARD_XY.value

    window.close()
