from __future__ import annotations

from dataclasses import dataclass, field
from math import degrees, isfinite
from typing import Any, Callable

from ...domain import CylindricalBearingSpec
from ..coordinates import rad_s_to_rpm
from .builder import RossModelBuilder

BearingProgress = Callable[[str], None]


@dataclass(slots=True)
class BearingCoefficientRow:
    rpm: float
    kxx: float
    kxy: float
    kyx: float
    kyy: float
    cxx: float
    cxy: float
    cyx: float
    cyy: float


@dataclass(slots=True)
class BearingOperatingPoint:
    rpm: float
    eccentricity_ratio: float | None = None
    attitude_deg: float | None = None
    min_film_thickness_mm: float | None = None
    max_pressure_pa: float | None = None
    max_temperature_c: float | None = None
    power_loss_kw: float | None = None
    flow_l_min: float | None = None
    journal_x_over_clearance: float | None = None
    journal_y_over_clearance: float | None = None
    converged: bool = True
    convergence_message: str = ""


@dataclass(slots=True)
class BearingCalculationResult:
    bearing_type: str
    tag: str
    coefficients: list[BearingCoefficientRow]
    operating_points: list[BearingOperatingPoint] = field(default_factory=list)
    pressure_fields_pa: list[Any] = field(default_factory=list)
    temperature_fields_c: list[Any] = field(default_factory=list)
    film_thickness_fields_mm: list[Any] = field(default_factory=list)
    theta_grids_rad: list[Any] = field(default_factory=list)
    axial_grids_mm: list[Any] = field(default_factory=list)
    execution_time_s: float | None = None

    @property
    def has_field_results(self) -> bool:
        return bool(self.pressure_fields_pa)


class RossBearingCalculator:
    """Calculate a bearing independently and normalize native ROSS results."""

    def __init__(self, builder: RossModelBuilder | None = None):
        self.builder = builder or RossModelBuilder()

    @staticmethod
    def _emit(progress: BearingProgress | None, message: str) -> None:
        if progress is not None:
            progress(message)

    @staticmethod
    def _list(value: Any) -> list:
        if value is None:
            return []
        if hasattr(value, "tolist"):
            value = value.tolist()
        if isinstance(value, (list, tuple)):
            return list(value)
        return [value]

    @classmethod
    def _scalar(cls, value: Any, default: float | None = None) -> float | None:
        seq = cls._list(value)
        if not seq:
            return default
        first = seq[0]
        while isinstance(first, (list, tuple)) and first:
            first = first[0]
        try:
            return float(first)
        except (TypeError, ValueError):
            return default

    @classmethod
    def _flatten(cls, value: Any):
        if hasattr(value, "tolist"):
            value = value.tolist()
        if isinstance(value, (list, tuple)):
            for item in value:
                yield from cls._flatten(item)
        else:
            try:
                yield float(value)
            except (TypeError, ValueError):
                return

    @classmethod
    def _scale_nested(cls, value: Any, factor: float, offset: float = 0.0):
        if hasattr(value, "tolist"):
            value = value.tolist()
        if isinstance(value, (list, tuple)):
            return [cls._scale_nested(v, factor, offset) for v in value]
        return float(value) * factor + offset

    @staticmethod
    def _spec_speed_rpm(spec) -> list[float]:
        if getattr(spec, "frequency_rpm", None) is not None:
            return [float(v) for v in spec.frequency_rpm]
        if isinstance(spec, CylindricalBearingSpec):
            return [float(v) for v in spec.speed_rpm]
        return []

    @classmethod
    def _coefficient_rows(cls, bearing: Any, spec) -> list[BearingCoefficientRow]:
        names = ("kxx", "kxy", "kyx", "kyy", "cxx", "cxy", "cyx", "cyy")
        arrays = {name: cls._list(getattr(bearing, name, 0.0)) for name in names}
        count = max([len(v) for v in arrays.values()] + [1])
        speeds = cls._spec_speed_rpm(spec)
        if not speeds:
            frequency = getattr(bearing, "frequency", None)
            if frequency is not None:
                speeds = [float(rad_s_to_rpm(v)) for v in cls._list(frequency)]
        if not speeds:
            speeds = [0.0] * count
        if len(speeds) == 1 and count > 1:
            speeds *= count

        def at(values: list, index: int) -> float:
            if not values:
                return 0.0
            return float(values[index] if index < len(values) else values[-1])

        return [
            BearingCoefficientRow(
                rpm=float(speeds[i] if i < len(speeds) else speeds[-1]),
                **{name: at(arrays[name], i) for name in names},
            )
            for i in range(count)
        ]

    @classmethod
    def _fluid_operating_points(cls, results: Any, speeds: list[float]) -> list[BearingOperatingPoint]:
        points: list[BearingOperatingPoint] = []
        outputs = list(getattr(results, "outputs", []) or [])
        film_fields = list(getattr(results, "film_thickness_fields", []) or [])
        temp_fields = list(getattr(results, "temperature_fields", []) or [])
        pressure_fields = list(getattr(results, "pressure_fields", []) or [])
        for i, out in enumerate(outputs):
            film_values = list(cls._flatten(film_fields[i])) if i < len(film_fields) else []
            temp_values = list(cls._flatten(temp_fields[i])) if i < len(temp_fields) else []
            pressure_values = list(cls._flatten(pressure_fields[i])) if i < len(pressure_fields) else []
            max_temp_k = max(temp_values) if temp_values else cls._scalar(out.get("max_pad_temperature"))
            message_raw = out.get("non_convergence", [""])
            message = str(message_raw[0] if isinstance(message_raw, (list, tuple)) and message_raw else message_raw or "")
            flow_m3_s = cls._scalar(out.get("differential_flow_rate"))
            power_w = cls._scalar(out.get("power_loss"))
            max_pressure = cls._scalar(out.get("max_pressure"))
            if max_pressure is None and pressure_values:
                max_pressure = max(pressure_values)
            eccentricity = cls._scalar(out.get("eccentricity"))
            attitude = cls._scalar(out.get("attitude"))
            numeric = [eccentricity, attitude, max_pressure, power_w, flow_m3_s]
            invalid = any(v is not None and not isfinite(v) for v in numeric)
            converged = not message.strip() and not invalid and bool(pressure_values or eccentricity is not None)
            if invalid and not message.strip():
                message = "ROSS returned non-finite values for this operating point."
            points.append(
                BearingOperatingPoint(
                    rpm=float(speeds[i] if i < len(speeds) else 0.0),
                    eccentricity_ratio=eccentricity,
                    attitude_deg=None if attitude is None else degrees(attitude),
                    min_film_thickness_mm=min(film_values) * 1000.0 if film_values else None,
                    max_pressure_pa=max_pressure,
                    max_temperature_c=(max_temp_k - 273.15 if max_temp_k is not None and max_temp_k > 100.0 else max_temp_k),
                    power_loss_kw=power_w / 1000.0 if power_w is not None else None,
                    flow_l_min=flow_m3_s * 60000.0 if flow_m3_s is not None else None,
                    journal_x_over_clearance=cls._scalar(out.get("xj_cb")),
                    journal_y_over_clearance=cls._scalar(out.get("yj_cb")),
                    converged=converged,
                    convergence_message=message.strip(),
                )
            )
        return points

    def calculate(self, spec, progress: BearingProgress | None = None) -> BearingCalculationResult:
        spec.validate()
        self._emit(progress, f"Building {type(spec).__name__} with ROSS...")
        node_map = {self.builder._p(spec.position_mm): 0}
        bearing = self.builder._build_bearing(spec, node_map)
        self._emit(progress, "ROSS bearing object created; collecting dynamic coefficients...")
        coefficients = self._coefficient_rows(bearing, spec)
        native = getattr(bearing, "_results", None)
        speeds = [row.rpm for row in coefficients]

        if native is None:
            operating_points: list[BearingOperatingPoint] = []
            if isinstance(spec, CylindricalBearingSpec):
                eccentricity = self._list(getattr(bearing, "eccentricity", []))
                attitude = self._list(getattr(bearing, "attitude_angle", []))
                operating_points = [
                    BearingOperatingPoint(
                        rpm=row.rpm,
                        eccentricity_ratio=float(eccentricity[i]) if i < len(eccentricity) else None,
                        attitude_deg=degrees(float(attitude[i])) if i < len(attitude) else None,
                    )
                    for i, row in enumerate(coefficients)
                ]
            self._emit(progress, "Bearing calculation completed.")
            return BearingCalculationResult(type(spec).__name__, spec.tag, coefficients, operating_points)

        self._emit(progress, "Native FluidFilmBearingResults found; extracting THD fields and operating points...")
        operating_points = self._fluid_operating_points(native, speeds)
        initial = getattr(native, "initial_time", None)
        final = getattr(native, "final_time", None)
        execution = None if initial is None or final is None else float(final - initial)
        result = BearingCalculationResult(
            bearing_type=type(spec).__name__,
            tag=spec.tag,
            coefficients=coefficients,
            operating_points=operating_points,
            pressure_fields_pa=[self._scale_nested(v, 1.0) for v in getattr(native, "pressure_fields", [])],
            temperature_fields_c=[self._scale_nested(v, 1.0, -273.15) for v in getattr(native, "temperature_fields", [])],
            film_thickness_fields_mm=[self._scale_nested(v, 1000.0) for v in getattr(native, "film_thickness_fields", [])],
            theta_grids_rad=[self._scale_nested(v, 1.0) for v in getattr(native, "theta_grids", [])],
            axial_grids_mm=[self._scale_nested(v, 1000.0) for v in getattr(native, "z_grids", [])],
            execution_time_s=execution,
        )
        self._emit(progress, "Native ROSS FluidFilmBearingResults extraction completed.")
        return result
