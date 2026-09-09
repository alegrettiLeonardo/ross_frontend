from __future__ import annotations

from math import pi
from typing import Any

import numpy as np

from .ross_backend import RossBackend, RossBuildResult
from .ross_compat import RossCompatibilityNote, install_ross_compatibility


class RossAnalysisBackend(RossBackend):
    """ROSS execution adapter that reuses one strict Rotor build across analyses."""

    def __init__(self, ross_module: Any | None = None) -> None:
        super().__init__(ross_module)
        self.compatibility_notes: tuple[RossCompatibilityNote, ...] = install_ross_compatibility(
            self.builder._ross()
        )

    @staticmethod
    def run_static_build(build: RossBuildResult) -> Any:
        return build.rotor.run_static()

    @staticmethod
    def run_modal_build(build: RossBuildResult, speed_rpm: float, *, num_modes: int = 12) -> Any:
        speed = float(speed_rpm) * 2.0 * pi / 60.0
        return build.rotor.run_modal(speed=speed, num_modes=num_modes)

    @staticmethod
    def run_campbell_build(
        build: RossBuildResult,
        speeds_rpm: list[float],
        *,
        frequencies: int = 6,
    ) -> Any:
        speeds = np.asarray(speeds_rpm, dtype=float) * 2.0 * pi / 60.0
        return build.rotor.run_campbell(speed_range=speeds, frequencies=frequencies)

    @staticmethod
    def run_unbalance_build(
        build: RossBuildResult,
        nodes: list[int],
        magnitudes_kg_m: list[float],
        phases_rad: list[float],
        speeds_rpm: list[float],
    ) -> Any:
        frequency = np.asarray(speeds_rpm, dtype=float) * 2.0 * pi / 60.0
        return build.rotor.run_unbalance_response(
            node=nodes,
            unbalance_magnitude=magnitudes_kg_m,
            unbalance_phase=phases_rad,
            frequency=frequency,
        )


__all__ = ["RossAnalysisBackend"]
