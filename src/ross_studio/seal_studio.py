from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from math import pi
from typing import Any

import numpy as np

from .domain import EngineeringError, RotorProject, SealSpec
from .ross_backend_base import RossModelBuilder as BaseRossModelBuilder
from .seal_models import (
    HolePatternSealSpec,
    HybridSealSpec,
    LabyrinthSealSpec,
    SealCoefficientPoint,
    SealModel,
    seal_model,
)


@dataclass(slots=True)
class SealCalculationPreview:
    source: SealSpec
    prepared: SealSpec
    native: Any
    node: int
    model: SealModel
    leakage_kg_s: list[float]
    summary: dict[str, object]

    @property
    def coefficients(self) -> list[SealCoefficientPoint]:
        return list(getattr(self.prepared, "calculated_coefficients", []))


class SealStudioService:
    """ROSS-native Calculate -> Preview service for Seal Studio 0.25.

    Advanced seal physics is never duplicated here. This service instantiates the
    exact ROSS 2.3.0 LabyrinthSeal, HolePatternSeal or HybridSeal, extracts its native
    frequency-dependent K/C/M matrices, and prepares a serializable engineering spec.
    Strict rotor assembly later consumes those qualified coefficients as SealElement
    data while retaining the original model inputs and calculation summary.
    """

    def __init__(self, ross_module: Any | None = None) -> None:
        self.rs = ross_module

    def _ross(self) -> Any:
        if self.rs is None:
            import ross as rs

            self.rs = rs
        if getattr(self.rs, "__version__", None) != "2.3.0":
            raise EngineeringError(
                f"Seal Studio 0.25 is qualified only against ROSS 2.3.0; received {getattr(self.rs, '__version__', 'unknown')}."
            )
        return self.rs

    @staticmethod
    def _node(project: RotorProject, source: SealSpec) -> int:
        """Resolve the node against the prospective model, never by nearest-node snapping.

        A brand-new seal is itself an exact-node insertion request. Calculating it must
        therefore use the topology that would exist after Apply, not only the current
        live project. Appending a duplicate draft for an Edit is harmless because the
        topology service unions physical coordinates.
        """

        candidate = deepcopy(project)
        candidate.seals.append(deepcopy(source))
        mapping = BaseRossModelBuilder.map_position(candidate, source.position_mm)
        if mapping.node is None:  # defensive: NodeInsertionService should insert it exactly
            raise EngineeringError(
                f"Seal position {source.position_mm:g} mm could not be represented as an exact ROSS shaft node."
            )
        return int(mapping.node)

    @staticmethod
    def _frequency_rpm(native: Any) -> np.ndarray:
        frequency = np.atleast_1d(np.asarray(getattr(native, "frequency", []), dtype=float))
        if frequency.size == 0:
            return np.asarray([0.0], dtype=float)
        return frequency * 60.0 / (2.0 * pi)

    @classmethod
    def _coefficients(cls, native: Any) -> list[SealCoefficientPoint]:
        rpm = cls._frequency_rpm(native)
        frequency = np.atleast_1d(np.asarray(getattr(native, "frequency", [0.0]), dtype=float))
        if frequency.size != rpm.size:
            raise EngineeringError("ROSS seal frequency axis could not be normalized.")
        rows: list[SealCoefficientPoint] = []
        for value_rpm, omega in zip(rpm, frequency):
            k = np.asarray(native.K(float(omega)), dtype=float)
            c = np.asarray(native.C(float(omega)), dtype=float)
            m = np.asarray(native.M(float(omega)), dtype=float)
            if min(k.shape[0], k.shape[1], c.shape[0], c.shape[1], m.shape[0], m.shape[1]) < 2:
                raise EngineeringError("ROSS seal native matrices do not expose the qualified lateral 2x2 block.")
            rows.append(
                SealCoefficientPoint(
                    rpm=float(value_rpm),
                    kxx=float(k[0, 0]),
                    kxy=float(k[0, 1]),
                    kyx=float(k[1, 0]),
                    kyy=float(k[1, 1]),
                    cxx=float(c[0, 0]),
                    cxy=float(c[0, 1]),
                    cyx=float(c[1, 0]),
                    cyy=float(c[1, 1]),
                    mxx=float(m[0, 0]),
                    mxy=float(m[0, 1]),
                    myx=float(m[1, 0]),
                    myy=float(m[1, 1]),
                )
            )
        return rows

    @staticmethod
    def _leakage(native: Any) -> list[float]:
        raw = getattr(native, "seal_leakage", [])
        try:
            values = np.atleast_1d(np.asarray(raw, dtype=float)).reshape(-1)
        except Exception:
            return []
        return [float(value) for value in values if np.isfinite(value)]

    @staticmethod
    def _pressure_payload(native: Any) -> dict[str, object]:
        payload: dict[str, object] = {}
        z = getattr(native, "z", None)
        if z is not None:
            try:
                values = np.asarray(z, dtype=float).reshape(-1)
                payload["axial_m"] = [float(value) for value in values if np.isfinite(value)]
            except Exception:
                pass
        pressure = getattr(native, "p", None)
        if pressure is not None:
            try:
                arr = np.asarray(pressure, dtype=float)
                if arr.ndim == 1:
                    payload["pressure_pa"] = [[float(value) for value in arr if np.isfinite(value)]]
                elif arr.ndim >= 2:
                    payload["pressure_pa"] = [
                        [float(value) for value in row.reshape(-1) if np.isfinite(value)] for row in arr
                    ]
            except Exception:
                pass
        return payload

    def _direct(self, rs: Any, source: SealSpec, node: int) -> SealCalculationPreview:
        native = rs.SealElement(
            n=node,
            kxx=source.kxx,
            kyy=source.kyy,
            kxy=source.kxy,
            kyx=source.kyx,
            cxx=source.cxx,
            cyy=source.cyy,
            cxy=source.cxy,
            cyx=source.cyx,
            tag=source.name,
        )
        return SealCalculationPreview(
            source=deepcopy(source),
            prepared=deepcopy(source),
            native=native,
            node=node,
            model=SealModel.DIRECT,
            leakage_kg_s=[],
            summary={"ross_class": type(native).__name__, "node": node, "model": SealModel.DIRECT.value},
        )

    def _labyrinth(self, source: LabyrinthSealSpec, node: int) -> SealCalculationPreview:
        from ross.seals.labyrinth_seal import LabyrinthSeal
        from ross.units import Q_

        source.validate_inputs()
        native = LabyrinthSeal(
            n=node,
            shaft_radius=source.shaft_radius_m,
            radial_clearance=source.radial_clearance_m,
            n_teeth=source.n_teeth,
            pitch=source.pitch_m,
            tooth_height=source.tooth_height_m,
            tooth_width=source.tooth_width_m,
            seal_type=source.seal_type,
            inlet_pressure=source.inlet_pressure_pa,
            outlet_pressure=source.outlet_pressure_pa,
            inlet_temperature=source.inlet_temperature_k,
            frequency=Q_(source.frequency_rpm, "RPM"),
            preswirl=source.preswirl,
            gas_composition=source.gas_composition or None,
            molar=source.molar_kg_kmol,
            gamma=source.gamma,
            tz=None if source.tz_k is None else list(source.tz_k),
            muz=None if source.muz_pa_s is None else list(source.muz_pa_s),
            analz=source.analz,
            nprt=source.nprt,
            iopt1=source.iopt1,
            tag=source.name,
        )
        coefficients = self._coefficients(native)
        leakage = self._leakage(native)
        prepared = deepcopy(source)
        prepared.calculated_coefficients = coefficients
        prepared.calculation = {
            "ross_class": type(native).__name__,
            "model": SealModel.LABYRINTH.value,
            "node": node,
            "leakage_kg_s": leakage,
            **self._pressure_payload(native),
        }
        prepared.validate_calculated()
        return SealCalculationPreview(deepcopy(source), prepared, native, node, SealModel.LABYRINTH, leakage, dict(prepared.calculation))

    def _hole_pattern(self, source: HolePatternSealSpec, node: int) -> SealCalculationPreview:
        from ross.seals.holepattern_seal import HolePatternSeal
        from ross.units import Q_

        source.validate_inputs()
        native = HolePatternSeal(
            n=node,
            shaft_radius=source.shaft_radius_m,
            inlet_pressure=source.inlet_pressure_pa,
            outlet_pressure=source.outlet_pressure_pa,
            inlet_temperature=source.inlet_temperature_k,
            frequency=Q_(source.frequency_rpm, "RPM"),
            gas_composition=source.gas_composition or None,
            molar=source.molar_kg_kmol,
            gamma=source.gamma,
            tag=source.name,
            **source.stage().ross_kwargs(),
        )
        coefficients = self._coefficients(native)
        leakage = self._leakage(native)
        prepared = deepcopy(source)
        prepared.calculated_coefficients = coefficients
        prepared.calculation = {
            "ross_class": type(native).__name__,
            "model": SealModel.HOLE_PATTERN.value,
            "node": node,
            "leakage_kg_s": leakage,
            **self._pressure_payload(native),
        }
        prepared.validate_calculated()
        return SealCalculationPreview(deepcopy(source), prepared, native, node, SealModel.HOLE_PATTERN, leakage, dict(prepared.calculation))

    def _hybrid(self, source: HybridSealSpec, node: int) -> SealCalculationPreview:
        from ross.seals.hybrid_seal import HybridSeal
        from ross.units import Q_

        source.validate_inputs()
        native = HybridSeal(
            n=node,
            shaft_radius=source.shaft_radius_m,
            inlet_pressure=source.inlet_pressure_pa,
            outlet_pressure=source.outlet_pressure_pa,
            inlet_temperature=source.inlet_temperature_k,
            frequency=Q_(source.frequency_rpm, "RPM"),
            gas_composition=source.gas_composition or None,
            molar=source.molar_kg_kmol,
            gamma=source.gamma,
            hole_pattern_parameters=source.hole_pattern.ross_kwargs(),
            labyrinth_parameters=source.labyrinth.ross_kwargs(),
            tolerance=source.pressure_match_tolerance,
            max_iterations=source.pressure_match_max_iterations,
            tag=source.name,
        )
        coefficients = self._coefficients(native)
        leakage = self._leakage(native)
        prepared = deepcopy(source)
        prepared.calculated_coefficients = coefficients
        convergence = [float(value) for value in getattr(native, "convergence_history", [])]
        prepared.calculation = {
            "ross_class": type(native).__name__,
            "model": SealModel.HYBRID.value,
            "node": node,
            "leakage_kg_s": leakage,
            "interface_pressure_pa": float(native.interface_pressure),
            "n_iterations": int(native.n_iterations),
            "convergence_history": convergence,
            "pressure_history_pa": [float(value) for value in getattr(native, "pressure_history", [])],
            "leakage_hole_history_kg_s": [float(value) for value in getattr(native, "leakage_hole_history", [])],
            "leakage_labyrinth_history_kg_s": [float(value) for value in getattr(native, "leakage_laby_history", [])],
            "final_convergence": float(convergence[-1]) if convergence else None,
        }
        prepared.validate_calculated()
        return SealCalculationPreview(deepcopy(source), prepared, native, node, SealModel.HYBRID, leakage, dict(prepared.calculation))

    def calculate(self, project: RotorProject, source: SealSpec) -> SealCalculationPreview:
        project.validate()
        rs = self._ross()
        node = self._node(project, source)
        model = seal_model(source)
        if model == SealModel.DIRECT:
            return self._direct(rs, source, node)
        if isinstance(source, LabyrinthSealSpec):
            return self._labyrinth(source, node)
        if isinstance(source, HolePatternSealSpec):
            return self._hole_pattern(source, node)
        if isinstance(source, HybridSealSpec):
            return self._hybrid(source, node)
        raise EngineeringError(
            f"Seal {source.name!r} declares model {model.value} but its engineering spec type is {type(source).__name__}."
        )


__all__ = ["SealCalculationPreview", "SealStudioService"]
