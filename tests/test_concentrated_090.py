from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import numpy as np
import pytest

from ross_studio.analysis_backend import RossAnalysisBackend
from ross_studio.concentrated import concentrated_disk_class
from ross_studio.legacy_import import load_irdin_project


FIXTURE = Path(__file__).parents[1] / "src" / "ross_studio" / "resources" / "OP-W60-500-60Hz-IC611-P3.txt"


def test_concentrated_element_exact_native_M_and_G() -> None:
    rs = pytest.importorskip("ross")
    cls = concentrated_disk_class(rs)
    element = cls(
        n=7,
        m=34.0,
        ix_kg_m2=1.25,
        iy_kg_m2=2.50,
        iz_kg_m2=3.75,
        tag="synthetic concent",
    )

    expected_M = np.diag([34.0, 34.0, 34.0, 1.25, 3.75, 2.50])
    expected_G = np.zeros((6, 6))
    expected_G[3, 4] = 2.50
    expected_G[4, 3] = -2.50

    assert np.array_equal(element.M(), expected_M)
    assert np.array_equal(element.G(), expected_G)
    assert element.Ip == pytest.approx(2.50)


def test_legacy_concent_parser_maps_mass_ix_iy_iz_columns(tmp_path: Path) -> None:
    source = FIXTURE.read_text(encoding="utf-8")
    original = "[Concent]\n1,0=105\n1,1=34\n1,2=0\n1,3=0\n1,4=0"
    replacement = "[Concent]\n1,0=105\n1,1=34\n1,2=1.25\n1,3=2.5\n1,4=3.75"
    assert original in source
    case = tmp_path / "concent_nonzero.txt"
    case.write_text(source.replace(original, replacement), encoding="utf-8")

    project = load_irdin_project(case)
    spec = project.point_masses[0]
    assert spec.position_mm == pytest.approx(105.0)
    assert spec.mass_kg == pytest.approx(34.0)
    assert spec.ix_kg_m2 == pytest.approx(1.25)
    assert spec.iy_kg_m2 == pytest.approx(2.50)
    assert spec.iz_kg_m2 == pytest.approx(3.75)


def test_rotordin_positive_concent_adds_exact_global_M_and_G_terms() -> None:
    rs = pytest.importorskip("ross")
    backend = RossAnalysisBackend(rs)

    baseline = load_irdin_project(FIXTURE)
    modified = deepcopy(baseline)
    spec = modified.point_masses[0]
    spec.ix_kg_m2 = 1.25
    spec.iy_kg_m2 = 2.50
    spec.iz_kg_m2 = 3.75

    build_0 = backend.build_rotor(baseline, strict=True)
    build_1 = backend.build_rotor(modified, strict=True)
    node = build_1.node_insertion_plan.node_for(spec.position_mm)
    assert node is not None
    ndof = int(build_1.rotor.number_dof)
    assert ndof == 6

    omega = 3600.0 * 2.0 * np.pi / 60.0
    delta_M = np.asarray(build_1.rotor.M(omega)) - np.asarray(build_0.rotor.M(omega))
    delta_G = np.asarray(build_1.rotor.G()) - np.asarray(build_0.rotor.G())
    expected_M = np.zeros_like(delta_M)
    expected_G = np.zeros_like(delta_G)
    alpha = node * ndof + 3
    beta = node * ndof + 4
    theta = node * ndof + 5
    expected_M[alpha, alpha] = 1.25
    expected_M[beta, beta] = 3.75
    expected_M[theta, theta] = 2.50

    # Native ROSS DiskElement has +Iy at (alpha,beta), -Iy at (beta,alpha).
    # The imported RotorDin-positive convention flips the complete rotor G matrix,
    # reproducing matrizes.f: mg(phi,theta)=-Iy; mg(theta,phi)=+Iy.
    expected_G[alpha, beta] = -2.50
    expected_G[beta, alpha] = 2.50

    assert np.allclose(delta_M, expected_M, rtol=0.0, atol=1e-12)
    assert np.allclose(delta_G, expected_G, rtol=0.0, atol=1e-12)
    assert np.allclose(build_1.rotor.C(omega), build_0.rotor.C(omega), rtol=0.0, atol=1e-12)
    assert np.allclose(build_1.rotor.K(omega), build_0.rotor.K(omega), rtol=0.0, atol=1e-12)


def test_concent_inertias_do_not_change_gravity_static_when_mass_is_unchanged() -> None:
    rs = pytest.importorskip("ross")
    backend = RossAnalysisBackend(rs)

    baseline = load_irdin_project(FIXTURE)
    modified = deepcopy(baseline)
    modified.point_masses[0].ix_kg_m2 = 1.25
    modified.point_masses[0].iy_kg_m2 = 2.50
    modified.point_masses[0].iz_kg_m2 = 3.75

    static_0 = backend.run_static_build(backend.build_rotor(baseline, strict=True))
    static_1 = backend.run_static_build(backend.build_rotor(modified, strict=True))
    assert np.allclose(static_1.deformation, static_0.deformation, rtol=0.0, atol=1e-12)
