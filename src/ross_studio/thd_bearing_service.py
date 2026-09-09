from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from math import pi
from typing import Any, Mapping

import numpy as np

from .domain import BearingCoefficientPoint, BearingGroup, BearingSpec, EngineeringError, RotorProject


@dataclass(slots=True, frozen=True)
class THDOperatingPoint:
    """Compact engineering summary for one solved fluid-film speed point."""

    rpm: float
    max_pressure_pa: float | None = None
    max_temperature_k: float | None = None
    min_film_thickness_m: float | None = None
    eccentricity_ratio: float | None = None
    attitude_angle_rad: float | None = None
    power_loss_w: float | None = None
    differential_flow_m3_s: float | None = None


@dataclass(slots=True, frozen=True)
class THDBearingCalculationResult:
    """Traceable result from a native ROSS fluid-film calculation.

    ROSS Studio intentionally stores the solved dynamic-coefficient table as a
    ``BearingElement`` when the result is applied to a rotor. This mirrors the
    ROSS fluid-film save/reload policy: expensive Reynolds/thermal fields remain
    calculation evidence while the rotor consumes the already-solved K/C table.
    """

    source_model: str
    application_class: str
    coefficients: tuple[BearingCoefficientPoint, ...]
    operating_points: tuple[THDOperatingPoint, ...]
    metadata: dict[str, float | int | str | list[float]]
    note: str
    native_element: Any

    @property
    def speed_dependent(self) -> bool:
        return bool(self.coefficients)


class THDBearingStudioService:
    """Scientific service for qualified THD/advanced lateral bearing models."""

    SUPPORTED_CLASSES = {"PlainJournal", "TiltingPad", "SqueezeFilmDamper"}

    def __init__(self, ross_module: Any | None = None) -> None:
        self.rs = ross_module

    def _ross(self) -> Any:
        if self.rs is None:
            self.rs = import_module("ross")
        return self.rs

    @staticmethod
    def _finite(value: Any, name: str) -> float:
        number = float(value)
        if not np.isfinite(number):
            raise EngineeringError(f"{name} must be finite; received {value!r}.")
        return number

    @classmethod
    def _positive(cls, value: Any, name: str, *, allow_zero: bool = False) -> float:
        number = cls._finite(value, name)
        if allow_zero:
            if number < 0.0:
                raise EngineeringError(f"{name} must be non-negative; received {number:g}.")
        elif number <= 0.0:
            raise EngineeringError(f"{name} must be positive; received {number:g}.")
        return number

    @staticmethod
    def _bearing(project: RotorProject, index: int) -> BearingSpec:
        if not 0 <= int(index) < len(project.bearings):
            raise EngineeringError(f"Bearing index {index} is outside project bearing range.")
        return project.bearings[int(index)]

    @classmethod
    def _speed_vector(cls, project: RotorProject, inputs: Mapping[str, Any], *, minimum_count: int = 1) -> np.ndarray:
        values = inputs.get("speed_rpm")
        if values is None:
            case = project.operating_cases[0]
            low = max(1.0, cls._positive(inputs.get("speed_min_rpm", max(case.speed_min_rpm, 1.0)), "Minimum speed"))
            high = cls._positive(inputs.get("speed_max_rpm", case.speed_max_rpm), "Maximum speed")
            if high < low:
                raise EngineeringError("Maximum speed must be greater than or equal to minimum speed.")
            count = int(inputs.get("speed_points", max(3, minimum_count)))
            if count < minimum_count:
                raise EngineeringError(f"At least {minimum_count} speed point(s) are required.")
            values = np.linspace(low, high, count)
        speeds = np.asarray(values, dtype=float)
        if speeds.ndim != 1 or speeds.size < minimum_count or not np.all(np.isfinite(speeds)):
            raise EngineeringError("THD speed vector must be a finite one-dimensional array.")
        if np.any(speeds <= 0.0) or (speeds.size > 1 and np.any(np.diff(speeds) <= 0.0)):
            raise EngineeringError("THD speeds must be positive and strictly increasing.")
        return speeds

    @staticmethod
    def _matrix_kc(element: Any, omega: float) -> tuple[float, float, float, float, float, float, float, float]:
        k = np.asarray(element.K(float(omega)), dtype=float)
        c = np.asarray(element.C(float(omega)), dtype=float)
        values = (
            float(k[0, 0]), float(k[0, 1]), float(k[1, 0]), float(k[1, 1]),
            float(c[0, 0]), float(c[0, 1]), float(c[1, 0]), float(c[1, 1]),
        )
        if not all(np.isfinite(value) for value in values):
            raise EngineeringError("ROSS THD calculation returned a non-finite lateral K/C coefficient.")
        return values

    @staticmethod
    def _point(rpm: float, values: tuple[float, float, float, float, float, float, float, float]) -> BearingCoefficientPoint:
        kxx, kxy, kyx, kyy, cxx, cxy, cyx, cyy = values
        return BearingCoefficientPoint(float(rpm), kxx, kxy, kyx, kyy, cxx, cxy, cyx, cyy)

    @staticmethod
    def _safe_extreme(value: Any, operation: str) -> float | None:
        if value is None:
            return None
        array = np.asarray(value, dtype=float)
        finite = array[np.isfinite(array)]
        if finite.size == 0:
            return None
        return float(np.max(finite) if operation == "max" else np.min(finite))

    def calculate(
        self,
        project: RotorProject,
        index: int,
        ross_class: str,
        inputs: Mapping[str, Any] | None = None,
    ) -> THDBearingCalculationResult:
        self._bearing(project, index)
        values = dict(inputs or {})
        if ross_class not in self.SUPPORTED_CLASSES:
            raise EngineeringError(
                f"{ross_class} is not in the qualified THD lateral adapter set. "
                "ThrustPad and AMB keep independent scientific gates."
            )
        if ross_class == "PlainJournal":
            return self._plain_journal(project, values)
        if ross_class == "TiltingPad":
            return self._tilting_pad(project, values)
        return self._squeeze_film_damper(project, values)

    def _fluid_result(
        self,
        source_model: str,
        element: Any,
        speeds_rpm: np.ndarray,
        metadata: dict[str, float | int | str | list[float]],
        note: str,
    ) -> THDBearingCalculationResult:
        omegas = speeds_rpm * 2.0 * pi / 60.0
        points = tuple(self._point(rpm, self._matrix_kc(element, omega)) for rpm, omega in zip(speeds_rpm, omegas))
        results = getattr(element, "_results", None)
        pressure_fields = getattr(results, "pressure_fields", []) if results is not None else []
        temperature_fields = getattr(results, "temperature_fields", []) if results is not None else []
        thickness_fields = getattr(results, "film_thickness_fields", []) if results is not None else []
        outputs = getattr(results, "outputs", []) if results is not None else []

        summaries: list[THDOperatingPoint] = []
        for i, rpm in enumerate(speeds_rpm):
            out = outputs[i] if i < len(outputs) else {}

            def scalar(name: str) -> float | None:
                raw = out.get(name) if isinstance(out, dict) else None
                if raw is None:
                    return None
                arr = np.asarray(raw, dtype=float).reshape(-1)
                return float(arr[0]) if arr.size and np.isfinite(arr[0]) else None

            summaries.append(THDOperatingPoint(
                rpm=float(rpm),
                max_pressure_pa=(
                    self._safe_extreme(pressure_fields[i], "max") if i < len(pressure_fields) else scalar("max_pressure")
                ),
                max_temperature_k=(
                    self._safe_extreme(temperature_fields[i], "max") if i < len(temperature_fields) else None
                ),
                min_film_thickness_m=(
                    self._safe_extreme(thickness_fields[i], "min") if i < len(thickness_fields) else None
                ),
                eccentricity_ratio=scalar("eccentricity"),
                attitude_angle_rad=scalar("attitude"),
                power_loss_w=scalar("power_loss"),
                differential_flow_m3_s=scalar("differential_flow_rate"),
            ))

        metadata = dict(metadata)
        metadata["source_model"] = source_model
        metadata["application_class"] = "BearingElement"
        metadata["speed_rpm"] = [float(value) for value in speeds_rpm]
        metadata["solved_kc_cache"] = 1
        return THDBearingCalculationResult(
            source_model=source_model,
            application_class="BearingElement",
            coefficients=points,
            operating_points=tuple(summaries),
            metadata=metadata,
            note=note,
            native_element=element,
        )

    def _plain_journal(self, project: RotorProject, inputs: dict[str, Any]) -> THDBearingCalculationResult:
        rs = self._ross()
        speeds = self._speed_vector(project, inputs)
        n_pads = int(inputs.get("n_pads", 2))
        if n_pads < 1:
            raise EngineeringError("PlainJournal requires at least one land/pad.")
        pad_arc_deg = self._positive(inputs.get("pad_arc_deg", 176.0), "Pad arc")
        if pad_arc_deg >= 360.0 / n_pads + 1e-9:
            raise EngineeringError("PlainJournal pad arc must leave a positive groove between adjacent lands.")
        thermal_type = inputs.get("thermal_type", "adiabatic")
        if thermal_type not in (None, "adiabatic", "full"):
            raise EngineeringError("PlainJournal thermal_type must be None, 'adiabatic' or 'full'.")
        mesh_x = int(inputs.get("total_ex_film", 20))
        mesh_z = int(inputs.get("total_ez_film", 10))
        mesh_y_film = int(inputs.get("total_ey_film", 10))
        mesh_y_pad = int(inputs.get("total_ey_pad", 10))
        if any(value <= 0 or value % 2 for value in (mesh_x, mesh_z, mesh_y_film, mesh_y_pad)):
            raise EngineeringError("ROSS fluid-film mesh counts must be positive even integers.")

        metadata: dict[str, float | int | str | list[float]] = {
            "pad_axial_length_m": self._positive(inputs.get("pad_axial_length_m", 0.263144), "Pad axial length"),
            "journal_diameter_m": self._positive(inputs.get("journal_diameter_m", 0.4), "Journal diameter"),
            "radial_clearance_m": self._positive(inputs.get("radial_clearance_m", 1.95e-4), "Radial clearance"),
            "n_pads": n_pads,
            "pad_arc_deg": pad_arc_deg,
            "preload": self._positive(inputs.get("preload", 0.0), "Preload", allow_zero=True),
            "oil_supply_temperature_c": self._finite(inputs.get("oil_supply_temperature_c", 50.0), "Oil supply temperature"),
            "fxs_load_n": self._finite(inputs.get("fxs_load_n", 0.0), "Static load X"),
            "fys_load_n": self._finite(inputs.get("fys_load_n", -112814.91), "Static load Y"),
            "lubricant": str(inputs.get("lubricant", "ISOVG32")),
            "oil_flow_l_min": self._positive(inputs.get("oil_flow_l_min", 37.86), "Oil flow"),
            "thermal_type": "isoviscous" if thermal_type is None else str(thermal_type),
            "total_ex_film": mesh_x,
            "total_ez_film": mesh_z,
            "total_ey_film": mesh_y_film,
            "total_ey_pad": mesh_y_pad,
        }
        element = rs.PlainJournal(
            n=0,
            pad_axial_length=metadata["pad_axial_length_m"],
            journal_diameter=metadata["journal_diameter_m"],
            radial_clearance=metadata["radial_clearance_m"],
            n_pads=n_pads,
            pad_arc=pad_arc_deg * pi / 180.0,
            preload=metadata["preload"],
            oil_supply_temperature=metadata["oil_supply_temperature_c"] + 273.15,
            frequency=speeds * 2.0 * pi / 60.0,
            fxs_load=metadata["fxs_load_n"],
            fys_load=metadata["fys_load_n"],
            lubricant=metadata["lubricant"],
            oil_flow_v=metadata["oil_flow_l_min"] / 60000.0,
            thermal_type=thermal_type,
            total_ex_film=mesh_x,
            total_ez_film=mesh_z,
            total_ey_film=mesh_y_film,
            total_ey_pad=mesh_y_pad,
        )
        return self._fluid_result(
            "PlainJournal",
            element,
            speeds,
            metadata,
            "Native ROSS PlainJournal Reynolds/thermal solution; solved K/C is cached as BearingElement for rotor execution.",
        )

    def _tilting_pad(self, project: RotorProject, inputs: dict[str, Any]) -> THDBearingCalculationResult:
        rs = self._ross()
        speeds = self._speed_vector(project, inputs)
        n_pads = int(inputs.get("n_pads", 5))
        if n_pads < 3:
            raise EngineeringError("TiltingPad requires at least three pads.")
        pivot_angles_deg = np.asarray(
            inputs.get("pivot_angles_deg", np.linspace(18.0, 306.0, n_pads)), dtype=float
        )
        if pivot_angles_deg.size != n_pads or not np.all(np.isfinite(pivot_angles_deg)):
            raise EngineeringError("TiltingPad pivot angle vector must contain one finite angle per pad.")
        pad_arc_deg = self._positive(inputs.get("pad_arc_deg", 60.0), "Pad arc")
        pad_length_m = self._positive(inputs.get("pad_axial_length_m", 0.0508), "Pad axial length")
        preload = self._positive(inputs.get("preload", 0.5), "Preload", allow_zero=True)
        offset = self._finite(inputs.get("offset", 0.5), "Pivot offset")
        if not 0.0 <= offset <= 1.0:
            raise EngineeringError("TiltingPad pivot offset must be between 0 and 1.")
        thermal_type = str(inputs.get("thermal_type", "adiabatic"))
        if thermal_type not in ("adiabatic", "full"):
            raise EngineeringError("TiltingPad thermal_type must be 'adiabatic' or 'full'.")
        mesh_x = int(inputs.get("total_ex_film", 20))
        mesh_z = int(inputs.get("total_ez_film", 10))
        mesh_y_film = int(inputs.get("total_ey_film", 10))
        mesh_y_pad = int(inputs.get("total_ey_pad", 10))
        if any(value <= 0 or value % 2 for value in (mesh_x, mesh_z, mesh_y_film, mesh_y_pad)):
            raise EngineeringError("ROSS fluid-film mesh counts must be positive even integers.")

        metadata: dict[str, float | int | str | list[float]] = {
            "journal_diameter_m": self._positive(inputs.get("journal_diameter_m", 0.1016), "Journal diameter"),
            "radial_clearance_m": self._positive(inputs.get("radial_clearance_m", 74.9e-6), "Radial clearance"),
            "pad_thickness_m": self._positive(inputs.get("pad_thickness_m", 12.7e-3), "Pad thickness"),
            "n_pads": n_pads,
            "pivot_angles_deg": [float(value) for value in pivot_angles_deg],
            "pad_arc_deg": pad_arc_deg,
            "pad_axial_length_m": pad_length_m,
            "preload": preload,
            "offset": offset,
            "lubricant": str(inputs.get("lubricant", "ISOVG32")),
            "oil_supply_temperature_c": self._finite(inputs.get("oil_supply_temperature_c", 40.0), "Oil supply temperature"),
            "oil_flow_l_min": self._positive(inputs.get("oil_flow_l_min", 10.0), "Oil flow"),
            "fxs_load_n": self._finite(inputs.get("fxs_load_n", 884.05), "Static load X"),
            "fys_load_n": self._finite(inputs.get("fys_load_n", -2670.4), "Static load Y"),
            "thermal_type": thermal_type,
            "total_ex_film": mesh_x,
            "total_ez_film": mesh_z,
            "total_ey_film": mesh_y_film,
            "total_ey_pad": mesh_y_pad,
        }
        element = rs.TiltingPad(
            n=0,
            frequency=speeds * 2.0 * pi / 60.0,
            equilibrium_type="match_load",
            thermal_type=thermal_type,
            journal_diameter=metadata["journal_diameter_m"],
            radial_clearance=metadata["radial_clearance_m"],
            pad_thickness=metadata["pad_thickness_m"],
            pivot_angle=np.radians(pivot_angles_deg),
            pad_arc=np.full(n_pads, pad_arc_deg * pi / 180.0),
            pad_axial_length=np.full(n_pads, pad_length_m),
            preload=np.full(n_pads, preload),
            offset=np.full(n_pads, offset),
            lubricant=metadata["lubricant"],
            oil_supply_temperature=metadata["oil_supply_temperature_c"] + 273.15,
            oil_flow_v=metadata["oil_flow_l_min"] / 60000.0,
            fxs_load=metadata["fxs_load_n"],
            fys_load=metadata["fys_load_n"],
            total_ex_film=mesh_x,
            total_ez_film=mesh_z,
            total_ey_film=mesh_y_film,
            total_ey_pad=mesh_y_pad,
        )
        return self._fluid_result(
            "TiltingPad",
            element,
            speeds,
            metadata,
            "Native ROSS TiltingPad Reynolds/thermal solution; solved K/C is cached as BearingElement for rotor execution.",
        )

    def _squeeze_film_damper(self, project: RotorProject, inputs: dict[str, Any]) -> THDBearingCalculationResult:
        rs = self._ross()
        speeds = self._speed_vector(project, inputs)
        geometry = str(inputs.get("geometry", "groove"))
        if geometry not in ("groove", "end_seals", "groove-end_seals"):
            raise EngineeringError("SqueezeFilmDamper geometry must be groove, end_seals or groove-end_seals.")
        eccentricity_ratio = self._finite(inputs.get("eccentricity_ratio", 0.5), "Eccentricity ratio")
        if not 0.0 <= eccentricity_ratio < 1.0:
            raise EngineeringError("SqueezeFilmDamper eccentricity ratio must satisfy 0 <= epsilon < 1.")
        metadata: dict[str, float | int | str | list[float]] = {
            "axial_length_m": self._positive(inputs.get("axial_length_m", 0.02286), "Damper axial length"),
            "journal_diameter_m": self._positive(inputs.get("journal_diameter_m", 0.12954), "Journal diameter"),
            "radial_clearance_m": self._positive(inputs.get("radial_clearance_m", 7.62e-5), "Radial clearance"),
            "eccentricity_ratio": eccentricity_ratio,
            "lubricant": str(inputs.get("lubricant", "ISOVG32")),
            "geometry": geometry,
            "cavitation": int(bool(inputs.get("cavitation", True))),
        }
        element = rs.SqueezeFilmDamper(
            n=0,
            frequency=speeds * 2.0 * pi / 60.0,
            axial_length=metadata["axial_length_m"],
            journal_diameter=metadata["journal_diameter_m"],
            radial_clearance=metadata["radial_clearance_m"],
            eccentricity_ratio=eccentricity_ratio,
            lubricant=metadata["lubricant"],
            geometry=geometry,
            cavitation=bool(metadata["cavitation"]),
        )
        result = self._fluid_result(
            "SqueezeFilmDamper",
            element,
            speeds,
            metadata,
            "Native ROSS SqueezeFilmDamper calculation; solved K/C is cached as BearingElement for rotor execution.",
        )
        # SFD exposes pressure maxima directly rather than full pressure fields.
        p_max = np.asarray(getattr(element, "p_max", []), dtype=float).reshape(-1)
        enriched: list[THDOperatingPoint] = []
        h_min = metadata["radial_clearance_m"] * (1.0 - eccentricity_ratio)
        for i, item in enumerate(result.operating_points):
            enriched.append(THDOperatingPoint(
                rpm=item.rpm,
                max_pressure_pa=float(p_max[i]) if i < p_max.size and np.isfinite(p_max[i]) else item.max_pressure_pa,
                max_temperature_k=item.max_temperature_k,
                min_film_thickness_m=float(h_min),
                eccentricity_ratio=eccentricity_ratio,
                attitude_angle_rad=item.attitude_angle_rad,
                power_loss_w=item.power_loss_w,
                differential_flow_m3_s=item.differential_flow_m3_s,
            ))
        return THDBearingCalculationResult(
            source_model=result.source_model,
            application_class=result.application_class,
            coefficients=result.coefficients,
            operating_points=tuple(enriched),
            metadata=result.metadata,
            note=result.note,
            native_element=result.native_element,
        )

    def apply(self, project: RotorProject, index: int, result: THDBearingCalculationResult) -> BearingSpec:
        spec = self._bearing(project, index)
        if not result.coefficients:
            raise EngineeringError("THD result cannot be applied without a solved K/C table.")
        case = project.operating_cases[0]
        rated_index = min(range(len(result.coefficients)), key=lambda i: abs(result.coefficients[i].rpm - case.rated_speed_rpm))
        rated = result.coefficients[rated_index]
        spec.ross_class = "BearingElement"
        spec.group = BearingGroup.THD
        spec.kxx, spec.kxy, spec.kyx, spec.kyy = rated.kxx, rated.kxy, rated.kyx, rated.kyy
        spec.cxx, spec.cxy, spec.cyx, spec.cyy = rated.cxx, rated.cxy, rated.cyx, rated.cyy
        spec.coefficients = list(result.coefficients)
        spec.metadata = dict(result.metadata)
        project.validate()
        return spec


__all__ = ["THDBearingCalculationResult", "THDBearingStudioService", "THDOperatingPoint"]
