from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import inspect
import json
from math import pi
from pathlib import Path
from tempfile import TemporaryDirectory
import time
from typing import Any, Mapping
import warnings

import numpy as np
from PySide6.QtCore import QSignalBlocker
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QLineEdit,
    QSpinBox,
)

from .app import RossStudioWindow
from .domain import BearingCoefficientPoint, EngineeringError
from .pages.static_modal_workspace import StaticModalWorkspacePage
from .project_io import load_project, save_project
from .ross_backend import RossModelBuilder
from .thd_bearing_service import THDBearingStudioService
from .thrust_pad_service import ThrustPadStudioService


LATERAL_MODELS = ("PlainJournal", "TiltingPad", "SqueezeFilmDamper")
ALL_MODELS = (*LATERAL_MODELS, "ThrustPad")
LATERAL_COEFFS = ("kxx", "kxy", "kyx", "kyy", "cxx", "cxy", "cyx", "cyy")


INPUTS: dict[str, dict[str, Any]] = {
    "PlainJournal": {
        "speed_rpm": [900.0, 1000.0, 1200.0],
        "journal_diameter_mm": 400.0,
        "radial_clearance_um": 195.0,
        "lubricant": "ISOVG32",
        "axial_length_mm": 263.144,
        "n_pad": 2,
        "pad_arc_deg": 176.0,
        "preload": 0.0,
        "geometry": "circular",
        "reference_temperature_c": 50.0,
        "fxs_load_n": 0.0,
        "fys_load_n": -112814.91,
        "groove_factor": [0.52, 0.48],
        "sommerfeld_type": "2",
        "initial_eccentricity_ratio": 0.1,
        "initial_attitude_angle_deg": -5.729577951308233,
        "method": "perturbation",
        "operating_type": "flooded",
        "oil_flow_l_min": 37.86,
        "oil_supply_pressure_bar": 0.0,
        "elements_circumferential": 11,
        "elements_axial": 3,
    },
    "TiltingPad": {
        "speed_rpm": [3000.0, 3300.0, 3600.0],
        "journal_diameter_mm": 101.6,
        "radial_clearance_um": 74.9,
        "lubricant": "ISOVG32",
        "pad_thickness_mm": 12.7,
        "n_pads": 5,
        "pivot_angles_deg": [18.0, 90.0, 162.0, 234.0, 306.0],
        "pad_arc_deg": 60.0,
        "pad_axial_length_mm": 50.8,
        "preload": 0.5,
        "offset": 0.5,
        "oil_supply_temperature_c": 40.0,
        "fxs_load_n": 884.05,
        "fys_load_n": -2670.4,
        "equilibrium_type": "match_eccentricity",
        "eccentricity_ratio": 0.35,
        "attitude_angle_deg": 287.5,
        "thermal_type": "adiabatic",
        "nx": 10,
        "nz": 10,
        "solver_xtol": 1.0e-3,
        "solver_ftol": 1.0e-3,
        "solver_maxiter": 1000,
        "inlet_temperature_tolerance_c": 0.5,
        "max_inlet_iterations": 25,
        "max_jtemp_iter": 100,
        "journal_temperature_tolerance_c": 1.0,
        "journal_temperature_c": 25.0,
        "hot_oil_carry_over": 0.8,
    },
    "SqueezeFilmDamper": {
        "speed_rpm": [900.0, 2250.0, 3600.0],
        "journal_diameter_mm": 129.54,
        "radial_clearance_um": 76.2,
        "lubricant": "ISOVG32",
        "axial_length_mm": 22.86,
        "eccentricity_ratio": 0.43,
        "geometry": "groove",
        "cavitation": True,
    },
    "ThrustPad": {
        "speed_rpm": [90.0, 120.0, 150.0],
        "pad_inner_radius_mm": 1150.0,
        "pad_outer_radius_mm": 1725.0,
        "pad_pivot_radius_mm": 1442.5,
        "pad_arc_deg": 26.0,
        "angular_pivot_position_deg": 15.0,
        "oil_supply_temperature_c": 40.0,
        "lubricant": "ISOVG68",
        "n_pad": 12,
        "n_theta": 10,
        "n_radial": 10,
        "equilibrium_position_mode": "calculate",
        "axial_load_n": 13.320e6,
        "radial_inclination_angle_mrad": -0.275,
        "circumferential_inclination_angle_mrad": -0.017,
        "initial_film_thickness_um": 200.0,
        "tolerance_force_moment_n": 0.1,
        "residual_force_moment_n": 50.0,
    },
}


@dataclass(slots=True)
class THDBearings027Qualification:
    status: str
    payload: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        data = dict(self.payload)
        data["status"] = self.status
        return data


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _set_widget(widget, value: Any) -> None:
    if isinstance(widget, QComboBox):
        widget.setCurrentText(str(value))
    elif isinstance(widget, QCheckBox):
        widget.setChecked(bool(value))
    elif isinstance(widget, QLineEdit):
        if isinstance(value, (list, tuple)):
            widget.setText(", ".join(f"{float(v):.15g}" for v in value))
        else:
            widget.setText(str(value))
    elif isinstance(widget, QSpinBox):
        widget.setValue(int(value))
    elif isinstance(widget, QDoubleSpinBox):
        widget.setValue(float(value))
    else:
        raise TypeError(f"Unsupported THD widget {type(widget).__name__}.")


def _set_gui_inputs(window: RossStudioWindow, model: str, values: Mapping[str, Any]) -> dict[str, Any]:
    window._open_bearing_group("THD")
    key = window._bearing_key_for_class(window.bearing_page, model)
    if key is None:
        raise RuntimeError(f"Bearing Studio does not expose {model}.")
    window.bearing_page.type_buttons[key].click()
    panel = window.bearing_page.input_panel
    for name, value in values.items():
        if name not in panel.fields:
            raise RuntimeError(f"{model}: GUI is missing required engineering input {name!r}.")
        _set_widget(panel.fields[name], value)
    return deepcopy(window.bearing_page.input_values())


def _mutated_value(widget) -> Any:
    if isinstance(widget, QDoubleSpinBox):
        value = float(widget.value())
        return value * 1.001 + (0.001 if value == 0.0 else 0.0)
    if isinstance(widget, QSpinBox):
        return int(widget.value()) + 1
    if isinstance(widget, QLineEdit):
        text = widget.text()
        parts = [item.strip() for item in text.split(",") if item.strip()]
        if parts:
            parts[0] = f"{float(parts[0]) * 1.001:.15g}"
            return ", ".join(parts)
        return text + "1"
    raise TypeError(type(widget).__name__)


def _stale_preview_and_apply(window: RossStudioWindow, model: str, values: Mapping[str, Any]) -> tuple[dict[str, object], Any]:
    field = {
        "PlainJournal": "radial_clearance_um",
        "TiltingPad": "preload",
        "SqueezeFilmDamper": "eccentricity_ratio",
        "ThrustPad": "axial_load_n",
    }[model]
    panel = window.bearing_page.input_panel
    widget = panel.fields[field]
    original = values[field]

    # Normal Qt signal path.
    _set_widget(widget, _mutated_value(widget))
    QApplication.processEvents()
    normal = window.bearing_calculation is None and not window.bearing_page.apply_button.isEnabled()

    _set_widget(widget, original)
    window.bearing_page.calculate_button.click()
    result = window.bearing_calculation
    if result is None or not window.bearing_page.apply_button.isEnabled():
        raise RuntimeError(f"{model}: recalculation failed before blocked-signal stale gate.")

    # Suppress the widget signal deliberately. Apply must still re-read visible inputs.
    blocker = QSignalBlocker(widget)
    _set_widget(widget, _mutated_value(widget))
    del blocker
    QApplication.processEvents()
    preview_survived = window.bearing_calculation is result and window.bearing_page.apply_button.isEnabled()
    before = deepcopy(window.project.engineering)
    window.bearing_page.apply_button.click()
    QApplication.processEvents()
    blocked_rejected = window.project.engineering == before and window.bearing_calculation is result

    # Restore exact calculated input without relying on a new solver run, then Apply.
    blocker = QSignalBlocker(widget)
    _set_widget(widget, original)
    del blocker
    window.bearing_page.apply_button.click()
    QApplication.processEvents()
    applied = window.bearing_calculation is None

    return {
        "scientific_field": field,
        "normal_signal_invalidated_preview": bool(normal),
        "blocked_signals_left_preview_present": bool(preview_survived),
        "apply_revalidated_visible_input_and_rejected_stale": bool(blocked_rejected),
        "restored_exact_snapshot_applied_without_resolve": bool(applied),
        "pass": bool(normal and preview_survived and blocked_rejected and applied),
    }, result


def _manual_native(rs, model: str, v: Mapping[str, Any]):
    speeds = list(map(float, v["speed_rpm"]))
    if model == "PlainJournal":
        return rs.PlainJournal(
            n=0,
            axial_length=float(v["axial_length_mm"]) / 1000.0,
            journal_radius=float(v["journal_diameter_mm"]) / 2000.0,
            radial_clearance=float(v["radial_clearance_um"]) * 1.0e-6,
            elements_circumferential=int(v["elements_circumferential"]),
            elements_axial=int(v["elements_axial"]),
            n_pad=int(v["n_pad"]),
            pad_arc_length=float(v["pad_arc_deg"]),
            preload=float(v["preload"]),
            geometry=str(v["geometry"]),
            reference_temperature=float(v["reference_temperature_c"]),
            frequency=rs.Q_(speeds, "RPM"),
            fxs_load=float(v["fxs_load_n"]),
            fys_load=float(v["fys_load_n"]),
            lubricant=str(v["lubricant"]),
            sommerfeld_type=int(v["sommerfeld_type"]),
            initial_guess=[
                float(v["initial_eccentricity_ratio"]),
                float(v["initial_attitude_angle_deg"]) * pi / 180.0,
            ],
            method=str(v["method"]),
            operating_type=str(v["operating_type"]),
            groove_factor=list(v["groove_factor"]),
            oil_supply_pressure=float(v["oil_supply_pressure_bar"]) * 1.0e5,
            oil_flow_v=rs.Q_(float(v["oil_flow_l_min"]), "l/min"),
        )
    if model == "TiltingPad":
        n = int(v["n_pads"])
        return rs.TiltingPad(
            n=0,
            journal_diameter=float(v["journal_diameter_mm"]) / 1000.0,
            pre_load=[float(v["preload"])] * n,
            pad_thickness=float(v["pad_thickness_mm"]) / 1000.0,
            pad_arc=rs.Q_([float(v["pad_arc_deg"])] * n, "deg"),
            offset=[float(v["offset"])] * n,
            pad_axial_length=[float(v["pad_axial_length_mm"]) / 1000.0] * n,
            lubricant=str(v["lubricant"]),
            oil_supply_temperature=rs.Q_(float(v["oil_supply_temperature_c"]), "degC"),
            radial_clearance=float(v["radial_clearance_um"]) * 1.0e-6,
            pivot_angle=rs.Q_(list(v["pivot_angles_deg"]), "deg"),
            frequency=rs.Q_(speeds, "RPM"),
            nx=int(v["nx"]),
            nz=int(v["nz"]),
            equilibrium_type=str(v["equilibrium_type"]),
            eccentricity=float(v["eccentricity_ratio"]),
            attitude_angle=rs.Q_(float(v["attitude_angle_deg"]), "deg"),
            load=[float(v["fxs_load_n"]), float(v["fys_load_n"])],
            thermal_type=str(v["thermal_type"]),
            solver_options={
                "xtol": float(v["solver_xtol"]),
                "ftol": float(v["solver_ftol"]),
                "maxiter": int(v["solver_maxiter"]),
            },
            hot_oil_carry_over=float(v["hot_oil_carry_over"]),
            inlet_temperature_tolerance=float(v["inlet_temperature_tolerance_c"]),
            max_inlet_iterations=int(v["max_inlet_iterations"]),
            max_jtemp_iter=int(v["max_jtemp_iter"]),
            jtemp_error=float(v["journal_temperature_tolerance_c"]),
            journal_temperature=float(v["journal_temperature_c"]),
        )
    if model == "SqueezeFilmDamper":
        return rs.SqueezeFilmDamper(
            n=0,
            frequency=rs.Q_(speeds, "RPM"),
            axial_length=float(v["axial_length_mm"]) / 1000.0,
            journal_radius=float(v["journal_diameter_mm"]) / 2000.0,
            radial_clearance=float(v["radial_clearance_um"]) * 1.0e-6,
            eccentricity_ratio=float(v["eccentricity_ratio"]),
            lubricant=str(v["lubricant"]),
            geometry=str(v["geometry"]),
            cavitation=bool(v["cavitation"]),
        )
    return rs.ThrustPad(
        n=0,
        pad_inner_radius=rs.Q_(float(v["pad_inner_radius_mm"]) / 1000.0, "m"),
        pad_outer_radius=rs.Q_(float(v["pad_outer_radius_mm"]) / 1000.0, "m"),
        pad_pivot_radius=rs.Q_(float(v["pad_pivot_radius_mm"]) / 1000.0, "m"),
        pad_arc_length=rs.Q_(float(v["pad_arc_deg"]), "deg"),
        angular_pivot_position=rs.Q_(float(v["angular_pivot_position_deg"]), "deg"),
        oil_supply_temperature=rs.Q_(float(v["oil_supply_temperature_c"]), "degC"),
        lubricant=str(v["lubricant"]),
        n_pad=int(v["n_pad"]),
        n_theta=int(v["n_theta"]),
        n_radial=int(v["n_radial"]),
        frequency=rs.Q_(speeds, "RPM"),
        equilibrium_position_mode=str(v["equilibrium_position_mode"]),
        radial_inclination_angle=rs.Q_(float(v["radial_inclination_angle_mrad"]) * 1.0e-3, "rad"),
        circumferential_inclination_angle=rs.Q_(float(v["circumferential_inclination_angle_mrad"]) * 1.0e-3, "rad"),
        initial_film_thickness=rs.Q_(float(v["initial_film_thickness_um"]) * 1.0e-6, "m"),
        tolerance_force_moment=float(v["tolerance_force_moment_n"]),
        residual_force_moment=float(v["residual_force_moment_n"]),
        model_type="thermo_hydro_dynamic",
        axial_load=float(v["axial_load_n"]),
    )


def _matrices(rs, element, rpm: float) -> tuple[np.ndarray, np.ndarray]:
    omega = float(rpm) * 2.0 * pi / 60.0
    return (
        np.asarray(rs.BearingElement.K(element, omega), dtype=float),
        np.asarray(rs.BearingElement.C(element, omega), dtype=float),
    )


def _parity(rs, model: str, studio, independent, speeds: list[float]) -> tuple[list[dict[str, object]], bool]:
    rpms = list(map(float, speeds))
    if len(rpms) > 1:
        rpms.insert(1, 0.5 * (rpms[0] + rpms[1]))
    rows: list[dict[str, object]] = []
    passed = True
    for rpm in rpms:
        sk, sc = _matrices(rs, studio, rpm)
        rk, rc = _matrices(rs, independent, rpm)
        if model == "ThrustPad":
            entries = (("kzz", sk[2, 2], rk[2, 2], 1.0e-4), ("czz", sc[2, 2], rc[2, 2], 1.0e-7))
        else:
            entries = (
                ("kxx", sk[0, 0], rk[0, 0], 1.0e-4),
                ("kxy", sk[0, 1], rk[0, 1], 1.0e-4),
                ("kyx", sk[1, 0], rk[1, 0], 1.0e-4),
                ("kyy", sk[1, 1], rk[1, 1], 1.0e-4),
                ("cxx", sc[0, 0], rc[0, 0], 1.0e-7),
                ("cxy", sc[0, 1], rc[0, 1], 1.0e-7),
                ("cyx", sc[1, 0], rc[1, 0], 1.0e-7),
                ("cyy", sc[1, 1], rc[1, 1], 1.0e-7),
            )
        for quantity, actual, reference, atol in entries:
            actual = float(actual)
            reference = float(reference)
            absolute = abs(actual - reference)
            relative = absolute / max(abs(reference), atol)
            ok = bool(np.isclose(actual, reference, rtol=1.0e-9, atol=atol))
            passed &= ok
            rows.append(
                {
                    "rpm": rpm,
                    "quantity": quantity,
                    "studio": actual,
                    "independent_ross": reference,
                    "absolute_error": absolute,
                    "relative_error": relative,
                    "rtol": 1.0e-9,
                    "atol": atol,
                    "pass": ok,
                }
            )
    return rows, bool(passed)


def _unit_binding(model: str, inputs: Mapping[str, Any], native) -> list[dict[str, object]]:
    """Audit values sent from real GUI engineering units to the native ROSS object."""
    rows: list[dict[str, object]] = []

    def add(
        quantity: str,
        gui_value: float,
        gui_unit: str,
        expected_native_value: float,
        native_value: float,
        native_unit: str,
        *,
        conversion: str,
        si_audit_value: float | None = None,
        atol: float = 1.0e-12,
    ) -> None:
        expected = float(expected_native_value)
        actual = float(native_value)
        rows.append(
            {
                "quantity": quantity,
                "gui_value": float(gui_value),
                "gui_unit": gui_unit,
                "conversion": conversion,
                "expected_native_value": expected,
                "native_value": actual,
                "native_unit": native_unit,
                "si_audit_value": None if si_audit_value is None else float(si_audit_value),
                "absolute_error": abs(actual - expected),
                "pass": bool(np.isclose(actual, expected, rtol=1.0e-12, atol=atol)),
            }
        )

    if model in LATERAL_MODELS:
        add(
            "journal_diameter_to_native_radius",
            inputs["journal_diameter_mm"],
            "mm diameter",
            float(inputs["journal_diameter_mm"]) / 2000.0,
            native.journal_radius,
            "m radius",
            conversion="diameter_mm / 2000",
        )
        add(
            "radial_clearance",
            inputs["radial_clearance_um"],
            "um",
            float(inputs["radial_clearance_um"]) * 1.0e-6,
            native.radial_clearance,
            "m",
            conversion="um * 1e-6",
        )
        omega = np.asarray(native.frequency, dtype=float).reshape(-1)
        for rpm, actual in zip(inputs["speed_rpm"], omega):
            add(
                "speed",
                rpm,
                "rpm",
                float(rpm) * 2.0 * pi / 60.0,
                actual,
                "rad/s",
                conversion="rpm * 2*pi/60",
            )

        if model == "PlainJournal":
            add("axial_length", inputs["axial_length_mm"], "mm", float(inputs["axial_length_mm"]) / 1000.0, native.axial_length, "m", conversion="mm / 1000")
            add(
                "reference_temperature",
                inputs["reference_temperature_c"],
                "degC",
                float(inputs["reference_temperature_c"]),
                native.reference_temperature,
                "degC native ROSS contract",
                conversion="degC retained by ROSS constructor; SI audit K = degC + 273.15",
                si_audit_value=float(inputs["reference_temperature_c"]) + 273.15,
            )
            add("load_x", inputs["fxs_load_n"], "N", float(inputs["fxs_load_n"]), native.fxs_load, "N", conversion="identity")
            add("load_y", inputs["fys_load_n"], "N", float(inputs["fys_load_n"]), native.fys_load, "N", conversion="identity")
            add("oil_supply_pressure", inputs["oil_supply_pressure_bar"], "bar", float(inputs["oil_supply_pressure_bar"]) * 1.0e5, native.oil_supply_pressure, "Pa", conversion="bar * 1e5")
            add("preload", inputs["preload"], "1", float(inputs["preload"]), native.preload, "1", conversion="identity")
        elif model == "TiltingPad":
            add("pad_thickness", inputs["pad_thickness_mm"], "mm", float(inputs["pad_thickness_mm"]) / 1000.0, native.pad_thickness, "m", conversion="mm / 1000")
            add(
                "oil_supply_temperature",
                inputs["oil_supply_temperature_c"],
                "degC",
                float(inputs["oil_supply_temperature_c"]),
                native.oil_supply_temperature,
                "degC native ROSS contract",
                conversion="degC retained internally after Pint conversion; SI audit K = degC + 273.15",
                si_audit_value=float(inputs["oil_supply_temperature_c"]) + 273.15,
            )
            add("load_x", inputs["fxs_load_n"], "N", float(inputs["fxs_load_n"]), native.fxs_load, "N", conversion="identity")
            add("load_y", inputs["fys_load_n"], "N", float(inputs["fys_load_n"]), native.fys_load, "N", conversion="identity")
            add("preload", inputs["preload"], "1", float(inputs["preload"]), 1.0 - native.radial_clearance / (native.pad_radius - native.journal_radius), "1", conversion="identity through pad-radius geometry", atol=1.0e-10)
            add("eccentricity_ratio", inputs["eccentricity_ratio"], "1", float(inputs["eccentricity_ratio"]), native.eccentricity, "1", conversion="identity")
        else:
            add("axial_length", inputs["axial_length_mm"], "mm", float(inputs["axial_length_mm"]) / 1000.0, native.axial_length, "m", conversion="mm / 1000")
            add("eccentricity_ratio", inputs["eccentricity_ratio"], "1", float(inputs["eccentricity_ratio"]), native.eccentricity_ratio, "1", conversion="identity")
    else:
        add("pad_inner_radius", inputs["pad_inner_radius_mm"], "mm", float(inputs["pad_inner_radius_mm"]) / 1000.0, native.pad_inner_radius, "m", conversion="mm / 1000")
        add("pad_outer_radius", inputs["pad_outer_radius_mm"], "mm", float(inputs["pad_outer_radius_mm"]) / 1000.0, native.pad_outer_radius, "m", conversion="mm / 1000")
        add("pad_pivot_radius", inputs["pad_pivot_radius_mm"], "mm", float(inputs["pad_pivot_radius_mm"]) / 1000.0, native.pad_pivot_radius, "m", conversion="mm / 1000")
        add("initial_film_thickness", inputs["initial_film_thickness_um"], "um", float(inputs["initial_film_thickness_um"]) * 1.0e-6, native.initial_film_thickness, "m", conversion="um * 1e-6")
        omega = np.asarray(native.frequency, dtype=float).reshape(-1)
        for rpm, actual in zip(inputs["speed_rpm"], omega):
            add("speed", rpm, "rpm", float(rpm) * 2.0 * pi / 60.0, actual, "rad/s", conversion="rpm * 2*pi/60")
        add(
            "oil_supply_temperature",
            inputs["oil_supply_temperature_c"],
            "degC",
            float(inputs["oil_supply_temperature_c"]),
            native.oil_supply_temperature,
            "degC native ROSS contract",
            conversion="degC retained internally after Pint conversion; SI audit K = degC + 273.15",
            si_audit_value=float(inputs["oil_supply_temperature_c"]) + 273.15,
        )
        add("axial_load", inputs["axial_load_n"], "N", float(inputs["axial_load_n"]), native.axial_load, "N", conversion="identity")

    return rows


def _physical_invariants(model: str, result) -> dict[str, object]:
    checks: list[bool] = []
    rows = []
    for point in result.operating_points:
        item = {"rpm": float(point.rpm)}
        if point.max_pressure_pa is not None:
            item["max_pressure_pa"] = float(point.max_pressure_pa)
            checks.append(np.isfinite(point.max_pressure_pa) and point.max_pressure_pa >= 0.0)
        if point.max_temperature_c is not None:
            item["max_temperature_c"] = float(point.max_temperature_c)
            checks.append(np.isfinite(point.max_temperature_c) and point.max_temperature_c > -273.15)
        if point.min_film_thickness_m is not None:
            item["min_film_thickness_m"] = float(point.min_film_thickness_m)
            checks.append(np.isfinite(point.min_film_thickness_m) and point.min_film_thickness_m > 0.0)
        if getattr(point, "eccentricity_ratio", None) is not None:
            item["eccentricity_ratio"] = float(point.eccentricity_ratio)
            checks.append(np.isfinite(point.eccentricity_ratio) and 0.0 <= point.eccentricity_ratio < 1.0)
        rows.append(item)
    return {"operating_points": rows, "pass": bool(checks and all(checks))}


def _zero_lateral_target(project, model: str) -> None:
    if model == "ThrustPad":
        project.bearings = [b for b in project.bearings if b.metadata.get("source_model") != "ThrustPad"]
        return
    target = project.bearings[0]
    target.kxx = target.kxy = target.kyx = target.kyy = 0.0
    target.cxx = target.cxy = target.cyx = target.cyy = 0.0
    target.coefficients = [
        BearingCoefficientPoint(point.rpm, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        for point in target.coefficients
    ]


def _matrix_evidence(rs, project, model: str, speed_rpm: float) -> dict[str, object]:
    built = RossModelBuilder(rs).build(project, strict=True)
    baseline_project = deepcopy(project)
    _zero_lateral_target(baseline_project, model)
    baseline = RossModelBuilder(rs).build(baseline_project, strict=True)
    omega = float(speed_rpm) * 2.0 * pi / 60.0
    k_delta = np.asarray(built.rotor.K(omega)) - np.asarray(baseline.rotor.K(omega))
    c_delta = np.asarray(built.rotor.C(omega)) - np.asarray(baseline.rotor.C(omega))
    return {
        "K_frobenius_delta": float(np.linalg.norm(k_delta)),
        "K_max_abs_delta": float(np.max(np.abs(k_delta))),
        "C_frobenius_delta": float(np.linalg.norm(c_delta)),
        "C_max_abs_delta": float(np.max(np.abs(c_delta))),
        "pass": bool(np.linalg.norm(k_delta) > 0.0 and np.linalg.norm(c_delta) > 0.0),
        "build": built,
    }


def _wait_modal(page: StaticModalWorkspacePage, *, timeout_s: float) -> None:
    page.num_modes.setValue(12)
    page.campbell_points.setValue(5)
    page.campbell_frequencies.setValue(2)
    page.run_modal()
    deadline = time.monotonic() + timeout_s
    app = QApplication.instance()
    while page._modal_thread is not None and page._modal_thread.isRunning():
        if app is not None:
            app.processEvents()
        time.sleep(0.01)
        if time.monotonic() > deadline:
            page._modal_thread.requestInterruption()
            raise RuntimeError("Timed out waiting for THD qualification Modal worker.")
    if app is not None:
        app.processEvents()
    if page.modal_result is None:
        raise RuntimeError(f"THD qualification Modal result unavailable: {page.modal_state.text()}")


def _stale_analysis(project_model, target_spec, *, timeout_s: float) -> dict[str, object]:
    page = StaticModalWorkspacePage(project_model, mode_filter="Lateral")
    page.speed_rpm.setValue(1200.0)
    _wait_modal(page, timeout_s=timeout_s)
    saved = deepcopy(target_spec)
    target_spec.kxx = float(target_spec.kxx) + 17.0
    page._invalidate_if_project_changed()
    invalidated = page.modal_result is None and "invalidated" in page.modal_state.text().casefold()
    target_spec.kxx = saved.kxx

    page.run_modal()
    target_spec.kxx = float(target_spec.kxx) + 19.0
    deadline = time.monotonic() + timeout_s
    app = QApplication.instance()
    while page._modal_thread is not None and page._modal_thread.isRunning():
        if app is not None:
            app.processEvents()
        time.sleep(0.01)
        if time.monotonic() > deadline:
            page._modal_thread.requestInterruption()
            raise RuntimeError("Timed out waiting for stale THD Modal worker.")
    if app is not None:
        app.processEvents()
    race = page.modal_result is None and "discarded" in page.modal_state.text().casefold()
    target_spec.kxx = saved.kxx
    state = page.modal_state.text()
    page.close()
    return {"cache_invalidated_after_edit": bool(invalidated), "old_worker_rejected": bool(race), "state": state, "pass": bool(invalidated and race)}


def _coeff_vector(result, model: str) -> np.ndarray:
    if model == "ThrustPad":
        return np.asarray([[p.kzz, p.czz] for p in result.axial_coefficients], dtype=float).ravel()
    return np.asarray([[getattr(p, name) for name in LATERAL_COEFFS] for p in result.coefficients], dtype=float).ravel()


def _controlled_variation(rs, model: str, project, nominal_result, inputs: Mapping[str, Any]) -> dict[str, object]:
    changed = deepcopy(dict(inputs))
    changed["speed_rpm"] = [float(inputs["speed_rpm"][0])]
    if model == "PlainJournal":
        changed["reference_temperature_c"] = float(inputs["reference_temperature_c"]) + 7.0
        changed_key = "reference_temperature_c"
        service = THDBearingStudioService(rs)
        varied = service.calculate(deepcopy(project), 0, model, changed)
    elif model == "TiltingPad":
        changed["oil_supply_temperature_c"] = float(inputs["oil_supply_temperature_c"]) + 6.0
        changed_key = "oil_supply_temperature_c"
        service = THDBearingStudioService(rs)
        varied = service.calculate(deepcopy(project), 0, model, changed)
    elif model == "SqueezeFilmDamper":
        changed["radial_clearance_um"] = float(inputs["radial_clearance_um"]) * 1.05
        changed_key = "radial_clearance_um"
        service = THDBearingStudioService(rs)
        varied = service.calculate(deepcopy(project), 0, model, changed)
    else:
        changed["oil_supply_temperature_c"] = float(inputs["oil_supply_temperature_c"]) + 5.0
        changed_key = "oil_supply_temperature_c"
        service = ThrustPadStudioService(rs)
        varied = service.calculate(deepcopy(project), 0, model, changed)

    if model == "ThrustPad":
        nominal = np.asarray([nominal_result.axial_coefficients[0].kzz, nominal_result.axial_coefficients[0].czz])
    else:
        nominal = np.asarray([getattr(nominal_result.coefficients[0], name) for name in LATERAL_COEFFS])
    varied_coeff = _coeff_vector(varied, model)[: nominal.size]
    delta = float(np.linalg.norm(varied_coeff - nominal))
    temperature_delta = None
    if nominal_result.operating_points[0].max_temperature_c is not None and varied.operating_points[0].max_temperature_c is not None:
        temperature_delta = abs(float(varied.operating_points[0].max_temperature_c) - float(nominal_result.operating_points[0].max_temperature_c))
    thermal_expected = model in {"PlainJournal", "TiltingPad", "ThrustPad"}
    thermal_pass = (temperature_delta is not None and temperature_delta > 0.0) if thermal_expected else True
    return {
        "changed_input": changed_key,
        "nominal_value": inputs[changed_key],
        "varied_value": changed[changed_key],
        "coefficient_delta_norm": delta,
        "temperature_output_delta_c": temperature_delta,
        "thermal_model_expected": thermal_expected,
        "note": (
            "SqueezeFilmDamper is the ROSS 2.3 analytical hydrodynamic model; no THD temperature field is claimed."
            if model == "SqueezeFilmDamper"
            else "Sensitivity proves the thermal input participates; no universal monotonic trend is asserted."
        ),
        "pass": bool(delta > 0.0 and thermal_pass),
    }


def _persistence_recompute(rs, project_model, model: str, original_result, engineering_inputs: Mapping[str, Any]) -> dict[str, object]:
    with TemporaryDirectory() as tmp:
        path = save_project(project_model, Path(tmp) / f"thd_{model.lower()}_027.rossproj")
        reopened_model = load_project(path)
        reopened = reopened_model.engineering
        if reopened is None:
            raise RuntimeError("Reopened THD project lost engineering domain.")
        RossModelBuilder(rs).build(reopened, strict=True)

        if model == "ThrustPad":
            target = next(b for b in reopened.bearings if b.metadata.get("source_model") == "ThrustPad")
            recomputed = ThrustPadStudioService(rs).calculate(reopened, 0, model, engineering_inputs)
            original = _coeff_vector(original_result, model)
            recalculated = _coeff_vector(recomputed, model)
        else:
            target = reopened.bearings[0]
            recomputed = THDBearingStudioService(rs).calculate(reopened, 0, model, engineering_inputs)
            original = _coeff_vector(original_result, model)
            recalculated = _coeff_vector(recomputed, model)

        return {
            "source_model": target.metadata.get("source_model"),
            "engineering_input_equal": target.metadata.get("engineering_input") == dict(engineering_inputs),
            "property_backend_equal": target.metadata.get("property_backend") == original_result.metadata.get("property_backend"),
            "convergence_metadata_persisted": "convergence" in target.metadata,
            "coefficient_table_equal": bool(np.allclose(original, recalculated, rtol=1.0e-9, atol=1.0e-5)),
            "rebuild_pass": True,
            "pass": bool(
                target.metadata.get("source_model") == model
                and target.metadata.get("engineering_input") == dict(engineering_inputs)
                and "convergence" in target.metadata
                and np.allclose(original, recalculated, rtol=1.0e-9, atol=1.0e-5)
            ),
        }


def _target_spec(project, model: str):
    if model == "ThrustPad":
        return next(b for b in project.bearings if b.metadata.get("source_model") == "ThrustPad")
    return project.bearings[0]


def _qualify_one(rs, model: str, *, frozen_mode: bool) -> dict[str, object]:
    app = _app()
    window = RossStudioWindow()
    window.show()
    app.processEvents()

    gui_inputs = _set_gui_inputs(window, model, INPUTS[model])
    gui_model_description = window.bearing_page.input_panel.description.text()
    gui_editor_note = window.bearing_page.editor_note.text()
    project_before = deepcopy(window.project.engineering)
    window.bearing_page.calculate_button.click()
    app.processEvents()
    initial = window.bearing_calculation
    if initial is None:
        raise RuntimeError(
            f"{model}: GUI Calculate failed: {window.status.message.text()} | {window.status.detail.text()}"
        )
    if initial.native_element.__class__.__name__ != model:
        raise RuntimeError(f"{model}: native class is {initial.native_element.__class__.__name__}.")

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        independent = _manual_native(rs, model, INPUTS[model])
    parity, parity_pass = _parity(rs, model, initial.native_element, independent, INPUTS[model]["speed_rpm"])
    binding = _unit_binding(model, INPUTS[model], initial.native_element)
    unit_pass = all(bool(row["pass"]) for row in binding)
    invariants = _physical_invariants(model, initial)

    stale_preview, final_result = _stale_preview_and_apply(window, model, INPUTS[model])
    if not stale_preview["pass"]:
        raise RuntimeError(f"{model}: stale preview gate failed: {stale_preview}")
    if window.project.engineering == project_before:
        raise RuntimeError(f"{model}: Apply did not mutate the selected bearing transaction.")

    target = _target_spec(window.project.engineering, model)
    matrix = _matrix_evidence(rs, window.project.engineering, model, float(INPUTS[model]["speed_rpm"][1]))
    build = matrix.pop("build")
    omega = float(INPUTS[model]["speed_rpm"][1]) * 2.0 * pi / 60.0
    modal = build.rotor.run_modal(speed=omega, num_modes=12)
    modal_wd = np.asarray(modal.wd, dtype=float)
    campbell = build.rotor.run_campbell(np.asarray([0.5 * omega, omega, 1.5 * omega]), frequencies=4)
    campbell_wd = np.asarray(campbell.wd, dtype=float)
    solver = {
        "modal_positive_finite": bool(np.any(np.isfinite(modal_wd) & (modal_wd > 0.0))),
        "modal_wd_rad_s": [float(v) for v in modal_wd[:6]],
        "campbell_finite": bool(campbell_wd.size and np.all(np.isfinite(campbell_wd))),
        "campbell_shape": list(campbell_wd.shape),
    }
    solver["pass"] = bool(solver["modal_positive_finite"] and solver["campbell_finite"])

    gui_result = {
        "kc_rows": window.bearing_page.kc_table.rowCount(),
        "input_summary": window.bearing_page.input_summary.text(),
        "native_result_retained_after_apply": window.bearing_field_result is final_result,
    }
    expected_rows = len(INPUTS[model]["speed_rpm"])
    gui_result["pass"] = bool(gui_result["kc_rows"] == expected_rows and gui_result["native_result_retained_after_apply"])

    stale_analysis = _stale_analysis(
        window.project,
        target,
        timeout_s=300.0 if frozen_mode else 240.0,
    )
    persistence = _persistence_recompute(
        rs,
        window.project,
        model,
        final_result,
        gui_inputs,
    )
    variation = _controlled_variation(
        rs,
        model,
        project_before,
        final_result,
        INPUTS[model],
    )

    convergence = deepcopy(final_result.metadata.get("convergence"))
    backend = deepcopy(final_result.metadata.get("property_backend"))
    scientific_classification = final_result.metadata.get("scientific_model_classification")
    diagnostics = deepcopy(final_result.metadata.get("diagnostics", []))
    warning_classes = {
        "INFORMATIONAL": sum(1 for x in diagnostics if x.get("classification") == "INFORMATIONAL"),
        "ENGINEERING REVIEW REQUIRED": sum(1 for x in diagnostics if x.get("classification") == "ENGINEERING REVIEW REQUIRED"),
        "SCIENTIFIC FAILURE": sum(1 for x in diagnostics if x.get("classification") == "SCIENTIFIC FAILURE"),
    }

    if model == "ThrustPad":
        node_element = next(e for e in build.rotor.bearing_elements if getattr(e, "tag", None) == target.name)
        axial_contract = {
            "native_class": "ThrustPad",
            "applied_class": type(node_element).__name__,
            "lateral_kc_zero": bool(
                np.allclose(np.asarray(node_element.K(omega))[:2, :2], 0.0)
                and np.allclose(np.asarray(node_element.C(omega))[:2, :2], 0.0)
            ),
            "kzz_nonzero": bool(abs(float(np.asarray(node_element.K(omega))[2, 2])) > 0.0),
            "czz_nonzero": bool(abs(float(np.asarray(node_element.C(omega))[2, 2])) > 0.0),
        }
        axial_contract["pass"] = all(
            bool(axial_contract[key]) for key in ("lateral_kc_zero", "kzz_nonzero", "czz_nonzero")
        )
    else:
        node_element = next(
            e for e in build.rotor.bearing_elements
            if getattr(e, "tag", None) == target.name
        )
        axial_contract = None

    node_evidence = {
        "bearing_position_mm": float(target.position_mm),
        "assembled_node": int(node_element.n),
        "n_link": None if getattr(node_element, "n_link", None) is None else int(node_element.n_link),
        "applied_class": type(node_element).__name__,
        "source_model_metadata": target.metadata.get("source_model"),
        "pass": bool(target.metadata.get("source_model") == model),
    }

    gates = {
        "real_gui_calculate_apply": bool(stale_preview["pass"]),
        "unit_binding": bool(unit_pass),
        "independent_ross_numeric_parity": bool(parity_pass),
        "physical_invariants": bool(invariants["pass"]),
        "rotor_matrix_delta": bool(matrix["pass"]),
        "correct_node_and_cached_native_representation": bool(node_evidence["pass"]),
        "native_modal_and_campbell": bool(solver["pass"]),
        "gui_result": bool(gui_result["pass"]),
        "save_reopen_rebuild_recompute": bool(persistence["pass"]),
        "stale_preview_blocked_signals": bool(stale_preview["pass"]),
        "stale_analysis_async_race": bool(stale_analysis["pass"]),
        "controlled_physical_or_thermal_sensitivity": bool(variation["pass"]),
        "no_scientific_failure_warning": warning_classes["SCIENTIFIC FAILURE"] == 0,
        "property_backend_visible": bool(
            backend
            and backend.get("effective_backend") == "ross.bearings.lubricants.lubricants_dict"
            and backend.get("ccp_refprop_heos_applicable") is False
            and bool(backend.get("native_effective_values"))
        ),
        "scientific_model_classification": bool(
            scientific_classification
            == {
                "PlainJournal": "THERMO-HYDRO-DYNAMIC (THD)",
                "TiltingPad": "THERMO-HYDRO-DYNAMIC (THD)",
                "SqueezeFilmDamper": "HYDRODYNAMIC ANALYTICAL MODEL — NOT THERMAL THD",
                "ThrustPad": "AXIAL THERMO-HYDRO-DYNAMIC (THD)",
            }[model]
        ),
    }
    if model == "SqueezeFilmDamper":
        gates["sfd_gui_semantic_not_false_thd"] = bool(
            "hydrodynamic" in gui_model_description.casefold()
            and "not" in gui_model_description.casefold()
            and "thd" in gui_model_description.casefold()
            and "hydrodynamic" in gui_editor_note.casefold()
            and "not" in gui_editor_note.casefold()
            and "thd" in gui_editor_note.casefold()
        )
    if axial_contract is not None:
        gates["axial_not_lateralized"] = bool(axial_contract["pass"])

    passed = all(gates.values())
    window.close()
    app.processEvents()
    return {
        "status": "PASS" if passed else "FAIL",
        "gates": gates,
        "native_class": model,
        "application_class": "BearingElement",
        "gui_engineering_input": gui_inputs,
        "constructor_unit_binding": binding,
        "parity": parity,
        "independent_ross_warnings": [str(item.message) for item in caught],
        "operating_points": _physical_invariants(model, final_result)["operating_points"],
        "convergence": convergence,
        "diagnostics": diagnostics,
        "warning_classification": warning_classes,
        "property_backend": backend,
        "scientific_model_classification": scientific_classification,
        "gui_model_description": gui_model_description,
        "gui_editor_note": gui_editor_note,
        "rotor_node": node_evidence,
        "global_matrix_deltas": matrix,
        "solver": solver,
        "gui_result": gui_result,
        "persistence": persistence,
        "stale_preview": stale_preview,
        "stale_analysis": stale_analysis,
        "controlled_variation": variation,
        "axial_contract": axial_contract,
    }


def _plain_historical_failure_regression(rs) -> dict[str, object]:
    """Reproduce the d40b485 failure case with corrected semantics.

    Historical source run 35336650952 observed, at 1000 rpm:
    success=True, fun=1.271480 N, nit=30, load=112814.91 N. The previous
    validator incorrectly compared fun with scipy tol=0.8. The corrected
    contract must accept solver termination independently and then apply the
    fixed 1e-3 relative physical-equilibrium criterion.
    """
    window = RossStudioWindow()
    project = deepcopy(window.project.engineering)
    window.close()
    values = deepcopy(INPUTS["PlainJournal"])
    values["speed_rpm"] = [900.0, 1000.0]
    values["sommerfeld_type"] = "1"
    result = THDBearingStudioService(rs).calculate(project, 0, "PlainJournal", values)
    evidence = result.metadata["convergence"][1]
    solver = evidence["solver_termination"]
    physical = evidence["physical_equilibrium"]
    historical_fun_match = bool(np.isclose(solver["final_objective_fun_n"], 1.271480, rtol=5.0e-4, atol=5.0e-4))
    historical_nit_match = solver["iterations"] == 30
    load_match = bool(np.isclose(physical["load_magnitude_n"], 112814.91, rtol=0.0, atol=1.0e-6))
    semantic_separation = bool(
        solver["termination_tolerance"] == 0.8
        and solver["final_objective_fun_n"] > solver["termination_tolerance"]
        and solver["status"] == "PASS"
        and physical["status"] == "PASS"
        and physical["relative_equilibrium_residual"] <= physical["acceptance_threshold"]
    )
    return {
        "historical_failed_sha": "d40b485742190559601df83697b35d619168f0aa",
        "historical_source_run": 35336650952,
        "historical_source_job": 105572921577,
        "expected_historical_case": {
            "success": True,
            "final_objective_fun_n": 1.271480,
            "iterations": 30,
            "load_magnitude_n": 112814.91,
        },
        "measured_solver_termination": solver,
        "measured_physical_equilibrium": physical,
        "historical_fun_match": historical_fun_match,
        "historical_iterations_match": historical_nit_match,
        "historical_load_match": load_match,
        "tol_not_used_as_force_limit": semantic_separation,
        "pass": bool(historical_fun_match and historical_nit_match and load_match and semantic_separation),
    }


def _plain_deliberate_physical_rejection(rs) -> dict[str, object]:
    """Preserve the real 1500-rpm physical-balance rejection discovered by bd3eda.

    No solver internals, load scale or acceptance threshold are modified. The exact
    nominal geometry/load is solved directly with ROSS 2.3 at 1500 rpm. The native
    optimizer terminates successfully, but the predeclared <=1e-3 physical
    equilibrium criterion rejects the returned state.
    """
    values = deepcopy(INPUTS["PlainJournal"])
    values["speed_rpm"] = [1500.0]
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        native = _manual_native(rs, "PlainJournal", values)
    omega = float(np.asarray(native.frequency, dtype=float).reshape(-1)[0])
    opt = native._opt_results[omega]
    native_terminated = bool(
        opt.success
        and np.isfinite(float(opt.fun))
        and hasattr(opt, "nit")
        and np.isfinite(float(opt.nit))
    )
    rejected = False
    message = ""
    relative = None
    applied = np.asarray([native.fxs_load, native.fys_load], dtype=float)
    eq = np.asarray(native._equilibrium_pos_by_speed[omega], dtype=float)
    fhx, fhy = native._forces(eq, omega)
    physical = applied + np.asarray([fhx, fhy], dtype=float)
    load_norm = float(np.linalg.norm(applied))
    residual_norm = float(np.linalg.norm(physical))
    relative = residual_norm / load_norm
    try:
        THDBearingStudioService._plain_convergence(native)
    except EngineeringError as exc:
        message = str(exc)
        rejected = (
            "solver terminated successfully but physical equilibrium is rejected" in message.casefold()
            and "relative_residual" in message
            and "acceptance_threshold" in message
        )
    return {
        "origin": "Real 1500-rpm nominal point that caused source/frozen failure on bd3eda; retained as rejection evidence instead of weakening the threshold.",
        "failed_sha": "bd3eda1440e68755c3a1da6ecb9ce5797cebef19",
        "source_run": 35346847900,
        "frozen_run": 35346847929,
        "native_case": values,
        "native_solver_success": bool(opt.success),
        "native_solver_message": str(opt.message),
        "native_solver_iterations": int(opt.nit),
        "native_final_objective_fun_n": float(opt.fun),
        "native_solver_returned_and_terminated": native_terminated,
        "load_magnitude_n": load_norm,
        "equilibrium_residual_vector_n": [float(v) for v in physical],
        "equilibrium_residual_norm_n": residual_norm,
        "relative_equilibrium_residual": relative,
        "production_validator_rejected": bool(rejected),
        "preview_ready": False,
        "apply_enabled": False,
        "message": message,
        "warnings": [str(item.message) for item in caught],
        "acceptance_threshold": THDBearingStudioService.PLAIN_EQUILIBRIUM_RELATIVE_RESIDUAL_MAX,
        "threshold_source": THDBearingStudioService.PLAIN_EQUILIBRIUM_THRESHOLD_RATIONALE,
        "pass": bool(
            native_terminated
            and np.isfinite(relative)
            and relative > THDBearingStudioService.PLAIN_EQUILIBRIUM_RELATIVE_RESIDUAL_MAX
            and rejected
        ),
    }


def _tilting_nonconvergence_regression(rs) -> dict[str, object]:
    window = RossStudioWindow()
    project = deepcopy(window.project.engineering)
    window.close()
    values = deepcopy(INPUTS["TiltingPad"])
    values.update(
        {
            "speed_rpm": [3000.0],
            "thermal_type": "full",
            "nx": 4,
            "nz": 4,
            "max_inlet_iterations": 1,
            "inlet_temperature_tolerance_c": 1.0e-12,
        }
    )
    try:
        THDBearingStudioService(rs).calculate(project, 0, "TiltingPad", values)
    except EngineeringError as exc:
        message = str(exc)
        return {
            "pass": "did not converge" in message.casefold() and "scientific-failure" in message.casefold(),
            "native_solver_returned_before_validation": True,
            "requested_inlet_temperature_tolerance_c": values["inlet_temperature_tolerance_c"],
            "max_inlet_iterations": values["max_inlet_iterations"],
            "preview_ready": False,
            "apply_enabled": False,
            "message": message,
        }
    return {
        "pass": False,
        "native_solver_returned_before_validation": True,
        "requested_inlet_temperature_tolerance_c": values["inlet_temperature_tolerance_c"],
        "max_inlet_iterations": values["max_inlet_iterations"],
        "preview_ready": True,
        "apply_enabled": True,
        "message": "TiltingPad max_inlet_iterations=1 / tolerance=1e-12 unexpectedly accepted.",
    }


def _ross_230_api_inventory(rs) -> dict[str, object]:
    return {
        "PlainJournal": {
            "class": f"{rs.PlainJournal.__module__}.{rs.PlainJournal.__name__}",
            "signature": str(inspect.signature(rs.PlainJournal)),
            "scientific_classification": "THERMO-HYDRO-DYNAMIC (THD)",
            "solver": "scipy.optimize.minimize(method='Nelder-Mead', tol=0.8, maxiter=1e10) for equilibrium; thermal Reynolds/energy solution inside _forces",
            "objective": "sqrt((fxs_load + Fhx)^2 + (fys_load + Fhy)^2), N",
            "dynamic_coefficients": list(LATERAL_COEFFS),
            "speed_dependent": True,
            "thermal_dependency": "temperature-dependent viscosity from ross.bearings.lubricants.lubricants_dict participates in the coupled thermal solution",
        },
        "TiltingPad": {
            "class": f"{rs.TiltingPad.__module__}.{rs.TiltingPad.__name__}",
            "signature": str(inspect.signature(rs.TiltingPad)),
            "scientific_classification": "THERMO-HYDRO-DYNAMIC (THD)",
            "solver": "native ROSS equilibrium fmin plus Reynolds/energy thermal loops; solver_options, inlet/journal thermal controls are native 2.3.0 inputs",
            "optimizer_diagnostics_limit": "ROSS 2.3 does not retain scipy.fmin warnflag or final optimizer iteration count in results",
            "dynamic_coefficients": list(LATERAL_COEFFS),
            "speed_dependent": True,
            "thermal_dependency": "oil supply/journal temperatures and temperature-dependent viscosity enter the native thermal solution",
        },
        "SqueezeFilmDamper": {
            "class": f"{rs.SqueezeFilmDamper.__module__}.{rs.SqueezeFilmDamper.__name__}",
            "signature": str(inspect.signature(rs.SqueezeFilmDamper)),
            "scientific_classification": "HYDRODYNAMIC ANALYTICAL MODEL — NOT THERMAL THD",
            "solver": "analytical hydrodynamic short-bearing formulation; no iterative thermal convergence loop",
            "dynamic_coefficients": list(LATERAL_COEFFS),
            "speed_dependent": True,
            "thermal_dependency": "none claimed; ROSS 2.3 uses database liquid_viscosity1 directly",
        },
        "ThrustPad": {
            "class": f"{rs.ThrustPad.__module__}.{rs.ThrustPad.__name__}",
            "signature": str(inspect.signature(rs.ThrustPad)),
            "scientific_classification": "AXIAL THERMO-HYDRO-DYNAMIC (THD)",
            "solver": "native outer force/moment equilibrium loop plus pressure/temperature/viscosity coupling",
            "objective": "calculate mode norm([moment_x, moment_y, axial_force_residual]); imposed mode norm([moment_x, moment_y])",
            "dynamic_coefficients": ["kzz", "czz"],
            "speed_dependent": True,
            "thermal_dependency": "temperature-dependent viscosity and energy solution participate in the native axial THD solve",
        },
    }


def _input_validation(rs) -> dict[str, object]:
    window = RossStudioWindow()
    project = deepcopy(window.project.engineering)
    window.close()
    service = THDBearingStudioService(rs)
    cases = {
        "nan_clearance": ("PlainJournal", {"radial_clearance_um": float("nan")}),
        "zero_clearance": ("PlainJournal", {"radial_clearance_um": 0.0}),
        "nonmonotonic_speed": ("SqueezeFilmDamper", {"speed_rpm": [1200.0, 1100.0, 1500.0]}),
        "absolute_temperature": ("TiltingPad", {"oil_supply_temperature_c": -273.15}),
        "invalid_solver_maxiter": ("TiltingPad", {"solver_maxiter": 0}),
        "invalid_solver_tolerance": ("TiltingPad", {"solver_xtol": 0.0}),
    }
    results: dict[str, object] = {}
    for label, (model, patch) in cases.items():
        values = deepcopy(INPUTS[model])
        values.update(patch)
        try:
            service.calculate(deepcopy(project), 0, model, values)
        except EngineeringError as exc:
            message = str(exc)
            has_received = "received" in message.casefold() or any(str(v) in message for v in patch.values())
            has_expected = any(token in message.casefold() for token in ("must", "expected", "positive", "finite", "increasing", "> 0"))
            has_reason = any(
                token in message.casefold()
                for token in ("nonphysical", "undefined", "ambiguous", "optimizer", "thermal", "equations", "interpolation")
            )
            has_correction = any(
                token in message.casefold()
                for token in ("enter", "correct", "increase", "choose", "recalculate", "use ")
            )
            results[label] = {
                "pass": bool(has_received and has_expected and has_reason and has_correction),
                "message": message,
                "has_received_value": has_received,
                "has_expected_condition": has_expected,
                "has_reason": has_reason,
                "has_corrective_action": has_correction,
            }
        else:
            results[label] = {"pass": False, "message": "unexpectedly accepted"}
    results["pass"] = all(bool(v["pass"]) for k, v in results.items() if k != "pass")
    return results


def run_thd_bearings_027_qualification(*, frozen_mode: bool = False) -> THDBearings027Qualification:
    import ross as rs

    if rs.__version__ != "2.3.0":
        raise RuntimeError(f"THD Bearings 0.27 is pinned to ROSS 2.3.0; received {rs.__version__}.")

    ledgers: dict[str, object] = {}
    for model in ALL_MODELS:
        ledgers[model] = _qualify_one(rs, model, frozen_mode=frozen_mode)

    plain_historical = _plain_historical_failure_regression(rs)
    plain_rejection = _plain_deliberate_physical_rejection(rs)
    nonconvergence = _tilting_nonconvergence_regression(rs)
    validation = _input_validation(rs)
    matrix = {
        "PLAIN JOURNAL — THD": ledgers["PlainJournal"]["status"],
        "TILTING PAD — THD": ledgers["TiltingPad"]["status"],
        "SQUEEZE FILM DAMPER — HD ANALYTICAL": ledgers["SqueezeFilmDamper"]["status"],
        "THRUST PAD — AXIAL THD": ledgers["ThrustPad"]["status"],
    }
    release_pass = bool(
        all(status == "PASS" for status in matrix.values())
        and plain_historical["pass"]
        and plain_rejection["pass"]
        and nonconvergence["pass"]
        and validation["pass"]
    )
    payload: dict[str, object] = {
        "ross_version": rs.__version__,
        "studio_version": "0.30.0",
        "frozen_mode": bool(frozen_mode),
        "declared_scope": (
            "ROSS Studio THD Bearings 0.27 on ross-rotordynamics==2.3.0: native PlainJournal and "
            "TiltingPad thermo-hydrodynamic solutions, native analytical hydrodynamic SqueezeFilmDamper, "
            "and separate axial native ThrustPad THD; solved native coefficients are cached as BearingElement "
            "tables for rotor execution without re-solving fields."
        ),
        "scope_notes": [
            "PlainJournal solver termination and physical equilibrium are separate gates. scipy tol=0.8 is recorded only as a Nelder-Mead termination tolerance; physical acceptance uses the predeclared <=1e-3 resultant-force-imbalance/load criterion.",
            "SqueezeFilmDamper is classified as an analytical hydrodynamic model (HD); no thermal THD field or thermal coupling is claimed.",
            "TiltingPad ROSS 2.3 does not retain scipy.fmin warnflag/iteration count. Native thermal nonconvergence warnings are fail-closed; finite objective history is reported without fabricating a success flag.",
            "ThrustPad remains axial-only; Kzz/Czz are never mapped into lateral K/C.",
            "Lubricant properties come from ross.bearings.lubricants.lubricants_dict; ccp/REFPROP/HEOS is not used by these bearing models.",
        ],
        "qualification_matrix": matrix,
        "ross_230_api_inventory": _ross_230_api_inventory(rs),
        "plain_journal_qualification_speed_grid_rpm": [900.0, 1000.0, 1200.0],
        "plain_journal_rejected_regression_speed_rpm": 1500.0,
        "plain_journal_physical_acceptance_contract": {
            "metric_definition": "||[Fx_applied + Fhx_hydrodynamic, Fy_applied + Fhy_hydrodynamic]|| / ||[Fx_applied, Fy_applied]||",
            "acceptance_threshold": THDBearingStudioService.PLAIN_EQUILIBRIUM_RELATIVE_RESIDUAL_MAX,
            "threshold_source": THDBearingStudioService.PLAIN_EQUILIBRIUM_THRESHOLD_RATIONALE,
            "solver_termination_tolerance": THDBearingStudioService.PLAIN_SOLVER_TERMINATION_TOLERANCE,
            "solver_termination_tolerance_semantics": "Nelder-Mead solver termination only; never compared directly to force residual in N",
        },
        "models": ledgers,
        "plain_journal_historical_failure_regression": plain_historical,
        "plain_journal_deliberate_physical_rejection": plain_rejection,
        "tilting_pad_intentional_nonconvergence": nonconvergence,
        "input_validation": validation,
        "unit_contract": {
            "mm_to_m": "x / 1000",
            "um_to_m": "x * 1e-6",
            "rpm_to_rad_s": "x * 2*pi/60",
            "degC_to_K_for_SI_audit": "x + 273.15; native ROSS constructors retain documented degC contracts where applicable",
            "bar_to_Pa": "x * 1e5",
            "N_load": "identity",
            "dimensionless_ratios": "identity",
        },
    }
    return THDBearings027Qualification("PASS" if release_pass else "FAIL", payload)


__all__ = ["THDBearings027Qualification", "run_thd_bearings_027_qualification"]
