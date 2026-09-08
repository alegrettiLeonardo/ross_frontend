from __future__ import annotations

from dataclasses import dataclass, field
from math import atan2, degrees, hypot, pi
from typing import Callable

from ...domain import RotorProject
from ..coordinates import rpm_to_rad_s
from .builder import RossModelBuilder

ResponseProgress = Callable[[str], None]


@dataclass(slots=True)
class FrequencyResponseRequest:
    start_rpm: float = 0.0
    final_rpm: float = 10000.0
    points: int = 201
    input_dof: int = 0
    output_dof: int = 0
    modes: list[int] | None = None

    def validate(self):
        if self.start_rpm < 0 or self.final_rpm <= self.start_rpm:
            raise ValueError("Frequency-response speed range is invalid.")
        if self.points < 2:
            raise ValueError("Frequency response requires at least two speed points.")
        if min(self.input_dof, self.output_dof) < 0:
            raise ValueError("FRF input/output DOF indices cannot be negative.")


@dataclass(slots=True)
class UnbalanceResponseRequest:
    node: int = 0
    probe_node: int | None = None
    magnitude_g_mm: float = 100.0
    phase_deg: float = 0.0
    start_rpm: float = 0.0
    final_rpm: float = 10000.0
    points: int = 201
    modes: list[int] | None = None

    def validate(self):
        if self.node < 0 or (self.probe_node is not None and self.probe_node < 0):
            raise ValueError("Unbalance/probe node indices cannot be negative.")
        if self.magnitude_g_mm < 0:
            raise ValueError("Unbalance magnitude cannot be negative.")
        if self.start_rpm < 0 or self.final_rpm <= self.start_rpm or self.points < 2:
            raise ValueError("Unbalance-response speed range is invalid.")


@dataclass(slots=True)
class TimeResponseRequest:
    node: int = 0
    speed_rpm: float = 1800.0
    force_x_n: float = 10.0
    force_y_n: float = 0.0
    excitation_hz: float = 30.0
    duration_s: float = 1.0
    time_step_s: float = 0.001
    method: str = "default"

    def validate(self):
        if self.node < 0:
            raise ValueError("Time-response node index cannot be negative.")
        if self.speed_rpm < 0 or self.excitation_hz < 0:
            raise ValueError("Time-response speed/frequency cannot be negative.")
        if self.duration_s <= 0 or self.time_step_s <= 0 or self.time_step_s >= self.duration_s:
            raise ValueError("Time-response duration/time step are invalid.")
        if self.method not in {"default", "newmark"}:
            raise ValueError("Time-response method must be 'default' or 'newmark'.")


@dataclass(slots=True)
class ComplexResponseCurve:
    x: list[float]
    magnitude: list[float]
    phase_deg: list[float]
    label: str
    magnitude_unit: str


@dataclass(slots=True)
class TimeResponseCurve:
    time_s: list[float]
    x_m: list[float]
    y_m: list[float]
    radial_m: list[float]


@dataclass(slots=True)
class RotorResponseResult:
    kind: str
    curves: list[ComplexResponseCurve] = field(default_factory=list)
    time_curve: TimeResponseCurve | None = None
    metadata: dict = field(default_factory=dict)


class RossResponseCalculator:
    """Run response analyses using a project-built native ROSS rotor."""

    def __init__(self, builder: RossModelBuilder | None = None):
        self.builder = builder or RossModelBuilder()

    @staticmethod
    def _emit(progress: ResponseProgress | None, message: str):
        if progress is not None:
            progress(message)

    @staticmethod
    def _speed_grid(start_rpm: float, final_rpm: float, points: int):
        step = (final_rpm - start_rpm) / (points - 1)
        rpm = [start_rpm + i * step for i in range(points)]
        return rpm, rpm_to_rad_s(rpm)

    @staticmethod
    def _complex_series(values):
        data = values.tolist() if hasattr(values, "tolist") else list(values)
        magnitude = [abs(complex(v)) for v in data]
        phase = [degrees(atan2(complex(v).imag, complex(v).real)) for v in data]
        return magnitude, phase

    @staticmethod
    def _check_dof(rotor, dof: int):
        ndof = int(getattr(rotor, "ndof", 0))
        if not 0 <= dof < ndof:
            raise ValueError(f"DOF {dof} is outside the rotor range [0, {max(ndof - 1, 0)}].")

    @staticmethod
    def _check_node(rotor, node: int):
        number_dof = int(getattr(rotor, "number_dof", 0))
        ndof = int(getattr(rotor, "ndof", 0))
        nodes = ndof // number_dof if number_dof else 0
        if not 0 <= node < nodes:
            raise ValueError(f"Node {node} is outside the rotor range [0, {max(nodes - 1, 0)}].")
        return number_dof

    def frequency_response(self, project: RotorProject, request: FrequencyResponseRequest, progress: ResponseProgress | None = None):
        request.validate()
        project.validate()
        self._emit(progress, "Building ROSS rotor for frequency response...")
        rotor = self.builder.build(project).rotor
        self._check_dof(rotor, request.input_dof)
        self._check_dof(rotor, request.output_dof)
        rpm, speed = self._speed_grid(request.start_rpm, request.final_rpm, request.points)
        self._emit(progress, f"Running FRF at {request.points} frequency points...")
        native = rotor.run_freq_response(speed_range=speed, modes=request.modes)
        values = native.freq_resp[request.output_dof, request.input_dof, :]
        magnitude, phase = self._complex_series(values)
        self._emit(progress, "Frequency response completed.")
        return RotorResponseResult(
            kind="frequency_response",
            curves=[ComplexResponseCurve(rpm, magnitude, phase, f"H[{request.output_dof},{request.input_dof}]", "m/N")],
            metadata={"input_dof": request.input_dof, "output_dof": request.output_dof},
        )

    def unbalance_response(self, project: RotorProject, request: UnbalanceResponseRequest, progress: ResponseProgress | None = None):
        request.validate()
        project.validate()
        self._emit(progress, "Building ROSS rotor for unbalance response...")
        rotor = self.builder.build(project).rotor
        number_dof = self._check_node(rotor, request.node)
        probe_node = request.node if request.probe_node is None else request.probe_node
        self._check_node(rotor, probe_node)
        rpm, speed = self._speed_grid(request.start_rpm, request.final_rpm, request.points)
        magnitude_kg_m = request.magnitude_g_mm * 1e-6
        phase_rad = request.phase_deg * pi / 180.0
        self._emit(progress, f"Running unbalance response at node {request.node}...")
        native = rotor.run_unbalance_response(
            node=request.node,
            unbalance_magnitude=magnitude_kg_m,
            unbalance_phase=phase_rad,
            frequency=speed,
            modes=request.modes,
        )
        x_values = native.forced_resp[probe_node * number_dof + 0, :]
        y_values = native.forced_resp[probe_node * number_dof + 1, :]
        x_mag, x_phase = self._complex_series(x_values)
        y_mag, y_phase = self._complex_series(y_values)
        radial = [hypot(x, y) for x, y in zip(x_mag, y_mag)]
        self._emit(progress, "Unbalance response completed.")
        return RotorResponseResult(
            kind="unbalance_response",
            curves=[
                ComplexResponseCurve(rpm, x_mag, x_phase, "X", "m"),
                ComplexResponseCurve(rpm, y_mag, y_phase, "Y", "m"),
                ComplexResponseCurve(rpm, radial, [0.0] * len(radial), "Radial", "m"),
            ],
            metadata={
                "unbalance_node": request.node,
                "probe_node": probe_node,
                "unbalance_magnitude_g_mm": request.magnitude_g_mm,
                "phase_deg": request.phase_deg,
            },
        )

    def time_response(self, project: RotorProject, request: TimeResponseRequest, progress: ResponseProgress | None = None):
        request.validate()
        project.validate()
        self._emit(progress, "Building ROSS rotor for time response...")
        rotor = self.builder.build(project).rotor
        number_dof = self._check_node(rotor, request.node)
        import numpy as np

        count = int(round(request.duration_s / request.time_step_s)) + 1
        t = np.linspace(0.0, request.duration_s, count)
        force = np.zeros((count, rotor.ndof), dtype=float)
        omega = 2.0 * pi * request.excitation_hz
        force[:, request.node * number_dof + 0] = request.force_x_n * np.cos(omega * t)
        force[:, request.node * number_dof + 1] = request.force_y_n * np.sin(omega * t)
        self._emit(progress, f"Running {request.method} time integration with {count} steps...")
        native = rotor.run_time_response(rpm_to_rad_s(request.speed_rpm), force, t, method=request.method)
        time_values = native.t.tolist() if hasattr(native.t, "tolist") else list(native.t)
        x = native.yout[:, request.node * number_dof + 0]
        y = native.yout[:, request.node * number_dof + 1]
        x_values = [float(v) for v in (x.tolist() if hasattr(x, "tolist") else x)]
        y_values = [float(v) for v in (y.tolist() if hasattr(y, "tolist") else y)]
        radial = [hypot(a, b) for a, b in zip(x_values, y_values)]
        self._emit(progress, "Time response completed.")
        return RotorResponseResult(
            kind="time_response",
            time_curve=TimeResponseCurve([float(v) for v in time_values], x_values, y_values, radial),
            metadata={
                "node": request.node,
                "speed_rpm": request.speed_rpm,
                "force_x_n": request.force_x_n,
                "force_y_n": request.force_y_n,
                "excitation_hz": request.excitation_hz,
                "method": request.method,
            },
        )
