from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


NavigationKind = Literal["section", "group", "route"]


@dataclass(frozen=True, slots=True)
class NavigationNode:
    """Declarative navigation entry.

    The registry is intentionally UI-agnostic. Scientific ownership lives in the
    page/service layer; the sidebar only renders this tree and emits stable route ids.
    """

    id: str
    title: str
    kind: NavigationKind
    parent: str | None = None
    icon: str = "home"
    enabled: bool = True
    locked: bool = False
    expanded: bool = True
    tooltip: str = ""


NAVIGATION_NODES: tuple[NavigationNode, ...] = (
    NavigationNode("home", "HOME", "section"),
    NavigationNode("home.project", "Project Data", "route", parent="home", icon="home",
                   tooltip="Project identity, operating case, model summary and validation status."),

    NavigationNode("model", "ROTOR MODEL", "section"),
    NavigationNode("model.shaft", "Shaft", "route", parent="model", icon="shaft",
                   tooltip="Physical shaft sections, material and finite-element discretization."),
    NavigationNode("model.masses", "Disks / Masses", "route", parent="model", icon="disk",
                   tooltip="Rigid disks, distributed rotor masses and concentrated masses."),

    NavigationNode("model.bearings", "Bearing Studio", "group", parent="model", icon="bearing"),
    NavigationNode("model.bearings.general", "General Bearing Models", "route",
                   parent="model.bearings", icon="bearing"),
    NavigationNode("model.bearings.fluid_film", "Fluid-Film Bearing Models", "route",
                   parent="model.bearings", icon="bearing"),
    NavigationNode("model.bearings.amb", "Active Magnetic Bearings", "route",
                   parent="model.bearings", icon="bearing",
                   tooltip="Native MagneticBearingElement with PID feedback, Newmark time integration and ISO 14839 sensitivity."),

    NavigationNode("model.seals", "Seals", "route", parent="model", icon="seal"),
    NavigationNode("model.supports", "Supports", "group", parent="model", icon="support"),
    NavigationNode("model.supports.flexible", "Bearing / Flexible Supports", "route",
                   parent="model.supports", icon="support"),
    NavigationNode("model.supports.foundation", "Foundation", "route",
                   parent="model.supports", icon="support",
                   tooltip="Foundation is a distinct subsystem from local bearing/support K/C."),

    NavigationNode("model.couplings", "Couplings", "route", parent="model", icon="coupling"),

    NavigationNode("model.loads", "Loads", "group", parent="model", icon="loads"),
    NavigationNode("model.loads.unbalance", "Unbalance", "route",
                   parent="model.loads", icon="loads"),
    NavigationNode("model.loads.harmonic", "Harmonic / External Force", "route",
                   parent="model.loads", icon="wave"),
    NavigationNode("model.loads.electromagnetic", "Electromagnetic / UMP", "route",
                   parent="model.loads", icon="wave"),

    NavigationNode("model.probes", "Probes", "route", parent="model", icon="probe"),

    NavigationNode("analysis", "ANALYSIS", "section"),
    NavigationNode("analysis.static_modal", "Static & Modal", "group",
                   parent="analysis", icon="wave"),
    NavigationNode("analysis.static_modal.lateral", "Lateral Analysis", "route",
                   parent="analysis.static_modal", icon="wave"),
    NavigationNode("analysis.static_modal.torsional", "Torsional Analysis", "route",
                   parent="analysis.static_modal", icon="wave"),
    NavigationNode("analysis.time_frequency", "Time & Frequency", "route",
                   parent="analysis", icon="response"),
    NavigationNode("analysis.stochastic", "Stochastic", "route",
                   parent="analysis", icon="stochastic"),
    NavigationNode("analysis.multirotor", "MultiRotor System", "route",
                   parent="analysis", icon="rotor"),
)


_BY_ID = {node.id: node for node in NAVIGATION_NODES}
if len(_BY_ID) != len(NAVIGATION_NODES):  # pragma: no cover - import-time architecture guard
    raise RuntimeError("Navigation registry contains duplicate ids.")


LEGACY_ROUTE_ALIASES: dict[str, str] = {
    "home": "home.project",
    "rotor": "model.shaft",
    "shaft": "model.shaft",
    "disks": "model.masses",
    "bearings": "model.bearings.general",
    "seals": "model.seals",
    "supports": "model.supports.flexible",
    "couplings": "model.couplings",
    "loads": "model.loads.unbalance",
    "ump": "model.loads.electromagnetic",
    "probes": "model.probes",
    "rotor_dynamics": "analysis.static_modal.lateral",
    "stability": "analysis.static_modal.lateral",
    "response": "analysis.time_frequency",
    "transient": "analysis.time_frequency",
    "faults": "analysis.time_frequency",
    "stochastic": "analysis.stochastic",
    # Historical global Results remains an internal compatibility alias only.
    "results": "analysis.static_modal.lateral",
}


def navigation_node(node_id: str) -> NavigationNode:
    return _BY_ID[node_id]


def canonical_route(route_id: str) -> str:
    candidate = LEGACY_ROUTE_ALIASES.get(route_id, route_id)
    node = _BY_ID.get(candidate)
    if node is None or node.kind != "route":
        raise KeyError(f"Unknown navigation route {route_id!r}.")
    return candidate


def children(parent_id: str) -> tuple[NavigationNode, ...]:
    return tuple(node for node in NAVIGATION_NODES if node.parent == parent_id)


def sections() -> tuple[NavigationNode, ...]:
    return tuple(node for node in NAVIGATION_NODES if node.kind == "section")


def public_routes() -> tuple[str, ...]:
    return tuple(node.id for node in NAVIGATION_NODES if node.kind == "route")


__all__ = [
    "LEGACY_ROUTE_ALIASES",
    "NAVIGATION_NODES",
    "NavigationNode",
    "canonical_route",
    "children",
    "navigation_node",
    "public_routes",
    "sections",
]
