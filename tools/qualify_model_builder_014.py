from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

from ross_studio.domain import (
    CouplingSpec,
    DiskSpec,
    DistributedMassSpec,
    LoadSpec,
    PointMassSpec,
    ProbeSpec,
    SealSpec,
)
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


def require_preview_only(live, before, label: str) -> None:
    require(live == before, f"{label} preview mutated the live OP-W60 project")


def main() -> int:
    project = load_irdin_project(FIXTURE)
    service = RotorModelMutationService()
    baseline = deepcopy(project)
    baseline_plan = NodeInsertionService.plan(project)
    transactions: dict[str, object] = {}

    before = deepcopy(project)
    shaft_preview = service.preview_update(project, "shaft", 7, {"fe_elements": 4})
    require_preview_only(project, before, "Shaft")
    require(
        shaft_preview.audit.shaft_elements > baseline_plan.shaft_element_count,
        "FE refinement did not increase shaft elements",
    )
    service.commit(project, shaft_preview)
    transactions["shaft_refinement"] = {
        "preview_only": True,
        "target_section": 8,
        "requested_elements": project.shaft_sections[7].fe_elements,
        "effective_elements_after": shaft_preview.audit.shaft_elements,
        "realization": "strict ROSS ShaftElement mesh",
    }

    before = deepcopy(project)
    distributed = DistributedMassSpec("QUAL-014 Massas", 1000.123, 40.0, 20.0, 200.0, 20.0)
    preview = service.preview_add(project, "distributed_mass", distributed)
    require_preview_only(project, before, "Distributed mass")
    candidate_plan = NodeInsertionService.plan(preview.candidate)
    for position in (distributed.start_mm, distributed.center_mm, distributed.end_mm):
        require(candidate_plan.node_for(position) is not None, f"[Massas] station {position:g} mm is not exact")
    candidate_build = RossModelBuilder().build(preview.candidate, strict=True)
    equivalent = next(item for item in candidate_build.equivalent_disks if item.name == distributed.name)
    expected_id, expected_ip = distributed.equivalent_disk_inertias_kg_m2()
    require(abs(equivalent.id_kg_m2 - expected_id) <= 1e-12, "[Massas] Id realization mismatch")
    require(abs(equivalent.ip_kg_m2 - expected_ip) <= 1e-12, "[Massas] Ip realization mismatch")
    service.commit(project, preview)
    transactions["distributed_mass"] = {
        "preview_only": True,
        "start_mm": distributed.start_mm,
        "center_mm": distributed.center_mm,
        "end_mm": distributed.end_mm,
        "Id_kg_m2": equivalent.id_kg_m2,
        "Ip_kg_m2": equivalent.ip_kg_m2,
        "realization": "equivalent ROSS DiskElement from finite hollow-cylinder mass/geometry",
    }

    before = deepcopy(project)
    disk_x = 1100.234
    disk = DiskSpec("QUAL-014 disk", disk_x, 10.0, 0.03, 0.06)
    preview = service.preview_add(project, "disk", disk)
    require_preview_only(project, before, "Disk")
    require(NodeInsertionService.plan(preview.candidate).node_for(disk_x) is not None, "Added disk did not receive an exact FE node")
    service.commit(project, preview)
    transactions["disk"] = {
        "preview_only": True,
        "position_mm": disk_x,
        "realization": "ROSS DiskElement",
    }

    before = deepcopy(project)
    concent = PointMassSpec("QUAL-014 Concent", 1150.345, 6.0, 0.011, 0.022, 0.033)
    preview = service.preview_add(project, "point_mass", concent)
    require_preview_only(project, before, "[Concent]")
    candidate_build = RossModelBuilder().build(preview.candidate, strict=True)
    point = next(item for item in candidate_build.equivalent_point_masses if item.name == concent.name)
    require(point.ix_kg_m2 == concent.ix_kg_m2, "[Concent] Ix was not preserved")
    require(point.iy_kg_m2 == concent.iy_kg_m2, "[Concent] Iy was not preserved")
    require(point.iz_kg_m2 == concent.iz_kg_m2, "[Concent] Iz was not preserved")
    service.commit(project, preview)
    transactions["concentrated_mass"] = {
        "preview_only": True,
        "position_mm": concent.position_mm,
        "Ix_kg_m2": point.ix_kg_m2,
        "Iy_kg_m2": point.iy_kg_m2,
        "Iz_kg_m2": point.iz_kg_m2,
        "realization": "qualified concentrated DiskElement preserving independent principal inertias",
    }

    support_before = deepcopy(project.supports[1])
    preview = service.preview_update(project, "support", 1, {"kxx": support_before.kxx * 1.05})
    service.commit(project, preview)
    require(project.supports[1].bearing_index == support_before.bearing_index, "Support edit changed bearing ownership")
    transactions["support"] = {
        "bearing_index_preserved": True,
        "kxx_factor": 1.05,
        "realization": "existing qualified ROSS flexible-support chain",
    }

    before = deepcopy(project)
    seal = SealSpec(
        "QUAL-014 seal",
        1250.456,
        kxx=1.10e6,
        kyy=1.20e6,
        cxx=101.0,
        cyy=102.0,
        kxy=-2.10e5,
        kyx=2.20e5,
        cxy=-21.0,
        cyx=22.0,
    )
    preview = service.preview_add(project, "seal", seal)
    require_preview_only(project, before, "Seal")
    candidate_build = RossModelBuilder().build(preview.candidate, strict=True)
    seal_candidates = [
        *getattr(candidate_build.rotor, "seal_elements", []),
        *getattr(candidate_build.rotor, "bearing_elements", []),
    ]
    native_seal = next((element for element in seal_candidates if getattr(element, "tag", None) == seal.name), None)
    require(native_seal is not None and type(native_seal).__name__ == "SealElement", "Seal was not realized as ROSS SealElement")
    require(native_seal.n == NodeInsertionService.plan(preview.candidate).node_for(seal.position_mm), "Seal node mismatch")
    require(abs(float(native_seal.K(0.0)[0, 1]) - seal.kxy) <= 1e-9, "Seal Kxy sign/value changed")
    require(abs(float(native_seal.C(0.0)[1, 0]) - seal.cyx) <= 1e-9, "Seal Cyx sign/value changed")
    service.commit(project, preview)
    transactions["seal"] = {
        "preview_only": True,
        "position_mm": seal.position_mm,
        "ross_class": "SealElement",
        "cross_coupling_preserved": True,
        "realization": "native ROSS SealElement in strict Rotor",
    }

    before = deepcopy(project)
    coupling = CouplingSpec(
        "QUAL-014 coupling",
        1350.567,
        left_mass_kg=3.0,
        right_mass_kg=4.0,
        left_ip_kg_m2=0.05,
        right_ip_kg_m2=0.06,
        kt_x_n_m=1.0e7,
        kt_y_n_m=1.1e7,
        kt_z_n_m=1.2e7,
        kr_x_n_m_rad=2.0e6,
        kr_y_n_m_rad=2.1e6,
        kr_z_n_m_rad=2.2e6,
        ct_x_n_s_m=100.0,
        ct_y_n_s_m=110.0,
        ct_z_n_s_m=120.0,
    )
    try:
        service.preview_add(project, "coupling", coupling)
    except Exception as exc:
        coupling_error = str(exc)
    else:
        raise RuntimeError("Legacy single-station coupling no longer failed closed")
    require_preview_only(project, before, "Coupling")
    transactions["coupling"] = {
        "preview_only": True,
        "position_mm": coupling.position_mm,
        "legacy_single_station_rejected": True,
        "error": coupling_error,
        "realization": "legacy one-station contract fails closed; native two-node ROSS CouplingElement is qualified by the 0.30 gate",
    }

    before = deepcopy(project)
    load = LoadSpec("QUAL-014 load", "harmonic", 1450.678, 250.0, 35.0, {"order": 2, "unit": "N"})
    preview = service.preview_add(project, "load", load)
    require_preview_only(project, before, "Load")
    require(NodeInsertionService.plan(preview.candidate).node_for(load.position_mm) is not None, "Load station is not exact")
    service.commit(project, preview)
    transactions["load"] = {
        "preview_only": True,
        "position_mm": load.position_mm,
        "exact_node": NodeInsertionService.plan(project).node_for(load.position_mm),
        "metadata_preserved": project.loads[-1].metadata == load.metadata,
        "realization": "analysis-force input at exact shaft station; not a structural Rotor element",
    }

    before = deepcopy(project)
    probe = ProbeSpec("QUAL-014 probe", 1550.789, 1, 30.0)
    preview = service.preview_add(project, "probe", probe)
    require_preview_only(project, before, "Probe")
    service.commit(project, preview)
    require(NodeInsertionService.plan(project).node_for(probe.position_mm) is not None, "Committed probe did not receive an exact FE node")
    transactions["probe"] = {
        "preview_only": True,
        "position_mm": probe.position_mm,
        "exact_node": NodeInsertionService.plan(project).node_for(probe.position_mm),
        "realization": "postprocessing input at exact shaft station",
    }

    final = RossModelBuilder().build(project, strict=True)
    require(final.unresolved_positions_mm == [], f"Strict ROSS build contains unresolved positions: {final.unresolved_positions_mm}")
    require(len(final.shaft_plan) == NodeInsertionService.plan(project).shaft_element_count, "Builder/topology shaft element count mismatch")
    require(any(item.name == distributed.name for item in final.equivalent_disks), "Final rotor lost [Massas] realization")
    require(any(item.name == concent.name for item in final.equivalent_point_masses), "Final rotor lost [Concent] realization")
    final_seals = [*getattr(final.rotor, "seal_elements", []), *getattr(final.rotor, "bearing_elements", [])]
    require(any(getattr(element, "tag", None) == seal.name for element in final_seals), "Final rotor lost SealElement")

    payload = {
        "status": "PASS",
        "ross_version": __import__("ross").__version__,
        "fixture": FIXTURE.name,
        "transaction_contract": "deepcopy candidate -> domain validation -> engineering validation -> strict ROSS build -> stale-check -> commit",
        "baseline": {
            "physical_sections": baseline.physical_section_count,
            "requested_elements": baseline.requested_shaft_element_count,
            "effective_elements": baseline_plan.shaft_element_count,
            "shaft_nodes": len(baseline_plan.positions_mm),
        },
        "transactions": transactions,
        "strict_rotor": {
            "shaft_elements": len(final.shaft_plan),
            "shaft_nodes": len(final.node_positions_mm),
            "unresolved_positions_mm": final.unresolved_positions_mm,
            "support_links": final.support_link_nodes,
            "seal_count": len(getattr(final.rotor, "seal_elements", [])),
        },
        "explicit_blocks": {
            "bearing_ownership": "Bearing Studio only",
            "shaft_section_add_delete": "requires explicit downstream absolute-coordinate remapping policy",
            "coupling_native_mapping": "legacy single-station input fails closed; explicit two-node CouplingElement contract is qualified in 0.30",
            "ump_duplicate_editor": "blocked; UMP remains derived from qualified engineering source",
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
