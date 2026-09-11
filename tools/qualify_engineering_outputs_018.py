from __future__ import annotations

import json
from pathlib import Path

from ross_studio.analysis_pipeline import AnalysisPipelineService
from ross_studio.engineering_outputs import EngineeringOutputsService
from ross_studio.models import load_reference_project_model


def main() -> int:
    project = load_reference_project_model()
    if project.engineering is None:
        raise RuntimeError("Reference project lost its engineering domain.")

    result = AnalysisPipelineService().run(project.engineering)
    service = EngineeringOutputsService()
    snapshot = service.build(project, result)

    if snapshot.summary["unresolved_positions_mm"] != []:
        raise RuntimeError("Engineering Outputs contains unresolved positions.")
    if snapshot.provenance["ross_version"] != "2.3.0":
        raise RuntimeError(f"ROSS version drift: {snapshot.provenance['ross_version']}")
    if snapshot.provenance["ross_studio_version"] != "0.18.0":
        raise RuntimeError(f"ROSS Studio version drift: {snapshot.provenance['ross_studio_version']}")

    required_tables = {
        "node_map",
        "mass_properties",
        "bearing_audit",
        "support_audit",
        "natural_frequencies",
        "critical_speeds",
        "unbalance_response",
        "solver_trace",
        "engineering_audit",
    }
    available_tables = {table.key for table in snapshot.tables}
    if available_tables != required_tables:
        raise RuntimeError(
            f"Engineering Outputs table inventory mismatch: expected={sorted(required_tables)}, got={sorted(available_tables)}"
        )

    root = Path("artifacts/engineering_outputs_018")
    package = service.export_package(snapshot, root)
    qualification = {
        "status": "PASS",
        "ross_version": snapshot.provenance["ross_version"],
        "ross_studio_version": snapshot.provenance["ross_studio_version"],
        "project": project.name,
        "project_fingerprint_sha256": snapshot.provenance["project_fingerprint_sha256"],
        "strict_build": snapshot.summary["strict_build"],
        "unresolved_positions_mm": snapshot.summary["unresolved_positions_mm"],
        "tables": sorted(available_tables),
        "capabilities": snapshot.capabilities,
        "limitations": list(snapshot.limitations),
        "manifest": str(package.manifest),
        "csv_files": {key: str(path) for key, path in package.tables.items()},
    }
    output = Path("artifacts/engineering_outputs_018_qualification.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(qualification, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(qualification, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
