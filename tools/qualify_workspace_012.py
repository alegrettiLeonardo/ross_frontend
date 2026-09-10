from __future__ import annotations

import json
from pathlib import Path

import ross
import ross_studio

from ross_studio.domain import AdapterStatus, BearingGroup
from ross_studio.legacy_import import load_irdin_project
from ross_studio.ross_backend import RossModelBuilder
from ross_studio.ross_native_view import RossRotorPlotService
from ross_studio.services import BearingCatalogService
from ross_studio.topology import NodeInsertionService


ROOT = Path(__file__).parents[1]
FIXTURE = ROOT / "src" / "ross_studio" / "resources" / "OP-W60-500-60Hz-IC611-P3.txt"
ARTIFACT = ROOT / "artifacts" / "workspace_012_qualification.json"
READY = {
    "BearingElement",
    "BallBearingElement",
    "RollerBearingElement",
    "CylindricalBearing",
    "PlainJournal",
    "TiltingPad",
    "ThrustPad",
    "SqueezeFilmDamper",
}


def main() -> int:
    # This is the 0.12 mesh/workspace regression gate executed against the current
    # release candidate. The scientific expectations are unchanged; only the
    # application version advances with the Bearing Studio 2.0 tranche.
    assert ross_studio.__version__ == "0.13.0"
    assert ross.__version__ == "2.3.0"

    project = load_irdin_project(FIXTURE)
    default_plan = NodeInsertionService.plan(project)
    assert project.physical_section_count == 15
    assert project.requested_shaft_element_count == 15
    assert default_plan.shaft_element_count == 27
    assert len(default_plan.positions_mm) == 28

    mandatory = (467.8, 2202.2, 918.0, 1633.0, 105.0, 737.5, 1275.5, 1932.5, 2550.2)
    assert all(default_plan.node_for(x) is not None for x in mandatory)

    project.shaft_sections[7].fe_elements = 5
    project.validate()
    refined_plan = NodeInsertionService.plan(project)
    expected_mesh = (1000.5, 1223.5, 1446.5, 1669.5)
    assert all(refined_plan.node_for(x) is not None for x in expected_mesh)
    assert all(refined_plan.node_for(x) is not None for x in mandatory)
    assert refined_plan.shaft_element_count > default_plan.shaft_element_count
    refined_shaft = RossModelBuilder.shaft_plan(project)
    assert len(refined_shaft) == refined_plan.shaft_element_count
    assert all(element.x1_mm > element.x0_mm for element in refined_shaft)

    native_project = load_irdin_project(FIXTURE)
    native = RossRotorPlotService().build_figure(native_project)
    assert native.shaft_elements == 27
    assert native.nodes == 28
    assert len(native.figure.data) > 0

    catalog = BearingCatalogService()
    catalog_rows = {
        row["class"]: row
        for group in (BearingGroup.GENERAL, BearingGroup.THD, BearingGroup.AMB)
        for row in catalog.entries(group)
    }
    for ross_class in READY:
        assert catalog_rows[ross_class]["status"] == AdapterStatus.VALIDATED.value
        assert catalog_rows[ross_class]["can_execute"] is True
    assert catalog_rows["MagneticBearingElement"]["status"] == AdapterStatus.BLOCKED.value
    assert catalog_rows["MagneticBearingElement"]["can_execute"] is False

    payload = {
        "status": "PASS",
        "gate_origin": "0.12.0 mesh/workspace regression",
        "ross_studio_version": ross_studio.__version__,
        "ross_version": ross.__version__,
        "reference_case": project.name,
        "default_mesh": {
            "physical_sections": 15,
            "requested_base_elements": 15,
            "effective_ross_shaft_elements": default_plan.shaft_element_count,
            "shaft_nodes": len(default_plan.positions_mm),
        },
        "refined_mesh_sample": {
            "physical_section": 8,
            "requested_section_elements": 5,
            "requested_total_base_elements": project.requested_shaft_element_count,
            "effective_ross_shaft_elements": refined_plan.shaft_element_count,
            "uniform_internal_mesh_nodes_mm": list(expected_mesh),
            "mandatory_engineering_nodes_preserved": list(mandatory),
        },
        "native_ross_plot": {
            "api": "Rotor.plot_rotor",
            "source": "strict RossModelBuilder rotor",
            "shaft_elements": native.shaft_elements,
            "shaft_nodes": native.nodes,
            "plotly_traces": len(native.figure.data),
        },
        "bearing_catalog": {
            key: {
                "status": row["status"],
                "can_execute": row["can_execute"],
            }
            for key, row in sorted(catalog_rows.items())
        },
    }
    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
