from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from .domain import BearingGroup


class BearingUiState(str, Enum):
    NO_STATION = "NO_STATION"
    MODEL_SELECTED = "MODEL_SELECTED"
    INPUT_READY = "INPUT_READY"
    CALCULATING = "CALCULATING"
    CALCULATED_PREVIEW = "CALCULATED_PREVIEW"
    STALE = "STALE"
    APPLIED = "APPLIED"
    ERROR = "ERROR"


@dataclass(frozen=True)
class BearingFieldSpec:
    key: str
    label: str
    section: str
    widget_type: str
    unit: str | None = None
    required: bool = True
    choices: tuple[str, ...] = ()
    visible_if: dict[str, Any] | None = None
    tooltip: str = ""
    advanced: bool = False


@dataclass(frozen=True)
class BearingModelSpec:
    key: str
    public_name: str
    ross_class: str
    family: BearingGroup
    icon_asset: str
    fields: tuple[BearingFieldSpec, ...]
    result_tabs: tuple[str, ...]
    additional_results: tuple[str, ...] = ()
    executable: bool = True
    axial: bool = False
    subtitle: str = ""


def F(
    key: str,
    label: str,
    section: str,
    widget_type: str,
    unit: str | None = None,
    *,
    required: bool = True,
    choices: tuple[str, ...] = (),
    visible_if: dict[str, Any] | None = None,
    tooltip: str = "",
    advanced: bool = False,
) -> BearingFieldSpec:
    return BearingFieldSpec(
        key, label, section, widget_type, unit, required, choices, visible_if, tooltip, advanced
    )


BALL = BearingModelSpec(
    key="ball",
    public_name="Ball Bearing",
    ross_class="BallBearingElement",
    family=BearingGroup.GENERAL,
    icon_asset="ball_bearing.svg",
    fields=(
        F("n_balls", "Number of balls", "Geometry", "int", tooltip="ROSS BallBearingElement.n_balls"),
        F("d_balls_mm", "Ball diameter", "Geometry", "float", "mm", tooltip="ROSS d_balls; converted to m at the scientific boundary."),
        F("contact_angle_deg", "Contact angle", "Geometry", "float", "deg", tooltip="ROSS alpha; converted to rad at the scientific boundary."),
        F("static_load_n", "Static radial load", "Operation", "float", "N", tooltip="ROSS fs"),
    ),
    result_tabs=("K & C Coefficients",),
)

ROLLER = BearingModelSpec(
    key="roller",
    public_name="Roller Bearing",
    ross_class="RollerBearingElement",
    family=BearingGroup.GENERAL,
    icon_asset="roller_bearing.svg",
    fields=(
        F("n_rollers", "Number of rollers", "Geometry", "int", tooltip="ROSS RollerBearingElement.n_rollers"),
        F("roller_length_mm", "Roller length", "Geometry", "float", "mm", tooltip="ROSS l_rollers; converted to m at the scientific boundary."),
        F("contact_angle_deg", "Contact angle", "Geometry", "float", "deg", tooltip="ROSS alpha; converted to rad at the scientific boundary."),
        F("static_load_n", "Static radial load", "Operation", "float", "N", tooltip="ROSS fs"),
    ),
    result_tabs=("K & C Coefficients",),
)

CYLINDRICAL = BearingModelSpec(
    key="cyl",
    public_name="Cylindrical",
    ross_class="CylindricalBearing",
    family=BearingGroup.GENERAL,
    icon_asset="cylindrical_bearing.svg",
    fields=(
        F("bearing_length_mm", "Bearing length", "Geometry", "float", "mm", tooltip="ROSS bearing_length"),
        F("journal_diameter_mm", "Journal diameter", "Geometry", "float", "mm", tooltip="ROSS journal_diameter"),
        F("radial_clearance_mm", "Radial clearance", "Geometry", "float", "mm", tooltip="ROSS radial_clearance"),
        F("speed_min_rpm", "Minimum speed", "Operation", "float", "RPM"),
        F("speed_max_rpm", "Maximum speed", "Operation", "float", "RPM"),
        F("speed_points", "Speed stations", "Operation", "int"),
        F("weight_n", "Supported weight / load", "Operation", "float", "N", tooltip="ROSS weight"),
        F("oil_viscosity_pa_s", "Oil viscosity", "Lubrication / Model", "float", "Pa·s", tooltip="ROSS oil_viscosity"),
    ),
    result_tabs=("K & C Coefficients",),
)

PLAIN = BearingModelSpec(
    key="plain",
    public_name="Plain Journal",
    ross_class="PlainJournal",
    family=BearingGroup.THD,
    icon_asset="plain_journal.svg",
    fields=(
        F("axial_length_mm", "Axial length", "Geometry", "float", "mm", tooltip="ROSS axial_length"),
        F("journal_diameter_mm", "Journal diameter", "Geometry", "float", "mm", tooltip="Converted to ROSS journal_radius."),
        F("radial_clearance_um", "Radial clearance", "Geometry", "float", "µm", tooltip="ROSS radial_clearance"),
        F("elements_circumferential", "Circumferential elements", "Geometry", "int"),
        F("elements_axial", "Axial elements", "Geometry", "int"),
        F("n_pad", "Number of pads", "Geometry", "int"),
        F("pad_arc_deg", "Pad arc", "Geometry", "float", "deg"),
        F("preload", "Preload", "Geometry", "float", "-"),
        F("geometry", "Geometry type", "Geometry", "choice", choices=("circular", "lobe", "elliptical")),
        F("speed_rpm", "Speed stations", "Operation", "vector", "RPM"),
        F("fxs_load_n", "Load X", "Operation", "float", "N"),
        F("fys_load_n", "Load Y", "Operation", "float", "N"),
        F("reference_temperature_c", "Oil / reference temperature", "Operation", "float", "°C"),
        F("operating_type", "Operating type", "Operation", "choice", choices=("flooded", "starvation")),
        F("oil_supply_pressure_bar", "Oil supply pressure", "Operation", "float", "bar", required=False),
        F("lubricant", "Lubricant", "Lubrication / Model", "text"),
        F("sommerfeld_type", "Sommerfeld type", "Lubrication / Model", "choice", choices=("1", "2")),
        F("method", "Coefficient method", "Lubrication / Model", "choice", choices=("perturbation", "lund")),
        F("initial_eccentricity_ratio", "Initial eccentricity ratio", "Lubrication / Model", "float", "-"),
        F("initial_attitude_angle_deg", "Initial attitude angle", "Lubrication / Model", "float", "deg"),
        F("groove_factor", "Groove factor per pad", "Lubrication / Model", "vector", "-", visible_if={"operating_type": "flooded"}),
        F("oil_flow_l_min", "Oil flow", "Lubrication / Model", "float", "L/min", visible_if={"operating_type": "starvation"}),
    ),
    result_tabs=("K & C Coefficients", "Pressure", "Temperature", "Convergence", "Dimensional"),
    additional_results=("Pressure Field", "Temperature Field", "Convergence", "Bearing Representation"),
)

TILTING = BearingModelSpec(
    key="tilting",
    public_name="Tilting Pad",
    ross_class="TiltingPad",
    family=BearingGroup.THD,
    icon_asset="tilting_pad.svg",
    fields=(
        F("journal_diameter_mm", "Journal diameter", "Geometry", "float", "mm"),
        F("radial_clearance_um", "Radial clearance", "Geometry", "float", "µm"),
        F("pad_thickness_mm", "Pad thickness", "Geometry", "float", "mm"),
        F("n_pads", "Number of pads", "Geometry", "int"),
        F("pad_data", "Pad geometry", "Geometry", "pad_table", tooltip="Edit per-pad pivot angle, arc, axial length, preload, offset and initial angle."),
        F("speed_rpm", "Speed stations", "Operation", "vector", "RPM"),
        F("fxs_load_n", "Load X", "Operation", "float", "N"),
        F("fys_load_n", "Load Y", "Operation", "float", "N"),
        F("oil_supply_temperature_c", "Oil inlet temperature", "Operation", "float", "°C"),
        F("lubricant", "Lubricant", "Lubrication / Model", "text"),
        F("nx", "Mesh circumferential", "Lubrication / Model", "int"),
        F("nz", "Mesh axial", "Lubrication / Model", "int"),
        F("thermal_type", "Thermal model", "Lubrication / Model", "choice", choices=("adiabatic", "full")),
        F("equilibrium_type", "Equilibrium type", "Lubrication / Model", "choice", choices=("match_eccentricity", "determine_eccentricity")),
        F("eccentricity_ratio", "Eccentricity", "Lubrication / Model", "float", "-"),
        F("attitude_angle_deg", "Attitude angle", "Lubrication / Model", "float", "deg"),
        F("xtol", "xtol", "Advanced", "float", advanced=True),
        F("ftol", "ftol", "Advanced", "float", advanced=True),
        F("maxiter", "maxiter", "Advanced", "int", advanced=True),
        F("nr_pad", "Pad radial mesh", "Advanced", "int", visible_if={"thermal_type": "full"}, advanced=True),
        F("k_pad", "Pad conductivity", "Advanced", "float", visible_if={"thermal_type": "full"}, advanced=True),
        F("h_edge", "Edge heat transfer", "Advanced", "float", visible_if={"thermal_type": "full"}, advanced=True),
        F("hot_oil_carry_over", "Hot oil carry over", "Advanced", "float", visible_if={"thermal_type": "full"}, advanced=True),
        F("journal_temperature", "Journal temperature", "Advanced", "float", "°C", visible_if={"thermal_type": "full"}, advanced=True),
        F("max_jtemp_iter", "Max journal temperature iterations", "Advanced", "int", visible_if={"thermal_type": "full"}, advanced=True),
        F("jtemp_error", "Journal temperature tolerance", "Advanced", "float", visible_if={"thermal_type": "full"}, advanced=True),
        F("max_inlet_iterations", "Max inlet iterations", "Advanced", "int", visible_if={"thermal_type": "full"}, advanced=True),
        F("inlet_temperature_tolerance", "Inlet temperature tolerance", "Advanced", "float", visible_if={"thermal_type": "full"}, advanced=True),
    ),
    result_tabs=("K & C Coefficients", "Pressure", "Temperature", "Film Thickness", "Convergence", "Dimensional"),
    additional_results=("Pressure Field", "Temperature Field", "Convergence", "Bearing Representation", "Pad Pressure", "Babbitt Temperature", "Solid Pad Temperature"),
)

THRUST = BearingModelSpec(
    key="thrust",
    public_name="Thrust Pad",
    ross_class="ThrustPad",
    family=BearingGroup.THD,
    icon_asset="thrust_pad.svg",
    fields=(
        F("pad_inner_radius_mm", "Pad inner radius", "Geometry", "float", "mm"),
        F("pad_outer_radius_mm", "Pad outer radius", "Geometry", "float", "mm"),
        F("pad_pivot_radius_mm", "Pad pivot radius", "Geometry", "float", "mm"),
        F("pad_arc_deg", "Pad arc length", "Geometry", "float", "deg"),
        F("angular_pivot_position_deg", "Angular pivot position", "Geometry", "float", "deg"),
        F("n_pad", "Number of pads", "Geometry", "int"),
        F("n_theta", "Circumferential mesh", "Geometry", "int"),
        F("n_radial", "Radial mesh", "Geometry", "int"),
        F("speed_rpm", "Speed stations", "Operation", "vector", "RPM"),
        F("axial_load_n", "Axial load", "Operation", "float", "N"),
        F("oil_supply_temperature_c", "Oil supply temperature", "Operation", "float", "°C"),
        F("equilibrium_position_mode", "Equilibrium mode", "Operation", "choice", choices=("calculate", "imposed")),
        F("radial_inclination_angle_mrad", "Radial inclination angle", "Operation", "float", "mrad"),
        F("circumferential_inclination_angle_mrad", "Circumferential inclination angle", "Operation", "float", "mrad"),
        F("initial_film_thickness_um", "Initial / imposed film thickness", "Operation", "float", "µm"),
        F("lubricant", "Lubricant", "Lubrication / Model", "text"),
    ),
    result_tabs=("K & C Coefficients", "Pressure", "Temperature", "Film Thickness", "Convergence"),
    additional_results=("Pressure Field", "Temperature Field", "Convergence"),
    axial=True,
)

SFD = BearingModelSpec(
    key="sfd",
    public_name="Squeeze Film Damper",
    subtitle="(SFD)",
    ross_class="SqueezeFilmDamper",
    family=BearingGroup.THD,
    icon_asset="squeeze_film_damper.svg",
    fields=(
        F("axial_length_mm", "Axial length", "Geometry", "float", "mm"),
        F("journal_diameter_mm", "Journal diameter", "Geometry", "float", "mm", tooltip="Converted to ROSS journal_radius."),
        F("radial_clearance_um", "Radial clearance", "Geometry", "float", "µm"),
        F("geometry", "Geometry", "Geometry", "choice", choices=("groove", "end_seals", "groove-end_seals")),
        F("speed_rpm", "Speed stations", "Operation", "vector", "RPM"),
        F("eccentricity_ratio", "Eccentricity ratio", "Operation", "float", "-"),
        F("lubricant", "Lubricant", "Lubrication / Model", "text"),
        F("cavitation", "Cavitation", "Lubrication / Model", "bool"),
    ),
    result_tabs=("K & C Coefficients", "Pressure"),
    additional_results=("Pressure Field",),
)

AMB = BearingModelSpec(
    key="amb",
    public_name="Magnetic Bearing",
    subtitle="(AMB)",
    ross_class="MagneticBearingElement",
    family=BearingGroup.AMB,
    icon_asset="magnetic_bearing.svg",
    executable=False,
    fields=(
        F("g0", "Nominal air gap", "Geometry", "float", "m"),
        F("i0", "Bias current", "Operation", "float", "A"),
        F("ag", "Pole area", "Geometry", "float", "m²"),
        F("nw", "Number of windings", "Geometry", "int"),
        F("alpha", "Pole angle", "Geometry", "float", "deg"),
        F("kp_pid", "PID Kp", "Lubrication / Model", "float"),
        F("ki_pid", "PID Ki", "Lubrication / Model", "float"),
        F("kd_pid", "PID Kd", "Lubrication / Model", "float"),
        F("k_sense", "Sensor gain", "Advanced", "float", advanced=True),
        F("k_amp", "Amplifier gain", "Advanced", "float", advanced=True),
        F("sensors_axis_rotation", "Sensor axis rotation", "Advanced", "float", "deg", advanced=True),
    ),
    result_tabs=(),
)


MODEL_SPECS: tuple[BearingModelSpec, ...] = (
    BALL,
    ROLLER,
    CYLINDRICAL,
    PLAIN,
    TILTING,
    THRUST,
    SFD,
    AMB,
)
MODEL_BY_KEY = {spec.key: spec for spec in MODEL_SPECS}
MODEL_BY_CLASS = {spec.ross_class: spec for spec in MODEL_SPECS}

PUBLIC_BEARING_CARD_INVENTORY = tuple(spec.public_name for spec in MODEL_SPECS)
PUBLIC_GROUPING = (
    (BearingGroup.GENERAL, tuple(spec.key for spec in MODEL_SPECS if spec.family == BearingGroup.GENERAL)),
    (BearingGroup.THD, tuple(spec.key for spec in MODEL_SPECS if spec.family == BearingGroup.THD)),
    (BearingGroup.AMB, tuple(spec.key for spec in MODEL_SPECS if spec.family == BearingGroup.AMB)),
)


def visible_fields(spec: BearingModelSpec, values: dict[str, Any], *, include_advanced: bool = False) -> tuple[BearingFieldSpec, ...]:
    result: list[BearingFieldSpec] = []
    for field in spec.fields:
        if field.advanced and not include_advanced:
            continue
        if field.visible_if:
            if any(values.get(key) != expected for key, expected in field.visible_if.items()):
                continue
        result.append(field)
    return tuple(result)


__all__ = [
    "BearingFieldSpec",
    "BearingModelSpec",
    "BearingUiState",
    "MODEL_SPECS",
    "MODEL_BY_KEY",
    "MODEL_BY_CLASS",
    "PUBLIC_BEARING_CARD_INVENTORY",
    "PUBLIC_GROUPING",
    "visible_fields",
]
