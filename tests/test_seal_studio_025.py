from __future__ import annotations

import json
from copy import deepcopy
from math import pi
from pathlib import Path

import numpy as np
import pytest

from ross_studio.domain import EngineeringError, SealSpec
from ross_studio.model_builder_service import RotorModelMutationService
from ross_studio.models import load_reference_project_model
from ross_studio.project_io import SCHEMA_VERSION, load_project, save_project
from ross_studio.ross_backend import RossModelBuilder
from ross_studio.seal_models import (
    HolePatternSealSpec,
    HybridSealSpec,
    LabyrinthSealSpec,
    SealCoefficientPoint,
    SealModel,
    seal_model,
)


def _engineering():
    model = load_reference_project_model()
    assert model.engineering is not None
    return model, model.engineering


def _manual_labyrinth(position_mm: float) -> LabyrinthSealSpec:
    return LabyrinthSealSpec(
        name="Labyrinth qualified table",
        position_mm=position_mm,
        kxx=0.0,
        kyy=0.0,
        cxx=0.0,
        cyy=0.0,
        frequency_rpm=[5000.0, 8000.0],
        calculated_coefficients=[
            SealCoefficientPoint(5000.0, 1.0e6, 2.0e5, -2.0e5, 1.1e6, 2.0e3, 30.0, -30.0, 2.2e3, 3.0, 0.2, -0.2, 3.1),
            SealCoefficientPoint(8000.0, 1.4e6, 2.8e5, -2.8e5, 1.5e6, 2.5e3, 40.0, -40.0, 2.7e3, 3.5, 0.3, -0.3, 3.6),
        ],
        calculation={"ross_class": "LabyrinthSeal", "leakage_kg_s": [0.01, 0.012]},
    )


def test_schema_3_is_seal_studio_schema() -> None:
    assert SCHEMA_VERSION == 3


def test_direct_seal_remains_backward_compatible_native_seal_element() -> None:
    rs = pytest.importorskip("ross")
    _, project = _engineering()
    position = project.bearings[0].position_mm
    direct = SealSpec(
        "Direct seal",
        position,
        1.0e6,
        1.2e6,
        2.0e3,
        2.2e3,
        1.0e5,
        -1.0e5,
        50.0,
        -50.0,
    )
    project.seals.append(direct)
    rotor = RossModelBuilder(rs).build(project, strict=True).rotor
    element = next(item for item in rotor.bearing_elements if item.tag == direct.name)
    assert type(element).__name__ == "SealElement"
    np.testing.assert_allclose(
        element.K(0.0)[:2, :2],
        np.asarray([[1.0e6, 1.0e5], [-1.0e5, 1.2e6]]),
    )
    np.testing.assert_allclose(
        element.C(0.0)[:2, :2],
        np.asarray([[2.0e3, 50.0], [-50.0, 2.2e3]]),
    )


def test_advanced_seal_uses_persisted_native_kcm_table_without_rerunning_flow_solver() -> None:
    rs = pytest.importorskip("ross")
    _, project = _engineering()
    spec = _manual_labyrinth(project.bearings[0].position_mm)
    project.seals.append(spec)
    rotor = RossModelBuilder(rs).build(project, strict=True).rotor
    element = next(item for item in rotor.bearing_elements if item.tag == spec.name)
    assert type(element).__name__ == "SealElement"
    omega = 5000.0 * 2.0 * pi / 60.0
    row = spec.calculated_coefficients[0]
    np.testing.assert_allclose(
        element.K(omega)[:2, :2],
        np.asarray([[row.kxx, row.kxy], [row.kyx, row.kyy]]),
    )
    np.testing.assert_allclose(
        element.C(omega)[:2, :2],
        np.asarray([[row.cxx, row.cxy], [row.cyx, row.cyy]]),
    )
    np.testing.assert_allclose(
        element.M(omega)[:2, :2],
        np.asarray([[row.mxx, row.mxy], [row.myx, row.myy]]),
    )


def test_advanced_seal_without_calculate_fails_closed() -> None:
    rs = pytest.importorskip("ross")
    _, project = _engineering()
    spec = LabyrinthSealSpec(
        name="Uncalculated",
        position_mm=project.bearings[0].position_mm,
        kxx=0.0,
        kyy=0.0,
        cxx=0.0,
        cyy=0.0,
        frequency_rpm=[5000.0],
    )
    project.seals.append(spec)
    with pytest.raises(EngineeringError, match="Calculate -> Preview -> Apply"):
        RossModelBuilder(rs).build(project, strict=True)


def test_transaction_service_accepts_advanced_seal_subclasses() -> None:
    rs = pytest.importorskip("ross")
    _, project = _engineering()
    service = RotorModelMutationService(rs)
    spec = _manual_labyrinth(project.bearings[0].position_mm)
    preview = service.preview_add(project, "seal", spec)
    audit = service.commit(project, preview)
    assert audit.entity_kind == "seal"
    assert project.seals[-1] == spec
    assert seal_model(project.seals[-1]) == SealModel.LABYRINTH


def test_advanced_seal_roundtrip_preserves_model_inputs_outputs_and_coefficients(tmp_path: Path) -> None:
    model, project = _engineering()
    spec = _manual_labyrinth(project.bearings[0].position_mm)
    project.seals.append(spec)
    target = save_project(model, tmp_path / "seal-native.rossproj")
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 3
    assert payload["app_version"] == "0.25.0"
    assert payload["engineering"]["seals"][-1]["model_type"] == SealModel.LABYRINTH.value

    restored = load_project(target)
    assert restored.engineering is not None
    restored_spec = restored.engineering.seals[-1]
    assert isinstance(restored_spec, LabyrinthSealSpec)
    assert restored_spec.frequency_rpm == [5000.0, 8000.0]
    assert restored_spec.calculated_coefficients == spec.calculated_coefficients
    assert restored_spec.calculation == spec.calculation


def test_schema2_direct_seal_migrates_without_inventing_advanced_origin(tmp_path: Path) -> None:
    model, project = _engineering()
    direct = SealSpec("Legacy direct", project.bearings[0].position_mm, 1.0e6, 1.1e6, 1.0e3, 1.1e3)
    project.seals.append(direct)
    target = save_project(model, tmp_path / "current.rossproj")
    payload = json.loads(target.read_text(encoding="utf-8"))
    payload["schema_version"] = 2
    payload["app_version"] = "0.24.0"
    legacy = tmp_path / "schema2.rossproj"
    legacy.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    restored = load_project(legacy)
    assert restored.engineering is not None
    restored_direct = restored.engineering.seals[-1]
    assert type(restored_direct) is SealSpec
    assert restored_direct == direct


def test_model_tags_cover_all_ross_native_seal_families() -> None:
    _, project = _engineering()
    position = project.bearings[0].position_mm
    common = dict(name="x", position_mm=position, kxx=0.0, kyy=0.0, cxx=0.0, cyy=0.0)
    assert seal_model(SealSpec("d", position, 0.0, 0.0, 0.0, 0.0)) == SealModel.DIRECT
    assert seal_model(LabyrinthSealSpec(**common)) == SealModel.LABYRINTH
    assert seal_model(HolePatternSealSpec(**common)) == SealModel.HOLE_PATTERN
    assert seal_model(HybridSealSpec(**common)) == SealModel.HYBRID
