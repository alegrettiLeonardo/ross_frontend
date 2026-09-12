from __future__ import annotations

import json
from pathlib import Path

from ross_studio.models import load_reference_project_model
from ross_studio.navigation_registry import canonical_route, navigation_node, public_routes
from ross_studio.page_registry import PAGE_ROUTES
from ross_studio.ross_backend import RossModelBuilder


EXPECTED_ROUTES = (
    "home.project",
    "model.shaft",
    "model.masses",
    "model.bearings.general",
    "model.bearings.fluid_film",
    "model.bearings.amb",
    "model.seals",
    "model.supports.flexible",
    "model.supports.foundation",
    "model.couplings",
    "model.loads.unbalance",
    "model.loads.harmonic",
    "model.loads.electromagnetic",
    "model.probes",
    "analysis.static_modal.lateral",
    "analysis.static_modal.torsional",
    "analysis.time_frequency",
    "analysis.stochastic",
    "analysis.multirotor",
)


def main() -> None:
    project = load_reference_project_model()
    if project.engineering is None:
        raise RuntimeError("Reference project did not load the engineering domain.")

    routes = public_routes()
    if routes != EXPECTED_ROUTES:
        raise RuntimeError(f"Navigation route contract mismatch: {routes}")
    if set(PAGE_ROUTES) != set(routes):
        raise RuntimeError("Page registry does not own every public navigation route.")
    amb_node = navigation_node("model.bearings.amb")
    if amb_node.kind != "route":
        raise RuntimeError("AMB must remain a first-class visible navigation route.")
    if canonical_route("ump") != "model.loads.electromagnetic":
        raise RuntimeError("Legacy UMP alias was not moved under Loads / Electromagnetic.")
    if canonical_route("results") == "results":
        raise RuntimeError("Global Results remained a public navigation state.")

    build = RossModelBuilder().build(project.engineering, strict=True)
    if build.unresolved_positions_mm:
        raise RuntimeError(f"Strict baseline has unresolved node positions: {build.unresolved_positions_mm}")

    payload = {
        "status": "PASS",
        "version": "0.17.0",
        "project": project.name,
        "routes": list(routes),
        "amb_locked": bool(amb_node.locked),
        "amb_route_policy": "0.17 established the visible AMB route; later qualified releases may unlock it without changing route ownership.",
        "foundation_owner": PAGE_ROUTES["model.supports.foundation"].owner,
        "global_results_public": False,
        "top_level_ump_public": False,
        "strict_rotor": {
            "shaft_elements": len(build.shaft_plan),
            "shaft_nodes": len(build.node_positions_mm),
            "unresolved_positions_mm": list(build.unresolved_positions_mm),
            "support_links": dict(sorted(build.support_link_nodes.items())),
        },
    }
    target = Path("artifacts/navigation_017_qualification.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
