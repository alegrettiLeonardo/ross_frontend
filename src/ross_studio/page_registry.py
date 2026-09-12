from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .navigation_registry import public_routes


PageOwner = Literal["home", "rotor", "bearing", "foundation", "analysis"]


@dataclass(frozen=True, slots=True)
class PageRouteSpec:
    route_id: str
    owner: PageOwner
    editor_key: str | None = None
    bearing_group: str | None = None
    title: str = ""
    implementation_phase: str = "0.17.0"
    operational: bool = True
    note: str = ""


PAGE_ROUTES: dict[str, PageRouteSpec] = {
    "home.project": PageRouteSpec("home.project", "home", title="Project Data"),
    "model.shaft": PageRouteSpec("model.shaft", "rotor", editor_key="shaft", title="Shaft"),
    "model.masses": PageRouteSpec("model.masses", "rotor", editor_key="disks", title="Disks / Masses"),
    "model.bearings.general": PageRouteSpec(
        "model.bearings.general", "bearing", bearing_group="General / Parametric", title="General Bearing Models"
    ),
    "model.bearings.fluid_film": PageRouteSpec(
        "model.bearings.fluid_film", "bearing", bearing_group="THD", title="Fluid-Film Bearing Models"
    ),
    "model.bearings.amb": PageRouteSpec(
        "model.bearings.amb", "bearing", bearing_group="AMB", title="Active Magnetic Bearings", operational=False,
        note="Blocked until the AMB actuator/sensor/controller/Newmark feedback contract is qualified.",
    ),
    "model.seals": PageRouteSpec("model.seals", "rotor", editor_key="seals", title="Seals"),
    "model.supports.flexible": PageRouteSpec(
        "model.supports.flexible", "rotor", editor_key="supports", title="Bearing / Flexible Supports"
    ),
    "model.supports.foundation": PageRouteSpec(
        "model.supports.foundation", "foundation", title="Foundation", implementation_phase="0.24.0",
        operational=False,
        note=(
            "Foundation Studio 0.24 tranche B is active: FoundationSpec, schema-2 persistence and strict "
            "bearing→support→foundation→ground assembly are implemented; editor and complete scientific/frozen gates remain under qualification."
        ),
    ),
    "model.couplings": PageRouteSpec("model.couplings", "rotor", editor_key="couplings", title="Couplings"),
    "model.loads.unbalance": PageRouteSpec(
        "model.loads.unbalance", "rotor", editor_key="loads", title="Unbalance", implementation_phase="0.18.0",
        note="Qualified legacy LoadSpec editor retained pending typed load schemas.",
    ),
    "model.loads.harmonic": PageRouteSpec(
        "model.loads.harmonic", "rotor", editor_key="loads", title="Harmonic / External Force",
        implementation_phase="0.18.0", note="Routes to the existing qualified load workspace without inventing a new force model.",
    ),
    "model.loads.electromagnetic": PageRouteSpec(
        "model.loads.electromagnetic", "rotor", editor_key="ump", title="Electromagnetic / UMP",
        note="The existing qualified UMP source is preserved; only its navigation ownership changes.",
    ),
    "model.probes": PageRouteSpec("model.probes", "rotor", editor_key="probes", title="Probes"),
    "analysis.static_modal.lateral": PageRouteSpec(
        "analysis.static_modal.lateral", "analysis", title="Lateral Analysis", implementation_phase="0.20.0",
        operational=True,
        note="Decoupled native ROSS transactions: Static owns only run_static(); Modal owns run_modal()/run_campbell() with independent caches.",
    ),
    "analysis.static_modal.torsional": PageRouteSpec(
        "analysis.static_modal.torsional", "analysis", title="Torsional Analysis", implementation_phase="0.20.0",
        operational=True,
        note="Independent Modal/Campbell transaction; torsional modes come from ROSS shape.mode_type and retain native 3D animation.",
    ),
    "analysis.time_frequency": PageRouteSpec(
        "analysis.time_frequency", "analysis", title="Time & Frequency", implementation_phase="0.21.0", operational=True,
        note=(
            "Independent native ROSS run_freq_response(), run_unbalance_response(), run_time_response(), "
            "run_harmonic_balance_response(), run_ucs() and run_clearance_analysis() transactions with native plots."
        ),
    ),
    "analysis.stochastic": PageRouteSpec(
        "analysis.stochastic", "analysis", title="Stochastic", implementation_phase="0.22.0", operational=True,
        note=(
            "Native ross.stochastic ST_Material/ST_ShaftElement/ST_DiskElement/ST_BearingElement/ST_PointMass + ST_Rotor; "
            "Campbell, Frequency Response, Unbalance Response and Time Response retain ROSS mean/percentile/confidence outputs."
        ),
    ),
    "analysis.multirotor": PageRouteSpec(
        "analysis.multirotor", "analysis", title="MultiRotor System", implementation_phase="0.23.0", operational=True,
        note=(
            "Native GearElement/GearElementTVMS + MultiRotor. Speeds are referenced to the driving rotor; "
            "run_static/run_ucs/run_level1 remain explicitly blocked and critical speed remains experimental."
        ),
    ),
}

_missing = set(public_routes()) - set(PAGE_ROUTES)
_extra = set(PAGE_ROUTES) - set(public_routes())
if _missing or _extra:
    raise RuntimeError(f"Page registry mismatch: missing={sorted(_missing)}, extra={sorted(_extra)}")


def route_spec(route_id: str) -> PageRouteSpec:
    return PAGE_ROUTES[route_id]


__all__ = ["PAGE_ROUTES", "PageRouteSpec", "route_spec"]
