from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from ross_studio.domain import BearingSpec, DiskSpec, OperatingCase, RotorProject, ShaftSection
from ross_studio.models import ProjectModel
from ross_studio.page_registry import route_spec
from ross_studio.stochastic_analysis import (
    RandomInputSpec,
    StochasticCampbellRequest,
    StochasticFrequencyRequest,
    StochasticRotorService,
    StochasticSamplingConfig,
    StochasticTimeRequest,
    StochasticUnbalanceRequest,
    StochasticVariableSpec,
)
from ross_studio.stochastic_native import (
    STOCHASTIC_NATIVE_OUTPUTS,
    STOCHASTIC_PLOT_LABELS,
    StochasticCampbellCatalog,
    StochasticFrequencyCatalog,
    StochasticInputCatalog,
    StochasticTimeCatalog,
    StochasticUnbalanceCatalog,
)


def compact_project() -> RotorProject:
    project = RotorProject(
        name="ST-022-compact",
        shaft_sections=[ShaftSection(1, 1000.0, 50.0, fe_elements=4)],
        bearings=[
            BearingSpec("DE", 0.0, kxx=1.0e6, kyy=1.0e6, cxx=500.0, cyy=500.0),
            BearingSpec("NDE", 1000.0, kxx=1.0e6, kyy=1.0e6, cxx=500.0, cyy=500.0),
        ],
        disks=[DiskSpec("Rotor", 500.0, 8.0, 0.02, 0.04)],
        operating_cases=[OperatingCase("Qualification", 1200.0, 600.0, 1800.0, 20.0)],
    )
    project.validate()
    return project


def sampling() -> StochasticSamplingConfig:
    return StochasticSamplingConfig(
        samples=3,
        seed=22022,
        variables=(
            StochasticVariableSpec(
                "bearing", 0, "kxx", RandomInputSpec("normal", "relative", 0.0, 2.0)
            ),
            StochasticVariableSpec(
                "disk", 0, "m", RandomInputSpec("uniform", "relative", -1.0, 1.0)
            ),
        ),
    )


@pytest.fixture(scope="module")
def stochastic_suite():
    pytest.importorskip("ross")
    project = compact_project()
    service = StochasticRotorService()
    cfg = sampling()
    campbell = service.run_campbell(project, cfg, StochasticCampbellRequest(600.0, 1200.0, 3, 4))
    frequency = service.run_frequency_response(
        project, cfg, StochasticFrequencyRequest(600.0, 1200.0, 5, 2, 1, 2, 1)
    )
    unbalance = service.run_unbalance_response(
        project,
        cfg,
        StochasticUnbalanceRequest(
            600.0, 1200.0, 5, 2, 1.0e-4, 0.0,
            magnitude_random=RandomInputSpec("uniform", "relative", -2.0, 2.0),
        ),
    )
    time = service.run_time_response(
        project,
        cfg,
        StochasticTimeRequest(
            1200.0, 0.05, 24, 2, 10.0, 2.0,
            force_random=RandomInputSpec("normal", "relative", 0.0, 2.0),
        ),
    )
    return project, cfg, campbell, frequency, unbalance, time


def _has_traces(figure) -> bool:
    return len(getattr(figure, "data", ())) > 0


def test_stochastic_route_is_operational_022() -> None:
    spec = route_spec("analysis.stochastic")
    assert spec.operational is True
    assert spec.implementation_phase == "0.22.0"


def test_stochastic_inventory_covers_native_ross_230_results_and_input_histograms() -> None:
    assert set(STOCHASTIC_NATIVE_OUTPUTS) == {
        "random_variables", "campbell", "frequency_response", "unbalance_response", "time_response"
    }
    assert {"plot", "plot_nat_freq", "plot_log_dec", "wd", "log_dec", "mode_type"} <= set(
        STOCHASTIC_NATIVE_OUTPUTS["campbell"]
    )
    assert {"plot", "plot_magnitude", "plot_phase", "plot_polar_bode", "freq_resp", "velc_resp", "accl_resp"} <= set(
        STOCHASTIC_NATIVE_OUTPUTS["frequency_response"]
    )
    assert {"plot", "plot_magnitude", "plot_phase", "plot_polar_bode", "forced_resp"} <= set(
        STOCHASTIC_NATIVE_OUTPUTS["unbalance_response"]
    )
    assert {"plot_1d", "plot_2d", "plot_3d", "yout", "xout"} <= set(
        STOCHASTIC_NATIVE_OUTPUTS["time_response"]
    )
    assert all("plot_random_var" in item for item in STOCHASTIC_NATIVE_OUTPUTS["random_variables"][:5])


def test_sampling_is_reproducible_and_uses_native_st_rotor() -> None:
    import ross.stochastic as srs

    project = compact_project()
    service = StochasticRotorService()
    first = service.build(project, sampling())
    second = service.build(project, sampling())
    assert isinstance(first.stochastic_rotor, srs.ST_Rotor)
    assert first.sample_count == 3
    assert second.sample_count == 3
    assert first.sampled_values.keys() == second.sampled_values.keys()
    for key in first.sampled_values:
        np.testing.assert_allclose(first.sampled_values[key], second.sampled_values[key])
    assert any(wrapper.native.__class__.__name__ == "ST_BearingElement" for wrapper in first.input_wrappers)
    assert any(wrapper.native.__class__.__name__ == "ST_DiskElement" for wrapper in first.input_wrappers)


def test_target_inventory_exposes_material_shaft_disk_and_bearing_without_synthetic_mc() -> None:
    targets = StochasticRotorService().available_targets(compact_project())
    families = {target.family for target in targets if target.randomizable}
    assert {"material", "shaft", "disk", "bearing"} <= families
    shaft_parameters = {target.parameter for target in targets if target.family == "shaft"}
    assert {"L", "idl", "odl", "idr", "odr"} <= shaft_parameters
    bearing_parameters = {target.parameter for target in targets if target.family == "bearing"}
    assert {"kxx", "kxy", "kyx", "kyy", "cxx", "cxy", "cyx", "cyy"} <= bearing_parameters


def test_native_input_histograms_are_retained(stochastic_suite) -> None:
    _project, _cfg, campbell, *_ = stochastic_suite
    catalog = StochasticInputCatalog(campbell.build)
    assert catalog.wrappers
    plottable = [i for i, wrapper in enumerate(catalog.wrappers) if [v for v in wrapper.variables if v != "material"]]
    assert plottable
    figure = catalog.figure(plottable[0])
    assert _has_traces(figure)
    assert catalog.sample_arrays


def test_campbell_exposes_combined_nat_freq_logdec_mean_percentile_confidence(stochastic_suite) -> None:
    _project, _cfg, result, *_ = stochastic_suite
    catalog = StochasticCampbellCatalog(result)
    before = dict(result.stage_elapsed_s)
    for key in STOCHASTIC_PLOT_LABELS["campbell"]:
        fig = catalog.figure(key, percentile=[5, 50, 95], conf_interval=[90], harmonics=[0.5, 1.0])
        assert _has_traces(fig)
    raw = catalog.raw_arrays()
    assert raw["natural_frequency_rad_s"].shape[-1] == result.build.sample_count
    assert raw["logarithmic_decrement"].shape == raw["natural_frequency_rad_s"].shape
    assert result.stage_elapsed_s == before
    assert catalog.scientific_recompute is False


def test_frequency_response_exposes_all_native_plot_families_and_three_response_quantities(stochastic_suite) -> None:
    _project, _cfg, _camp, result, *_ = stochastic_suite
    catalog = StochasticFrequencyCatalog(result)
    before = dict(result.stage_elapsed_s)
    for units in ("m/N", "m/s/N", "m/s**2/N"):
        for key in STOCHASTIC_PLOT_LABELS["frequency_response"]:
            assert _has_traces(catalog.figure(key, percentile=[50], conf_interval=[90], amplitude_units=units))
    raw = catalog.raw_arrays()
    assert raw["displacement_frf"].shape[-1] == result.build.sample_count
    assert raw["velocity_frf"].shape == raw["displacement_frf"].shape
    assert raw["acceleration_frf"].shape == raw["displacement_frf"].shape
    assert result.stage_elapsed_s == before


def test_unbalance_exposes_random_excitation_and_native_mean_percentile_confidence_plots(stochastic_suite) -> None:
    _project, _cfg, _camp, _fr, result, _time = stochastic_suite
    catalog = StochasticUnbalanceCatalog(result)
    for key in STOCHASTIC_PLOT_LABELS["unbalance_response"]:
        assert _has_traces(catalog.figure(key, percentile=[5, 50, 95], conf_interval=[90]))
    raw = catalog.raw_arrays()
    assert raw["displacement_response"].shape[0] == result.build.sample_count
    assert raw["velocity_response"].shape == raw["displacement_response"].shape
    assert raw["acceleration_response"].shape == raw["displacement_response"].shape


def test_time_response_exposes_native_1d_orbit_2d_and_all_node_3d(stochastic_suite) -> None:
    _project, _cfg, _camp, _fr, _ub, result = stochastic_suite
    catalog = StochasticTimeCatalog(result)
    for key in STOCHASTIC_PLOT_LABELS["time_response"]:
        assert _has_traces(catalog.figure(key, percentile=[50], conf_interval=[90]))
    raw = catalog.raw_arrays()
    assert raw["displacement_time"].shape[0] == result.build.sample_count
    assert raw["state_time"].shape[0] == result.build.sample_count
    assert raw["time_s"].size == result.request.points


def test_native_result_save_and_load_contract_is_exposed(stochastic_suite, tmp_path: Path) -> None:
    _project, _cfg, result, *_ = stochastic_suite
    catalog = StochasticCampbellCatalog(result)
    target = catalog.export_native_result(tmp_path / "campbell.json")
    assert target.is_file() and target.stat().st_size > 0


def test_stochastic_workspace_has_five_native_tabs(qtbot) -> None:
    from ross_studio.pages.stochastic_workspace import StochasticWorkspacePage

    page = StochasticWorkspacePage(ProjectModel.from_engineering(compact_project()))
    qtbot.addWidget(page)
    assert page.tabs.count() == 5
    assert [page.tabs.tabText(i) for i in range(page.tabs.count())] == [
        "Random Variables", "Campbell", "Frequency Response", "Unbalance Response", "Time Response"
    ]
    assert page.target_combo.count() > 0
    assert page.camp_output.count() == len(STOCHASTIC_PLOT_LABELS["campbell"])
    assert page.fr_output.count() == len(STOCHASTIC_PLOT_LABELS["frequency_response"])
    assert page.ub_output.count() == len(STOCHASTIC_PLOT_LABELS["unbalance_response"])
    assert page.tr_output.count() == len(STOCHASTIC_PLOT_LABELS["time_response"])


def test_all_random_variables_must_have_same_size_and_at_least_one_structural_st_variable() -> None:
    with pytest.raises(EngineeringError, match="At least one structural ST_\\*"):
        StochasticSamplingConfig(samples=3, seed=1, variables=()).validate()
