from __future__ import annotations

from copy import deepcopy

import pytest

from ross_studio.domain import SealSpec
from ross_studio.model_builder_service import RotorModelMutationService
from ross_studio.models import load_reference_project_model
from ross_studio.page_registry import route_spec
from ross_studio.seal_models import LabyrinthSealSpec, SealCoefficientPoint, SealModel
from ross_studio.seal_studio import SealStudioService


def test_seal_route_is_release_locked_until_frozen_gates_close() -> None:
    spec = route_spec("model.seals")
    assert spec.owner == "seal"
    assert spec.implementation_phase == "0.25.0"
    assert spec.operational is False


def test_seal_editor_exposes_only_native_ross_families(qtbot) -> None:
    pytest.importorskip("ross")
    from ross_studio.pages.seal_workspace import SealStudioEditorDialog

    model = load_reference_project_model()
    dialog = SealStudioEditorDialog(model)
    qtbot.addWidget(dialog)
    assert [dialog.model.itemData(index) for index in range(dialog.model.count())] == [
        SealModel.DIRECT,
        SealModel.LABYRINTH,
        SealModel.HOLE_PATTERN,
        SealModel.HYBRID,
    ]
    assert dialog.apply_button.isEnabled() is False
    dialog.model.setCurrentIndex(dialog.model.findData(SealModel.DIRECT))
    record = dialog.record()
    assert type(record) is SealSpec


def test_direct_calculate_uses_prospective_exact_node_not_nearest_node() -> None:
    rs = pytest.importorskip("ross")
    model = load_reference_project_model()
    assert model.engineering is not None
    project = model.engineering
    x = project.total_length_mm * 0.417321
    assert all(abs(existing - x) > 1e-7 for existing in project.topology_split_positions_mm())
    source = SealSpec("Prospective direct", x, 1e6, 1e6, 1e3, 1e3)
    preview = SealStudioService(rs).calculate(project, source)
    candidate = deepcopy(project)
    candidate.seals.append(source)
    assert preview.node == RotorModelMutationService(rs).builder.map_position(candidate, x).node
    assert preview.node is not None


def test_strict_replace_allows_deliberate_direct_to_advanced_family_change() -> None:
    rs = pytest.importorskip("ross")
    model = load_reference_project_model()
    assert model.engineering is not None
    project = model.engineering
    x = project.bearings[0].position_mm
    project.seals.append(SealSpec("Replace me", x, 1e6, 1e6, 1e3, 1e3))
    advanced = LabyrinthSealSpec(
        "Advanced replacement",
        x,
        0.0,
        0.0,
        0.0,
        0.0,
        frequency_rpm=[5000.0],
        calculated_coefficients=[
            SealCoefficientPoint(5000.0, 1e6, 1e5, -1e5, 1.1e6, 2e3, 20.0, -20.0, 2.1e3),
        ],
        calculation={"ross_class": "LabyrinthSeal"},
    )
    service = RotorModelMutationService(rs)
    preview = service.preview_replace(project, "seal", 0, advanced)
    audit = service.commit(project, preview)
    assert audit.operation == "replace"
    assert isinstance(project.seals[0], LabyrinthSealSpec)


def test_seal_workspace_is_dedicated_and_does_not_mutate_on_construction(qtbot) -> None:
    pytest.importorskip("ross")
    from ross_studio.pages.seal_workspace import SealStudioWorkspacePage

    model = load_reference_project_model()
    assert model.engineering is not None
    before = deepcopy(model.engineering)
    page = SealStudioWorkspacePage(model)
    qtbot.addWidget(page)
    assert page.project is model
    assert model.engineering == before
