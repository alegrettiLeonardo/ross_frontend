from __future__ import annotations

from dataclasses import dataclass, replace
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
    max_temperature_c: float | None = None
    min_film_thickness_m: float | None = None
    eccentricity_ratio: float | None = None
    attitude_angle_rad: float | None = None
    power_loss_w: float | None = None
    differential_flow_m3_s: float | None = None


@dataclass(slots=True, frozen=True)
class THDBearingCalculationResult:
    """Traceable result from a native ROSS 2.3 fluid-film calculation.

    The expensive native Reynolds/thermal solution is retained in ``native_element``
    for post-processing. Rotor execution consumes the solved speed-dependent K/C table
    through ``BearingElement`` so the same result can connect to a flexible ``n_link``
    support without re-solving the THD model inside each rotor analysis.
    """

    source_model: str
    application_class: str
    coefficients: tuple[BearingCoefficientPoint, ...]
    operating_points: tuple[THDOperatingPoint, ...]
    metadata: dict[str, Any]
    note: str
    native_element: Any

    @property
    def speed_dependent(self) -> bool:
        return bool(self.coefficients)


class THDBearingStudioService:
    """Scientific boundary for the pinned ROSS 2.3 lateral THD models."""

    SUPPORTED_CLASSES = {"PlainJournal", "TiltingPad", "SqueezeFilmDamper"}
    TARGET_ROSS_VERSION = "2.3.0"

    def __init__(self, ross_module: Any | None = None) -> None:
        self.rs = ross_module

    def _ross(self) -> Any:
        if self.rs is None:
            self.rs = import_module("ross")
        version = str(getattr(self.rs, "__version__", "unknown"))
        if version != self.TARGET_ROSS_VERSION:
            raise EngineeringError(
                f"THD adapter is qualified against ROSS {self.TARGET_ROSS_VERSION}; installed version is {version}."
            )
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

    def _matrix_kc(self, element: Any, omega: float) -> tuple[float, float, float, float, float, float, float, float]:
        """Evaluate the solved lateral K/C block without trusting instance name lookup.

        ROSS 2.3 ``TiltingPad`` uses ``self.K`` internally for a numerical matrix,
        which shadows the inherited ``BearingElement.K`` method on that instance.
        Calling the base implementation unbound preserves ROSS' own coefficient
        interpolation and avoids changing the native THD solution.
        """
        rs = self._ross()
        k_member = getattr(element, "K", None)
        c_member = getattr(element, "C", None)
        k_raw = k_member(float(omega)) if callable(k_member) else rs.BearingElement.K(element, float(omega))
        c_raw = c_member(float(omega)) if callable(c_member) else rs.BearingElement.C(element, float(omega))
        k = np.asarray(k_raw, dtype=float)
        c = np.asarray(c_raw, dtype=float)
        if k.shape[0] < 2 or k.shape[1] < 2 or c.shape[0] < 2 or c.shape[1] < 2:
            raise EngineeringError("ROSS THD calculation did not return a lateral 2x2 K/C block.")
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
    ) -> THDBearingCalculationResult:
        self._bearing(project, index)
        engineering_input = dict(inputs or {})
        values = self.normalize_inputs(engineering_input)
        if ross_class not in self.SUPPORTED_CLASSES:
            raise EngineeringError(
                f"{ross_class} is not in the qualified THD lateral adapter set. "
                "ThrustPad and AMB keep independent scientific gates."
            )
        if ross_class == "PlainJournal":
            result = self._plain_journal(project, values)
        elif ross_class == "TiltingPad":
            result = self._tilting_pad(project, values)
        else:
            result = self._squeeze_film_damper(project, values)
        metadata = dict(result.metadata)
        metadata["engineering_input"] = engineering_input
        metadata["normalized_input"] = values
        # SI audit is separate from the explicit mixed-unit ROSS constructor contract.
        si = {k: v for k, v in metadata.items() if k.endswith(("_m", "_n", "_pa"))}
        si["speed_rad_s"] = [float(p.rpm * 2*pi/60) for p in result.coefficients]
        for k, v in metadata.items():
            if k.endswith("_deg") and isinstance(v, (int, float)):
                si[k[:-4] + "_rad"] = float(v * pi/180)
            elif k.endswith("_c") and isinstance(v, (int, float)):
                si[k[:-2] + "_k"] = float(v + 273.15)
        if "oil_flow_l_min" in metadata:
            si["oil_flow_m3_s"] = metadata["oil_flow_l_min"] / 60000
        metadata["si_input"] = si
        metadata["discretization"] = {k: metadata[k] for k in ("nx", "nz", "elements_circumferential", "elements_axial") if k in metadata}
        metadata["operating_condition"] = {k: metadata[k] for k in ("fxs_load_n", "fys_load_n", "operating_type", "equilibrium_type", "thermal_type", "eccentricity_ratio", "cavitation") if k in metadata}
        return replace(result, metadata=metadata)

    @staticmethod
    def normalize_inputs(inputs: Mapping[str, Any]) -> dict[str, Any]:
        """Convert desktop engineering units at the scientific boundary only.

        ROSS mixed-unit arguments (rpm, degrees, Celsius, L/min) retain their
        explicit suffixes and are wrapped with Q_ where required by ROSS 2.3.
        """
        values = dict(inputs)
        for source, target, scale in (
            ("journal_diameter_mm", "journal_diameter_m", 1e-3),
            ("axial_length_mm", "axial_length_m", 1e-3),
            ("pad_axial_length_mm", "pad_axial_length_m", 1e-3),
            ("pad_thickness_mm", "pad_thickness_m", 1e-3),
            ("radial_clearance_um", "radial_clearance_m", 1e-6),
            ("oil_supply_pressure_bar", "oil_supply_pressure_pa", 1e5),
        ):
            if source in values:
                if target in values:
                    raise EngineeringError(f"Specify either {source} or {target}, not both.")
                values[target] = float(values.pop(source)) * scale
        if "initial_eccentricity_ratio" in values:
            values["initial_guess"] = [float(values.pop("initial_eccentricity_ratio")),
                                       float(values.pop("initial_attitude_angle_deg")) * pi / 180.0]
        return values

    def _base_result(
        self,
        source_model: str,
        element: Any,
        speeds_rpm: np.ndarray,
        metadata: dict[str, Any],
        operating_points: list[THDOperatingPoint],
        note: str,
    ) -> THDBearingCalculationResult:
        omegas = speeds_rpm * 2.0 * pi / 60.0
        points = tuple(self._point(rpm, self._matrix_kc(element, omega)) for rpm, omega in zip(speeds_rpm, omegas))
        meta = dict(metadata)
        meta.update({
            "source_model": source_model,
            "application_class": "BearingElement",
            "speed_rpm": [float(value) for value in speeds_rpm],
            "solved_kc_cache": 1,
            "ross_api_contract": self.TARGET_ROSS_VERSION,
        })
        return THDBearingCalculationResult(
            source_model=source_model,
            application_class="BearingElement",
            coefficients=points,
            operating_points=tuple(operating_points),
            metadata=meta,
            note=note,
            native_element=element,
        )

    def _plain_journal(self, project: RotorProject, inputs: dict[str, Any]) -> THDBearingCalculationResult:
        rs = self._ross()
        speeds = self._speed_vector(project, inputs)
        n_pad = int(inputs.get("n_pads", inputs.get("n_pad", 2)))
        if n_pad < 1:
            raise EngineeringError("PlainJournal requires at least one pad/land.")
        pad_arc_deg = self._positive(inputs.get("pad_arc_deg", 176.0), "Pad arc")
        if pad_arc_deg >= 360.0 / n_pad + 1e-9:
            raise EngineeringError("PlainJournal pad arc must leave a positive groove between adjacent lands.")
        elements_circumferential = int(inputs.get("elements_circumferential", inputs.get("total_ex_film", 11)))
        elements_axial = int(inputs.get("elements_axial", inputs.get("total_ez_film", 3)))
        if elements_circumferential < 3 or elements_axial < 2:
            raise EngineeringError("PlainJournal mesh requires at least 3 circumferential and 2 axial volumes.")
        geometry = str(inputs.get("geometry", "circular"))
        if geometry not in {"circular", "lobe", "elliptical"}:
            raise EngineeringError("PlainJournal geometry must be circular, lobe or elliptical.")
        operating_type = str(inputs.get("operating_type", "flooded"))
        if operating_type not in {"flooded", "starvation"}:
            raise EngineeringError("PlainJournal operating_type must be flooded or starvation.")
        method = str(inputs.get("method", "perturbation"))
        if method not in {"perturbation", "lund"}:
            raise EngineeringError("PlainJournal method must be perturbation or lund.")
        groove_factor = inputs.get("groove_factor", [1.0 / n_pad] * n_pad)
        groove = np.asarray(groove_factor, dtype=float)
        if groove.ndim != 1 or groove.size != n_pad or not np.all(np.isfinite(groove)):
            raise EngineeringError("PlainJournal groove_factor must contain one finite value per pad/land.")

        axial_length = self._positive(inputs.get("pad_axial_length_m", inputs.get("axial_length_m", 0.263144)), "Axial length")
        journal_diameter = self._positive(inputs.get("journal_diameter_m", 0.4), "Journal diameter")
        radial_clearance = self._positive(inputs.get("radial_clearance_m", 1.95e-4), "Radial clearance")
        preload = self._positive(inputs.get("preload", 0.0), "Preload", allow_zero=True)
        reference_temperature_c = self._finite(inputs.get("oil_supply_temperature_c", inputs.get("reference_temperature_c", 50.0)), "Reference temperature")
        fxs_load = self._finite(inputs.get("fxs_load_n", 0.0), "Static load X")
        fys_load = self._finite(inputs.get("fys_load_n", -112814.91), "Static load Y")
        lubricant = str(inputs.get("lubricant", "ISOVG32"))
        oil_flow_l_min = self._positive(inputs.get("oil_flow_l_min", 37.86), "Oil flow", allow_zero=True)
        oil_supply_pressure_pa = self._positive(inputs.get("oil_supply_pressure_pa", 0.0), "Oil supply pressure", allow_zero=True)
        sommerfeld_type = int(inputs.get("sommerfeld_type", 2))
        if sommerfeld_type not in {1, 2}:
            raise EngineeringError("Sommerfeld type must be 1 or 2.")
        if np.any(groove < 0) or np.any(groove > 1):
            raise EngineeringError("Groove factors must be fractions in [0, 1]; correct the value for each pad.")
        if not 0 <= preload < 1:
            raise EngineeringError("Preload must satisfy 0 <= preload < 1.")
        initial_guess = np.asarray(inputs.get("initial_guess", [0.1, -0.1]), dtype=float)
        if initial_guess.shape != (2,) or not np.all(np.isfinite(initial_guess)):
            raise EngineeringError("PlainJournal initial_guess must be [eccentricity_ratio, attitude_angle_rad].")

        if not 0 <= initial_guess[0] < 1:
            raise EngineeringError("Initial eccentricity ratio must satisfy 0 <= epsilon < 1.")
        element = rs.PlainJournal(
            n=0,
            axial_length=axial_length,
            journal_radius=journal_diameter / 2.0,
            radial_clearance=radial_clearance,
            elements_circumferential=elements_circumferential,
            elements_axial=elements_axial,
            n_pad=n_pad,
            pad_arc_length=pad_arc_deg,
            preload=preload,
            geometry=geometry,
            reference_temperature=reference_temperature_c,
            frequency=rs.Q_(speeds, "RPM"),
            fxs_load=fxs_load,
            fys_load=fys_load,
            groove_factor=groove.tolist(),
            lubricant=lubricant,
            sommerfeld_type=int(inputs.get("sommerfeld_type", 2)),
            initial_guess=initial_guess.tolist(),
            method=method,
            operating_type=operating_type,
            oil_supply_pressure=oil_supply_pressure_pa,
            oil_flow_v=rs.Q_(oil_flow_l_min, "l/min"),
        )
        results = element._results
        pressure_fields = getattr(results, "pressure_fields", [])
        temperature_fields = getattr(results, "temperature_fields", [])
        eq_by_speed = getattr(results, "equilibrium_pos_by_speed", {})
        ops: list[THDOperatingPoint] = []
        omegas = speeds * 2.0 * pi / 60.0
        for i, (rpm, omega) in enumerate(zip(speeds, omegas)):
            eq = eq_by_speed.get(float(omega)) if isinstance(eq_by_speed, dict) else None
            eq_arr = np.asarray(eq, dtype=float).reshape(-1) if eq is not None else np.empty(0)
            ecc = float(eq_arr[0]) if eq_arr.size > 0 and np.isfinite(eq_arr[0]) else None
            att = float(eq_arr[1]) if eq_arr.size > 1 and np.isfinite(eq_arr[1]) else None
            ops.append(THDOperatingPoint(
                rpm=float(rpm),
                max_pressure_pa=self._extreme(pressure_fields[i], "max") if i < len(pressure_fields) else None,
                max_temperature_c=self._extreme(temperature_fields[i], "max") if i < len(temperature_fields) else None,
                min_film_thickness_m=(radial_clearance * (1.0 - ecc) if geometry == "circular" and ecc is not None else None),
                eccentricity_ratio=ecc,
                attitude_angle_rad=att,
            ))
        return self._base_result(
            "PlainJournal",
            element,
            speeds,
            {
                "axial_length_m": axial_length,
                "journal_diameter_m": journal_diameter,
                "radial_clearance_m": radial_clearance,
                "elements_circumferential": elements_circumferential,
                "elements_axial": elements_axial,
                "n_pad": n_pad,
                "pad_arc_deg": pad_arc_deg,
                "preload": preload,
                "geometry": geometry,
                "reference_temperature_c": reference_temperature_c,
                "fxs_load_n": fxs_load,
                "fys_load_n": fys_load,
                "lubricant": lubricant,
                "operating_type": operating_type,
                "method": method,
                "oil_flow_l_min": oil_flow_l_min,
                "oil_supply_pressure_pa": oil_supply_pressure_pa,
                "groove_factor": groove.tolist(),
                "sommerfeld_type": int(inputs.get("sommerfeld_type", 2)),
                "initial_guess": initial_guess.tolist(),
            },
            ops,
            "Native ROSS 2.3 PlainJournal THD/Reynolds solution; solved K/C is cached as BearingElement for rotor execution.",
        )

    def _tilting_pad(self, project: RotorProject, inputs: dict[str, Any]) -> THDBearingCalculationResult:
        rs = self._ross()
        speeds = self._speed_vector(project, inputs)
        n_pads = int(inputs.get("n_pads", 5))
        if n_pads < 3:
            raise EngineeringError("TiltingPad requires at least three pads.")
        pivot_angles_deg = np.asarray(inputs.get("pivot_angles_deg", np.linspace(18.0, 306.0, n_pads)), dtype=float)
        if pivot_angles_deg.size != n_pads or not np.all(np.isfinite(pivot_angles_deg)):
            raise EngineeringError("TiltingPad pivot angle vector must contain one finite angle per pad.")
        pad_arc_deg = self._positive(inputs.get("pad_arc_deg", 60.0), "Pad arc")
        pad_length_m = self._positive(inputs.get("pad_axial_length_m", 0.0508), "Pad axial length")
        preload = self._positive(inputs.get("preload", 0.5), "Preload", allow_zero=True)
        if preload >= 1.0:
            raise EngineeringError("TiltingPad preload must be smaller than 1.")
        offset = self._finite(inputs.get("offset", 0.5), "Pivot offset")
        if not 0.0 <= offset <= 1.0:
            raise EngineeringError("TiltingPad pivot offset must be between 0 and 1.")
        thermal_type = str(inputs.get("thermal_type", "adiabatic"))
        if thermal_type not in {"adiabatic", "full"}:
            raise EngineeringError("TiltingPad thermal_type must be adiabatic or full.")
        nx = int(inputs.get("nx", inputs.get("total_ex_film", 10)))
        nz = int(inputs.get("nz", inputs.get("total_ez_film", 10)))
        if nx < 4 or nz < 4:
            raise EngineeringError("TiltingPad mesh requires at least 4 x 4 film volumes.")
        journal_diameter = self._positive(inputs.get("journal_diameter_m", 0.1016), "Journal diameter")
        radial_clearance = self._positive(inputs.get("radial_clearance_m", 74.9e-6), "Radial clearance")
        pad_thickness = self._positive(inputs.get("pad_thickness_m", 12.7e-3), "Pad thickness")
        oil_supply_temperature_c = self._finite(inputs.get("oil_supply_temperature_c", 40.0), "Oil supply temperature")
        lubricant = str(inputs.get("lubricant", "ISOVG32"))
        eccentricity = self._finite(inputs.get("eccentricity_ratio", 0.35), "Eccentricity ratio")
        if not 0.0 <= eccentricity < 1.0:
            raise EngineeringError("TiltingPad eccentricity ratio must satisfy 0 <= epsilon < 1.")
        attitude_deg = self._finite(inputs.get("attitude_angle_deg", 287.5), "Attitude angle")
        fxs_load = self._finite(inputs.get("fxs_load_n", 884.05), "Static load X")
        fys_load = self._finite(inputs.get("fys_load_n", -2670.4), "Static load Y")
        equilibrium_type = str(inputs.get("equilibrium_type", "match_eccentricity"))
        if equilibrium_type not in {"match_eccentricity", "determine_eccentricity"}:
            raise EngineeringError("TiltingPad equilibrium_type is invalid.")

        element = rs.TiltingPad(
            n=0,
            journal_diameter=journal_diameter,
            pre_load=[preload] * n_pads,
            pad_thickness=pad_thickness,
            pad_arc=rs.Q_([pad_arc_deg] * n_pads, "deg"),
            offset=[offset] * n_pads,
            pad_axial_length=[pad_length_m] * n_pads,
            lubricant=lubricant,
            oil_supply_temperature=rs.Q_(oil_supply_temperature_c, "degC"),
            radial_clearance=radial_clearance,
            pivot_angle=rs.Q_(pivot_angles_deg, "deg"),
            frequency=rs.Q_(speeds, "RPM"),
            nx=nx,
            nz=nz,
            equilibrium_type=equilibrium_type,
            eccentricity=eccentricity,
            attitude_angle=rs.Q_(attitude_deg, "deg"),
            load=[fxs_load, fys_load],
            thermal_type=thermal_type,
        )
        results = element._results
        pressure_fields = getattr(results, "pressure_fields", [])
        temperature_fields = getattr(results, "temperature_fields", [])
        ops: list[THDOperatingPoint] = []
        for i, rpm in enumerate(speeds):
            max_p = self._sequence_value(getattr(results, "maxP_list", None), i)
            max_t = self._sequence_value(getattr(results, "maxT_list", None), i)
            ops.append(THDOperatingPoint(
                rpm=float(rpm),
                max_pressure_pa=self._extreme(pressure_fields[i], "max") if i < len(pressure_fields) else max_p,
                max_temperature_c=self._extreme(temperature_fields[i], "max") if i < len(temperature_fields) else max_t,
                min_film_thickness_m=None,  # ROSS minH_list is h_pivot, not a global film minimum.
                eccentricity_ratio=self._sequence_value(getattr(results, "ecc_list", None), i),
                attitude_angle_rad=self._sequence_value(getattr(results, "attitude_angle_list", None), i),
            ))
        return self._base_result(
            "TiltingPad",
            element,
            speeds,
            {
                "journal_diameter_m": journal_diameter,
                "radial_clearance_m": radial_clearance,
                "pad_thickness_m": pad_thickness,
                "geometry": "tilting_pads",
                "n_pads": n_pads,
                "pivot_angles_deg": [float(value) for value in pivot_angles_deg],
                "pad_arc_deg": pad_arc_deg,
                "pad_axial_length_m": pad_length_m,
                "preload": preload,
                "offset": offset,
                "lubricant": lubricant,
                "oil_supply_temperature_c": oil_supply_temperature_c,
                "fxs_load_n": fxs_load,
                "fys_load_n": fys_load,
                "equilibrium_type": equilibrium_type,
                "eccentricity_ratio": eccentricity,
                "attitude_angle_deg": attitude_deg,
                "thermal_type": thermal_type,
                "nx": nx,
                "nz": nz,
            },
            ops,
            "Native ROSS 2.3 TiltingPad THD solution; solved K/C is cached as BearingElement for rotor execution.",
        )

    def _squeeze_film_damper(self, project: RotorProject, inputs: dict[str, Any]) -> THDBearingCalculationResult:
        rs = self._ross()
        speeds = self._speed_vector(project, inputs)
        geometry = str(inputs.get("geometry", "groove"))
        if geometry not in {"groove", "end_seals", "groove-end_seals"}:
            raise EngineeringError("SqueezeFilmDamper geometry must be groove, end_seals or groove-end_seals.")
        eccentricity_ratio = self._finite(inputs.get("eccentricity_ratio", 0.5), "Eccentricity ratio")
        if not 0.0 <= eccentricity_ratio < 1.0:
            raise EngineeringError("SqueezeFilmDamper eccentricity ratio must satisfy 0 <= epsilon < 1.")
        axial_length = self._positive(inputs.get("axial_length_m", 0.02286), "Damper axial length")
        journal_diameter = self._positive(inputs.get("journal_diameter_m", 0.12954), "Journal diameter")
        radial_clearance = self._positive(inputs.get("radial_clearance_m", 7.62e-5), "Radial clearance")
        lubricant = str(inputs.get("lubricant", "ISOVG32"))
        cavitation = bool(inputs.get("cavitation", True))
        element = rs.SqueezeFilmDamper(
            n=0,
            frequency=rs.Q_(speeds, "RPM"),
            axial_length=axial_length,
            journal_radius=journal_diameter / 2.0,
            radial_clearance=radial_clearance,
            eccentricity_ratio=eccentricity_ratio,
            lubricant=lubricant,
            geometry=geometry,
            cavitation=cavitation,
        )
        pressure = np.asarray(getattr(element, "p_max", []), dtype=float).reshape(-1)
        h_min = radial_clearance * (1.0 - eccentricity_ratio)
        ops = [
            THDOperatingPoint(
                rpm=float(rpm),
                max_pressure_pa=float(pressure[i]) if i < pressure.size and np.isfinite(pressure[i]) else None,
                min_film_thickness_m=h_min,
                eccentricity_ratio=eccentricity_ratio,
            )
            for i, rpm in enumerate(speeds)
        ]
        return self._base_result(
            "SqueezeFilmDamper",
            element,
            speeds,
            {
                "axial_length_m": axial_length,
                "journal_diameter_m": journal_diameter,
                "radial_clearance_m": radial_clearance,
                "eccentricity_ratio": eccentricity_ratio,
                "lubricant": lubricant,
                "geometry": geometry,
                "cavitation": int(cavitation),
            },
            ops,
            "Native ROSS 2.3 SqueezeFilmDamper solution; solved K/C is cached as BearingElement for rotor execution.",
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
