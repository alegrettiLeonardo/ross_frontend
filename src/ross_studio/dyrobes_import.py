from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import re
from pathlib import Path

from .domain import DiskSpec, MaterialSpec, RotorProject, ShaftSection


class DyrobesImportError(ValueError):
    """Raised when a DyRoBeS file cannot be imported without guessing physics."""


_NUMBER = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[EeDd][-+]?\d+)?"
_UNIT_RE = re.compile(r"Unit\s*System\s*=\s*(\d+)", re.IGNORECASE)


@dataclass(slots=True, frozen=True)
class DyrobesUnits:
    unit_system: int
    length_to_mm: float
    density_to_kg_m3: float
    modulus_to_pa: float
    mass_to_kg: float
    inertia_to_kg_m2: float
    label: str


def _units(unit_system: int) -> DyrobesUnits:
    # DyRoBeS manual: 1=consistent English, 2=engineering English,
    # 3=consistent SI, 4=engineering metric. Unit 0 is user-defined and cannot
    # be converted safely without an explicit unit map.
    if unit_system == 1:
        # length=in, force=lbf, mass unit=lbf*s^2/in
        mass_unit_kg = 4.4482216152605 / 0.0254
        return DyrobesUnits(
            1, 25.4,
            mass_unit_kg / (0.0254**3),
            4.4482216152605 / (0.0254**2),
            mass_unit_kg,
            mass_unit_kg * (0.0254**2),
            "consistent English (s, in, lbf, lbf*s^2/in)",
        )
    if unit_system == 2:
        return DyrobesUnits(
            2, 25.4,
            0.45359237 / (0.0254**3),
            4.4482216152605 / (0.0254**2),
            0.45359237,
            0.45359237 * (0.0254**2),
            "engineering English (s, in, lbf, lbm)",
        )
    if unit_system == 3:
        return DyrobesUnits(3, 1000.0, 1.0, 1.0, 1.0, 1.0, "consistent SI (s, m, N, kg)")
    if unit_system == 4:
        # Geometry is in mm while material density/modulus are normally printed
        # in kg/m^3 and N/m^2 by DyRoBeS model summaries. The parser additionally
        # inspects header text and will reject an ambiguous material table.
        return DyrobesUnits(4, 1.0, 1.0, 1.0, 1.0, 1.0e-6, "engineering metric (s, mm, N, kg)")
    raise DyrobesImportError(
        f"DyRoBeS Unit System {unit_system} is not safely convertible. "
        "Unit=0 is user-defined and requires an explicit unit map."
    )


def _read_text(path: Path) -> str:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise DyrobesImportError(f"Cannot decode DyRoBeS file {path.name} as text.")


def _float(token: str) -> float:
    return float(token.replace("D", "E").replace("d", "e"))


def _section(text: str, heading: str, next_headings: tuple[str, ...]) -> str:
    start = re.search(rf"\*+\s*{re.escape(heading)}\s*\*+", text, re.IGNORECASE)
    if not start:
        return ""
    tail = text[start.end():]
    ends = []
    for candidate in next_headings:
        match = re.search(rf"\*+\s*{re.escape(candidate)}\s*\*+", tail, re.IGNORECASE)
        if match:
            ends.append(match.start())
    return tail[: min(ends)] if ends else tail


def _numeric_lines(block: str) -> list[list[float]]:
    rows: list[list[float]] = []
    for raw in block.splitlines():
        line = raw.strip()
        if not line or line.startswith("*"):
            continue
        tokens = re.findall(_NUMBER, line)
        # Reject lines containing alphabetic engineering labels. Exponents E/D
        # have already been accepted inside numeric tokens, so stripping numbers,
        # punctuation and whitespace leaves any true heading/comment text.
        residue = re.sub(_NUMBER, "", line)
        residue = re.sub(r"[\s,;:()\[\]/^*.-]+", "", residue)
        if residue:
            continue
        if tokens:
            rows.append([_float(token) for token in tokens])
    return rows


def _parse_materials(text: str, units: DyrobesUnits) -> dict[int, MaterialSpec]:
    block = _section(text, "Material Properties", ("Shaft Elements", "Rigid Disks", "Unbalance"))
    if not block:
        raise DyrobesImportError("DyRoBeS MODEL SUMMARY has no Material Properties section.")
    rows = [row for row in _numeric_lines(block) if len(row) >= 4]
    if not rows:
        # PDF/text exports sometimes put every material value on a separate line.
        values = [_float(token) for token in re.findall(_NUMBER, block)]
        if len(values) == 4:
            rows = [values]
    if not rows:
        raise DyrobesImportError("Could not read DyRoBeS material rows without guessing column boundaries.")

    lower = block.casefold()
    density_factor = units.density_to_kg_m3
    modulus_factor = units.modulus_to_pa
    if units.unit_system == 4:
        if "kg/mm" in lower:
            density_factor = 1.0e9
        elif "kg/m" not in lower:
            raise DyrobesImportError("DyRoBeS Unit=4 material density unit is ambiguous in this export.")
        if "n/mm" in lower:
            modulus_factor = 1.0e6
        elif "n/m" not in lower:
            raise DyrobesImportError("DyRoBeS Unit=4 material modulus unit is ambiguous in this export.")

    out: dict[int, MaterialSpec] = {}
    for row in rows:
        number = int(round(row[0]))
        density = row[1] * density_factor
        young = row[2] * modulus_factor
        shear = row[3] * modulus_factor
        if density <= 0 or young <= 0 or shear <= 0:
            raise DyrobesImportError(f"DyRoBeS material {number} contains non-positive properties.")
        poisson = young / (2.0 * shear) - 1.0
        if not -1.0 < poisson < 0.5:
            raise DyrobesImportError(
                f"DyRoBeS material {number} implies Poisson ratio {poisson:g}; refusing an unphysical conversion."
            )
        out[number] = MaterialSpec(
            name=f"DyRoBeS Material {number}", density_kg_m3=density, young_pa=young, poisson=poisson
        )
    return out


def _parse_shaft(text: str, units: DyrobesUnits, materials: dict[int, MaterialSpec]) -> list[ShaftSection]:
    block = _section(
        text,
        "Shaft Elements",
        ("Rigid Disks", "Rotor Equivalent Rigid Body Properties", "Unbalance", "Bearing Coefficients"),
    )
    if not block:
        raise DyrobesImportError("DyRoBeS MODEL SUMMARY has no Shaft Elements section.")

    # Normal ASCII Model Summary row:
    # element, subelement, left location, length, mass ID, mass OD,
    # stiffness ID, stiffness OD, material number.
    raw_rows = [row for row in _numeric_lines(block) if len(row) >= 9]
    if not raw_rows:
        # Some text extractors wrap the parent element number onto its own line.
        current_element: int | None = None
        repaired: list[list[float]] = []
        for row in _numeric_lines(block):
            if len(row) == 1 and abs(row[0] - round(row[0])) < 1e-9:
                current_element = int(round(row[0]))
            elif len(row) >= 8 and current_element is not None:
                repaired.append([float(current_element), *row[:8]])
        raw_rows = repaired
    if not raw_rows:
        raise DyrobesImportError("Could not read DyRoBeS shaft-element rows without guessing column boundaries.")

    grouped: dict[int, list[list[float]]] = defaultdict(list)
    for row in raw_rows:
        element = int(round(row[0]))
        grouped[element].append(row)

    sections: list[ShaftSection] = []
    for element in sorted(grouped):
        rows = sorted(grouped[element], key=lambda row: abs(int(round(row[1]))))
        if any(int(round(row[1])) < 0 for row in rows):
            raise DyrobesImportError(
                f"DyRoBeS element {element} contains a conical subelement. "
                "Tapered multi-subelement reconstruction is not yet qualified."
            )
        material_numbers = {int(round(row[8])) for row in rows}
        if len(material_numbers) != 1:
            raise DyrobesImportError(f"DyRoBeS element {element} uses multiple materials across subelements.")
        material_number = next(iter(material_numbers))
        if material_number not in materials:
            raise DyrobesImportError(f"DyRoBeS element {element} references unknown material {material_number}.")
        stiffness_ids = [row[6] for row in rows]
        stiffness_ods = [row[7] for row in rows]
        if max(stiffness_ids) - min(stiffness_ids) > 1e-9 or max(stiffness_ods) - min(stiffness_ods) > 1e-9:
            raise DyrobesImportError(
                f"DyRoBeS element {element} changes stiffness diameter within its subelements. "
                "Split-element reconstruction is required before this layout can be imported losslessly."
            )
        sections.append(
            ShaftSection(
                section=len(sections) + 1,
                length_mm=sum(row[3] for row in rows) * units.length_to_mm,
                od_left_mm=stiffness_ods[0] * units.length_to_mm,
                od_right_mm=stiffness_ods[-1] * units.length_to_mm,
                id_left_mm=stiffness_ids[0] * units.length_to_mm,
                id_right_mm=stiffness_ids[-1] * units.length_to_mm,
                material=materials[material_number].name,
                # Preserve DyRoBeS subelement discretization as the base FE count.
                fe_elements=len(rows),
            )
        )
    return sections


def _station_positions_mm(sections: list[ShaftSection]) -> dict[int, float]:
    positions = {1: 0.0}
    x = 0.0
    for index, section in enumerate(sections, 1):
        x += section.length_mm
        positions[index + 1] = x
    return positions


def _parse_rigid_disks(text: str, units: DyrobesUnits, sections: list[ShaftSection]) -> list[DiskSpec]:
    block = _section(
        text,
        "Rigid Disks",
        ("Rotor Equivalent Rigid Body Properties", "Unbalance", "Bearing Coefficients", "Gravity Constant"),
    )
    if not block:
        return []
    rows = [row for row in _numeric_lines(block) if len(row) >= 6]
    station_positions = _station_positions_mm(sections)
    disks: list[DiskSpec] = []
    for row in rows:
        station = int(round(row[0]))
        if station not in station_positions:
            raise DyrobesImportError(f"DyRoBeS rigid disk references station {station}, outside imported shaft.")
        disks.append(
            DiskSpec(
                name=f"DyRoBeS Disk {len(disks) + 1}",
                position_mm=station_positions[station],
                mass_kg=row[1] * units.mass_to_kg,
                id_kg_m2=row[2] * units.inertia_to_kg_m2,
                ip_kg_m2=row[3] * units.inertia_to_kg_m2,
            )
        )
    return disks


def load_dyrobes_project(path: str | Path) -> RotorProject:
    """Import the qualified, labelled ASCII DyRoBeS Model Summary contract.

    DyRoBeS `.rot` files are ASCII, but the vendor's internal data layout is not
    publicly specified as a stable interchange schema. ROSS Studio therefore
    imports labelled MODEL SUMMARY data and refuses unknown raw layouts rather than
    guessing columns or silently changing rotor physics.
    """
    source = Path(path)
    text = _read_text(source)
    unit_match = _UNIT_RE.search(text)
    if not unit_match:
        raise DyrobesImportError(
            "DyRoBeS file recognized by extension but Unit System was not found. "
            "Export/print Model Summary text or provide this .rot layout for qualification."
        )
    unit_system = int(unit_match.group(1))
    units = _units(unit_system)
    if "MODEL SUMMARY" not in text.upper():
        raise DyrobesImportError(
            "DyRoBeS .rot is ASCII, but this raw vendor layout is not yet qualified. "
            "ROSS Studio will not guess proprietary field positions. Export the DyRoBeS Model Summary "
            "(ASCII) or provide a representative .rot file to qualify this exact layout."
        )

    materials_by_number = _parse_materials(text, units)
    sections = _parse_shaft(text, units, materials_by_number)
    disks = _parse_rigid_disks(text, units, sections)
    materials = {material.name: material for material in materials_by_number.values()}

    warnings = [
        f"Imported from DyRoBeS labelled ASCII MODEL SUMMARY; Unit System={unit_system} ({units.label}).",
        "DyRoBeS Z is the spin axis; ROSS Studio stores shaft position in its axial model coordinate.",
    ]
    system_block = _section(text, "System Parameters", ("Description Headers", "Material Properties"))
    bearing_declared = 0
    match = re.search(rf"({_NUMBER})\s+Linear\s+Bearings", system_block, re.IGNORECASE)
    if match:
        bearing_declared = int(round(_float(match.group(1))))
    if bearing_declared:
        warnings.append(
            f"DyRoBeS summary declares {bearing_declared} linear bearing(s); coefficient-block import is not yet "
            "qualified for all DyRoBeS print layouts, so these bearings were not silently reconstructed."
        )

    project = RotorProject(
        name=source.stem,
        reference="DyRoBeS",
        description=f"Imported DyRoBeS model: {source.name}",
        materials=materials,
        shaft_sections=sections,
        disks=disks,
        warnings=warnings,
    )
    project.validate()
    return project


__all__ = ["DyrobesImportError", "DyrobesUnits", "load_dyrobes_project"]
