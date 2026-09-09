from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import re

from .domain import (
    BearingCoefficientPoint,
    BearingGroup,
    BearingSpec,
    DistributedMassSpec,
    LoadSpec,
    MaterialSpec,
    OperatingCase,
    PointMassSpec,
    ProbeSpec,
    RotorProject,
    ShaftSection,
    SupportSpec,
)

_GRID_KEY = re.compile(r"^(\d+)\s*,\s*(\d+)$")


def _number(value: str | None, default: float = 0.0) -> float:
    if value is None or not str(value).strip():
        return default
    return float(str(value).strip().replace(",", "."))


def _integer(value: str | None, default: int = 0) -> int:
    number = _number(value, float(default))
    rounded = round(number)
    if abs(number - rounded) > 1e-9:
        raise ValueError(f"Expected integer value, received {value!r}")
    return int(rounded)


def _parse(path: str | Path) -> dict[str, dict[str, str]]:
    text = Path(path).read_text(encoding="utf-8-sig")
    sections: dict[str, dict[str, str]] = {}
    current: dict[str, str] | None = None
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").splitlines():
        line = raw.strip()
        if not line or line.startswith((";", "#")):
            continue
        if line.startswith("[") and line.endswith("]"):
            current = sections.setdefault(line[1:-1].strip().casefold(), {})
            continue
        if current is None or "=" not in line:
            continue
        key, value = line.split("=", 1)
        current[key.strip().casefold()] = value.strip()
    return sections


def _grid_rows(section: dict[str, str] | None) -> list[dict[int, str]]:
    grouped: dict[int, dict[int, str]] = defaultdict(dict)
    for key, value in (section or {}).items():
        match = _GRID_KEY.match(key)
        if match:
            grouped[int(match.group(1))][int(match.group(2))] = value
    return [grouped[key] for key in sorted(grouped)]


def _cell(row: dict[int, str], col: int, default: str = "") -> str:
    return row.get(col, default)


def _bearing_table(raw: str) -> list[BearingCoefficientPoint]:
    value = raw.strip()
    if not value:
        return []
    chunks = [chunk.strip() for chunk in value.split("§") if chunk.strip()]
    if not chunks or not chunks[0].upper().startswith("TABLE"):
        return []
    points: list[BearingCoefficientPoint] = []
    for row in chunks[1:]:
        values = [_number(x) for x in row.replace("|", " ").split()]
        if len(values) != 9:
            raise ValueError("Legacy bearing TABLE must contain rpm + 8 K/C coefficients per point.")
        points.append(BearingCoefficientPoint(*values))
    return points


def load_irdin_project(path: str | Path) -> RotorProject:
    """Load the VB6/iRdin text format without performing scientific calculations."""
    doc = _parse(path)
    data = doc.get("dados", {})
    material = MaterialSpec(
        name="Steel",
        density_kg_m3=_number(data.get("s_masesp"), 7850.0),
        young_pa=_number(data.get("s_melast"), 207e9),
        poisson=_number(data.get("s_poisson"), 0.3),
    )
    component = data.get("comp", "Legacy rotor").strip()
    project = RotorProject(
        name=f"{data.get('ref', '').strip()}-{component}".strip("-"),
        reference=data.get("ref", "").strip(),
        line=data.get("linha", "").strip(),
        frame=data.get("carc", "").strip(),
        poles=max(1, _integer(data.get("polos"), 2)),
        description=component,
        materials={material.name: material},
        operating_cases=[OperatingCase(
            name="Legacy Campbell range",
            rated_speed_rpm=_number(data.get("nnom"), 0.0),
            speed_min_rpm=_number(data.get("c_rpmi"), 0.0),
            speed_max_rpm=_number(data.get("c_rpmf"), 0.0),
            frequency_hz=_number(data.get("freq"), 60.0),
        )],
    )

    for index, row in enumerate(_grid_rows(doc.get("secoes")), 1):
        od = _number(_cell(row, 1))
        project.shaft_sections.append(ShaftSection(index, _number(_cell(row, 0)), od, od, material=material.name))

    ump_value = _number(data.get("ump_crg"), 0.0)
    for index, row in enumerate(_grid_rows(doc.get("massas")), 1):
        ump = bool(_integer(_cell(row, 5), 0))
        project.distributed_masses.append(DistributedMassSpec(
            name=f"Rotor mass {index}",
            start_mm=_number(_cell(row, 0)),
            length_mm=_number(_cell(row, 1)),
            mass_kg=_number(_cell(row, 2)),
            od_mm=_number(_cell(row, 3), 0.0),
            id_mm=_number(_cell(row, 6), 0.0),
            is_package=bool(_integer(_cell(row, 4), 0)),
            ump_enabled=ump,
            ump_value=ump_value if ump else 0.0,
        ))

    for index, row in enumerate(_grid_rows(doc.get("mancais")), 1):
        points = _bearing_table(_cell(row, 11))
        project.bearings.append(BearingSpec(
            name=_cell(row, 10, f"Bearing {index}"),
            position_mm=_number(_cell(row, 0)),
            ross_class="BearingElement",
            group=BearingGroup.GENERAL,
            kxx=_number(_cell(row, 1), 0.0),
            kyy=_number(_cell(row, 2), 0.0),
            kxy=_number(_cell(row, 3), 0.0),
            kyx=_number(_cell(row, 4), 0.0),
            cxx=_number(_cell(row, 5), 0.0),
            cyy=_number(_cell(row, 6), 0.0),
            cxy=_number(_cell(row, 7), 0.0),
            cyx=_number(_cell(row, 8), 0.0),
            coefficients=points,
        ))

    for index, row in enumerate(_grid_rows(doc.get("desbal")), 1):
        # iRdin stores residual unbalance in g*mm. Preserve the raw engineering
        # value in the domain; SI normalization is intentionally deferred to the
        # ROSS execution boundary (RossAnalysisBackend).
        project.loads.append(LoadSpec(
            name=f"Unbalance {index}",
            kind="unbalance",
            position_mm=_number(_cell(row, 0)),
            phase_deg=_number(_cell(row, 1), 0.0),
            magnitude=_number(_cell(row, 2), 0.0),
            metadata={
                "magnitude_unit": "g*mm",
                "source_unit": "g*mm",
                "source": "iRdin [Desbal] raw residual-unbalance value",
                "normalization_policy": "Convert to kg*m only at ROSS execution boundary",
            },
        ))

    for index, row in enumerate(_grid_rows(doc.get("respo")), 1):
        project.probes.append(ProbeSpec(
            name=f"Probe {index}",
            position_mm=_number(_cell(row, 0)),
            coordinate=_integer(_cell(row, 1), 1),
            orientation_deg=_number(_cell(row, 2), 0.0),
        ))

    for index, row in enumerate(_grid_rows(doc.get("concent")), 1):
        project.point_masses.append(PointMassSpec(
            name=f"Point mass {index}",
            position_mm=_number(_cell(row, 0)),
            mass_kg=_number(_cell(row, 1), 0.0),
        ))

    for index, row in enumerate(_grid_rows(doc.get("suporte")), 1):
        bearing_number = _integer(_cell(row, 0), index)
        project.supports.append(SupportSpec(
            name=f"Support {bearing_number}",
            bearing_index=bearing_number - 1,
            kxx=_number(_cell(row, 1), 0.0),
            kyy=_number(_cell(row, 2), 0.0),
            kxy=_number(_cell(row, 3), 0.0),
            kyx=_number(_cell(row, 4), 0.0),
            cxx=_number(_cell(row, 5), 0.0),
            cyy=_number(_cell(row, 6), 0.0),
            cxy=_number(_cell(row, 7), 0.0),
            cyx=_number(_cell(row, 8), 0.0),
            mass_kg=_number(_cell(row, 9), 0.0),
        ))

    project.validate()
    return project


__all__ = ["load_irdin_project"]
