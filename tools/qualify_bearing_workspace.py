from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

from ross_studio.bearing_studio_service import BearingStudioService
from ross_studio.bearing_workspace import BearingWorkspaceService
from ross_studio.domain import BearingSpec
from ross_studio.legacy_import import load_irdin_project
from ross_studio.ross_backend import RossModelBuilder
from ross_studio.services import EngineeringValidationService


ROOT = Path(__file__).parents[1]
FIXTURE = ROOT / "src" / "ross_studio" / "resources" / "OP-W60-500-60Hz-IC611-P3.txt"
OUT = ROOT / "artifacts" / "bearing_workspace_qualification.json"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> int:
    project = load_irdin_project(FIXTURE)
    workspace = BearingWorkspaceService()
    stations = workspace.stations(project)
    require(len(stations) == 2, f"OP-W60 must expose two physical bearing stations, received {len(stations)}")
    require([station.index for station in stations] == [0, 1], "Bearing station indices must remain deterministic")
    require([station.position_mm for station in stations] == [467.8, 2202.2], "OP-W60 DE/NDE positions changed")
    require(all(station.ross_node is not None for station in stations), "Every bearing station must map to an exact shaft node")

    baseline_inventory = [workspace.inventory(project, station.index) for station in stations]
    require(
        all(len(inventory.elements) == 1 for inventory in baseline_inventory),
        "Baseline OP-W60 radial stations must each own exactly one bearing element",
    )
    require(
        all(inventory.radial_anchor.role == "radial_anchor" for inventory in baseline_inventory),
        "Baseline station inventory lost the radial anchor contract",
    )

    de_before = deepcopy(project.bearings[0])
    nde_before = deepcopy(project.bearings[1])
    service = BearingStudioService()
    result = service.calculate(
        project,
        1,
        "BallBearingElement",
        {
            "n_balls": 9,
            "d_balls_m": 0.028,
            "static_load_n": 900.0,
            "contact_angle_rad": 0.15,
        },
    )

    require(project.bearings[0] == de_before, "Calculate mutated DE before Apply")
    require(project.bearings[1] == nde_before, "Calculate mutated NDE before Apply")

    service.apply(project, 1, result)
    require(project.bearings[0] == de_before, "Applying NDE transaction modified DE")
    require(project.bearings[1] != nde_before, "Applying NDE transaction did not modify NDE")
    require(project.bearings[1].metadata.get("source_model") == "BallBearingElement", "NDE source model mismatch")

    errors = [issue for issue in EngineeringValidationService().validate(project) if issue.severity == "error"]
    require(not errors, f"Engineering validation failed after NDE Apply: {[issue.message for issue in errors]}")

    built = RossModelBuilder().build(project, strict=True)
    bearing_elements = list(built.rotor.bearing_elements)
    require(len(bearing_elements) >= 2, "Strict rotor lost radial bearing elements")
    radial_links = [element.n_link for element in bearing_elements[:2]]
    require(radial_links == [28, 29], f"DE/NDE flexible support links changed: {radial_links}")

    # Station inventory must expose axial auxiliaries without promoting them to a
    # third radial editing station. The dedicated ThrustPad qualification proves the
    # native scientific solve; this gate qualifies only ownership/selection topology.
    project.bearings.append(
        BearingSpec(
            name="DE thrust inventory probe",
            position_mm=project.bearings[0].position_mm,
            ross_class="BearingElement",
            metadata={
                "source_model": "ThrustPad",
                "axial_coefficients": [{"rpm": 3600.0, "kzz": 2.0e8, "czz": 2.0e5}],
            },
        )
    )
    axial_index = len(project.bearings) - 1
    require([station.index for station in workspace.stations(project)] == [0, 1], "Axial auxiliary became a radial station")
    require(workspace.anchor_index(project, axial_index) == 0, "Axial auxiliary did not map back to DE")
    de_inventory = workspace.inventory(project, 0)
    nde_inventory = workspace.inventory(project, 1)
    require(
        [element.role for element in de_inventory.elements] == ["radial_anchor", "axial_auxiliary"],
        "DE inventory did not distinguish radial and axial elements",
    )
    require(
        [element.source_model for element in de_inventory.axial_auxiliaries] == ["ThrustPad"],
        "DE inventory lost ThrustPad source identity",
    )
    require(len(nde_inventory.elements) == 1 and not nde_inventory.axial_auxiliaries, "DE axial auxiliary contaminated NDE inventory")

    payload = {
        "status": "PASS",
        "ross_version": __import__("ross").__version__,
        "fixture": FIXTURE.name,
        "station_count": len(stations),
        "stations": [
            {
                "index": station.index,
                "name": station.name,
                "position_mm": station.position_mm,
                "ross_node": station.ross_node,
                "source_model": station.source_model,
                "support_names": list(station.support_names),
            }
            for station in stations
        ],
        "transaction": {
            "target_index": 1,
            "source_model": result.source_model,
            "application_class": result.application_class,
            "calculate_preview_only": True,
            "de_unchanged_after_apply": project.bearings[0] == de_before,
            "nde_changed_after_apply": project.bearings[1] != nde_before,
        },
        "station_inventory": {
            "radial_station_indices": [station.index for station in workspace.stations(project)],
            "axial_element_index": axial_index,
            "axial_anchor_index": workspace.anchor_index(project, axial_index),
            "de_elements": [
                {
                    "element_index": element.element_index,
                    "role": element.role,
                    "name": element.name,
                    "source_model": element.source_model,
                    "ross_class": element.ross_class,
                }
                for element in de_inventory.elements
            ],
            "nde_elements": [
                {
                    "element_index": element.element_index,
                    "role": element.role,
                    "name": element.name,
                    "source_model": element.source_model,
                    "ross_class": element.ross_class,
                }
                for element in nde_inventory.elements
            ],
        },
        "strict_rotor": {
            "shaft_elements": len(built.shaft_plan),
            "radial_support_links": radial_links,
            "validation_errors": [],
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
