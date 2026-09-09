from __future__ import annotations

import csv
import json
from math import cos, pi, radians, sin
from pathlib import Path

import numpy as np
import ross as rs

from ross_studio.legacy_import import load_irdin_project
from ross_studio.topology import NodeInsertionService
from isolate_op_w60_response_differences import _bearing_values, _node_for, _section_properties


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "src" / "ross_studio" / "resources" / "OP-W60-500-60Hz-IC611-P3.txt"
GOLDEN = ROOT / "tests" / "golden" / "op_w60_rotordin_gmm_900_4500.csv"
OUT = ROOT / "artifacts" / "op_w60_convention_isolation.json"


def _read_golden() -> dict[str, np.ndarray]:
    with GOLDEN.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    return {key: np.asarray([float(row[key]) for row in rows], dtype=float) for key in rows[0]}


def _transform_cross(values: dict[str, np.ndarray], mode: str) -> dict[str, np.ndarray]:
    out = {key: np.asarray(value, dtype=float).copy() for key, value in values.items()}
    if mode in {"transpose", "transpose_flip"}:
        out["kxy"], out["kyx"] = out["kyx"].copy(), out["kxy"].copy()
        out["cxy"], out["cyx"] = out["cyx"].copy(), out["cxy"].copy()
    if mode in {"cross_flip", "transpose_flip"}:
        for name in ("kxy", "kyx", "cxy", "cyx"):
            out[name] *= -1.0
    return out


def _build(project, positions_mm: np.ndarray, rpm_grid: np.ndarray, cross_mode: str, gyro_scale: float):
    materials = {
        name: rs.Material(name=spec.name, rho=spec.density_kg_m3, E=spec.young_pa, G_s=spec.shear_pa)
        for name, spec in project.materials.items()
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
            tag=f"CONV-S{section.section:02d}.{n:02d}",
        ))

    disks = []
    for mass in project.distributed_masses:
        node = _node_for(positions_mm, mass.center_mm)
        id_kg_m2, ip_kg_m2 = mass.equivalent_disk_inertias_kg_m2()
        disks.append(rs.DiskElement(node, mass.mass_kg, id_kg_m2, ip_kg_m2, tag=f"{mass.name} / CONV"))
    for mass in project.point_masses:
        disks.append(rs.DiskElement(_node_for(positions_mm, mass.position_mm), mass.mass_kg, 0.0, 0.0, tag=f"{mass.name} / CONV"))

    support_by_bearing = {support.bearing_index: support for support in project.supports}
    bearings = []
    support_masses = []
    next_link = len(positions_mm)
    for index, spec in enumerate(project.bearings):
        support = support_by_bearing[index]
        link_node = next_link
        next_link += 1
        table_rpm, values0 = _bearing_values(spec, rpm_grid, "ross_spline")
        values = _transform_cross(values0, cross_mode)
        bearings.append(rs.BearingElement(
            n=_node_for(positions_mm, spec.position_mm),
            n_link=link_node,
            kxx=values["kxx"], kyy=values["kyy"], kxy=values["kxy"], kyx=values["kyx"],
            cxx=values["cxx"], cyy=values["cyy"], cxy=values["cxy"], cyx=values["cyx"],
            frequency=table_rpm * 2.0 * pi / 60.0,
            tag=f"{spec.name} / CONV {cross_mode}",
        ))
        bearings.append(rs.BearingElement(
            n=link_node,
            kxx=support.kxx, kyy=support.kyy or support.kxx,
            kxy=support.kxy, kyx=support.kyx,
            cxx=support.cxx, cyy=support.cyy or support.cxx,
            cxy=support.cxy, cyx=support.cyx,
            tag=f"{support.name} / CONV ground",
        ))
        support_masses.append(rs.PointMass(n=link_node, m=support.mass_kg, tag=f"{support.name} / CONV mass"))

    rotor = rs.Rotor(
        shaft_elements=shaft,
        disk_elements=disks,
        bearing_elements=bearings,
        point_mass_elements=support_masses,
        tag=f"{project.name} / CONV {cross_mode} G={gyro_scale:+g}",
    )
    if gyro_scale != 1.0:
        base_g = np.asarray(rotor.G(), dtype=float).copy()
        rotor.G = lambda base_g=base_g, gyro_scale=gyro_scale: gyro_scale * base_g
    return rotor


def _forced_response(project, rotor, positions_mm: np.ndarray, rpm: np.ndarray, force_y_sign: int):
    omega = rpm * 2.0 * pi / 60.0
    force = np.zeros((rotor.ndof, len(omega)), dtype=complex)
    for load in project.loads:
        if load.kind.casefold() != "unbalance":
            continue
        node = _node_for(positions_mm, load.position_mm)
        unbalance = float(load.magnitude) * 1e-6
        phase = radians(float(load.phase_deg))
        phasor = unbalance * np.exp(1j * phase) * omega**2
        base = node * rotor.number_dof
        force[base + 0, :] += phasor
        force[base + 1, :] += force_y_sign * 1j * phasor
    return rotor.run_forced_response(force=force, speed_range=omega)


def _project(project, rotor, positions_mm: np.ndarray, forced, orientation_unit: str, vertical_sign: int) -> np.ndarray:
    channels = []
    for probe in project.probes:
        node = _node_for(positions_mm, probe.position_mm)
        x = np.asarray(forced.forced_resp[node * rotor.number_dof + 0, :], dtype=complex)
        y = np.asarray(forced.forced_resp[node * rotor.number_dof + 1, :], dtype=complex)
        z = vertical_sign * y
        angle = radians(float(probe.orientation_deg)) if orientation_unit == "deg" else float(probe.orientation_deg)
        if probe.coordinate == 1:
            channel = x * cos(angle) + z * sin(angle)
        else:
            channel = z * cos(angle) - x * sin(angle)
        channels.append(channel)
    return np.asarray(channels, dtype=complex).T


def _orbit_kappa(a: complex, b: complex) -> float:
    matrix = np.asarray([[a.real, -a.imag], [b.real, -b.imag]], dtype=float)
    singular = np.linalg.svd(matrix, compute_uv=False)
    if singular[0] <= 0.0:
        return 0.0
    hand = 1.0 if np.linalg.det(matrix) >= 0.0 else -1.0
    return float(hand * singular[1] / singular[0])


def _metrics(response: np.ndarray, ref: dict[str, np.ndarray], rpm: np.ndarray) -> dict:
    ref_amp = np.column_stack([ref[f"amp_p{i}_um"] for i in range(1, 5)])
    ref_phase = np.column_stack([ref[f"phase_p{i}_deg"] for i in range(1, 5)])
    ref_complex = ref_amp * np.exp(1j * np.deg2rad(ref_phase))
    test_complex = response * 1e6
    test_amp = np.abs(test_complex)

    oriented = []
    active = np.zeros(test_amp.shape, dtype=bool)
    for i in range(4):
        active[:, i] = ref_amp[:, i] >= 0.20 * float(np.max(ref_amp[:, i]))
        rmse = float(np.sqrt(np.mean((test_amp[:, i] - ref_amp[:, i]) ** 2)))
        oriented.append({
            "probe": i + 1,
            "correlation_r": float(np.corrcoef(test_amp[:, i], ref_amp[:, i])[0, 1]),
            "nrmse_percent": 100.0 * rmse / float(np.max(ref_amp[:, i])),
        })

    # One global unit-magnitude phasor is allowed because RotorDin and ROSS define
    # synchronous unbalance force phasors differently. It is diagnostic only.
    cross = np.sum(ref_complex[active] * np.conj(test_complex[active]))
    offset = float(np.angle(cross)) if abs(cross) > 0 else 0.0
    corrected = test_complex * np.exp(1j * offset)
    complex_error = corrected[active] - ref_complex[active]
    complex_nrmse = 100.0 * float(np.linalg.norm(complex_error)) / float(np.linalg.norm(ref_complex[active]))
    phase_delta = np.rad2deg(np.angle(corrected[active] * np.conj(ref_complex[active])))

    pairs = []
    for name, idx in (("DE", (0, 1)), ("NDE", (2, 3))):
        ta = np.sqrt(np.sum(test_amp[:, list(idx)] ** 2, axis=1))
        ra = np.sqrt(np.sum(ref_amp[:, list(idx)] ** 2, axis=1))
        rmse = float(np.sqrt(np.mean((ta - ra) ** 2)))
        pairs.append({
            "bearing": name,
            "correlation_r": float(np.corrcoef(ta, ra)[0, 1]),
            "nrmse_percent": 100.0 * rmse / float(np.max(ra)),
        })

    rated = int(np.argmin(np.abs(rpm - 3600.0)))
    orbit = []
    for name, idx in (("DE", (0, 1)), ("NDE", (2, 3))):
        test_kappa = _orbit_kappa(test_complex[rated, idx[0]], test_complex[rated, idx[1]])
        ref_kappa = _orbit_kappa(ref_complex[rated, idx[0]], ref_complex[rated, idx[1]])
        orbit.append({
            "bearing": name,
            "ross_kappa_rated": test_kappa,
            "rotordin_kappa_rated": ref_kappa,
            "abs_error": abs(test_kappa - ref_kappa),
        })

    mean_channel_nrmse = float(np.mean([row["nrmse_percent"] for row in oriented]))
    mean_pair_nrmse = float(np.mean([row["nrmse_percent"] for row in pairs]))
    mean_kappa_error = float(np.mean([row["abs_error"] for row in orbit]))
    phase_mae = float(np.mean(np.abs(phase_delta)))
    score = mean_channel_nrmse + 0.5 * mean_pair_nrmse + 0.35 * phase_mae + 20.0 * mean_kappa_error
    return {
        "score": score,
        "mean_channel_nrmse_percent": mean_channel_nrmse,
        "mean_pair_nrmse_percent": mean_pair_nrmse,
        "global_phasor_offset_deg": float(np.rad2deg(offset)),
        "phase_mae_after_global_offset_deg": phase_mae,
        "complex_nrmse_after_global_offset_percent": complex_nrmse,
        "oriented_channels": oriented,
        "pair_resultants": pairs,
        "orbit_rated": orbit,
    }


def main() -> int:
    project = load_irdin_project(FIXTURE)
    ref = _read_golden()
    rpm = ref["rpm"]
    positions = np.asarray(NodeInsertionService.plan(project).positions_mm, dtype=float)

    variants = []
    for cross_mode in ("identity", "cross_flip", "transpose", "transpose_flip"):
        for gyro_scale in (1.0, -1.0, 0.0):
            for force_y_sign in (-1, 1):
                rotor = _build(project, positions, rpm, cross_mode, gyro_scale)
                forced = _forced_response(project, rotor, positions, rpm, force_y_sign)
                for vertical_sign in (1, -1):
                    for orientation_unit in ("deg", "rad"):
                        response = _project(project, rotor, positions, forced, orientation_unit, vertical_sign)
                        metrics = _metrics(response, ref, rpm)
                        variants.append({
                            "cross_mode": cross_mode,
                            "gyro_scale": gyro_scale,
                            "force_y_imag_sign": force_y_sign,
                            "vertical_axis_sign": vertical_sign,
                            "orientation_unit": orientation_unit,
                            **metrics,
                        })

    variants.sort(key=lambda row: row["score"])
    output = {
        "case": project.name,
        "purpose": "Diagnostic search over bearing cross-coupling, gyroscopic sign, unbalance handedness, vertical-axis sign and legacy RANUN interpretation. No variant changes production physics.",
        "known_analytic_phasor_relation": {
            "rotordin_force_xy_same_axes": "[j, 1] * U*w^2*exp(j*phi)",
            "ross_force_xy": "[1, -j] * U*w^2*exp(j*phi)",
            "relation": "F_RotorDin = j * F_ROSS when vertical axes have the same sign",
            "expected_global_response_phase_offset_deg": 90.0,
        },
        "known_gyroscopic_sign_evidence": {
            "rotordin_rigid_disk_G_theta_x_theta_z": "-Ip",
            "ross_rigid_disk_G_alpha_beta": "+Ip",
            "rotordin_uniform_shaft_G_xz_coefficient": "-2.4*rho*I/L",
            "ross_uniform_shaft_G_xy_coefficient_at_phi0": "+2.4*rho*I/L",
        },
        "search_count": len(variants),
        "best": variants[0],
        "top10": variants[:10],
        "all_variants": variants,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({
        "best": variants[0],
        "output": str(OUT),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
