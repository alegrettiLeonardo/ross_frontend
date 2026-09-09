from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import numpy as np
import pytest

from ross_studio.analysis_backend import RossAnalysisBackend, RossUnbalanceInput
from ross_studio.legacy_import import load_irdin_project
from ross_studio.ump import consistent_lateral_ump_matrix, project_ump_specs


FIXTURE = Path(__file__).parents[1] / "src" / "ross_studio" / "resources" / "OP-W60-500-60Hz-IC611-P3.txt"


def test_consistent_ump_matrix_matches_rigid_translation_energy() -> None:
    length_m = 2.0
    k_per_length = 100.0
    ku = consistent_lateral_ump_matrix(length_m, k_per_length)

    assert ku.shape == (12, 12)
    assert np.allclose(ku, ku.T, rtol=0.0, atol=1e-12)
    assert np.min(np.linalg.eigvalsh(ku)) >= -1e-10

    qx = np.zeros(12)
    qx[[0, 6]] = 1.0
    qy = np.zeros(12)
    qy[[1, 7]] = 1.0

    # q^T K q = integral(k' * u^2 dx) = k' * L for unit rigid translation.
    assert qx @ ku @ qx == pytest.approx(k_per_length * length_m)
    assert qy @ ku @ qy == pytest.approx(k_per_length * length_m)


def test_op_w60_import_exposes_one_physical_ump_span() -> None:
    project = load_irdin_project(FIXTURE)
    specs = project_ump_specs(project)

    assert len(specs) == 1
    spec = specs[0]
    assert spec.start_mm == pytest.approx(918.0)
    assert spec.length_mm == pytest.approx(715.0)
    assert spec.end_mm == pytest.approx(1633.0)
    assert spec.stiffness_per_length_n_m2 == pytest.approx(1.002)
    assert spec.source_unit == "N/m^2"


def test_ump_changes_only_effective_dynamic_stiffness() -> None:
    rs = pytest.importorskip("ross")
    backend = RossAnalysisBackend(rs)

    with_ump = load_irdin_project(FIXTURE)
    without_ump = load_irdin_project(FIXTURE)
    for mass in without_ump.distributed_masses:
        mass.ump_enabled = False
        mass.ump_value = 0.0

    build_on = backend.build_rotor(with_ump, strict=True)
    build_off = backend.build_rotor(without_ump, strict=True)
    assembly = build_on.rotor.ump_assembly

    omega = 3600.0 * 2.0 * np.pi / 60.0
    assert assembly.active
    assert len(assembly.spans) == 1
    assert assembly.spans[0].integrated_stiffness_n_m == pytest.approx(1.002 * 0.715)

    assert np.allclose(build_on.rotor.M(omega), build_off.rotor.M(omega), rtol=1e-12, atol=1e-12)
    assert np.allclose(build_on.rotor.C(omega), build_off.rotor.C(omega), rtol=1e-12, atol=1e-12)
    assert np.allclose(build_on.rotor.G(), build_off.rotor.G(), rtol=1e-12, atol=1e-12)
    assert np.allclose(
        build_off.rotor.K(omega) - build_on.rotor.K(omega),
        assembly.matrix_n_m,
        rtol=1e-10,
        atol=1e-8,
    )


def test_ump_is_excluded_from_gravity_static_solution() -> None:
    rs = pytest.importorskip("ross")
    backend = RossAnalysisBackend(rs)

    with_ump = load_irdin_project(FIXTURE)
    without_ump = load_irdin_project(FIXTURE)
    for mass in without_ump.distributed_masses:
        mass.ump_enabled = False
        mass.ump_value = 0.0

    static_on = backend.run_static_build(backend.build_rotor(with_ump, strict=True))
    static_off = backend.run_static_build(backend.build_rotor(without_ump, strict=True))
    assert np.allclose(static_on.deformation, static_off.deformation, rtol=1e-12, atol=1e-12)


def test_ump_participates_in_real_harmonic_response() -> None:
    rs = pytest.importorskip("ross")
    backend = RossAnalysisBackend(rs)

    baseline = load_irdin_project(FIXTURE)
    excited = deepcopy(baseline)
    for mass in baseline.distributed_masses:
        mass.ump_enabled = False
        mass.ump_value = 0.0
    # Deliberately amplified synthetic coefficient so this test proves numerical
    # participation rather than relying on the tiny legacy OP-W60 value 1.002.
    active = [mass for mass in excited.distributed_masses if mass.ump_enabled]
    assert len(active) == 1
    active[0].ump_value = 1.0e8

    build_0 = backend.build_rotor(baseline, strict=True)
    build_u = backend.build_rotor(excited, strict=True)
    loads = [load for load in baseline.loads if load.kind == "unbalance"]
    inputs_0 = []
    inputs_u = []
    for load in loads:
        node_0 = build_0.node_insertion_plan.node_for(load.position_mm)
        node_u = build_u.node_insertion_plan.node_for(load.position_mm)
        assert node_0 is not None and node_u is not None
        source_unit = str(load.metadata["source_unit"])
        phase = np.deg2rad(load.phase_deg)
        inputs_0.append(RossUnbalanceInput(node_0, load.magnitude, source_unit, phase))
        inputs_u.append(RossUnbalanceInput(node_u, load.magnitude, source_unit, phase))

    response_0 = backend.run_unbalance_build(build_0, inputs_0, [3600.0]).response.forced_resp
    response_u = backend.run_unbalance_build(build_u, inputs_u, [3600.0]).response.forced_resp

    assert np.all(np.isfinite(np.abs(response_u)))
    relative_change = np.linalg.norm(response_u - response_0) / np.linalg.norm(response_0)
    assert relative_change > 1e-4
