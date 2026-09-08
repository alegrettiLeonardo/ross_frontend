from __future__ import annotations

from dataclasses import dataclass
from math import pi
from typing import Any


@dataclass(frozen=True, slots=True)
class RossLateralCoefficients:
    kxx: Any
    kyy: Any
    kxy: Any
    kyx: Any
    cxx: Any
    cyy: Any
    cxy: Any
    cyx: Any


def rotordin_xz_to_ross_xy(*, kxx, kzz, kxz, kzx, cxx, czz, cxz, czx) -> RossLateralCoefficients:
    """Map the historical RotorDin lateral x/z convention to ROSS x/y.

    ROSS uses z for the axial direction. Therefore copying RotorDin kzz/czz into
    ROSS kzz/czz would create an axial bearing and is physically wrong.
    """
    return RossLateralCoefficients(
        kxx=kxx,
        kyy=kzz,
        kxy=kxz,
        kyx=kzx,
        cxx=cxx,
        cyy=czz,
        cxy=cxz,
        cyx=czx,
    )


def rpm_to_rad_s(value):
    if isinstance(value, (list, tuple)):
        return [float(v) * 2.0 * pi / 60.0 for v in value]
    return float(value) * 2.0 * pi / 60.0


def rad_s_to_rpm(value: float) -> float:
    return float(value) * 60.0 / (2.0 * pi)
