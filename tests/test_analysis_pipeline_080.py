from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from ross_studio.analysis_backend import RossAnalysisBackend, RossUnbalanceInput
from ross_studio.analysis_pipeline import AnalysisPipelineService, AnalysisPolicy
from ross_studio.domain import ProbeSpec
from ross_studio.legacy_import import load_irdin_project
from ross_studio.ross_compat import _init_orbit_symmetric


FIXTURE = Path(__file__).parents[1] / "src" / "ross_studio" / "resources" / "OP-W60-500-60Hz-IC611-P3.txt"


def test_dynamic_envelope_respects_imported_bearing_kc_tables() -> None:
    project = load_irdin_project(FIXTURE)
    low, high, audits = AnalysisPipelineService._bearing_envelope_rpm(project)
    assert low == pytest.approx(900.0)
    assert high == pytest.approx(4500.0)
    assert any(audit.code == "BEARING_KC_ENVELOPE" for audit in audits)


def test_speed_grid_contains_rated_speed_exactly() -> None:
    grid = AnalysisPipelineService._speed_grid(900.0, 4500.0, 8, 3600.0)
    assert grid[0] == pytest.approx(900.0)
    assert grid[-1] == pytest.approx(4500.0)
    assert np.count_nonzero(np.isclose(grid, 3600.0)) == 1


def test_legacy_probe_projection_matches_rotordin_vrotate_semantics() -> None:
    rotor = SimpleNamespace(number_dof=6)
    forced = np.zeros((12, 1), dtype=complex)
    forced[6, 0] = 1.0 + 2.0j
    forced[7, 0] = 3.0 + 4.0j
    response = SimpleNamespace(forced_resp=forced)

    c1 = ProbeSpec("P1", position_mm=0.0, coordinate=1, orientation_deg=45.0)
    c2 = ProbeSpec("P2", position_mm=0.0, coordinate=2, orientation_deg=45.0)
    r1 = AnalysisPipelineService._project_probe(response, rotor, 1, c1)[0]
    r2 = AnalysisPipelineService._project_probe(response, rotor, 1, c2)[0]

    root2 = np.sqrt(2.0)
    assert r1 == pytest.approx((4.0 + 6.0j) / root2)
    assert r2 == pytest.approx((2.0 + 2.0j) / root2)


def test_legacy_import_preserves_raw_desbal_as_g_mm() -> None:
    project = load_irdin_project(FIXTURE)
    loads = [load for load in project.loads if load.kind == "unbalance"]
    assert len(loads) == 2
    assert [load.magnitude for load in loads] == pytest.approx([4581.2, 4581.2])
    assert all(load.metadata["magnitude_unit"] == "g*mm" for load in loads)
    assert all(load.metadata["source_unit"] == "g*mm" for load in loads)


def test_unbalance_is_normalized_only_inside_ross_execution_boundary() -> None:
    class CaptureRotor:
        def __init__(self) -> None:
            self.call = None

        def run_unbalance_response(self, **kwargs):
            self.call = kwargs
            return SimpleNamespace(forced_resp=np.zeros((1, len(kwargs["frequency"])), dtype=complex))

    rotor = CaptureRotor()
    build = SimpleNamespace(rotor=rotor)
    raw = [
        RossUnbalanceInput(node=7, raw_magnitude=4581.2, source_unit="g*mm", phase_rad=0.0),
        RossUnbalanceInput(node=12, raw_magnitude=4581.2, source_unit="g*mm", phase_rad=0.0),
    ]

    run = RossAnalysisBackend.run_unbalance_build(build, raw, [3600.0])

    assert rotor.call is not None
    assert rotor.call["node"] == [7, 12]
    assert rotor.call["unbalance_magnitude"] == pytest.approx([0.0045812, 0.0045812])
    assert rotor.call["unbalance_phase"] == pytest.approx([0.0, 0.0])
    assert rotor.call["frequency"][0] == pytest.approx(2.0 * np.pi * 60.0)
    assert [item.raw_magnitude for item in run.applied_inputs] == pytest.approx([4581.2, 4581.2])
    assert [item.source_unit for item in run.applied_inputs] == ["g*mm", "g*mm"]
    assert [item.magnitude_kg_m for item in run.applied_inputs] == pytest.approx([0.0045812, 0.0045812])


def test_unbalance_boundary_rejects_unknown_units() -> None:
    with pytest.raises(Exception, match="Unsupported unbalance unit"):
        RossAnalysisBackend._normalize_unbalance_kg_m(1.0, "mystery")


def test_critical_speed_extraction_uses_synchronous_crossing() -> None:
    speed = np.array([100.0, 200.0, 300.0])
    campbell = SimpleNamespace(
        speed_range=speed,
        wd=np.array([[150.0], [190.0], [250.0]]),
        damping_ratio=np.array([[0.01], [0.02], [0.03]]),
        log_dec=np.array([[0.06], [0.12], [0.18]]),
        whirl_values=np.zeros((3, 1)),
    )
    service = AnalysisPipelineService(backend=object(), policy=AnalysisPolicy(critical_dedup_rpm=1.0))
    rows = service._critical_from_campbell(campbell)
    assert len(rows) == 1
    assert rows[0].mode == 1
    expected = (100.0 + (50.0 / 60.0) * 100.0) * 60.0 / (2.0 * np.pi)
    assert rows[0].speed_rpm == pytest.approx(expected)
    assert rows[0].whirl == "Forward"


def test_ross_230_orbit_shim_handles_complex_mode_components_with_real_symmetric_axes() -> None:
    values = _init_orbit_symmetric(1.0 + 2.0j, 3.0 + 4.0j)
    major_index = values[7]
    minor_axis = values[10]
    major_axis = values[11]
    kappa = values[12]

    assert major_index in (0, 1)
    assert np.isfinite(minor_axis)
    assert np.isfinite(major_axis)
    assert np.isfinite(kappa)
    assert major_axis >= minor_axis >= 0.0
    assert abs(kappa) <= 1.0
