from __future__ import annotations

from dataclasses import asdict
from enum import Enum
import json
import math
from pathlib import Path
from typing import Any

from ..project_io import ProjectFormatError, _decode_engineering
from .domain import GearConnection, GearModel, GearSpec, MultiRotorProject

FORMAT_NAME = "ROSS Studio MultiRotor Project"
SCHEMA_VERSION = 1
EXTENSION = ".rossmulti"


def _safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ProjectFormatError("MultiRotor project contains a non-finite numeric value.")
        return value
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(k): _safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe(v) for v in value]
    raise ProjectFormatError(f"Unsupported MultiRotor persistence value {type(value).__name__}.")


def save_multirotor_project(project: MultiRotorProject, path: str | Path) -> Path:
    project.validate()
    target = Path(path)
    if target.suffix.casefold() != EXTENSION:
        target = target.with_suffix(EXTENSION)
    payload = {
        "format": FORMAT_NAME,
        "schema_version": SCHEMA_VERSION,
        "name": project.name,
        "rotors": [_safe(asdict(rotor)) for rotor in project.rotors],
        "gears": [_safe(asdict(gear)) for gear in project.gears],
        "connections": [_safe(asdict(connection)) for connection in project.connections],
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(f".{target.name}.tmp")
    temp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temp.replace(target)
    return target


def load_multirotor_project(path: str | Path) -> MultiRotorProject:
    source = Path(path)
    try:
        payload = json.loads(source.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ProjectFormatError(f"Cannot read MultiRotor project {source}: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("format") != FORMAT_NAME:
        raise ProjectFormatError(f"{source.name} is not a {FORMAT_NAME} file.")
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ProjectFormatError(
            f"Unsupported MultiRotor schema {payload.get('schema_version')!r}; supported={SCHEMA_VERSION}."
        )
    try:
        project = MultiRotorProject(
            name=str(payload["name"]),
            rotors=[_decode_engineering(dict(row)) for row in payload.get("rotors", [])],
            gears=[
                GearSpec(**{**dict(row), "model": GearModel(dict(row).get("model", GearModel.SIMPLE.value))})
                for row in payload.get("gears", [])
            ],
            connections=[GearConnection(**dict(row)) for row in payload.get("connections", [])],
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ProjectFormatError(f"Invalid MultiRotor payload: {exc}") from exc
    project.validate()
    return project


__all__ = ["EXTENSION", "FORMAT_NAME", "SCHEMA_VERSION", "load_multirotor_project", "save_multirotor_project"]
