from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import tempfile

import ross
import ross_studio

from .project_file_service import ProjectFileService
from .project_io import load_project, new_project_model, save_project


@dataclass(slots=True, frozen=True)
class FrozenProjectIOResult:
    status: str
    ross_version: str
    ross_studio_version: str
    irdin_sections: int
    irdin_shaft_elements: int
    irdin_bearings: int
    irdin_supports: int
    native_roundtrip_equal: bool
    blank_roundtrip_empty: bool
    dyrobes_model_summary_sections: int
    dyrobes_model_summary_base_elements: int
    dyrobes_model_summary_disks: int
    dyrobes_raw_vendor_cases: int
    dyrobes_raw_vendor_gate: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _resource(name: str) -> Path:
    path = Path(__file__).resolve().parent / "resources" / name
    if not path.is_file():
        raise FileNotFoundError(f"Packaged qualification resource is missing: {path}")
    return path


def run_frozen_project_io_test() -> FrozenProjectIOResult:
    if ross.__version__ != "2.3.0":
        raise RuntimeError(f"ROSS drift detected: expected 2.3.0, got {ross.__version__}")

    service = ProjectFileService()
    irdin_path = _resource("OP-W60-500-60Hz-IC611-P3.txt")
    imported = service.open_path(irdin_path)
    if imported.source_format != "RotorDin / iRdin" or not imported.imported:
        raise AssertionError(f"Unexpected OP-W60 dispatcher route: {imported.source_format}")
    engineering = imported.model.engineering
    if engineering is None:
        raise AssertionError("OP-W60 import lost the engineering domain")
    if imported.model.physical_sections != 15 or imported.model.ross_shaft_elements != 27:
        raise AssertionError("OP-W60 topology changed during frozen import")
    if len(engineering.bearings) != 2 or len(engineering.supports) != 2:
        raise AssertionError("OP-W60 bearing/support inventory changed during frozen import")

    dyrobes_path = _resource("dyrobes_corpus/public_manual/SMASS_6ST_COMP_Sect4_model_summary.rot")
    dyrobes = service.open_path(dyrobes_path)
    dyrobes_engineering = dyrobes.model.engineering
    if dyrobes.source_format != "DyRoBeS" or dyrobes_engineering is None:
        raise AssertionError("Public DyRoBeS MODEL SUMMARY did not use the qualified importer")
    if len(dyrobes_engineering.shaft_sections) != 4:
        raise AssertionError("DyRoBeS corpus shaft topology changed")
    if sum(row.fe_elements for row in dyrobes_engineering.shaft_sections) != 8:
        raise AssertionError("DyRoBeS subelement discretization was not preserved")
    if len(dyrobes_engineering.disks) != 1:
        raise AssertionError("DyRoBeS rigid disk was not preserved")

    manifest_path = _resource("dyrobes_corpus/manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw_entries = [entry for entry in manifest["entries"] if entry.get("raw_vendor_rot") is True]
    raw_gate = str(manifest["raw_vendor_rot_gate"]["status"])

    with tempfile.TemporaryDirectory(prefix="ross-studio-io-") as temp_root:
        root = Path(temp_root)
        native_path = save_project(imported.model, root / "op-w60.rossproj")
        restored = load_project(native_path)
        native_equal = restored.engineering == engineering
        if not native_equal:
            raise AssertionError("Frozen .rossproj round-trip changed the OP-W60 engineering model")

        blank = new_project_model()
        blank_path = save_project(blank, root / "blank.rossproj")
        blank_restored = load_project(blank_path)
        blank_empty = blank_restored.engineering is None and blank_restored.segments == []
        if not blank_empty:
            raise AssertionError("Frozen New/Save/Open invented rotor entities")

    return FrozenProjectIOResult(
        status="PASS",
        ross_version=ross.__version__,
        ross_studio_version=ross_studio.__version__,
        irdin_sections=imported.model.physical_sections,
        irdin_shaft_elements=imported.model.ross_shaft_elements,
        irdin_bearings=len(engineering.bearings),
        irdin_supports=len(engineering.supports),
        native_roundtrip_equal=native_equal,
        blank_roundtrip_empty=blank_empty,
        dyrobes_model_summary_sections=len(dyrobes_engineering.shaft_sections),
        dyrobes_model_summary_base_elements=sum(row.fe_elements for row in dyrobes_engineering.shaft_sections),
        dyrobes_model_summary_disks=len(dyrobes_engineering.disks),
        dyrobes_raw_vendor_cases=len(raw_entries),
        dyrobes_raw_vendor_gate=raw_gate,
    )


__all__ = ["FrozenProjectIOResult", "run_frozen_project_io_test"]
