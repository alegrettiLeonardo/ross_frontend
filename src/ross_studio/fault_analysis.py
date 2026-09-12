from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite, pi
from time import perf_counter
from typing import Any

import numpy as np

from .domain import EngineeringError, RotorProject
from .ross_backend import RossBuildResult
from .time_frequency_analysis import NativeProbe, _TimeFrequencyService


@dataclass(slots=True, frozen=True)
class MisalignmentRequest:
    speed_rpm: float
    duration_s: float = 2.0
    samples: int = 4001
    coupling: str = "flex"
    element_n: int = 0
    mis_type: str = "parallel"
    mis_distance_x_m: float = 2e-4
    mis_distance_y_m: float = 2e-4
    mis_angle_rad: float = 0.0
    radial_stiffness_n_m: float = 40e3
    bending_stiffness_n_m: float = 38e3
    rigid_mis_distance_m: float = 2e-4
    input_torque_n_m: float = 0.0
    load_torque_n_m: float = 0.0

    def validate(self) -> None:
        _common_validate(self.speed_rpm, self.duration_s, self.samples, self.element_n)
        if self.coupling not in {"flex", "rigid"}:
            raise EngineeringError("Misalignment coupling must be 'flex' or 'rigid'.")
        if self.mis_type not in {"parallel", "angular", "combined"}:
            raise EngineeringError("Flexible misalignment type must be parallel, angular or combined.")
        if min(self.mis_distance_x_m, self.mis_distance_y_m, self.rigid_mis_distance_m) < 0:
            raise EngineeringError("Misalignment distances must be non-negative.")
        if min(self.radial_stiffness_n_m, self.bending_stiffness_n_m) < 0:
            raise EngineeringError("Flexible coupling stiffness values must be non-negative.")


@dataclass(slots=True, frozen=True)
class RubbingRequest:
    speed_rpm: float
    duration_s: float = 2.0
    samples: int = 4001
    element_n: int = 0
    distance_m: float = 1e-4
    contact_stiffness_n_m: float = 1e6
    contact_damping_n_s_m: float = 10.0
    friction_coeff: float = 0.1
    torque: bool = False

    def validate(self) -> None:
        _common_validate(self.speed_rpm, self.duration_s, self.samples, self.element_n)
        if self.distance_m <= 0 or self.contact_stiffness_n_m < 0 or self.contact_damping_n_s_m < 0:
            raise EngineeringError("Rubbing clearance must be > 0 and contact K/C must be non-negative.")
        if self.friction_coeff < 0:
            raise EngineeringError("Rubbing friction coefficient must be non-negative.")


@dataclass(slots=True, frozen=True)
class CrackRequest:
    speed_rpm: float
    duration_s: float = 2.0
    samples: int = 4001
    element_n: int = 0
    depth_ratio: float = 0.2
    crack_model: str = "Mayes"
    cross_divisions: int | None = None

    def validate(self) -> None:
        _common_validate(self.speed_rpm, self.duration_s, self.samples, self.element_n)
        if not 0 < self.depth_ratio < 1:
            raise EngineeringError("Crack depth_ratio must be between 0 and 1.")
        if self.crack_model not in {"Mayes", "Gasch"}:
            raise EngineeringError("Crack model must be 'Mayes' or 'Gasch'.")
        if self.cross_divisions is not None and self.cross_divisions < 4:
            raise EngineeringError("Crack cross_divisions must be >= 4 when supplied.")


def _common_validate(speed_rpm: float, duration_s: float, samples: int, element_n: int) -> None:
    if not isfinite(speed_rpm) or speed_rpm <= 0:
        raise EngineeringError("Fault speed must be > 0 rpm.")
    if not isfinite(duration_s) or duration_s <= 0:
        raise EngineeringError("Fault duration must be > 0 s.")
    if isinstance(samples, bool) or samples < 101 or samples > 200_000:
        raise EngineeringError("Fault samples must be between 101 and 200000.")
    if isinstance(element_n, bool) or element_n < 0:
        raise EngineeringError("Fault shaft element index n must be non-negative.")


@dataclass(slots=True)
class FaultAnalysisResult:
    kind: str
    project_name: str
    build: RossBuildResult
    request: MisalignmentRequest | RubbingRequest | CrackRequest
    native: Any
    time_s: np.ndarray
    probes: tuple[NativeProbe, ...]
    elapsed_s: float
    notes: list[str] = field(default_factory=list)


class FaultAnalysisService(_TimeFrequencyService):
    """Native ROSS Misalignment/Rubbing/Crack execution boundary."""

    def run(self, project: RotorProject, request: MisalignmentRequest | RubbingRequest | CrackRequest) -> FaultAnalysisResult:
        project.validate()
        request.validate()
        elapsed: dict[str, float] = {}
        build = self._build(project, elapsed, progress=None, cancelled=None, label="Fault")
        if request.element_n >= len(build.rotor.shaft_elements):
            raise EngineeringError(
                f"Fault element n={request.element_n} is outside the built shaft/coupling element range 0..{len(build.rotor.shaft_elements)-1}."
            )
        inputs = self._unbalance_inputs(project, build)
        applied = self._applied_unbalance(inputs)
        node = [item.node for item in applied]
        magnitude = [item.magnitude_kg_m for item in applied]
        phase = [item.phase_rad for item in applied]
        t = np.linspace(0.0, float(request.duration_s), int(request.samples), dtype=float)
        speed = float(request.speed_rpm) * 2.0 * pi / 60.0
        start = perf_counter()

        if isinstance(request, MisalignmentRequest):
            if request.coupling == "rigid":
                native = build.rotor.run_misalignment(
                    coupling="rigid", mis_distance=float(request.rigid_mis_distance_m),
                    input_torque=float(request.input_torque_n_m), load_torque=float(request.load_torque_n_m),
                    n=int(request.element_n), speed=speed, node=node, unbalance_magnitude=magnitude,
                    unbalance_phase=phase, t=t,
                )
            else:
                native = build.rotor.run_misalignment(
                    coupling="flex", mis_type=request.mis_type,
                    radial_stiffness=float(request.radial_stiffness_n_m),
                    bending_stiffness=float(request.bending_stiffness_n_m),
                    mis_distance_x=float(request.mis_distance_x_m),
                    mis_distance_y=float(request.mis_distance_y_m), mis_angle=float(request.mis_angle_rad),
                    input_torque=float(request.input_torque_n_m), load_torque=float(request.load_torque_n_m),
                    n=int(request.element_n), speed=speed, node=node, unbalance_magnitude=magnitude,
                    unbalance_phase=phase, t=t,
                )
            kind = "Misalignment"
        elif isinstance(request, RubbingRequest):
            native = build.rotor.run_rubbing(
                n=int(request.element_n), distance=float(request.distance_m),
                contact_stiffness=float(request.contact_stiffness_n_m),
                contact_damping=float(request.contact_damping_n_s_m), friction_coeff=float(request.friction_coeff),
                node=node, unbalance_magnitude=magnitude, unbalance_phase=phase, speed=speed, t=t,
                torque=bool(request.torque),
            )
            kind = "Rubbing"
        else:
            native = build.rotor.run_crack(
                n=int(request.element_n), depth_ratio=float(request.depth_ratio), node=node,
                unbalance_magnitude=magnitude, unbalance_phase=phase, speed=speed, t=t,
                crack_model=request.crack_model, cross_divisions=request.cross_divisions,
            )
            kind = "Crack"

        return FaultAnalysisResult(
            kind=kind,
            project_name=project.name,
            build=build,
            request=request,
            native=native,
            time_s=t,
            probes=self._probes(project, build),
            elapsed_s=perf_counter() - start + sum(elapsed.values()),
            notes=["Native ROSS fault solver retained; coupling fault is separate from structural CouplingElement."],
        )


__all__ = [
    "CrackRequest", "FaultAnalysisResult", "FaultAnalysisService", "MisalignmentRequest", "RubbingRequest"
]
