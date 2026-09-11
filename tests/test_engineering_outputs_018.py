from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from ross_studio import __version__
from ross_studio.analysis_pipeline import AnalysisPipelineService
from ross_studio.domain import EngineeringError
from ross_studio.engineering_outputs import (
    EngineeringOutputsService,
    STATUS_AVAILABLE,
    STATUS_NOT_AVAILABLE,
    STATUS_NOT_QUALIFIED,
)
from ross_studio.models import ProjectModel, load_reference_project_model


@pytest.fixture(scope="module")
def qualified_outputs():
    project = load_reference_project_model()
    assert project.engineering is not None
    result = AnalysisPipelineService().run(project.engineering)
    snapshot = EngineeringOutputsService().build(project, result)
    return project, result, snapshot


def test_engineering_outputs_018_inventory_is_traceable_and_non_synthetic(qualified_outputs) -> None:
    project, result, snapshot = qualified_outputs

    assert snapshot.provenance["ross_version"] == "2.3.0"
    assert snapshot.provenance["ross_studio_version"] == __version__
    assert snapshot.provenance["analysis_result_type"] == "AnalysisPipelineResult"
    assert len(snapshot.provenance["project_fingerprint_sha256"]) == 64
    assert snapshot.summary["strict_build"] is True
    assert snapshot.summary["unresolved_positions_mm"] == []
    assert snapshot.summary["shaft_elements"] == project.ross_shaft_elements
    assert snapshot.summary["modal_mode_count"] == len(result.modal_modes)
    assert snapshot.summary["critical_speed_count"] == len(result.critical_speeds)

    for key in (
        "model_audit",
        "mass_properties",
        "node_map",
        "bearing_audit",
        "support_audit",
        "natural_frequencies",
        "critical_speed_map",
        "campbell",
        "unbalance_response",
        "engineering_warnings",
        "assumptions",
        "solver_trace",
    ):
        assert snapshot.capabilities[key] == STATUS_AVAILABLE

    assert snapshot.capabilities["orbit"] == STATUS_NOT_QUALIFIED
    assert snapshot.capabilities["amplification_factor"] == STATUS_NOT_QUALIFIED
    assert snapshot.capabilities["separation_margin"] == STATUS_NOT_QUALIFIED
    assert snapshot.capabilities["stability"] == STATUS_NOT_QUALIFIED
    assert snapshot.capabilities["transient_metrics"] == STATUS_NOT_AVAILABLE


def test_engineering_outputs_node_map_preserves_exact_ross_nodes(qualified_outputs) -> None:
    project, result, snapshot = qualified_outputs
    engineering = project.engineering
    assert engineering is not None

    node_table = snapshot.table("node_map")
    positions = {row[0]: row[1] for row in node_table.rows if row[1] is not None}
    assert len(positions) == len(result.build.node_positions_mm)

    for bearing in engineering.bearings:
        node = result.build.node_insertion_plan.node_for(bearing.position_mm)
        assert node is not None
        assert positions[node] == pytest.approx(bearing.position_mm)

    for probe in engineering.probes:
        node = result.build.node_insertion_plan.node_for(probe.position_mm)
        assert node is not None
        assert positions[node] == pytest.approx(probe.position_mm)

    support_rows = [row for row in node_table.rows if str(row[2]).startswith("SupportLink:")]
    assert len(support_rows) == len(engineering.supports)
    assert all(row[1] is None for row in support_rows)


def test_engineering_outputs_bearing_and_support_audits_use_real_build_mapping(qualified_outputs) -> None:
    project, result, snapshot = qualified_outputs
    engineering = project.engineering
    assert engineering is not None

    bearing_rows = snapshot.table("bearing_audit").rows
    support_rows = snapshot.table("support_audit").rows
    assert len(bearing_rows) == len(engineering.bearings)
    assert len(support_rows) == len(engineering.supports)

    for row, bearing in zip(bearing_rows, engineering.bearings):
        assert row[1] == bearing.name
        assert row[4] == pytest.approx(bearing.position_mm)
        assert row[5] == result.build.node_insertion_plan.node_for(bearing.position_mm)

    for row, support in zip(support_rows, engineering.supports):
        assert row[0] == support.name
        assert row[4] == result.build.support_link_nodes[support.name]
        assert row[5] == pytest.approx(support.mass_kg)


def test_engineering_outputs_mass_inventory_preserves_concentrated_inertias(qualified_outputs) -> None:
    _project, result, snapshot = qualified_outputs
    rows = snapshot.table("mass_properties").rows
    concent = next(row for row in rows if "Concent" in str(row[1]) or "PointMass" in str(row[0]))
    plan = result.build.equivalent_point_masses[0]
    assert concent[4] == pytest.approx(plan.mass_kg)
    assert concent[5] == pytest.approx(plan.ix_kg_m2)
    assert concent[6] == pytest.approx(plan.iy_kg_m2)
    assert concent[7] == pytest.approx(plan.iz_kg_m2)


def test_engineering_outputs_export_package_is_lossless_csv_plus_manifest(qualified_outputs, tmp_path: Path) -> None:
    _project, _result, snapshot = qualified_outputs
    package = EngineeringOutputsService.export_package(snapshot, tmp_path / "engineering")

    assert package.manifest.is_file()
    payload = json.loads(package.manifest.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["provenance"]["ross_studio_version"] == __version__
    assert payload["summary"]["unresolved_positions_mm"] == []

    assert set(package.tables) == {table.key for table in snapshot.tables}
    for table in snapshot.tables:
        path = package.tables[table.key]
        assert path.is_file()
        with path.open(newline="", encoding="utf-8") as stream:
            rows = list(csv.reader(stream))
        assert rows[0] == list(table.columns)
        assert len(rows) == len(table.rows) + 1


def test_engineering_outputs_rejects_result_from_other_project(qualified_outputs) -> None:
    _project, result, _snapshot = qualified_outputs
    wrong = ProjectModel(name="OTHER PROJECT", engineering=load_reference_project_model().engineering)
    with pytest.raises(EngineeringError, match="result/project mismatch"):
        EngineeringOutputsService().build(wrong, result)
