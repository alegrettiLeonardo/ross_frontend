from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import re

from .domain import (
    AnalysisRequest,
    CoefficientBearingSpec,
    DiskSpec,
    DomainError,
    MaterialSpec,
    PointMassSpec,
    ProbeSpec,
    RotorProject,
    ShaftSectionSpec,
    SupportSpec,
    UmpFormulation,
    UMPRegionSpec,
    UnbalanceSpec,
)
from .ross_ext.ump import (
    LEGACY_KGF_MM2_TO_N_M2,
    ROTORDIN_LEGACY_MAX_REGIONS,
    ROTORDIN_LEGACY_THRESHOLD_N_M2,
    legacy_ump_to_si,
)

_GRID_KEY = re.compile(r"^(\d+)\s*,\s*(\d+)$")


class LegacyImportError(DomainError):
    """Invalid or unsupported iRdin/VB6 project."""


def _read_text(path: str | Path) -> str:
    source = Path(path)
    if not source.is_file():
        raise LegacyImportError(f"Legacy project not found: {source}")
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return source.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    raise LegacyImportError(f"Could not decode legacy project: {source}")


def _parse_document(text: str) -> dict[str, dict[str, str]]:
    sections: dict[str, dict[str, str]] = {}
    current: dict[str, str] | None = None
    for line_no, raw in enumerate(text.replace("\r\n", "\n").replace("\r", "\n").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith((";", "#")):
            continue
        if line.startswith("[") and line.endswith("]"):
            current = sections.setdefault(line[1:-1].strip().casefold(), {})
            continue
        if "=" not in line:
            continue
        if current is None:
            raise LegacyImportError(f"Line {line_no}: value outside INI section.")
        key, value = line.split("=", 1)
        current[key.strip().casefold()] = value.strip()
    if "dados" not in sections or "secoes" not in sections:
        raise LegacyImportError("Legacy project requires [Dados] and [Secoes].")
    return sections


def _number(value, default: float = 0.0) -> float:
    if value is None or str(value).strip() == "":
        return default
    text = str(value).strip().replace("D", "E").replace("d", "e")
    if "," in text and "." not in text:
        text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError as exc:
        raise LegacyImportError(f"Invalid numeric value: {value!r}") from exc


def _integer(value, default: int = 0) -> int:
    if value is None or str(value).strip() == "":
        return default
    number = _number(value)
    rounded = int(round(number))
    if abs(number - rounded) > 1e-9:
        raise LegacyImportError(f"Invalid integer value: {value!r}")
    return rounded


def _bool(value) -> bool:
    if value is None:
        return False
    text = str(value).strip().casefold()
    if text in {"true", "yes", "sim", "on"}:
        return True
    return bool(_integer(value, 0))


def _grid_rows(section: dict[str, str] | None) -> list[dict[int, str]]:
    grouped: dict[int, dict[int, str]] = defaultdict(dict)
    for key, value in (section or {}).items():
        match = _GRID_KEY.match(key)
        if match:
            grouped[int(match.group(1))][int(match.group(2))] = value
    return [grouped[row] for row in sorted(grouped)]


def _cell(row: dict[int, str], col: int, default: str = "") -> str:
    return row.get(col, default)


def _shaft_diameter_at(sections: list[ShaftSectionSpec], position_mm: float) -> float:
    x = 0.0
    for section in sections:
        x1 = x + section.length_mm
        if x - 1e-9 <= position_mm <= x1 + 1e-9:
            ratio = min(1.0, max(0.0, (position_mm - x) / section.length_mm))
            return section.outer_diameter_left_mm + (section.odr_mm - section.outer_diameter_left_mm) * ratio
        x = x1
    raise LegacyImportError(f"Position {position_mm:g} mm is outside the shaft.")


def _rotordin_disk_inertias(mass_kg: float, length_mm: float, od_mm: float, id_mm: float) -> tuple[float, float]:
    """Reproduce RotorDin predad.f mmmidkf/smindkf formulas exactly."""
    od = od_mm / 1000.0
    inner = id_mm / 1000.0
    length = length_mm / 1000.0
    polar = mass_kg / 8.0 * (od * od + inner * inner)
    diametral = 0.5 * polar + mass_kg / 12.0 * length * length
    return diametral, polar


def _resolve_ump_source(value: float, source_unit: str, formulation: UmpFormulation) -> tuple[float, str, float]:
    """Resolve legacy source semantics without silently trusting the historical UI label."""
    unit = source_unit.strip().casefold().replace(" ", "")
    if unit in {"legacy_unknown", "unknown", "legacy"}:
        if formulation == UmpFormulation.PHYSICAL_CORRECTED:
            raise LegacyImportError(
                "PHYSICAL_CORRECTED UMP cannot be imported from a legacy_unknown unit. "
                "Declare the physical source unit explicitly."
            )
        return float(value), "legacy_unknown", 1.0
    if unit in {"n/m2", "n/m^2", "n/m²"}:
        return float(value), "N/m²", 1.0
    if unit in {"kgf/mm2", "kgf/mm^2", "kgf/mm²"}:
        return legacy_ump_to_si(value), "kgf/mm²", LEGACY_KGF_MM2_TO_N_M2
    raise LegacyImportError(
        f"Unsupported legacy UMP source unit {source_unit!r}; use legacy_unknown, N/m2, or explicitly kgf/mm2."
    )


def _table_bearing(row: dict[int, str], bearing_index: int) -> CoefficientBearingSpec:
    raw = _cell(row, 11).strip()
    position = _number(_cell(row, 0))
    tag = _cell(row, 10) or f"Bearing {bearing_index}"
    if raw.upper().startswith("TABLE"):
        chunks = [chunk.strip() for chunk in raw.split("§") if chunk.strip()]
        if len(chunks) < 2:
            raise LegacyImportError(f"Bearing #{bearing_index} TABLE has no data rows.")
        parsed: list[list[float]] = []
        for row_no, chunk in enumerate(chunks[1:], start=1):
            fields = [field.strip() for field in chunk.split("|")]
            if len(fields) != 9:
                raise LegacyImportError(
                    f"Bearing #{bearing_index} TABLE row {row_no}: expected rpm + 8 K/C values."
                )
            parsed.append([_number(v) for v in fields])
        return CoefficientBearingSpec(
            position_mm=position,
            frequency_rpm=[v[0] for v in parsed],
            kxx=[v[1] for v in parsed],
            kxz=[v[2] for v in parsed],
            kzz=[v[3] for v in parsed],
            kzx=[v[4] for v in parsed],
            cxx=[v[5] for v in parsed],
            cxz=[v[6] for v in parsed],
            czz=[v[7] for v in parsed],
            czx=[v[8] for v in parsed],
            tag=tag,
        )
    if raw and not raw.upper().startswith("COEF"):
        raise LegacyImportError(
            f"Bearing #{bearing_index} references unsupported external asset {raw!r}; embed TABLE/COEF first."
        )
    return CoefficientBearingSpec(
        position_mm=position,
        kxx=_number(_cell(row, 1)),
        kxz=_number(_cell(row, 3)),
        kzz=_number(_cell(row, 2)),
        kzx=_number(_cell(row, 4)),
        cxx=_number(_cell(row, 5)),
        cxz=_number(_cell(row, 7)),
        czz=_number(_cell(row, 6)),
        czx=_number(_cell(row, 8)),
        tag=tag,
    )


def loads_irdin_project(
    text: str,
    *,
    source_name: str = "legacy.irdin",
    ump_source_unit: str = "legacy_unknown",
    ump_formulation: UmpFormulation | str = UmpFormulation.ROTORDIN_LEGACY_COMPAT,
) -> RotorProject:
    document = _parse_document(text)
    header = document.get("irdin", {})
    data = document["dados"]
    formulation = UmpFormulation(ump_formulation)
    material = MaterialSpec(
        name="Legacy Steel",
        density_kg_m3=_number(data.get("s_masesp"), 7850.0),
        young_pa=_number(data.get("s_melast"), 2.07e11),
        poisson=_number(data.get("s_poisson"), 0.3),
    )

    shaft: list[ShaftSectionSpec] = []
    for idx, row in enumerate(_grid_rows(document.get("secoes")), start=1):
        package_diameter = _number(_cell(row, 2), 0.0)
        rib_count = _integer(_cell(row, 6), 0)
        if package_diameter > 0 or rib_count > 0:
            raise LegacyImportError(
                f"Section #{idx} is ribbed/packaged; no verified ROSS equivalent is enabled yet."
            )
        od = _number(_cell(row, 1))
        odr = _number(_cell(row, 8), od) or od
        inner = _number(_cell(row, 7), 0.0)
        shaft.append(
            ShaftSectionSpec(
                length_mm=_number(_cell(row, 0)),
                outer_diameter_left_mm=od,
                inner_diameter_left_mm=inner,
                outer_diameter_right_mm=odr,
                inner_diameter_right_mm=inner,
                material=material.name,
                tag=str(idx),
            )
        )

    disks: list[DiskSpec] = []
    ump_regions: list[UMPRegionSpec] = []
    mass_audit: list[dict[str, float | bool]] = []
    warnings: list[str] = []
    ump_audit: list[dict[str, float | str | bool]] = []
    global_ump = _number(data.get("ump_crg"), 0.0)
    ump_si, resolved_ump_unit, ump_factor = _resolve_ump_source(global_ump, ump_source_unit, formulation)
    for idx, row in enumerate(_grid_rows(document.get("massas")), start=1):
        xi = _number(_cell(row, 0))
        length = _number(_cell(row, 1))
        mass = _number(_cell(row, 2))
        center = xi + length / 2.0
        shaft_od = _shaft_diameter_at(shaft, center)
        od = _number(_cell(row, 3), 0.0) or shaft_od
        inner = _number(_cell(row, 6), 0.0) or shaft_od
        if inner >= od:
            raise LegacyImportError(f"Distributed mass #{idx} has ID >= OD after RotorDin fallback rules.")
        diametral, polar = _rotordin_disk_inertias(mass, length, od, inner)
        disks.append(DiskSpec(center, mass, diametral, polar, tag=f"Legacy distributed mass {idx}"))
        package = _bool(_cell(row, 4))
        ump = _bool(_cell(row, 5))
        if ump:
            region = UMPRegionSpec(
                start_mm=xi,
                end_mm=xi + length,
                kxx_prime_n_m2=ump_si,
                kyy_prime_n_m2=ump_si,
                formulation=formulation,
                tag=f"UMP active span {idx}",
                source_value=global_ump,
                source_unit=resolved_ump_unit,
                solver_interpretation="N/m²",
            )
            ump_regions.append(region)
            ump_audit.append(
                {
                    "mass_row": idx,
                    "start_mm": xi,
                    "end_mm": xi + length,
                    "source_value": global_ump,
                    "source_unit": resolved_ump_unit,
                    "conversion_factor_to_n_m2": ump_factor,
                    "solver_interpretation": "N/m²",
                    "formulation": formulation.value,
                    "legacy_threshold_n_m2": ROTORDIN_LEGACY_THRESHOLD_N_M2,
                    "legacy_rotary_term_enabled": formulation == UmpFormulation.ROTORDIN_LEGACY_COMPAT,
                    "undefined_region_pointer_bug_emulated": False,
                    "mkb_contamination_bug_emulated": False,
                }
            )
        mass_audit.append(
            {
                "xi_mm": xi,
                "length_mm": length,
                "mass_kg": mass,
                "od_mm": od,
                "id_mm": inner,
                "package": package,
                "ump": ump,
            }
        )

    if formulation == UmpFormulation.ROTORDIN_LEGACY_COMPAT and len(ump_regions) > ROTORDIN_LEGACY_MAX_REGIONS:
        raise LegacyImportError(
            f"RotorDin legacy compatibility supports at most {ROTORDIN_LEGACY_MAX_REGIONS} UMP regions."
        )

    if ump_regions and resolved_ump_unit == "legacy_unknown":
        warnings.append(
            "UMP source_unit=legacy_unknown: the historical UI does not establish a physical unit. The numeric legacy value "
            "is preserved only under ROTORDIN_LEGACY_COMPAT and interpreted by the solver as N/m². "
            "PHYSICAL_CORRECTED remains fail-closed until the physical source unit is explicitly confirmed."
        )
    elif ump_regions:
        warnings.append(
            f"UMP source was explicitly declared as {resolved_ump_unit}; formulation={formulation.value}."
        )

    bearings = [_table_bearing(row, idx) for idx, row in enumerate(_grid_rows(document.get("mancais")), start=1)]

    unbalances = [
        UnbalanceSpec(
            position_mm=_number(_cell(row, 0)),
            phase_deg=_number(_cell(row, 1), 0.0),
            magnitude_g_mm=_number(_cell(row, 2), 0.0),
            tag=f"Unbalance {idx}",
        )
        for idx, row in enumerate(_grid_rows(document.get("desbal")), start=1)
    ]
    probes = [
        ProbeSpec(
            position_mm=_number(_cell(row, 0)),
            coordinate=_integer(_cell(row, 1), 1),
            orientation_deg=_number(_cell(row, 2), 0.0),
            tag=f"Probe {idx}",
        )
        for idx, row in enumerate(_grid_rows(document.get("respo")), start=1)
    ]

    point_masses: list[PointMassSpec] = []
    for idx, row in enumerate(_grid_rows(document.get("concent")), start=1):
        inertias = [_number(_cell(row, col), 0.0) for col in (2, 3, 4)]
        if any(abs(v) > 1e-15 for v in inertias):
            raise LegacyImportError(
                f"Concentrated mass #{idx} contains rotational inertias; verified ROSS mapping is not enabled yet."
            )
        point_masses.append(
            PointMassSpec(_number(_cell(row, 0)), _number(_cell(row, 1)), tag=f"Concentrated mass {idx}")
        )

    supports: list[SupportSpec] = []
    for idx, row in enumerate(_grid_rows(document.get("suporte")), start=1):
        supports.append(
            SupportSpec(
                bearing_index=_integer(_cell(row, 0)) - 1,
                kxx=_number(_cell(row, 1)),
                kzz=_number(_cell(row, 2)),
                kxz=_number(_cell(row, 3)),
                kzx=_number(_cell(row, 4)),
                cxx=_number(_cell(row, 5)),
                czz=_number(_cell(row, 6)),
                cxz=_number(_cell(row, 7)),
                czx=_number(_cell(row, 8)),
                mass_kg=_number(_cell(row, 9)),
                tag=_cell(row, 10) or f"Support {idx}",
            )
        )

    analyses = AnalysisRequest(
        static=True,
        modal=True,
        critical_speed=True,
        campbell=True,
        modal_speed_rpm=_number(data.get("nnom"), 0.0),
        campbell_initial_rpm=_number(data.get("c_rpmi"), 0.0),
        campbell_final_rpm=_number(data.get("c_rpmf"), 6000.0),
        campbell_step_rpm=_number(data.get("c_div"), 100.0),
        modes=max(1, _integer(data.get("m_nrmodos"), 10)),
    )

    metadata = {
        "component": data.get("comp", ""),
        "line": data.get("linha", ""),
        "frame": data.get("carc", ""),
        "poles": _integer(data.get("polos"), 2),
        "frequency_hz": _number(data.get("freq"), 60.0),
        "rotor_speed_rpm": _number(data.get("nnom"), 0.0),
        "legacy_import": {
            "format": "iRdin/VB6 INI",
            "source_name": source_name,
            "date": header.get("data", ""),
            "user": header.get("usuario", ""),
            "warnings": warnings,
            "distributed_mass_audit": mass_audit,
            "ump_audit": ump_audit,
        },
        "response": {
            "initial_rpm": _number(data.get("d_rpmi"), 0.0),
            "final_rpm": _number(data.get("d_rpmf"), 0.0),
            "step_rpm": _number(data.get("d_div"), 0.0),
            "modes": _integer(data.get("d_nrmodos"), 0),
            "orbit_position_mm": _number(data.get("t_pos"), 0.0),
            "orbit_speed_rpm": _number(data.get("t_rpm"), 0.0),
        },
    }
    project = RotorProject(
        reference=data.get("ref", source_name),
        materials=[material],
        shaft=shaft,
        disks=disks,
        point_masses=point_masses,
        bearings=bearings,
        unbalances=unbalances,
        probes=probes,
        supports=supports,
        ump_regions=ump_regions,
        analyses=analyses,
        metadata=metadata,
    )
    project.validate()
    return project


def load_irdin_project(
    path: str | Path,
    *,
    ump_source_unit: str = "legacy_unknown",
    ump_formulation: UmpFormulation | str = UmpFormulation.ROTORDIN_LEGACY_COMPAT,
) -> RotorProject:
    source = Path(path)
    return loads_irdin_project(
        _read_text(source),
        source_name=source.name,
        ump_source_unit=ump_source_unit,
        ump_formulation=ump_formulation,
    )


__all__ = ["LegacyImportError", "load_irdin_project", "loads_irdin_project"]
