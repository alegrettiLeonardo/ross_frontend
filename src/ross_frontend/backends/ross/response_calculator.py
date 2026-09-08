from __future__ import annotations

from dataclasses import dataclass, field
from math import atan2, cos, degrees, hypot, pi, sin
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
class ProjectUnbalanceResponseRequest:
    start_rpm: float | None = None
    final_rpm: float | None = None
    step_rpm: float | None = None
    modes: list[int] | None = None

    def validate(self):
        if self.start_rpm is not None and self.start_rpm < 0:
            raise ValueError("Unbalance-response initial speed cannot be negative.")
        if self.final_rpm is not None and self.start_rpm is not None and self.final_rpm <= self.start_rpm:
            raise ValueError("Unbalance-response final speed must exceed initial speed.")
        if self.step_rpm is not None and self.step_rpm <= 0:
            raise ValueError("Unbalance-response speed step must be positive.")


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
    def _stepped_speed_grid(start_rpm: float, final_rpm: float, step_rpm: float):
        count = int((final_rpm - start_rpm) // step_rpm)
        rpm = [start_rpm + i * step_rpm for i in range(count + 1)]
        if not rpm or rpm[-1] < final_rpm - 1e-9:
            rpm.append(final_rpm)
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

    @staticmethod
    def _rotate_probe(x_values, y_values, orientation_deg: float, coordinate: int):
        """Reproduce RotorDin vrotate + DISPL semantics on complex phasors.

        Historical RotorDin first rotates the lateral x/z complex pair by ORIENT
        and only then selects DISPL=1 (rotated horizontal) or DISPL=2 (rotated
        vertical). ROSS lateral axes are x/y, so y is used in place of RotorDin z.
        """
        angle = orientation_deg * pi / 180.0
        ca, sa = cos(angle), sin(angle)
        x_data = x_values.tolist() if hasattr(x_values, "tolist") else list(x_values)
        y_data = y_values.tolist() if hasattr(y_values, "tolist") else list(y_values)
        if coordinate == 1:
            return [complex(x) * ca + complex(y) * sa for x, y in zip(x_data, y_data)]
        if coordinate == 2:
            return [complex(y) * ca - complex(x) * sa for x, y in zip(x_data, y_data)]
        raise ValueError("Probe coordinate must be 1 or 2.")

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

    def project_unbalance_response(
        self,
        project: RotorProject,
        request: ProjectUnbalanceResponseRequest | None = None,
        progress: ResponseProgress | None = None,
    ) -> RotorResponseResult:
        """Solve all imported unbalance planes and return each physical probe.

        This is the engineering-facing path used by ROSS Studio. It consumes
        physical positions from ``RotorProject`` instead of exposing ROSS node/DOF
        indices to the user.
        """
        request = request or ProjectUnbalanceResponseRequest()
        request.validate()
        project.validate()
        if not project.unbalances:
            raise ValueError("The project has no unbalance planes.")
        if not project.probes:
            raise ValueError("The project has no response probes.")

        cfg = project.metadata.get("response", {})
        start = float(request.start_rpm if request.start_rpm is not None else cfg.get("initial_rpm", 0.0))
        final = float(request.final_rpm if request.final_rpm is not None else cfg.get("final_rpm", 0.0))
        step = float(request.step_rpm if request.step_rpm is not None else cfg.get("step_rpm", 0.0))
        if final <= start:
            raise ValueError("Project response speed range is not defined or is invalid.")
        if step <= 0:
            step = (final - start) / 100.0

        self._emit(progress, "Building ROSS rotor with imported TABLE bearings and flexible supports...")
        build = self.builder.build(project)
        rotor = build.rotor
        number_dof = int(rotor.number_dof)
        rpm, speed = self._stepped_speed_grid(start, final, step)

        nodes = [build.node_by_position_mm[self.builder._p(item.position_mm)] for item in project.unbalances]
        magnitude = [item.magnitude_g_mm * 1e-6 for item in project.unbalances]
        phase = [item.phase_deg * pi / 180.0 for item in project.unbalances]
        self._emit(
            progress,
            f"Running ROSS unbalance response: {len(nodes)} plane(s), {len(project.probes)} probe(s), {len(rpm)} speed points...",
        )
        native = rotor.run_unbalance_response(
            node=nodes,
            unbalance_magnitude=magnitude,
            unbalance_phase=phase,
            frequency=speed,
            modes=request.modes,
        )

        curves: list[ComplexResponseCurve] = []
        probe_metadata = []
        for probe in project.probes:
            node = build.node_by_position_mm[self.builder._p(probe.position_mm)]
            x_values = native.forced_resp[node * number_dof + 0, :]
            y_values = native.forced_resp[node * number_dof + 1, :]
            projected = self._rotate_probe(x_values, y_values, probe.orientation_deg, probe.coordinate)
            magnitude_values, phase_values = self._complex_series(projected)
            label = probe.tag or f"x={probe.position_mm:g} mm / coord {probe.coordinate}"
            curves.append(ComplexResponseCurve(rpm, magnitude_values, phase_values, label, "m"))
            probe_metadata.append(
                {
                    "tag": label,
                    "position_mm": probe.position_mm,
                    "coordinate": probe.coordinate,
                    "orientation_deg": probe.orientation_deg,
                    "ross_node": node,
                }
            )

        self._emit(progress, "Imported-project unbalance response completed.")
        return RotorResponseResult(
            kind="project_unbalance_response",
            curves=curves,
            metadata={
                "unbalances": [
                    {
                        "position_mm": item.position_mm,
                        "magnitude_g_mm": item.magnitude_g_mm,
                        "phase_deg": item.phase_deg,
                        "ross_node": node,
                    }
                    for item, node in zip(project.unbalances, nodes)
                ],
                "probes": probe_metadata,
                "speed_start_rpm": start,
                "speed_final_rpm": final,
                "speed_step_rpm": step,
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
