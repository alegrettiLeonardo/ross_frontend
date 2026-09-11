from __future__ import annotations

import numpy as np
import pytest

from ross_studio.domain import (
    BearingSpec,
    DiskSpec,
    LoadSpec,
    OperatingCase,
    ProbeSpec,
    RotorProject,
    ShaftSection,
)
from ross_studio.models import ProjectModel
from ross_studio.page_registry import route_spec
from ross_studio.time_frequency_analysis import (
    ClearanceRequest,
    ClearanceService,
    FrequencyResponseRequest,
    FrequencyResponseService,
    HarmonicBalanceRequest,
    HarmonicBalanceService,
    TimeResponseRequest,
    TimeResponseService,
    UCSRequest,
    UCSService,
    UnbalanceResponseRequest,
    UnbalanceResponseService,
)
from ross_studio.time_frequency_native import (
    ClearanceNativeCatalog,
    FREQUENCY_PLOT_LABELS,
    FrequencyResponseNativeCatalog,
    HBM_PLOT_LABELS,
    HarmonicBalanceNativeCatalog,
    TIME_FREQUENCY_NATIVE_OUTPUTS,
    TIME_PLOT_LABELS,
    TimeResponseNativeCatalog,
    UCSNativeCatalog,
    UCS_PLOT_LABELS,
    UNBALANCE_PLOT_LABELS,
    UnbalanceResponseNativeCatalog,
)


def compact_project() -> RotorProject:
    project = RotorProject(
        name="TF-021-compact",
        shaft_sections=[ShaftSection(1, 1000.0, 50.0, fe_elements=4)],
        bearings=[
            BearingSpec(
                "DE", 0.0, kxx=1.0e6, kyy=1.0e6, cxx=500.0, cyy=500.0,
                metadata={"radial_clearance_m": 100e-6},
            ),
            BearingSpec(
                "NDE", 1000.0, kxx=1.0e6, kyy=1.0e6, cxx=500.0, cyy=500.0,
                metadata={"radial_clearance_m": 120e-6},
            ),
        ],
        disks=[DiskSpec("Rotor", 500.0, 8.0, 0.02, 0.04)],
        loads=[
            LoadSpec(
                "U1", "unbalance", 500.0, 100.0, 0.0,
                metadata={"source_unit": "g*mm", "magnitude_unit": "g*mm"},
            )
        ],
        probes=[
            ProbeSpec("PX", 500.0, 1, 0.0),
            ProbeSpec("PY", 500.0, 1, 90.0),
        ],
        operating_cases=[OperatingCase("Qualification", 1200.0, 600.0, 1800.0, 20.0)],
    )
    project.validate()
    return project


@pytest.fixture(scope="module")
def native_suite():
    pytest.importorskip("ross")
    project = compact_project()
    frequency = FrequencyResponseService().run(
        project,
        FrequencyResponseRequest(600.0, 1800.0, 7, 500.0, 1, 500.0, 1),
    )
    unbalance = UnbalanceResponseService().run(project, UnbalanceResponseRequest(600.0, 1800.0, 7))
    time = TimeResponseService().run(
        project,
        TimeResponseRequest(1200.0, 1200.0, duration_s=0.10, samples=81, method="newmark"),
    )
    hbm = HarmonicBalanceService().run(
        project,
        HarmonicBalanceRequest(1200.0, duration_s=0.10, samples=81, n_harmonics=1),
    )
    ucs = UCSService().run(project, UCSRequest(5.0, 8.0, num=4, num_modes=8))
    clearance = ClearanceService().run(project, ClearanceRequest(1200.0, band_percent=5.0, points=3))
    return project, frequency, unbalance, time, hbm, ucs, clearance


def _has_traces(figure) -> bool:
    return len(getattr(figure, "data", ())) > 0


def test_time_frequency_route_is_operational_021() -> None:
    spec = route_spec("analysis.time_frequency")
    assert spec.operational is True
    assert spec.implementation_phase == "0.21.0"


def test_native_output_inventory_tracks_all_ross_230_tutorial_families() -> None:
    assert set(TIME_FREQUENCY_NATIVE_OUTPUTS) == {
        "frequency_response", "unbalance_response", "time_response",
        "harmonic_balance", "ucs", "clearance",
    }
    assert {"plot", "plot_magnitude", "plot_phase", "plot_polar_bode"} <= set(
        TIME_FREQUENCY_NATIVE_OUTPUTS["frequency_response"]
    )
    assert {
        "plot", "plot_magnitude", "plot_phase", "plot_bode", "plot_polar_bode",
        "plot_deflected_shape", "plot_deflected_shape_2d", "plot_deflected_shape_3d", "plot_bending_moment",
    } <= set(TIME_FREQUENCY_NATIVE_OUTPUTS["unbalance_response"])
    assert {"plot_1d", "plot_2d", "plot_3d", "plot_dfft"} <= set(
        TIME_FREQUENCY_NATIVE_OUTPUTS["time_response"]
    )
    assert {"plot", "plot_deflected_shape", "get_time_response"} <= set(
        TIME_FREQUENCY_NATIVE_OUTPUTS["harmonic_balance"]
    )
    assert {"plot", "plot_mode_2d", "plot_mode_3d"} <= set(TIME_FREQUENCY_NATIVE_OUTPUTS["ucs"])
    assert "plot" in TIME_FREQUENCY_NATIVE_OUTPUTS["clearance"]


def test_frequency_response_exposes_every_native_plot_without_resolve(native_suite) -> None:
    _project, result, *_ = native_suite
    catalog = FrequencyResponseNativeCatalog(result)
    before = dict(result.stage_elapsed_s)
    for key in FREQUENCY_PLOT_LABELS:
        figure = catalog.figure(key, frequency_units="rad/s", amplitude_units="m/N", phase_units="rad")
        assert _has_traces(figure)
        assert catalog.figure(key, frequency_units="rad/s", amplitude_units="m/N", phase_units="rad") is figure
    raw = catalog.raw_arrays()
    assert raw["displacement_frf"].size > 0
    assert raw["velocity_frf"].shape == raw["displacement_frf"].shape
    assert raw["acceleration_frf"].shape == raw["displacement_frf"].shape
    assert result.stage_elapsed_s == before
    assert catalog.scientific_recompute is False


def test_unbalance_exposes_bode_polar_shapes_and_bending_moment(native_suite) -> None:
    _project, _frequency, result, *_ = native_suite
    catalog = UnbalanceResponseNativeCatalog(result)
    before = dict(result.stage_elapsed_s)
    for key in UNBALANCE_PLOT_LABELS:
        figure = catalog.figure(key, speed_rpm=1200.0, frequency_units="rad/s", amplitude_units="m", phase_units="rad")
        assert _has_traces(figure)
    assert not catalog.data_magnitude(frequency_units="rad/s", amplitude_units="m").empty
    assert not catalog.data_phase(frequency_units="rad/s", amplitude_units="m", phase_units="rad").empty
    assert catalog.raw_arrays()["displacement_response"].size > 0
    assert result.stage_elapsed_s == before


def test_time_response_exposes_probe_orbit_3d_and_dfft(native_suite) -> None:
    _project, _fr, _ub, result, *_ = native_suite
    catalog = TimeResponseNativeCatalog(result)
    before = dict(result.stage_elapsed_s)
    node = result.probes[0].node
    for key in TIME_PLOT_LABELS:
        figure = catalog.figure(key, node=node, displacement_units="m", frequency_units="Hz")
        assert _has_traces(figure)
    assert not catalog.data(displacement_units="m", time_units="s").empty
    raw = catalog.raw_arrays()
    assert raw["time_s"].size == result.request.samples
    assert raw["displacement_time"].shape[0] == result.request.samples
    assert result.stage_elapsed_s == before


def test_hbm_exposes_frequency_deflected_and_reconstructed_time_outputs(native_suite) -> None:
    _project, _fr, _ub, _time, result, *_ = native_suite
    catalog = HarmonicBalanceNativeCatalog(result)
    before = dict(result.stage_elapsed_s)
    node = result.probes[0].node
    for key in HBM_PLOT_LABELS:
        figure = catalog.figure(key, node=node, amplitude_units="m", frequency_units="Hz")
        assert _has_traces(figure)
    assert catalog.reconstructed_time() is catalog.reconstructed_time()
    assert not catalog.data(amplitude_units="m", frequency_units="Hz").empty
    assert result.stage_elapsed_s == before


def test_ucs_exposes_map_and_native_critical_mode_shapes_when_available(native_suite) -> None:
    _project, _fr, _ub, _time, _hbm, result, _clearance = native_suite
    catalog = UCSNativeCatalog(result)
    assert _has_traces(catalog.figure("map"))
    if catalog.critical_mode_count:
        assert _has_traces(catalog.figure("mode_2d", critical_mode=0))
        assert _has_traces(catalog.figure("mode_3d", critical_mode=0))
    raw = catalog.raw_arrays()
    assert raw["wn"].size > 0


def test_clearance_uses_explicit_bearing_clearance_and_native_plot(native_suite) -> None:
    _project, _fr, _ub, _time, _hbm, _ucs, result = native_suite
    catalog = ClearanceNativeCatalog(result)
    assert _has_traces(catalog.figure())
    rows = catalog.rows()
    assert len(rows) == 2
    assert [row[2] for row in rows] == pytest.approx([100.0, 120.0])
    assert [row[3] for row in rows] == pytest.approx([75.0, 90.0])
    assert np.all(np.isfinite(catalog.raw_arrays()["magnitudes_um_pkpk"]))


def test_time_frequency_workspace_has_six_independent_analysis_tabs(qtbot) -> None:
    from ross_studio.pages.time_frequency_workspace import TimeFrequencyWorkspacePage

    project = ProjectModel.from_engineering(compact_project())
    page = TimeFrequencyWorkspacePage(project)
    qtbot.addWidget(page)
    assert page.tabs.count() == 6
    assert [page.tabs.tabText(i) for i in range(page.tabs.count())] == [
        "Frequency Response", "Unbalance Response", "Time Response",
        "Harmonic Balance", "UCS Map", "Clearance",
    ]
    assert set(page._buttons) == {"frequency", "unbalance", "time", "hbm", "ucs", "clearance"}
    assert page.fr_output.count() == len(FREQUENCY_PLOT_LABELS)
    assert page.ub_output.count() == len(UNBALANCE_PLOT_LABELS)
    assert page.tr_output.count() == len(TIME_PLOT_LABELS)
    assert page.hb_output.count() == len(HBM_PLOT_LABELS)
    assert page.ucs_output.count() == len(UCS_PLOT_LABELS)
