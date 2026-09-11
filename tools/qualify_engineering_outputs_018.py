from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("ROSS_STUDIO_DISABLE_WEBENGINE", "1")

from PySide6.QtWidgets import QApplication

from ross_studio.analysis_pipeline import AnalysisPipelineService
from ross_studio.engineering_figures import EngineeringFigureCatalog
from ross_studio.engineering_outputs import EngineeringOutputsService
from ross_studio.engineering_report_pdf import install_engineering_report_export
from ross_studio.models import load_reference_project_model
from ross_studio.pages.engineering_results import EngineeringAnalysisResultsPage


def main() -> int:
    # Presentation-only PDF fix: install the bounded/wrapped report composer before
    # exercising the exact same Engineering Outputs service used by the GUI.
    install_engineering_report_export()

    project = load_reference_project_model()
    if project.engineering is None:
        raise RuntimeError("Reference project lost its engineering domain.")

    result = AnalysisPipelineService().run(project.engineering)
    service = EngineeringOutputsService()
    snapshot = service.build(project, result)
    figures = EngineeringFigureCatalog(project, result)

    if getattr(service, "PDF_LAYOUT_POLICY", None) != "LANDSCAPE_A4_FIT_AND_WRAP":
        raise RuntimeError("Engineering Outputs PDF fit/wrap policy is not installed.")
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

    required_figures = {
        "rotor_model",
        "static_free_body",
        "static_deformation",
        "static_shearing_force",
        "static_bending_moment",
        "campbell",
        "unbalance_bode",
        "unbalance_deflected_shape",
        "unbalance_bending_moment",
    }
    if not required_figures.issubset(set(figures.keys)):
        raise RuntimeError(
            f"Native ROSS figure inventory incomplete: expected at least={sorted(required_figures)}, got={sorted(figures.keys)}"
        )
    if not any(key.startswith("modal_mode_") and key.endswith("_2d") for key in figures.keys):
        raise RuntimeError("Native modal 2D output is missing.")
    if not any(key.startswith("modal_mode_") and key.endswith("_3d") for key in figures.keys):
        raise RuntimeError("Native modal 3D output is missing.")

    # Exercise representative native ROSS figures from each currently qualified
    # analysis family. The full GUI catalog exposes every solved modal 2D/3D shape.
    representative = (
        "rotor_model",
        "static_deformation",
        "campbell",
        "unbalance_bode",
    )
    for key in representative:
        figure = figures.figure(key)
        if len(getattr(figure, "data", ())) == 0:
            raise RuntimeError(f"Native ROSS figure {key!r} contains no traces.")

    app = QApplication.instance() or QApplication([])
    page = EngineeringAnalysisResultsPage(project)
    page.resize(1500, 850)
    page.set_results(result)
    app.processEvents()
    if not page.engineering_outputs_button.isEnabled():
        raise RuntimeError("Engineering Outputs GUI entry point did not enable after a real ROSS result.")
    if page.engineering_snapshot is None or page.engineering_figure_catalog is None:
        raise RuntimeError("Engineering Outputs GUI did not retain snapshot/native figure catalog.")

    root = Path("artifacts/engineering_outputs_018")
    package = service.export_package(
        snapshot,
        root,
        figure_catalog=figures,
        figure_keys=representative,
        include_xlsx=True,
        include_pdf=True,
        include_images=True,
        include_qualification_manifest=True,
    )
    required_files = [
        package.manifest,
        package.workbook,
        package.report,
        package.qualification_manifest,
        *package.tables.values(),
        *(package.figures or {}).values(),
    ]
    for path in required_files:
        if path is None or not path.is_file() or path.stat().st_size <= 0:
            raise RuntimeError(f"Engineering Outputs export missing/empty file: {path}")

    qualification_payload = json.loads(package.qualification_manifest.read_text(encoding="utf-8"))
    if qualification_payload.get("status") != "PASS":
        raise RuntimeError("Qualification Manifest is not PASS.")
    if qualification_payload["qualification_policy"]["scientific_recompute"] is not False:
        raise RuntimeError("Engineering Outputs qualification must prove no scientific recompute.")
    source_methods = {item["source_method"] for item in qualification_payload["native_ross_figures"]}
    expected_methods = {
        "Rotor.plot_rotor",
        "StaticResults.plot_deformation",
        "CampbellResults.plot",
        "ForcedResponseResults.plot",
        "ModalResults.plot_mode_2d",
        "ModalResults.plot_mode_3d",
    }
    if not expected_methods.issubset(source_methods):
        raise RuntimeError(f"Tutorial/native ROSS source methods missing: {sorted(expected_methods - source_methods)}")

    qualification = {
        "status": "PASS",
        "ross_version": snapshot.provenance["ross_version"],
        "ross_studio_version": snapshot.provenance["ross_studio_version"],
        "project": project.name,
        "project_fingerprint_sha256": snapshot.provenance["project_fingerprint_sha256"],
        "strict_build": snapshot.summary["strict_build"],
        "unresolved_positions_mm": snapshot.summary["unresolved_positions_mm"],
        "tables": sorted(available_tables),
        "native_ross_figure_count": len(figures.keys),
        "representative_png": {key: str(path) for key, path in (package.figures or {}).items()},
        "native_ross_sources": figures.inventory(),
        "capabilities": snapshot.capabilities,
        "limitations": list(snapshot.limitations),
        "manifest": str(package.manifest),
        "qualification_manifest": str(package.qualification_manifest),
        "xlsx": str(package.workbook),
        "pdf": str(package.report),
        "pdf_layout_policy": service.PDF_LAYOUT_POLICY,
        "csv_files": {key: str(path) for key, path in package.tables.items()},
        "gui_entry_point": "Engineering Outputs button on local analysis result page",
        "global_results_sidebar_route_added": False,
    }
    output = Path("artifacts/engineering_outputs_018_qualification.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(qualification, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(qualification, indent=2, ensure_ascii=False))
    page.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
