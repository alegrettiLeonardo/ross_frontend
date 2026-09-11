from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import csv
import json
from pathlib import Path
from typing import Any, Iterable

import ross

from . import __version__
from .analysis_pipeline import AnalysisPipelineResult
from .domain import EngineeringError
from .models import ProjectModel
from .project_io import project_fingerprint


STATUS_AVAILABLE = "AVAILABLE"
STATUS_NOT_QUALIFIED = "NOT_QUALIFIED"
STATUS_NOT_AVAILABLE = "NOT_AVAILABLE_FROM_CURRENT_PIPELINE"


@dataclass(slots=True, frozen=True)
class EngineeringTable:
    key: str
    title: str
    columns: tuple[str, ...]
    rows: tuple[tuple[object, ...], ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "title": self.title,
            "columns": list(self.columns),
            "rows": [list(row) for row in self.rows],
        }


@dataclass(slots=True, frozen=True)
class EngineeringOutputsSnapshot:
    schema_version: int
    generated_utc: str
    project: dict[str, object]
    provenance: dict[str, object]
    summary: dict[str, object]
    capabilities: dict[str, str]
    tables: tuple[EngineeringTable, ...]
    warnings: tuple[dict[str, object], ...]
    limitations: tuple[str, ...]

    def table(self, key: str) -> EngineeringTable:
        for table in self.tables:
            if table.key == key:
                return table
        raise KeyError(key)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "generated_utc": self.generated_utc,
            "project": dict(self.project),
            "provenance": dict(self.provenance),
            "summary": dict(self.summary),
            "capabilities": dict(self.capabilities),
            "tables": [table.to_dict() for table in self.tables],
            "warnings": [dict(item) for item in self.warnings],
            "limitations": list(self.limitations),
        }


@dataclass(slots=True, frozen=True)
class EngineeringPackage:
    root: Path
    manifest: Path
    tables: dict[str, Path]


class EngineeringOutputsService:
    """Create auditable engineering deliverables from already-computed ROSS results.

    This service never re-runs an analysis and never synthesizes missing engineering
    quantities. It only packages the qualified ``AnalysisPipelineResult`` together
    with the exact model/build trace that produced it. Capabilities not present in
    the current pipeline are reported explicitly as not qualified/available.
    """

    SCHEMA_VERSION = 1

    @staticmethod
    def _require_engineering(project: ProjectModel):
        if project.engineering is None:
            raise EngineeringError("Engineering Outputs requires a populated RotorProject; the current project is empty.")
        return project.engineering

    @staticmethod
    def _assert_same_project(project: ProjectModel, result: AnalysisPipelineResult) -> None:
        if result.project_name != project.name:
            raise EngineeringError(
                f"Engineering Outputs result/project mismatch: result={result.project_name!r}, project={project.name!r}. "
                "Re-run the analysis for the active project before exporting."
            )
        if result.build.unresolved_positions_mm:
            joined = ", ".join(f"{value:g}" for value in result.build.unresolved_positions_mm)
            raise EngineeringError(
                f"Engineering Outputs refuses an unresolved strict model; unresolved positions: {joined} mm."
            )

    @staticmethod
    def _table(key: str, title: str, columns: Iterable[str], rows: Iterable[Iterable[object]]) -> EngineeringTable:
        return EngineeringTable(
            key=key,
            title=title,
            columns=tuple(str(column) for column in columns),
            rows=tuple(tuple(row) for row in rows),
        )

    def _node_map(self, project: ProjectModel, result: AnalysisPipelineResult) -> EngineeringTable:
        engineering = self._require_engineering(project)
        build = result.build
        ownership: dict[int, list[str]] = {index: [] for index in range(len(build.node_positions_mm))}

        def add_owner(position_mm: float, label: str) -> None:
            node = build.node_insertion_plan.node_for(position_mm)
            if node is None:
                raise EngineeringError(f"Node Map cannot resolve {label} at x={position_mm:g} mm to an exact ROSS node.")
            ownership.setdefault(node, []).append(label)

        for item in engineering.bearings:
            add_owner(item.position_mm, f"Bearing:{item.name}")
        for item in engineering.disks:
            add_owner(item.position_mm, f"Disk:{item.name}")
        for item in engineering.distributed_masses:
            add_owner(item.center_mm, f"DistributedMass:{item.name}")
        for item in engineering.point_masses:
            add_owner(item.position_mm, f"PointMass:{item.name}")
        for item in engineering.seals:
            add_owner(item.position_mm, f"Seal:{item.name}")
        for item in engineering.couplings:
            add_owner(item.position_mm, f"Coupling:{item.name}")
        for item in engineering.loads:
            add_owner(item.position_mm, f"Load:{item.name}")
        for item in engineering.probes:
            add_owner(item.position_mm, f"Probe:{item.name}")

        rows: list[tuple[object, ...]] = []
        for node, position_mm in enumerate(build.node_positions_mm):
            rows.append((node, float(position_mm), "; ".join(ownership.get(node, ())) or "shaft"))
        for support_name, link_node in sorted(build.support_link_nodes.items(), key=lambda item: item[1]):
            rows.append((int(link_node), None, f"SupportLink:{support_name}"))
        return self._table("node_map", "Exact ROSS Node Map", ("node", "x_mm", "ownership"), rows)

    def _bearing_audit(self, project: ProjectModel, result: AnalysisPipelineResult) -> EngineeringTable:
        engineering = self._require_engineering(project)
        rows: list[tuple[object, ...]] = []
        for index, bearing in enumerate(engineering.bearings):
            node = result.build.node_insertion_plan.node_for(bearing.position_mm)
            if node is None:
                raise EngineeringError(f"Bearing audit cannot resolve {bearing.name!r} at x={bearing.position_mm:g} mm.")
            axial_rows = bearing.metadata.get("axial_coefficients")
            coefficient_rows = len(bearing.coefficients)
            if isinstance(axial_rows, list):
                coefficient_rows = max(coefficient_rows, len(axial_rows))
            support = next((item for item in engineering.supports if item.bearing_index == index), None)
            rows.append((
                index,
                bearing.name,
                bearing.ross_class,
                bearing.group.value,
                float(bearing.position_mm),
                int(node),
                bool(bearing.frequency_dependent or coefficient_rows > 1),
                coefficient_rows,
                support.name if support is not None else "",
            ))
        return self._table(
            "bearing_audit",
            "Bearing Audit",
            ("index", "name", "ross_class", "group", "x_mm", "node", "frequency_dependent", "coefficient_rows", "support"),
            rows,
        )

    def _support_audit(self, project: ProjectModel, result: AnalysisPipelineResult) -> EngineeringTable:
        engineering = self._require_engineering(project)
        rows: list[tuple[object, ...]] = []
        for support in engineering.supports:
            bearing = engineering.bearings[support.bearing_index]
            shaft_node = result.build.node_insertion_plan.node_for(bearing.position_mm)
            if shaft_node is None:
                raise EngineeringError(f"Support audit cannot resolve bearing {bearing.name!r} to an exact ROSS node.")
            rows.append((
                support.name,
                support.bearing_index,
                bearing.name,
                int(shaft_node),
                int(result.build.support_link_nodes[support.name]),
                float(support.mass_kg),
                float(support.kxx), float(support.kxy), float(support.kyx), float(support.kyy),
                float(support.cxx), float(support.cxy), float(support.cyx), float(support.cyy),
            ))
        return self._table(
            "support_audit",
            "Flexible Support Audit",
            (
                "name", "bearing_index", "bearing", "shaft_node", "link_node", "mass_kg",
                "kxx", "kxy", "kyx", "kyy", "cxx", "cxy", "cyx", "cyy",
            ),
            rows,
        )

    def _mass_properties(self, project: ProjectModel, result: AnalysisPipelineResult) -> EngineeringTable:
        engineering = self._require_engineering(project)
        rows: list[tuple[object, ...]] = []
        for item in result.build.equivalent_disks:
            rows.append((item.name, item.source, item.node, item.position_mm, item.mass_kg, item.id_kg_m2, item.ip_kg_m2, None))
        for item in result.build.equivalent_point_masses:
            rows.append((item.name, item.source, item.node, item.position_mm, item.mass_kg, item.ix_kg_m2, item.iy_kg_m2, item.iz_kg_m2))
        for item in engineering.disks:
            node = result.build.node_insertion_plan.node_for(item.position_mm)
            if node is None:
                raise EngineeringError(f"Mass Properties cannot resolve disk {item.name!r} to an exact ROSS node.")
            rows.append((item.name, "DiskSpec", node, item.position_mm, item.mass_kg, item.id_kg_m2, item.ip_kg_m2, None))
        for support in engineering.supports:
            rows.append((support.name, "Support point mass", result.build.support_link_nodes[support.name], None, support.mass_kg, None, None, None))
        return self._table(
            "mass_properties",
            "Mass / Inertia Inventory",
            ("name", "source", "node", "x_mm", "mass_kg", "inertia_1_kg_m2", "inertia_2_kg_m2", "inertia_3_kg_m2"),
            rows,
        )

    @staticmethod
    def _modal_table(result: AnalysisPipelineResult) -> EngineeringTable:
        return EngineeringOutputsService._table(
            "natural_frequencies",
            "Natural Frequencies at Rated Speed",
            ("mode", "wn_hz", "wd_hz", "damping_ratio", "log_dec", "whirl"),
            (
                (item.mode, item.wn_hz, item.wd_hz, item.damping_ratio, item.log_dec, item.whirl)
                for item in result.modal_modes
            ),
        )

    @staticmethod
    def _critical_table(result: AnalysisPipelineResult) -> EngineeringTable:
        return EngineeringOutputsService._table(
            "critical_speeds",
            "Critical Speed Map",
            ("mode", "speed_rpm", "frequency_hz", "damping_ratio", "log_dec", "whirl", "method"),
            (
                (item.mode, item.speed_rpm, item.frequency_hz, item.damping_ratio, item.log_dec, item.whirl, item.method)
                for item in result.critical_speeds
            ),
        )

    @staticmethod
    def _probe_table(result: AnalysisPipelineResult) -> EngineeringTable:
        return EngineeringOutputsService._table(
            "unbalance_response",
            "Unbalance Response / Probes",
            (
                "probe", "node", "x_mm", "coordinate", "orientation_deg", "peak_speed_rpm",
                "peak_amplitude_um", "peak_phase_deg", "rated_speed_rpm", "rated_amplitude_um", "rated_phase_deg",
            ),
            (
                (
                    item.name, item.node, item.position_mm, item.coordinate, item.orientation_deg,
                    item.peak_speed_rpm, item.peak_amplitude_um, item.peak_phase_deg,
                    item.rated_speed_rpm, item.rated_amplitude_um, item.rated_phase_deg,
                )
                for item in result.probe_responses
            ),
        )

    @staticmethod
    def _solver_trace(result: AnalysisPipelineResult) -> EngineeringTable:
        return EngineeringOutputsService._table(
            "solver_trace",
            "Solver Trace",
            ("stage", "elapsed_s"),
            ((stage, float(elapsed)) for stage, elapsed in result.stage_elapsed_s.items()),
        )

    @staticmethod
    def _audit_table(result: AnalysisPipelineResult) -> EngineeringTable:
        return EngineeringOutputsService._table(
            "engineering_audit",
            "Engineering Warnings and Assumptions",
            ("severity", "code", "message"),
            ((item.severity, item.code, item.message) for item in result.audits),
        )

    def build(self, project: ProjectModel, result: AnalysisPipelineResult) -> EngineeringOutputsSnapshot:
        engineering = self._require_engineering(project)
        self._assert_same_project(project, result)
        case = engineering.operating_cases[0]

        capabilities = {
            "model_audit": STATUS_AVAILABLE,
            "mass_properties": STATUS_AVAILABLE,
            "node_map": STATUS_AVAILABLE,
            "bearing_audit": STATUS_AVAILABLE,
            "support_audit": STATUS_AVAILABLE,
            "natural_frequencies": STATUS_AVAILABLE,
            "critical_speed_map": STATUS_AVAILABLE,
            "campbell": STATUS_AVAILABLE,
            "unbalance_response": STATUS_AVAILABLE,
            "orbit": STATUS_NOT_QUALIFIED,
            "amplification_factor": STATUS_NOT_QUALIFIED,
            "separation_margin": STATUS_NOT_QUALIFIED,
            "stability": STATUS_NOT_QUALIFIED,
            "transient_metrics": STATUS_NOT_AVAILABLE,
            "engineering_warnings": STATUS_AVAILABLE,
            "assumptions": STATUS_AVAILABLE,
            "solver_trace": STATUS_AVAILABLE,
        }

        tables = (
            self._node_map(project, result),
            self._mass_properties(project, result),
            self._bearing_audit(project, result),
            self._support_audit(project, result),
            self._modal_table(result),
            self._critical_table(result),
            self._probe_table(result),
            self._solver_trace(result),
            self._audit_table(result),
        )
        warnings = tuple(asdict(item) for item in result.audits if item.severity == "warning")
        limitations = (
            "Orbit output is not exported until a qualified orbit extraction contract is implemented.",
            "Amplification factor and separation margin are not inferred from peaks; dedicated qualified rules are required.",
            "Stability output is not promoted from modal damping alone; a dedicated stability analysis contract is required.",
            "Transient metrics are unavailable because the current qualified pipeline does not execute run_time_response().",
            "PDF/XLSX rendering is outside this first 0.18 tranche; JSON manifest and lossless CSV tables are the qualified package formats.",
        )

        summary = {
            "strict_build": True,
            "physical_sections": engineering.physical_section_count,
            "shaft_elements": len(result.build.shaft_plan),
            "shaft_nodes": len(result.build.node_positions_mm),
            "bearings": len(engineering.bearings),
            "supports": len(engineering.supports),
            "seals": len(engineering.seals),
            "loads": len(engineering.loads),
            "probes": len(engineering.probes),
            "critical_speed_count": len(result.critical_speeds),
            "modal_mode_count": len(result.modal_modes),
            "probe_response_count": len(result.probe_responses),
            "total_solver_elapsed_s": result.total_elapsed_s,
            "unresolved_positions_mm": list(result.build.unresolved_positions_mm),
        }
        provenance = {
            "ross_version": ross.__version__,
            "ross_studio_version": __version__,
            "project_fingerprint_sha256": project_fingerprint(project),
            "lateral_convention": engineering.lateral_convention.value,
            "probe_angle_contract": engineering.probe_angle_contract.value,
            "analysis_result_type": type(result).__name__,
        }
        project_data = {
            "name": project.name,
            "description": project.description,
            "created": project.created,
            "modified": project.modified,
            "line": project.line,
            "frame": project.frame,
            "poles": project.poles,
            "rated_speed_rpm": float(case.rated_speed_rpm),
            "speed_min_rpm": float(case.speed_min_rpm),
            "speed_max_rpm": float(case.speed_max_rpm),
        }
        return EngineeringOutputsSnapshot(
            schema_version=self.SCHEMA_VERSION,
            generated_utc=datetime.now(timezone.utc).isoformat(),
            project=project_data,
            provenance=provenance,
            summary=summary,
            capabilities=capabilities,
            tables=tables,
            warnings=warnings,
            limitations=limitations,
        )

    @staticmethod
    def export_package(snapshot: EngineeringOutputsSnapshot, root: str | Path) -> EngineeringPackage:
        target = Path(root)
        target.mkdir(parents=True, exist_ok=True)
        table_dir = target / "tables"
        table_dir.mkdir(parents=True, exist_ok=True)

        manifest = target / "engineering_outputs_manifest.json"
        manifest.write_text(json.dumps(snapshot.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

        table_paths: dict[str, Path] = {}
        for table in snapshot.tables:
            path = table_dir / f"{table.key}.csv"
            with path.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.writer(stream)
                writer.writerow(table.columns)
                writer.writerows(table.rows)
            table_paths[table.key] = path
        return EngineeringPackage(root=target, manifest=manifest, tables=table_paths)


__all__ = [
    "EngineeringOutputsService",
    "EngineeringOutputsSnapshot",
    "EngineeringPackage",
    "EngineeringTable",
    "STATUS_AVAILABLE",
    "STATUS_NOT_AVAILABLE",
    "STATUS_NOT_QUALIFIED",
]
