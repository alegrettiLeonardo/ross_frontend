from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from ross_studio.analysis_pipeline import AnalysisPipelineService, AnalysisPolicy
from ross_studio.domain import LoadSpec, ProbeSpec
from ross_studio.legacy_import import load_irdin_project


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
    # node 1: x=1+2j and y=3+4j over one speed station.
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


def test_unbalance_unit_adapter_is_explicit() -> None:
    assert AnalysisPipelineService._unbalance_kg_m(
        LoadSpec("u", "unbalance", 0.0, 1000.0, metadata={"magnitude_unit": "g*mm"})
    ) == pytest.approx(1e-3)
    assert AnalysisPipelineService._unbalance_kg_m(
        LoadSpec("u", "unbalance", 0.0, 2.5, metadata={"magnitude_unit": "kg*m"})
    ) == pytest.approx(2.5)


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
    # Linear crossing between 100 and 200 rad/s: (wd-speed) changes +50 -> -10.
    expected = (100.0 + (50.0 / 60.0) * 100.0) * 60.0 / (2.0 * np.pi)
    assert rows[0].speed_rpm == pytest.approx(expected)
    assert rows[0].whirl == "Forward"
