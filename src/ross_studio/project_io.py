from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from enum import Enum
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from .domain import (
    BearingCoefficientPoint,
    BearingGroup,
    BearingSpec,
    CouplingSpec,
    DiskSpec,
    DistributedMassSpec,
    FoundationCoefficientPoint,
    FoundationModel,
    FoundationSpec,
    LateralConvention,
    LoadSpec,
    MaterialSpec,
    OperatingCase,
    PointMassSpec,
    ProbeAngleContract,
    ProbeSpec,
    RotorProject,
    SealSpec,
    ShaftSection,
    SupportSpec,
)
from .models import ProjectModel

FORMAT_NAME = "ROSS Studio Project"
SCHEMA_VERSION = 1
NATIVE_EXTENSION = ".rossproj"


class ProjectFormatError(ValueError):
    """Raised when a project file is invalid or uses an unsupported schema."""


def _json_safe(value: Any, path: str = "root") -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ProjectFormatError(f"{path}: non-finite numeric value cannot be persisted.")
        return value
    if isinstance(value, Enum):
        return _json_safe(value.value, path)
    if isinstance(value, dict):
        return {str(key): _json_safe(item, f"{path}.{key}") for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item, f"{path}[{index}]") for index, item in enumerate(value)]
    if hasattr(value, "item"):
        try:
            return _json_safe(value.item(), path)
        except Exception:
            pass
    if hasattr(value, "tolist"):
        try:
            return _json_safe(value.tolist(), path)
        except Exception:
            pass
    raise ProjectFormatError(
        f"{path}: unsupported metadata value {type(value).__name__}; refusing a lossy project save."
    )


def _project_payload(model: ProjectModel) -> dict[str, Any]:
    engineering = None if model.engineering is None else _json_safe(asdict(model.engineering), "engineering")
    return {
        "format": FORMAT_NAME,
        "schema_version": SCHEMA_VERSION,
        "app_version": "0.24.0",
        "project_meta": {
            "name": model.name,
            "description": model.description,
            "created": model.created,
            "modified": model.modified,
        },
        "engineering": engineering,
    }


def project_fingerprint(model: ProjectModel) -> str:
    data = json.dumps(_project_payload(model), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def save_project(model: ProjectModel, path: str | Path) -> Path:
    target = Path(path)
    if target.suffix.casefold() != NATIVE_EXTENSION:
        target = target.with_suffix(NATIVE_EXTENSION)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = _project_payload(model)
    temp = target.with_name(f".{target.name}.tmp")
    try:
        temp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        temp.replace(target)
    finally:
        if temp.exists():
            temp.unlink()
    return target


def _material(row: dict[str, Any]) -> MaterialSpec:
    return MaterialSpec(**row)


def _shaft(row: dict[str, Any]) -> ShaftSection:
    return ShaftSection(**row)


def _bearing_point(row: dict[str, Any]) -> BearingCoefficientPoint:
    return BearingCoefficientPoint(**row)


def _bearing(row: dict[str, Any]) -> BearingSpec:
    data = dict(row)
    data["group"] = BearingGroup(data.get("group", BearingGroup.GENERAL.value))
    data["coefficients"] = [_bearing_point(point) for point in data.get("coefficients", [])]
    return BearingSpec(**data)


def _distributed_mass(row: dict[str, Any]) -> DistributedMassSpec:
    return DistributedMassSpec(**row)


def _point_mass(row: dict[str, Any]) -> PointMassSpec:
    return PointMassSpec(**row)


def _disk(row: dict[str, Any]) -> DiskSpec:
    return DiskSpec(**row)


def _support(row: dict[str, Any]) -> SupportSpec:
    return SupportSpec(**row)


def _foundation_point(row: dict[str, Any]) -> FoundationCoefficientPoint:
    return FoundationCoefficientPoint(**row)


def _foundation(row: dict[str, Any]) -> FoundationSpec:
    data = dict(row)
    data["model_type"] = FoundationModel(data.get("model_type", FoundationModel.RIGID.value))
    data["coefficients"] = [_foundation_point(point) for point in data.get("coefficients", [])]
    from .domain import AdapterStatus

    data["status"] = AdapterStatus(data.get("status", AdapterStatus.VALIDATED.value))
    return FoundationSpec(**data)


def _seal(row: dict[str, Any]) -> SealSpec:
    return SealSpec(**row)


def _coupling(row: dict[str, Any]) -> CouplingSpec:
    return CouplingSpec(**row)


def _load(row: dict[str, Any]) -> LoadSpec:
    return LoadSpec(**row)


def _probe(row: dict[str, Any]) -> ProbeSpec:
    return ProbeSpec(**row)


def _operating_case(row: dict[str, Any]) -> OperatingCase:
    return OperatingCase(**row)


def _decode_engineering(data: dict[str, Any]) -> RotorProject:
    try:
        project = RotorProject(
            name=str(data["name"]),
            reference=str(data.get("reference", "")),
            line=str(data.get("line", "")),
            frame=str(data.get("frame", "")),
            poles=int(data.get("poles", 2)),
            description=str(data.get("description", "")),
            lateral_convention=LateralConvention(data.get("lateral_convention", LateralConvention.ROSS_NATIVE.value)),
            probe_angle_contract=ProbeAngleContract(data.get("probe_angle_contract", ProbeAngleContract.DEGREES.value)),
            materials={name: _material(row) for name, row in data.get("materials", {}).items()},
            shaft_sections=[_shaft(row) for row in data.get("shaft_sections", [])],
            bearings=[_bearing(row) for row in data.get("bearings", [])],
            distributed_masses=[_distributed_mass(row) for row in data.get("distributed_masses", [])],
            point_masses=[_point_mass(row) for row in data.get("point_masses", [])],
            disks=[_disk(row) for row in data.get("disks", [])],
            supports=[_support(row) for row in data.get("supports", [])],
            foundations=[_foundation(row) for row in data.get("foundations", [])],
            seals=[_seal(row) for row in data.get("seals", [])],
            couplings=[_coupling(row) for row in data.get("couplings", [])],
            loads=[_load(row) for row in data.get("loads", [])],
            probes=[_probe(row) for row in data.get("probes", [])],
            operating_cases=[_operating_case(row) for row in data.get("operating_cases", [])],
            warnings=[str(item) for item in data.get("warnings", [])],
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ProjectFormatError(f"Invalid ROSS Studio engineering payload: {exc}") from exc
    if not project.materials:
        project.materials = {"Steel": MaterialSpec()}
    if not project.operating_cases:
        project.operating_cases = [OperatingCase()]
    project.validate()
    return project


def load_project(path: str | Path) -> ProjectModel:
    source = Path(path)
    try:
        payload = json.loads(source.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ProjectFormatError(f"Cannot read ROSS Studio project {source}: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("format") != FORMAT_NAME:
        raise ProjectFormatError(f"{source.name} is not a {FORMAT_NAME} file.")
    schema = payload.get("schema_version")
    if schema != SCHEMA_VERSION:
        raise ProjectFormatError(
            f"Unsupported ROSS Studio project schema {schema!r}; supported schema is {SCHEMA_VERSION}."
        )
    meta = payload.get("project_meta") or {}
    raw_engineering = payload.get("engineering")
    if raw_engineering is None:
        return ProjectModel(
            name=str(meta.get("name", "Untitled")),
            description=str(meta.get("description", "")),
            created=str(meta.get("created", "ROSS Studio project")),
            modified=str(meta.get("modified", "ROSS Studio project")),
            segments=[],
            engineering=None,
            total_mass_kg=0.0,
            disks=0,
            bearings=0,
            supports=0,
        )
    if not isinstance(raw_engineering, dict):
        raise ProjectFormatError("engineering must be an object or null.")
    engineering = _decode_engineering(raw_engineering)
    model = ProjectModel.from_engineering(engineering)
    model.created = str(meta.get("created", model.created))
    model.modified = str(meta.get("modified", model.modified))
    model.name = str(meta.get("name", model.name))
    model.description = str(meta.get("description", model.description))
    return model


def new_project_model() -> ProjectModel:
    now = datetime.now().strftime("%b %d, %Y  %H:%M")
    return ProjectModel(
        name="Untitled",
        description="",
        created=now,
        modified=now,
        speed_rpm=0,
        speed_min_rpm=0,
        speed_max_rpm=0,
        frequency_hz=0.0,
        line="",
        frame="",
        poles=2,
        material="",
        total_mass_kg=0.0,
        dof=0,
        disks=0,
        bearings=0,
        supports=0,
        segments=[],
        engineering=None,
    )


__all__ = [
    "FORMAT_NAME", "SCHEMA_VERSION", "NATIVE_EXTENSION", "ProjectFormatError",
    "load_project", "new_project_model", "project_fingerprint", "save_project",
]
