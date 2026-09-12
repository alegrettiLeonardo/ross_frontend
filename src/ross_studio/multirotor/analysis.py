from __future__ import annotations

from dataclasses import dataclass, field
from math import pi
from time import perf_counter
from typing import Any, Callable

import numpy as np

from ..domain import EngineeringError
from .builder import MultiRotorBuildResult, MultiRotorBuilder
from .domain import METHOD_QUALIFICATION, MultiRotorMethodStatus, MultiRotorProject


ProgressCallback = Callable[[str, str], None]


@dataclass(slots=True, frozen=True)
class NodeRef:
    rotor_index: int
    local_node: int


@dataclass(slots=True, frozen=True)
class ModalRequest:
    speed_rpm: float
    num_modes: int = 26


@dataclass(slots=True, frozen=True)
class CampbellRequest:
    min_speed_rpm: float = 0.0
    max_speed_rpm: float = 5000.0
    points: int = 51
    frequencies: int = 13


@dataclass(slots=True, frozen=True)
class FrequencyResponseRequest:
    min_speed_rpm: float = 0.0
    max_speed_rpm: float = 5000.0
    points: int = 101


@dataclass(slots=True, frozen=True)
class UnbalanceRequest:
    nodes: tuple[NodeRef, ...]
    magnitudes_kg_m: tuple[float, ...]
    phases_deg: tuple[float, ...]
    min_speed_rpm: float = 0.0
    max_speed_rpm: float = 5000.0
    points: int = 101


@dataclass(slots=True, frozen=True)
class TimeResponseRequest:
    speed_rpm: float
    duration_s: float = 0.2
    samples: int = 2001
    unbalance_nodes: tuple[NodeRef, ...] = ()
    unbalance_magnitudes_kg_m: tuple[float, ...] = ()
    unbalance_phases_deg: tuple[float, ...] = ()
    method: str = "newmark"


@dataclass(slots=True, frozen=True)
class HarmonicBalanceRequest:
    speed_rpm: float
    duration_s: float = 0.2
    samples: int = 1001
    forces: tuple[dict[str, object], ...] = ()
    n_harmonics: int = 1
    gravity: bool = False


@dataclass(slots=True)
class MultiRotorAnalysisResult:
    kind: str
    build: MultiRotorBuildResult
    native_result: Any
    elapsed_s: float
    audits: list[str] = field(default_factory=list)
    metadata: dict[str, object] = field(default_factory=dict)


class MultiRotorAnalysisService:
    """Native ROSS MultiRotor analysis boundary.

    Speeds are always supplied as the driving-rotor speed. Driven-shaft
    unbalance physics is delegated to ROSS ``MultiRotor.check_speed()`` through
    the native response methods; the Studio does not duplicate gear-ratio/sign
    logic.
    """

    def __init__(self, builder: MultiRotorBuilder | None = None) -> None:
        self.builder = builder or MultiRotorBuilder()

    @staticmethod
    def _emit(progress: ProgressCallback | None, stage: str, state: str) -> None:
        if progress is not None:
            progress(stage, state)

    @staticmethod
    def _require(kind: str) -> None:
        status = METHOD_QUALIFICATION[kind]
        if status == MultiRotorMethodStatus.BLOCKED:
            raise EngineeringError(
                f"{kind} is not qualified for ROSS MultiRotor 2.3.0 and is intentionally blocked."
            )
        if status == MultiRotorMethodStatus.EXPERIMENTAL:
            raise EngineeringError(
                f"{kind} remains EXPERIMENTAL / qualification pending for ROSS MultiRotor 2.3.0."
            )

    @staticmethod
    def _speed_rad_s(rpm: float) -> float:
        if rpm < 0:
            raise EngineeringError(f"Driving-rotor speed must be >= 0 rpm; received {rpm:g}.")
        return float(rpm) * 2.0 * pi / 60.0

    @staticmethod
    def _speed_grid(min_rpm: float, max_rpm: float, points: int) -> np.ndarray:
        if min_rpm < 0 or max_rpm <= min_rpm:
            raise EngineeringError("Speed range must satisfy 0 <= min < max rpm.")
        if points < 2:
            raise EngineeringError("Speed range requires at least two points.")
        return np.linspace(min_rpm, max_rpm, int(points)) * 2.0 * pi / 60.0

    @staticmethod
    def _node(build: MultiRotorBuildResult, ref: NodeRef) -> int:
        return build.global_node(ref.rotor_index, ref.local_node)

    def _build(self, project: MultiRotorProject, progress: ProgressCallback | None) -> MultiRotorBuildResult:
        self._emit(progress, "MultiRotor · Strict assembly", "running")
        build = self.builder.build(project)
        self._emit(progress, "MultiRotor · Strict assembly", "completed")
        return build

    def run_modal(self, project: MultiRotorProject, request: ModalRequest, *, progress: ProgressCallback | None = None) -> MultiRotorAnalysisResult:
        self._require("modal")
        build = self._build(project, progress)
        speed = self._speed_rad_s(request.speed_rpm)
        if request.num_modes < 4 or request.num_modes % 2:
            raise EngineeringError("MultiRotor modal num_modes must be an even integer >= 4.")
        start = perf_counter()
        self._emit(progress, "MultiRotor · Modal", "running")
        result = build.rotor.run_modal(speed=speed, num_modes=request.num_modes)
        self._emit(progress, "MultiRotor · Modal", "completed")
        return MultiRotorAnalysisResult("modal", build, result, perf_counter() - start, audits=["Driving-rotor speed supplied to native MultiRotor.run_modal()."], metadata={"driving_speed_rpm": request.speed_rpm})

    def run_campbell(self, project: MultiRotorProject, request: CampbellRequest, *, progress: ProgressCallback | None = None) -> MultiRotorAnalysisResult:
        self._require("campbell")
        build = self._build(project, progress)
        speed = self._speed_grid(request.min_speed_rpm, request.max_speed_rpm, request.points)
        if request.frequencies < 2:
            raise EngineeringError("Campbell requires at least two tracked frequencies.")
        start = perf_counter()
        self._emit(progress, "MultiRotor · Campbell", "running")
        result = build.rotor.run_campbell(speed, frequencies=request.frequencies)
        self._emit(progress, "MultiRotor · Campbell", "completed")
        return MultiRotorAnalysisResult("campbell", build, result, perf_counter() - start, audits=["Campbell speed grid is referenced to the driving rotor."], metadata={"speed_range_rpm": [request.min_speed_rpm, request.max_speed_rpm], "harmonics": [1.0, *[abs(value) for value in build.connection_ratios]]})

    def run_frequency_response(self, project: MultiRotorProject, request: FrequencyResponseRequest, *, progress: ProgressCallback | None = None) -> MultiRotorAnalysisResult:
        self._require("frequency_response")
        build = self._build(project, progress)
        speed = self._speed_grid(request.min_speed_rpm, request.max_speed_rpm, request.points)
        start = perf_counter()
        self._emit(progress, "MultiRotor · Frequency response", "running")
        result = build.rotor.run_freq_response(speed_range=speed)
        self._emit(progress, "MultiRotor · Frequency response", "completed")
        return MultiRotorAnalysisResult("frequency_response", build, result, perf_counter() - start)

    def run_unbalance(self, project: MultiRotorProject, request: UnbalanceRequest, *, progress: ProgressCallback | None = None) -> MultiRotorAnalysisResult:
        self._require("unbalance_response")
        count = len(request.nodes)
        if not (count and count == len(request.magnitudes_kg_m) == len(request.phases_deg)):
            raise EngineeringError("Unbalance nodes, magnitudes and phases must have the same non-zero length.")
        build = self._build(project, progress)
        nodes = [self._node(build, ref) for ref in request.nodes]
        frequency = self._speed_grid(request.min_speed_rpm, request.max_speed_rpm, request.points)
        phases = np.deg2rad(np.asarray(request.phases_deg, dtype=float))
        start = perf_counter()
        self._emit(progress, "MultiRotor · Unbalance", "running")
        result = build.rotor.run_unbalance_response(node=nodes, unbalance_magnitude=list(request.magnitudes_kg_m), unbalance_phase=phases.tolist(), frequency=frequency)
        self._emit(progress, "MultiRotor · Unbalance", "completed")
        physical_speeds = {f"rotor{ref.rotor_index}:node{ref.local_node}": float(build.rotor.check_speed(node, self._speed_rad_s(request.max_speed_rpm))) for ref, node in zip(request.nodes, nodes)}
        return MultiRotorAnalysisResult("unbalance_response", build, result, perf_counter() - start, audits=["Unbalance speed/sign delegated to native MultiRotor.check_speed()."], metadata={"physical_speed_rad_s_at_max": physical_speeds})

    def run_time_response(self, project: MultiRotorProject, request: TimeResponseRequest, *, progress: ProgressCallback | None = None) -> MultiRotorAnalysisResult:
        self._require("time_response")
        if request.duration_s <= 0 or request.samples < 3:
            raise EngineeringError("Time response requires duration > 0 and at least three samples.")
        if not (len(request.unbalance_nodes) == len(request.unbalance_magnitudes_kg_m) == len(request.unbalance_phases_deg)):
            raise EngineeringError("Time-response unbalance arrays must have equal lengths.")
        build = self._build(project, progress)
        rotor = build.rotor
        t = np.linspace(0.0, request.duration_s, int(request.samples))
        speed = self._speed_rad_s(request.speed_rpm)
        if request.unbalance_nodes:
            nodes = [self._node(build, ref) for ref in request.unbalance_nodes]
            F = rotor.unbalance_force_over_time(node=nodes, magnitude=list(request.unbalance_magnitudes_kg_m), phase=np.deg2rad(np.asarray(request.unbalance_phases_deg, dtype=float)).tolist(), omega=speed, t=t).T
        else:
            F = np.zeros((len(t), rotor.ndof))
        start = perf_counter()
        self._emit(progress, "MultiRotor · Time response", "running")
        result = rotor.run_time_response(speed=speed, F=F, t=t, method=request.method)
        self._emit(progress, "MultiRotor · Time response", "completed")
        metadata: dict[str, object] = {"mesh_dynamics": bool(hasattr(result, "mesh_dynamics"))}
        if hasattr(result, "mesh_dynamics"):
            metadata["mesh_keys"] = sorted(result.mesh_dynamics)
        return MultiRotorAnalysisResult("time_response", build, result, perf_counter() - start, audits=["Transient unbalance force uses native MultiRotor.unbalance_force_over_time()."], metadata=metadata)

    def run_harmonic_balance(self, project: MultiRotorProject, request: HarmonicBalanceRequest, *, progress: ProgressCallback | None = None) -> MultiRotorAnalysisResult:
        self._require("harmonic_balance")
        if request.duration_s <= 0 or request.samples < 3:
            raise EngineeringError("HBM requires duration > 0 and at least three time samples.")
        build = self._build(project, progress)
        speed = self._speed_rad_s(request.speed_rpm)
        t = np.linspace(0.0, request.duration_s, int(request.samples))
        forces: list[dict[str, object]] = []
        for force in request.forces:
            row = dict(force)
            ref = row.pop("node_ref", None)
            if isinstance(ref, NodeRef):
                row["node"] = self._node(build, ref)
            elif "node" not in row:
                raise EngineeringError("HBM force requires node_ref or global node.")
            forces.append(row)
        start = perf_counter()
        self._emit(progress, "MultiRotor · Harmonic Balance", "running")
        result = build.rotor.run_harmonic_balance_response(speed=speed, t=t, harmonic_forces=forces, gravity=request.gravity, n_harmonics=request.n_harmonics)
        self._emit(progress, "MultiRotor · Harmonic Balance", "completed")
        return MultiRotorAnalysisResult("harmonic_balance", build, result, perf_counter() - start)

    def run_blocked(self, kind: str, *args, **kwargs):
        if kind not in METHOD_QUALIFICATION:
            raise EngineeringError(f"Unknown MultiRotor method {kind!r}.")
        self._require(kind)
        raise AssertionError("Qualified methods must use their dedicated service entry point.")


__all__ = ["CampbellRequest", "FrequencyResponseRequest", "HarmonicBalanceRequest", "ModalRequest", "MultiRotorAnalysisResult", "MultiRotorAnalysisService", "NodeRef", "TimeResponseRequest", "UnbalanceRequest"]
