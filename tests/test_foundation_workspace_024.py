from __future__ import annotations

from ross_studio.domain import FoundationModel, FoundationSpec
from ross_studio.model_builder_service import RotorModelMutationService
from ross_studio.models import load_reference_project_model
from ross_studio.pages.foundation_workspace import FoundationEditorDialog, FoundationWorkspacePage


def test_foundation_mutations_are_strict_transactional_entities() -> None:
    model = load_reference_project_model()
    assert model.engineering is not None
    service = RotorModelMutationService()
    assert "foundation" in service.supported_kinds()

    preview = service.preview_add(
        model.engineering,
        "foundation",
        FoundationSpec("DE rigid", 0, FoundationModel.RIGID),
    )
    assert model.engineering.foundations == []
    audit = service.commit(model.engineering, preview)
    assert audit.entity_kind == "foundation"
    assert audit.operation == "add"
    assert len(model.engineering.foundations) == 1

    delete_preview = service.preview_delete(model.engineering, "foundation", 0)
    service.commit(model.engineering, delete_preview)
    assert model.engineering.foundations == []


def test_foundation_editor_exposes_only_qualified_2dof_models(qtbot) -> None:
    model = load_reference_project_model()
    dialog = FoundationEditorDialog(model, default_support_index=0)
    qtbot.addWidget(dialog)
    offered = {dialog.model.itemData(index) for index in range(dialog.model.count())}
    assert offered == {
        FoundationModel.RIGID,
        FoundationModel.LUMPED_KC,
        FoundationModel.LUMPED_KCM,
        FoundationModel.FREQUENCY_DEPENDENT_KC,
    }
    assert FoundationModel.REDUCED_MATRIX not in offered
    assert dialog.record().dof == 2


def test_foundation_workspace_is_editable_and_tracks_unused_supports(qtbot) -> None:
    model = load_reference_project_model()
    page = FoundationWorkspacePage(model)
    qtbot.addWidget(page)
    assert page.table.rowCount() == 0
    assert page.add_button.isEnabled()

    assert model.engineering is not None
    preview = page.mutations.preview_add(
        model.engineering,
        "foundation",
        FoundationSpec("DE rigid", 0, FoundationModel.RIGID),
    )
    page._commit_preview(preview)
    assert page.table.rowCount() == 1
    assert page.add_button.isEnabled()  # NDE remains unused.

    preview = page.mutations.preview_add(
        model.engineering,
        "foundation",
        FoundationSpec("NDE rigid", 1, FoundationModel.RIGID),
    )
    page._commit_preview(preview)
    assert page.table.rowCount() == 2
    assert not page.add_button.isEnabled()
