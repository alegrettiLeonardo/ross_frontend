from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, pi
from time import perf_counter
from typing import Any

from .domain import EngineeringError, RotorProject
from .ross_backend import RossBuildResult
from .time_frequency_analysis import _TimeFrequencyService


@dataclass(slots=True, frozen=True)
class AMBSensitivityRequest:
    speed_rpm: float = 0.0
    t_max_s: float = 45.0
    dt_s: float = 1e-3
    disturbance_amplitude_m: float = 1e-5
    min_frequency_hz: float = 0.001
    max_frequency_hz: float = 150.0
    amb_tags: tuple[str, ...] | None = None

    def validate(self) -> None:
        if not isfinite(self.speed_rpm) or self.speed_rpm < 0:
            raise EngineeringError("AMB sensitivity speed must be >= 0 rpm.")
        if not isfinite(self.t_max_s) or self.t_max_s <= 0:
            raise EngineeringError("AMB sensitivity t_max must be > 0 s.")
        if not isfinite(self.dt_s) or self.dt_s <= 0 or self.dt_s >= self.t_max_s:
            raise EngineeringError("AMB sensitivity dt must satisfy 0 < dt < t_max.")
        if self.t_max_s / self.dt_s > 500_000:
            raise EngineeringError("AMB sensitivity is limited to 500000 time steps in ROSS Studio.")
        if not isfinite(self.disturbance_amplitude_m) or self.disturbance_amplitude_m <= 0:
            raise EngineeringError("AMB sensitivity disturbance amplitude must be > 0 m.")
        if self.min_frequency_hz <= 0 or self.max_frequency_hz <= self.min_frequency_hz:
            raise EngineeringError("AMB sensitivity frequency range must satisfy 0 < min < max.")


@dataclass(slots=True)
class AMBSensitivityAnalysisResult:
    project_name: str
    build: RossBuildResult
    request: AMBSensitivityRequest
    native: Any
    elapsed_s: float
    amb_tags: tuple[str, ...]


class AMBSensitivityService(_TimeFrequencyService):
    """Native ``Rotor.run_amb_sensitivity`` transaction."""

    def run(self, project: RotorProject, request: AMBSensitivityRequest) -> AMBSensitivityAnalysisResult:
        project.validate()
        request.validate()
        elapsed: dict[str, float] = {}
        build = self._build(project, elapsed, progress=None, cancelled=None, label="AMB Sensitivity")
        magnetic = [element for element in build.rotor.bearing_elements if type(element).__name__ == "MagneticBearingElement"]
        if not magnetic:
            raise EngineeringError("AMB sensitivity requires at least one applied MagneticBearingElement.")
        available = tuple(str(getattr(element, "tag", "") or f"AMB {index}") for index, element in enumerate(magnetic))
        tags = available if request.amb_tags is None else tuple(request.amb_tags)
        unknown = sorted(set(tags) - set(available))
        if unknown:
            raise EngineeringError(f"AMB sensitivity requested unknown tags: {', '.join(unknown)}")
        start = perf_counter()
        native = build.rotor.run_amb_sensitivity(
            speed=float(request.speed_rpm) * 2.0 * pi / 60.0,
            t_max=float(request.t_max_s),
            dt=float(request.dt_s),
            disturbance_amplitude=float(request.disturbance_amplitude_m),
            disturbance_min_frequency=float(request.min_frequency_hz),
            disturbance_max_frequency=float(request.max_frequency_hz),
            amb_tags=list(tags),
            verbose=0,
        )
        return AMBSensitivityAnalysisResult(
            project_name=project.name,
            build=build,
            request=request,
            native=native,
            elapsed_s=perf_counter() - start + sum(elapsed.values()),
            amb_tags=tags,
        )


__all__ = ["AMBSensitivityAnalysisResult", "AMBSensitivityRequest", "AMBSensitivityService"]
