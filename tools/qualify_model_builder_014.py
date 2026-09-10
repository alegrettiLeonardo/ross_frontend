from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

from ross_studio.domain import DiskSpec, ProbeSpec
from ross_studio.legacy_import import load_irdin_project
from ross_studio.model_builder_service import RotorModelMutationService
from ross_studio.ross_backend import RossModelBuilder
from ross_studio.topology import NodeInsertionService


ROOT = Path(__file__).parents[1]
FIXTURE = ROOT / "src" / "ross_studio" / "resources" / "OP-W60-500-60Hz-IC611-P3.txt"
OUT = ROOT / "artifacts" / "model_builder_014_qualification.json"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> int:
    project = load_irdin_project(FIXTURE)
    service = RotorModelMutationService()
    baseline = deepcopy(project)
    baseline_plan = NodeInsertionService.plan(project)

    shaft_preview = service.preview_update(project, "shaft", 7, {"fe_elements": 4})
    require(project == baseline, "Shaft preview mutated the live OP-W60 project")
    require(shaft_preview.audit.shaft_elements > baseline_plan.shaft_element_count, "FE refinement did not increase shaft elements")
    service.commit(project, shaft_preview)

    disk_x = 1000.123
    disk = DiskSpec("QUAL-014 added disk", disk_x, 10.0, 0.03, 0.06)
    disk_preview = service.preview_add(project, "disk", disk)
    require(NodeInsertionService.plan(disk_preview.candidate).node_for(disk_x) is not None, "Added disk did not receive an exact FE node")
    service.commit(project, disk_preview)

    support_before = deepcopy(project.supports[1])
    support_preview = service.preview_update(project, "support", 1, {"kxx": support_before.kxx * 1.05})
    service.commit(project, support_preview)
    require(project.supports[1].bearing_index == support_before.bearing_index, "Support edit changed bearing ownership")

    probe = ProbeSpec("QUAL-014 probe", 1111.111, 1, 30.0)
    probe_preview = service.preview_add(project, "probe", probe)
    require(project.probes == baseline.probes, "Probe preview mutated live project before Apply")
    service.commit(project, probe_preview)
    require(NodeInsertionService.plan(project).node_for(probe.position_mm) is not None, "Committed probe did not receive an exact FE node")

    final = RossModelBuilder().build(project, strict=True)
    require(final.unresolved_positions_mm == [], f"Strict ROSS build contains unresolved positions: {final.unresolved_positions_mm}")
    require(len(final.shaft_plan) == NodeInsertionService.plan(project).shaft_element_count, "Builder/topology shaft element count mismatch")
    require(len(final.rotor.disk_elements) >= 1, "Strict rotor did not retain disk elements")

    payload = {
        "status": "PASS",
        "ross_version": __import__("ross").__version__,
        "fixture": FIXTURE.name,
        "baseline": {
            "physical_sections": baseline.physical_section_count,
            "requested_elements": baseline.requested_shaft_element_count,
            "effective_elements": baseline_plan.shaft_element_count,
            "shaft_nodes": len(baseline_plan.positions_mm),
        },
        "transactions": {
            "shaft_refinement": {
                "preview_only": True,
                "target_section": 8,
                "requested_elements": project.shaft_sections[7].fe_elements,
                "effective_elements_after": shaft_preview.audit.shaft_elements,
            },
            "disk_add": {
                "preview_only": True,
                "position_mm": disk_x,
                "exact_node": NodeInsertionService.plan(project).node_for(disk_x),
            },
            "support_update": {
                "bearing_index_preserved": project.supports[1].bearing_index == support_before.bearing_index,
                "kxx_factor": 1.05,
            },
            "probe_add": {
                "preview_only": True,
                "position_mm": probe.position_mm,
                "exact_node": NodeInsertionService.plan(project).node_for(probe.position_mm),
            },
        },
        "strict_rotor": {
            "shaft_elements": len(final.shaft_plan),
            "shaft_nodes": len(final.node_positions_mm),
            "unresolved_positions_mm": final.unresolved_positions_mm,
            "support_links": final.support_link_nodes,
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
