from __future__ import annotations

import csv
import json
from math import cos, pi, radians, sin
from pathlib import Path
from typing import Iterable

import numpy as np
import ross as rs

from ross_studio.legacy_import import load_irdin_project
from ross_studio.topology import NodeInsertionService


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "src" / "ross_studio" / "resources" / "OP-W60-500-60Hz-IC611-P3.txt"
GOLDEN = ROOT / "tests" / "golden" / "op_w60_rotordin_gmm_900_4500.csv"
OUT = ROOT / "artifacts" / "op_w60_response_ab_isolation.json"

# Station coordinates regenerated from the supplied RotorDin solver's MODEL_AUDIT /
# static displacement output for this exact OP-W60 case. Small non-decimal tails are
# retained because the legacy solver stores geometry in single precision.
ROTORDIN_STATIONS_MM = np.asarray([
    0.0,
    104.9999967,
    209.9999934,
    230.0000042,
    424.8000085,
    467.7999914,
    510.8000040,
    577.7999759,
    630.9999824,
    737.5000119,
    777.4999738,
    917.9999828,
    1037.166715,
    1156.333327,
    1275.500059,
    1633.000016,
    1892.500043,
    1932.500005,
    2039.000034,
    2092.200041,
    2157.200098,
    2202.199936,
    2247.200012,
    2446.199894,
    2546.200037,
    2550.199986,
    2555.200100,
], dtype=float)


def _read_golden() -> dict[str, np.ndarray]:
    with GOLDEN.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    return {key: np.asarray([float(row[key]) for row in rows]) for key in rows[0]}


def _node_for(positions_mm: np.ndarray, position_mm: float, tolerance_mm: float = 1e-3) -> int:
    index = int(np.argmin(np.abs(positions_mm - float(position_mm))))
    error = abs(float(positions_mm[index]) - float(position_mm))
    if error > tolerance_mm:
        raise RuntimeError(f"Position {position_mm:g} mm is absent from experimental mesh; nearest error={error:g} mm")
    return index


def _intlag(vx: Iterable[float], vy: Iterable[float], x: float) -> float:
    """Python transcription of RotorDin matfun.f:intlag for A/B diagnostics."""
    xx = np.asarray(tuple(vx), dtype=float)
    yy = np.asarray(tuple(vy), dtype=float)
    if len(xx) < 2:
        raise RuntimeError("intlag requires at least two points")
    ci = 1e-15
    for ii in range(1, len(xx) - 1):
        if abs(x - xx[ii]) <= ci:
            return float(yy[ii])
        if xx[ii] > x:
            indices = (ii - 1, ii, ii + 1)
            result = 0.0
            for jj in indices:
                term = float(yy[jj])
                for kk in indices:
                    if kk != jj and abs(xx[kk] - xx[jj]) >= ci:
                        term *= (x - xx[kk]) / (xx[jj] - xx[kk])
                result += term
            return float(result)
    if x < xx[0]:
        return float((x - xx[0]) * (yy[1] - yy[0]) / (xx[1] - xx[0]) + yy[0])
    return float((x - xx[-2]) * (yy[-1] - yy[-2]) / (xx[-1] - xx[-2]) + yy[-2])


def _section_properties(project, x0_mm: float, x1_mm: float):
    midpoint = 0.5 * (x0_mm + x1_mm)
    start = 0.0
    for section in project.shaft_sections:
        end = start + section.length_mm
        if start - 1e-3 <= midpoint <= end + 1e-3:
            t0 = (x0_mm - start) / section.length_mm
            t1 = (x1_mm - start) / section.length_mm
            od0 = section.od_left_mm + (section.odr_mm - section.od_left_mm) * t0
            od1 = section.od_left_mm + (section.odr_mm - section.od_left_mm) * t1
            id0 = section.id_left_mm + (section.idr_mm - section.id_left_mm) * t0
            id1 = section.id_left_mm + (section.idr_mm - section.id_left_mm) * t1
            return section, od0, od1, id0, id1
        start = end
    raise RuntimeError(f"Cannot map [{x0_mm:g},{x1_mm:g}] mm to a physical section")


def _bearing_values(spec, rpm_grid: np.ndarray, interpolation: str):
    source_rpm = np.asarray([point.rpm for point in spec.coefficients], dtype=float)
    names = ("kxx", "kyy", "kxy", "kyx", "cxx", "cyy", "cxy", "cyx")
    source = {name: np.asarray([getattr(point, name) for point in spec.coefficients], dtype=float) for name in names}
    if interpolation == "ross_spline":
        return source_rpm, source
    if interpolation != "rotordin_intlag":
        raise RuntimeError(f"Unknown interpolation {interpolation!r}")
    dense = {
        name: np.asarray([_intlag(source_rpm, values, float(rpm)) for rpm in rpm_grid], dtype=float)
        for name, values in source.items()
    }
    return rpm_grid, dense


def _build_variant(project, positions_mm: np.ndarray, rpm_grid: np.ndarray, interpolation: str):
    material_specs = project.materials
    materials = {
        name: rs.Material(name=spec.name, rho=spec.density_kg_m3, E=spec.young_pa, G_s=spec.shear_pa)
        for name, spec in material_specs.items()
    }
    shaft = []
    for n, (x0, x1) in enumerate(zip(positions_mm[:-1], positions_mm[1:])):
        section, od0, od1, id0, id1 = _section_properties(project, float(x0), float(x1))
        shaft.append(rs.ShaftElement(
            L=(float(x1) - float(x0)) / 1000.0,
            idl=id0 / 1000.0,
            odl=od0 / 1000.0,
            idr=id1 / 1000.0,
            odr=od1 / 1000.0,
            material=materials[section.material],
            n=n,
            tag=f"AB-S{section.section:02d}.{n:02d}",
        ))

    disks = []
    for mass in project.distributed_masses:
        node = _node_for(positions_mm, mass.center_mm)
        id_kg_m2, ip_kg_m2 = mass.equivalent_disk_inertias_kg_m2()
        disks.append(rs.DiskElement(node, mass.mass_kg, id_kg_m2, ip_kg_m2, tag=f"{mass.name} / AB"))
    for mass in project.point_masses:
        node = _node_for(positions_mm, mass.position_mm)
        disks.append(rs.DiskElement(node, mass.mass_kg, 0.0, 0.0, tag=f"{mass.name} / AB"))

    support_by_bearing = {support.bearing_index: support for support in project.supports}
    bearings = []
    support_masses = []
    next_link = len(positions_mm)
    for index, spec in enumerate(project.bearings):
        support = support_by_bearing[index]
        rotor_node = _node_for(positions_mm, spec.position_mm)
        link_node = next_link
        next_link += 1
        table_rpm, values = _bearing_values(spec, rpm_grid, interpolation)
        bearings.append(rs.BearingElement(
            n=rotor_node,
            n_link=link_node,
            kxx=values["kxx"], kyy=values["kyy"], kxy=values["kxy"], kyx=values["kyx"],
            cxx=values["cxx"], cyy=values["cyy"], cxy=values["cxy"], cyx=values["cyx"],
            frequency=table_rpm * 2.0 * pi / 60.0,
            tag=f"{spec.name} / AB {interpolation}",
        ))
        bearings.append(rs.BearingElement(
            n=link_node,
            kxx=support.kxx, kyy=support.kyy or support.kxx,
            kxy=support.kxy, kyx=support.kyx,
            cxx=support.cxx, cyy=support.cyy or support.cxx,
            cxy=support.cxy, cyx=support.cyx,
            tag=f"{support.name} / AB ground",
        ))
        support_masses.append(rs.PointMass(n=link_node, m=support.mass_kg, tag=f"{support.name} / AB mass"))

    return rs.Rotor(
        shaft_elements=shaft,
        disk_elements=disks,
        bearing_elements=bearings,
        point_mass_elements=support_masses,
        tag=f"{project.name} / AB",
    )


def _solve(project, rotor, positions_mm: np.ndarray, rpm: np.ndarray, orientation_unit: str = "deg"):
    nodes = [_node_for(positions_mm, load.position_mm) for load in project.loads if load.kind.casefold() == "unbalance"]
    magnitude = [float(load.magnitude) * 1e-6 for load in project.loads if load.kind.casefold() == "unbalance"]
    phase = [radians(float(load.phase_deg)) for load in project.loads if load.kind.casefold() == "unbalance"]
    response = rotor.run_unbalance_response(
        node=nodes,
        unbalance_magnitude=magnitude,
        unbalance_phase=phase,
        frequency=rpm * 2.0 * pi / 60.0,
    )
    result = []
    for probe in project.probes:
        node = _node_for(positions_mm, probe.position_mm)
        x = np.asarray(response.forced_resp[node * rotor.number_dof + 0, :], dtype=complex)
        y = np.asarray(response.forced_resp[node * rotor.number_dof + 1, :], dtype=complex)
        angle = radians(float(probe.orientation_deg)) if orientation_unit == "deg" else float(probe.orientation_deg)
        projected = x * cos(angle) + y * sin(angle) if probe.coordinate == 1 else y * cos(angle) - x * sin(angle)
        result.append(projected)
    return np.asarray(result).T


def _metrics(response: np.ndarray, golden: dict[str, np.ndarray], rpm: np.ndarray):
    ross_amp = np.abs(response) * 1e6
    ref_amp = np.column_stack([golden[f"amp_p{i}_um"] for i in range(1, 5)])
    direct = []
    for i in range(4):
        rmse = float(np.sqrt(np.mean((ross_amp[:, i] - ref_amp[:, i]) ** 2)))
        direct.append({
            "probe": i + 1,
            "correlation_r": float(np.corrcoef(ross_amp[:, i], ref_amp[:, i])[0, 1]),
            "rmse_um": rmse,
            "nrmse_percent": 100.0 * rmse / float(np.max(ref_amp[:, i])),
        })
    pairs = []
    for name, indices in (("DE", (0, 1)), ("NDE", (2, 3))):
        ra = np.sqrt(np.sum(ross_amp[:, list(indices)] ** 2, axis=1))
        da = np.sqrt(np.sum(ref_amp[:, list(indices)] ** 2, axis=1))
        rmse = float(np.sqrt(np.mean((ra - da) ** 2)))
        rated = int(np.argmin(np.abs(rpm - 3600.0)))
        pairs.append({
            "bearing": name,
            "correlation_r": float(np.corrcoef(ra, da)[0, 1]),
            "rmse_um": rmse,
            "nrmse_percent": 100.0 * rmse / float(np.max(da)),
            "rated_error_percent": 100.0 * (float(ra[rated]) - float(da[rated])) / float(da[rated]),
            "ross_peak_um": float(np.max(ra)),
            "rotordin_peak_um": float(np.max(da)),
            "ross_peak_rpm": float(rpm[int(np.argmax(ra))]),
            "rotordin_peak_rpm": float(rpm[int(np.argmax(da))]),
        })
    return {"oriented_channels": direct, "pair_resultants": pairs}


def main() -> int:
    project = load_irdin_project(FIXTURE)
    golden = _read_golden()
    rpm = golden["rpm"]
    current_positions = np.asarray(NodeInsertionService.plan(project).positions_mm, dtype=float)

    variants = [
        ("current_mesh__ross_spline", current_positions, "ross_spline"),
        ("rotordin_mesh__ross_spline", ROTORDIN_STATIONS_MM, "ross_spline"),
        ("current_mesh__rotordin_intlag", current_positions, "rotordin_intlag"),
        ("rotordin_mesh__rotordin_intlag", ROTORDIN_STATIONS_MM, "rotordin_intlag"),
    ]
    output = {
        "case": project.name,
        "purpose": "A/B isolation only; no experimental variant changes production builder physics.",
        "rotordin_mesh": {"stations": int(len(ROTORDIN_STATIONS_MM)), "elements": int(len(ROTORDIN_STATIONS_MM) - 1)},
        "current_ross_mesh": {"nodes": int(len(current_positions)), "elements": int(len(current_positions) - 1)},
        "variants": {},
    }
    for name, positions, interpolation in variants:
        print(f"running {name} ...")
        rotor = _build_variant(project, positions, rpm, interpolation)
        response_deg = _solve(project, rotor, positions, rpm, "deg")
        metrics = _metrics(response_deg, golden, rpm)
        # Probe orientation is post-processing only; re-solve is unnecessary for the
        # radian diagnostic but kept explicit here for clarity of the A/B contract.
        response_rad = _solve(project, rotor, positions, rpm, "rad")
        metrics["raw_45_rad_projection"] = _metrics(response_rad, golden, rpm)
        output["variants"][name] = metrics

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(f"A/B isolation written to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
