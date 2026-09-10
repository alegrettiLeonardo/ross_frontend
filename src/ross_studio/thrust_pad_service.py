from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from math import pi
from typing import Any, Mapping

import numpy as np

from .domain import BearingGroup, BearingSpec, EngineeringError, RotorProject


@dataclass(slots=True, frozen=True)
class AxialBearingCoefficientPoint:
    """Solved axial dynamic coefficients at one rotor speed."""

    rpm: float
    kzz: float
    czz: float


@dataclass(slots=True, frozen=True)
class ThrustPadOperatingPoint:
    """Native ROSS ThrustPad result summary at one solved speed."""

    rpm: float
    max_pressure_pa: float | None = None
    max_temperature_c: float | None = None
    min_film_thickness_m: float | None = None
    max_film_thickness_m: float | None = None
    pivot_film_thickness_m: float | None = None


@dataclass(slots=True, frozen=True)
class ThrustPadCalculationResult:
    """Traceable axial THD result.

    This result intentionally has no lateral K/C table. ``axial_coefficients`` is
    the only dynamic-coefficient contract. The expensive native ROSS element is
    retained for field post-processing, while rotor execution consumes a separate
    BearingElement containing only Kzz/Czz versus speed.
    """

    source_model: str
    application_class: str
    axial_coefficients: tuple[AxialBearingCoefficientPoint, ...]
    operating_points: tuple[ThrustPadOperatingPoint, ...]
    metadata: dict[str, Any]
    note: str
    native_element: Any

    @property
    def speed_dependent(self) -> bool:
        return bool(self.axial_coefficients)


class ThrustPadStudioService:
    """Scientific boundary for the ROSS 2.3 axial ThrustPad model."""

    SUPPORTED_CLASSES = {"ThrustPad"}
    TARGET_ROSS_VERSION = "2.3.0"

    def __init__(self, ross_module: Any | None = None) -> None:
        self.rs = ross_module

    def _ross(self) -> Any:
        if self.rs is None:
            self.rs = import_module("ross")
        version = str(getattr(self.rs, "__version__", "unknown"))
        if version != self.TARGET_ROSS_VERSION:
            raise EngineeringError(
                f"ThrustPad adapter is qualified against ROSS {self.TARGET_ROSS_VERSION}; installed version is {version}."
            )
        return self.rs

    @staticmethod
    def _bearing(project: RotorProject, index: int) -> BearingSpec:
        if not 0 <= int(index) < len(project.bearings):
            raise EngineeringError(f"Bearing index {index} is outside project bearing range.")
        return project.bearings[int(index)]

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

    @classmethod
    def _speed_vector(cls, project: RotorProject, inputs: Mapping[str, Any]) -> np.ndarray:
        values = inputs.get("speed_rpm")
        if values is None:
            case = project.operating_cases[0]
            low = max(1.0, cls._positive(inputs.get("speed_min_rpm", max(case.speed_min_rpm, 1.0)), "Minimum speed"))
            high = cls._positive(inputs.get("speed_max_rpm", case.speed_max_rpm), "Maximum speed")
            count = int(inputs.get("speed_points", 3))
            if high < low:
                raise EngineeringError("Maximum speed must be greater than or equal to minimum speed.")
            if count < 1:
                raise EngineeringError("At least one ThrustPad speed point is required.")
            values = np.linspace(low, high, count)
        speeds = np.asarray(values, dtype=float)
        if speeds.ndim != 1 or not speeds.size or not np.all(np.isfinite(speeds)):
            raise EngineeringError("ThrustPad speed vector must be a finite one-dimensional array.")
        if np.any(speeds <= 0.0) or (speeds.size > 1 and np.any(np.diff(speeds) <= 0.0)):
            raise EngineeringError("ThrustPad speeds must be positive and strictly increasing.")
        return speeds

    @staticmethod
    def normalize_inputs(inputs: Mapping[str, Any]) -> dict[str, Any]:
        """Convert desktop engineering units only at the scientific boundary."""
        values = dict(inputs)
        conversions = (
            ("pad_inner_radius_mm", "pad_inner_radius_m", 1e-3),
            ("pad_outer_radius_mm", "pad_outer_radius_m", 1e-3),
            ("pad_pivot_radius_mm", "pad_pivot_radius_m", 1e-3),
            ("initial_film_thickness_um", "initial_film_thickness_m", 1e-6),
            ("radial_inclination_angle_mrad", "radial_inclination_angle_rad", 1e-3),
            ("circumferential_inclination_angle_mrad", "circumferential_inclination_angle_rad", 1e-3),
        )
        for source, target, scale in conversions:
            if source in values:
                if target in values:
                    raise EngineeringError(f"Specify either {source} or {target}, not both.")
                values[target] = float(values.pop(source)) * scale
        return values

    @staticmethod
    def _extreme(value: Any, mode: str) -> float | None:
        if value is None:
            return None
        arr = np.asarray(value, dtype=float)
        finite = arr[np.isfinite(arr)]
        if finite.size == 0:
            return None
        return float(np.max(finite) if mode == "max" else np.min(finite))

    @staticmethod
    def _sequence_value(values: Any, index: int) -> float | None:
        if values is None:
            return None
        try:
            value = np.asarray(values, dtype=float).reshape(-1)[index]
        except (IndexError, TypeError, ValueError):
            return None
        return float(value) if np.isfinite(value) else None

    def calculate(
        self,
        project: RotorProject,
        index: int,
        ross_class: str,
        inputs: Mapping[str, Any] | None = None,
    ) -> ThrustPadCalculationResult:
        self._bearing(project, index)
        if ross_class != "ThrustPad":
            raise EngineeringError(f"{ross_class} is not handled by the axial ThrustPad service.")

        engineering_input = dict(inputs or {})
        values = self.normalize_inputs(engineering_input)
        rs = self._ross()
        speeds = self._speed_vector(project, values)

        r_i = self._positive(values.get("pad_inner_radius_m", 1.150), "Pad inner radius")
        r_o = self._positive(values.get("pad_outer_radius_m", 1.725), "Pad outer radius")
        r_p = self._positive(values.get("pad_pivot_radius_m", 1.4425), "Pad pivot radius")
        if not r_i < r_p < r_o:
            raise EngineeringError("ThrustPad geometry requires inner radius < pivot radius < outer radius.")

        pad_arc_deg = self._positive(values.get("pad_arc_deg", 26.0), "Pad arc")
        angular_pivot_deg = self._finite(values.get("angular_pivot_position_deg", 15.0), "Angular pivot position")
        n_pad = int(values.get("n_pad", 12))
        n_theta = int(values.get("n_theta", 10))
        n_radial = int(values.get("n_radial", 10))
        if n_pad < 1:
            raise EngineeringError("ThrustPad requires at least one pad.")
        if n_theta < 3 or n_radial < 3:
            raise EngineeringError("ThrustPad mesh requires at least 3 circumferential and 3 radial volumes.")

        equilibrium_mode = str(values.get("equilibrium_position_mode", "calculate"))
        if equilibrium_mode not in {"calculate", "imposed"}:
            raise EngineeringError("ThrustPad equilibrium_position_mode must be calculate or imposed.")

        oil_temperature_c = self._finite(values.get("oil_supply_temperature_c", 40.0), "Oil supply temperature")
        lubricant = str(values.get("lubricant", "ISOVG68"))
        axial_load_n = self._positive(values.get("axial_load_n", 13.320e6), "Axial load")
        radial_angle = self._finite(values.get("radial_inclination_angle_rad", -2.75e-4), "Radial inclination angle")
        circumferential_angle = self._finite(
            values.get("circumferential_inclination_angle_rad", -1.70e-5),
            "Circumferential inclination angle",
        )
        initial_film_m = self._positive(values.get("initial_film_thickness_m", 2.0e-4), "Initial film thickness")
        tolerance_n = self._positive(values.get("tolerance_force_moment_n", 0.1), "Force/moment tolerance")
        residual_n = self._positive(values.get("residual_force_moment_n", 50.0), "Initial residual force/moment")

        element = rs.ThrustPad(
            n=0,
            pad_inner_radius=rs.Q_(r_i, "m"),
            pad_outer_radius=rs.Q_(r_o, "m"),
            pad_pivot_radius=rs.Q_(r_p, "m"),
            pad_arc_length=rs.Q_(pad_arc_deg, "deg"),
            angular_pivot_position=rs.Q_(angular_pivot_deg, "deg"),
            oil_supply_temperature=rs.Q_(oil_temperature_c, "degC"),
            lubricant=lubricant,
            n_pad=n_pad,
            n_theta=n_theta,
            n_radial=n_radial,
            frequency=rs.Q_(speeds, "RPM"),
            equilibrium_position_mode=equilibrium_mode,
            model_type="thermo_hydro_dynamic",
            axial_load=axial_load_n,
            radial_inclination_angle=rs.Q_(radial_angle, "rad"),
            circumferential_inclination_angle=rs.Q_(circumferential_angle, "rad"),
            initial_film_thickness=rs.Q_(initial_film_m, "m"),
            tolerance_force_moment=tolerance_n,
            residual_force_moment=residual_n,
        )

        omegas = speeds * 2.0 * pi / 60.0
        axial_points: list[AxialBearingCoefficientPoint] = []
        for rpm, omega in zip(speeds, omegas):
            # Evaluate the inherited BearingElement contract so interpolation and
            # matrix placement are exactly the ROSS 2.3 implementation.
            k = np.asarray(rs.BearingElement.K(element, float(omega)), dtype=float)
            c = np.asarray(rs.BearingElement.C(element, float(omega)), dtype=float)
            if k.shape != (3, 3) or c.shape != (3, 3):
                raise EngineeringError("ROSS ThrustPad did not return the expected 3x3 BearingElement K/C matrices.")
            kzz = float(k[2, 2])
            czz = float(c[2, 2])
            if not np.isfinite(kzz) or not np.isfinite(czz):
                raise EngineeringError("ROSS ThrustPad returned non-finite Kzz/Czz coefficients.")
            lateral_k = k[:2, :2]
            lateral_c = c[:2, :2]
            if not np.allclose(lateral_k, 0.0) or not np.allclose(lateral_c, 0.0):
                raise EngineeringError("ROSS ThrustPad unexpectedly returned lateral K/C terms; axial adapter is blocked.")
            axial_points.append(AxialBearingCoefficientPoint(float(rpm), kzz, czz))

        results = element._results
        pressure_fields = getattr(results, "pressure_fields", ())
        temperature_fields = getattr(results, "temperature_fields", ())
        min_h = getattr(results, "min_thicknesses", ())
        max_h = getattr(results, "max_thicknesses", ())
        pivot_h = getattr(results, "pivot_film_thicknesses", ())
        operating_points: list[ThrustPadOperatingPoint] = []
        for i, rpm in enumerate(speeds):
            operating_points.append(
                ThrustPadOperatingPoint(
                    rpm=float(rpm),
                    max_pressure_pa=self._extreme(pressure_fields[i], "max") if i < len(pressure_fields) else None,
                    max_temperature_c=self._extreme(temperature_fields[i], "max") if i < len(temperature_fields) else None,
                    min_film_thickness_m=self._sequence_value(min_h, i),
                    max_film_thickness_m=self._sequence_value(max_h, i),
                    pivot_film_thickness_m=self._sequence_value(pivot_h, i),
                )
            )

        metadata: dict[str, Any] = {
            "source_model": "ThrustPad",
            "application_class": "BearingElement",
            "ross_api_contract": self.TARGET_ROSS_VERSION,
            "engineering_input": engineering_input,
            "normalized_input": values,
            "speed_rpm": [float(v) for v in speeds],
            "speed_rad_s": [float(v) for v in omegas],
            "pad_inner_radius_m": r_i,
            "pad_outer_radius_m": r_o,
            "pad_pivot_radius_m": r_p,
            "pad_arc_deg": pad_arc_deg,
            "angular_pivot_position_deg": angular_pivot_deg,
            "oil_supply_temperature_c": oil_temperature_c,
            "lubricant": lubricant,
            "n_pad": n_pad,
            "n_theta": n_theta,
            "n_radial": n_radial,
            "equilibrium_position_mode": equilibrium_mode,
            "axial_load_n": axial_load_n,
            "radial_inclination_angle_rad": radial_angle,
            "circumferential_inclination_angle_rad": circumferential_angle,
            "initial_film_thickness_m": initial_film_m,
            "tolerance_force_moment_n": tolerance_n,
            "residual_force_moment_n": residual_n,
            "solved_axial_kc_cache": 1,
            "axial_coefficients": [
                {"rpm": p.rpm, "kzz": p.kzz, "czz": p.czz} for p in axial_points
            ],
            "discretization": {"n_theta": n_theta, "n_radial": n_radial},
            "operating_condition": {
                "axial_load_n": axial_load_n,
                "equilibrium_position_mode": equilibrium_mode,
                "oil_supply_temperature_c": oil_temperature_c,
            },
            "si_input": {
                "pad_inner_radius_m": r_i,
                "pad_outer_radius_m": r_o,
                "pad_pivot_radius_m": r_p,
                "pad_arc_rad": pad_arc_deg * pi / 180.0,
                "angular_pivot_position_rad": angular_pivot_deg * pi / 180.0,
                "oil_supply_temperature_k": oil_temperature_c + 273.15,
                "axial_load_n": axial_load_n,
                "radial_inclination_angle_rad": radial_angle,
                "circumferential_inclination_angle_rad": circumferential_angle,
                "initial_film_thickness_m": initial_film_m,
                "speed_rad_s": [float(v) for v in omegas],
            },
        }

        return ThrustPadCalculationResult(
            source_model="ThrustPad",
            application_class="BearingElement",
            axial_coefficients=tuple(axial_points),
            operating_points=tuple(operating_points),
            metadata=metadata,
            note=(
                "Native ROSS 2.3 axial ThrustPad THD solution. Rotor application uses an independent "
                "BearingElement with Kzz/Czz only; the existing radial bearing is not replaced."
            ),
            native_element=element,
        )

    def apply(self, project: RotorProject, index: int, result: ThrustPadCalculationResult) -> BearingSpec:
        """Add/update an independent axial bearing at the selected radial-bearing station.

        The selected bearing is a placement anchor only. It remains untouched so its
        lateral K/C and flexible-support ``n_link`` contract cannot be corrupted by an
        axial ThrustPad model.
        """
        anchor = self._bearing(project, index)
        if result.source_model != "ThrustPad" or not result.axial_coefficients:
            raise EngineeringError("ThrustPad result cannot be applied without a solved axial Kzz/Czz table.")

        target_index = next(
            (
                i
                for i, bearing in enumerate(project.bearings)
                if bearing.metadata.get("source_model") == "ThrustPad"
                and abs(float(bearing.position_mm) - float(anchor.position_mm)) <= 1e-9
            ),
            None,
        )
        if target_index is None:
            target = BearingSpec(
                name=f"{anchor.name} / Axial ThrustPad",
                position_mm=float(anchor.position_mm),
                ross_class="BearingElement",
                group=BearingGroup.THD,
            )
            project.bearings.append(target)
        else:
            target = project.bearings[target_index]

        # No lateral coefficient is borrowed from or synthesized for the thrust pad.
        target.ross_class = "BearingElement"
        target.group = BearingGroup.THD
        target.kxx = target.kyy = target.kxy = target.kyx = 0.0
        target.cxx = target.cyy = target.cxy = target.cyx = 0.0
        target.coefficients = []
        target.metadata = dict(result.metadata)
        target.metadata["application_mode"] = "independent_axial_bearing_same_shaft_node"
        target.metadata["placement_anchor_bearing"] = anchor.name
        target.metadata["lateral_coefficients_forced_zero"] = 1
        project.validate()
        return target


__all__ = [
    "AxialBearingCoefficientPoint",
    "ThrustPadCalculationResult",
    "ThrustPadOperatingPoint",
    "ThrustPadStudioService",
]
