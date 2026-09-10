from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from ross_studio.domain import DiskSpec, EngineeringError, ProbeSpec
from ross_studio.legacy_import import load_irdin_project
from ross_studio.model_builder_service import RotorModelMutationService
from ross_studio.ross_backend import RossModelBuilder
from ross_studio.topology import NodeInsertionService


FIXTURE = Path(__file__).parents[1] / "src" / "ross_studio" / "resources" / "OP-W60-500-60Hz-IC611-P3.txt"


def test_shaft_geometry_and_mesh_update_is_preview_then_strict_commit() -> None:
    rs = pytest.importorskip("ross")
    project = load_irdin_project(FIXTURE)
    service = RotorModelMutationService(rs)
    before = deepcopy(project)
    baseline_plan = NodeInsertionService.plan(project)

    preview = service.preview_update(
        project,
        "shaft",
        7,
        {"od_left_mm": project.shaft_sections[7].od_left_mm + 2.0, "fe_elements": 4},
    )

    assert project == before
    assert preview.candidate.shaft_sections[7].od_left_mm == pytest.approx(before.shaft_sections[7].od_left_mm + 2.0)
    assert preview.candidate.shaft_sections[7].fe_elements == 4
    assert preview.audit.entity_kind == "shaft"
    assert preview.audit.operation == "update"
    assert preview.audit.shaft_elements > baseline_plan.shaft_element_count

    audit = service.commit(project, preview)
    assert audit == preview.audit
    assert project.shaft_sections[7].fe_elements == 4
    built = RossModelBuilder(rs).build(project, strict=True)
    assert built.unresolved_positions_mm == []
    assert len(built.shaft_plan) == audit.shaft_elements


def test_invalid_shaft_geometry_fails_closed_without_mutating_live_project() -> None:
    rs = pytest.importorskip("ross")
    project = load_irdin_project(FIXTURE)
    service = RotorModelMutationService(rs)
    before = deepcopy(project)
    section = project.shaft_sections[3]

    with pytest.raises(EngineeringError, match="inner diameter must be smaller"):
        service.preview_update(project, "shaft", 3, {"id_left_mm": section.od_left_mm})

    assert project == before


def test_added_disk_creates_exact_node_and_strict_ross_element_only_after_commit() -> None:
    rs = pytest.importorskip("ross")
    project = load_irdin_project(FIXTURE)
    service = RotorModelMutationService(rs)
    before = deepcopy(project)
    x_mm = 1000.123
    disk = DiskSpec("Engineering editor disk", x_mm, 12.5, 0.042, 0.081)

    preview = service.preview_add(project, "disk", disk)
    assert project == before
    assert len(preview.candidate.disks) == len(before.disks) + 1
    assert NodeInsertionService.plan(preview.candidate).node_for(x_mm) is not None
    candidate_build = RossModelBuilder(rs).build(preview.candidate, strict=True)
    assert candidate_build.unresolved_positions_mm == []
    assert any(getattr(element, "tag", "") == disk.name for element in candidate_build.rotor.disk_elements)

    service.commit(project, preview)
    assert len(project.disks) == len(before.disks) + 1
    assert NodeInsertionService.plan(project).node_for(x_mm) is not None


def test_support_update_preserves_bearing_ownership_and_link_topology() -> None:
    rs = pytest.importorskip("ross")
    project = load_irdin_project(FIXTURE)
    service = RotorModelMutationService(rs)
    before_bearings = deepcopy(project.bearings)
    before_support = deepcopy(project.supports[1])

    preview = service.preview_update(project, "support", 1, {"kxx": before_support.kxx * 1.05})
    assert project.supports[1] == before_support
    assert preview.candidate.supports[1].bearing_index == before_support.bearing_index
    assert dict(preview.audit.support_links).keys() == {support.name for support in project.supports}

    service.commit(project, preview)
    assert project.bearings == before_bearings
    assert project.supports[1].bearing_index == before_support.bearing_index
    assert project.supports[1].kxx == pytest.approx(before_support.kxx * 1.05)


def test_stale_preview_cannot_overwrite_newer_model_changes() -> None:
    rs = pytest.importorskip("ross")
    project = load_irdin_project(FIXTURE)
    service = RotorModelMutationService(rs)

    preview = service.preview_add(project, "probe", ProbeSpec("P-new", 1000.0, 1, 45.0))
    project.shaft_sections[0].fe_elements = 2

    with pytest.raises(EngineeringError, match="changed after preview"):
        service.commit(project, preview)

    assert all(probe.name != "P-new" for probe in project.probes)


def test_bearings_and_shaft_topology_add_delete_are_explicitly_owned_or_blocked() -> None:
    rs = pytest.importorskip("ross")
    project = load_irdin_project(FIXTURE)
    service = RotorModelMutationService(rs)

    with pytest.raises(EngineeringError, match="Bearing Studio"):
        service.preview_update(project, "bearing", 0, {"position_mm": 500.0})
    with pytest.raises(EngineeringError, match="absolute-coordinate remapping"):
        service.preview_add(project, "shaft", deepcopy(project.shaft_sections[-1]))
    with pytest.raises(EngineeringError, match="absolute-coordinate remapping"):
        service.preview_delete(project, "shaft", len(project.shaft_sections) - 1)
