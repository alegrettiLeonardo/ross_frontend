from __future__ import annotations

from enum import StrEnum
from math import isclose
from typing import TYPE_CHECKING

from .domain import EngineeringError

if TYPE_CHECKING:
    from .domain import ShaftSection


class ShaftGeometryType(StrEnum):
    """Guided shaft geometries exposed by the ROSS Modeling tutorial.

    These labels intentionally match the terminology shown to the user in the
    ROSS shaft tutorial. The underlying scientific realization remains a native
    ``ross.ShaftElement`` with ``idl``, ``odl``, ``idr`` and ``odr``.
    """

    SOLID_CYLINDRICAL = "Solid cylindrical shaft element"
    SOLID_CONICAL = "Solid conical shaft element"
    HOLLOW_CYLINDRICAL = "Hollow cylindrical shaft element"
    HOLLOW_CONICAL = "Hollow conical shaft element"


GUIDED_SHAFT_GEOMETRIES: tuple[ShaftGeometryType, ...] = tuple(ShaftGeometryType)
CUSTOM_LEGACY_LABEL = "Custom / legacy ROSS shaft geometry"

_TOL = 1.0e-9


def _same(a: float, b: float) -> bool:
    return isclose(float(a), float(b), rel_tol=0.0, abs_tol=_TOL)


def classify_shaft_geometry(section: "ShaftSection") -> ShaftGeometryType | None:
    """Classify an existing physical section against the four tutorial families.

    The tutorial defines the guided families as:

    * solid cylindrical: ``idl == idr == 0`` and ``odl == odr``;
    * solid conical: ``idl == idr == 0`` and ``odl != odr``;
    * hollow cylindrical: ``idl == idr != 0`` and ``odl == odr``;
    * hollow conical: ``idl == idr != 0`` and ``odl != odr``.

    Existing imported geometries with a tapered bore (``idl != idr``) are retained
    as custom/legacy rather than silently coerced into one of these guided types.
    """

    id_left = float(section.id_left_mm)
    id_right = float(section.idr_mm)
    od_left = float(section.od_left_mm)
    od_right = float(section.odr_mm)

    ids_zero = _same(id_left, 0.0) and _same(id_right, 0.0)
    ids_equal_positive = id_left > _TOL and id_right > _TOL and _same(id_left, id_right)
    ods_equal = _same(od_left, od_right)

    if ids_zero and ods_equal:
        return ShaftGeometryType.SOLID_CYLINDRICAL
    if ids_zero and not ods_equal:
        return ShaftGeometryType.SOLID_CONICAL
    if ids_equal_positive and ods_equal:
        return ShaftGeometryType.HOLLOW_CYLINDRICAL
    if ids_equal_positive and not ods_equal:
        return ShaftGeometryType.HOLLOW_CONICAL
    return None


def display_shaft_geometry(section: "ShaftSection") -> str:
    geometry = classify_shaft_geometry(section)
    return geometry.value if geometry is not None else CUSTOM_LEGACY_LABEL


def tutorial_contract(geometry: ShaftGeometryType) -> str:
    return {
        ShaftGeometryType.SOLID_CYLINDRICAL: "idl = idr = 0; odl = odr",
        ShaftGeometryType.SOLID_CONICAL: "idl = idr = 0; odl != odr",
        ShaftGeometryType.HOLLOW_CYLINDRICAL: "idl = idr > 0; odl = odr",
        ShaftGeometryType.HOLLOW_CONICAL: "idl = idr > 0; odl != odr",
    }[geometry]


def guided_diameters(
    geometry: ShaftGeometryType,
    *,
    od_left_mm: float,
    od_right_mm: float,
    id_left_mm: float,
    id_right_mm: float,
) -> tuple[float, float, float, float]:
    """Return diameters normalized exactly to the selected tutorial family.

    No ROSS physics is reimplemented here. This is only an input-contract adapter
    that maps the guided GUI choice to the four diameter arguments consumed by
    ``ross.ShaftElement``.
    """

    od_left = float(od_left_mm)
    od_right = float(od_right_mm)
    id_left = float(id_left_mm)
    _ = float(id_right_mm)  # accepted for a stable editor API; guided types own idr.

    if od_left <= 0.0 or od_right <= 0.0:
        raise EngineeringError("Shaft outer diameters must be positive.")

    if geometry in {
        ShaftGeometryType.SOLID_CYLINDRICAL,
        ShaftGeometryType.HOLLOW_CYLINDRICAL,
    }:
        od_right = od_left
    elif _same(od_left, od_right):
        raise EngineeringError(
            f"{geometry.value} requires different left/right outer diameters (odl != odr)."
        )

    if geometry in {
        ShaftGeometryType.SOLID_CYLINDRICAL,
        ShaftGeometryType.SOLID_CONICAL,
    }:
        id_left = 0.0
        id_right = 0.0
    else:
        if id_left <= 0.0:
            raise EngineeringError(f"{geometry.value} requires a positive inner diameter.")
        id_right = id_left

    if id_left < 0.0 or id_right < 0.0:
        raise EngineeringError("Shaft inner diameters cannot be negative.")
    if id_left >= od_left or id_right >= od_right:
        raise EngineeringError("Shaft inner diameter must be smaller than the outer diameter at both ends.")

    return od_left, od_right, id_left, id_right


__all__ = [
    "CUSTOM_LEGACY_LABEL",
    "GUIDED_SHAFT_GEOMETRIES",
    "ShaftGeometryType",
    "classify_shaft_geometry",
    "display_shaft_geometry",
    "guided_diameters",
    "tutorial_contract",
]
