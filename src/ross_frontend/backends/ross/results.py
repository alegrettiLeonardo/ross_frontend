from __future__ import annotations

from math import pi
from typing import Any

from ..base import CriticalSpeedPoint
from ..coordinates import rad_s_to_rpm


def _list(value):
    if hasattr(value, "tolist"):
        return value.tolist()
    return list(value)


def _matrix(value):
    data = value.tolist() if hasattr(value, "tolist") else value
    return [list(row) for row in data]


def modal_summary(result: Any) -> dict[str, Any]:
    wd = _list(result.wd)
    return {
        "speed_rpm": rad_s_to_rpm(result.speed),
        "damped_frequency_hz": [float(v) / (2.0 * pi) for v in wd],
        "undamped_frequency_hz": [float(v) / (2.0 * pi) for v in _list(result.wn)],
        "damping_ratio": [float(v) for v in _list(result.damping_ratio)],
        "log_dec": [float(v) for v in _list(result.log_dec)],
    }


def critical_speed_summary(result: Any) -> tuple[dict[str, Any], list[CriticalSpeedPoint]]:
    rpm = [float(v) for v in _list(result.wd("rpm"))]
    damping = [float(v) for v in _list(result.damping_ratio)]
    log_dec = [float(v) for v in _list(result.log_dec)]
    whirl = [str(v) for v in _list(result.whirl_direction)]
    points = [
        CriticalSpeedPoint(
            rpm=value,
            hz=value / 60.0,
            damping_ratio=damping[i] if i < len(damping) else None,
            log_dec=log_dec[i] if i < len(log_dec) else None,
            whirl=whirl[i] if i < len(whirl) else "",
        )
        for i, value in enumerate(rpm)
    ]
    return {
        "damped_rpm": rpm,
        "undamped_rpm": [float(v) for v in _list(result.wn("rpm"))],
        "damping_ratio": damping,
        "log_dec": log_dec,
        "whirl_direction": whirl,
    }, points


def campbell_summary(result: Any) -> dict[str, Any]:
    return {
        "speed_rpm": [rad_s_to_rpm(v) for v in _list(result.speed_range)],
        "damped_frequency_hz": [[float(v) / (2.0 * pi) for v in row] for row in _matrix(result.wd)],
        "log_dec": _matrix(result.log_dec),
        "damping_ratio": _matrix(result.damping_ratio),
        "whirl_values": _matrix(result.whirl_values),
    }


def static_summary(result: Any) -> dict[str, Any]:
    return {
        "nodes": _list(result.nodes),
        "node_position_m": _list(result.nodes_pos),
        "deformation_m": _list(result.deformation),
        "bearing_forces_n": {str(k): float(v) for k, v in result.bearing_forces.items()},
        "disk_forces_n": {str(k): float(v) for k, v in result.disk_forces.items()},
    }
