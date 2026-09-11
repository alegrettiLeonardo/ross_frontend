from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("ROSS_STUDIO_DISABLE_WEBENGINE", "1")

from PySide6.QtWidgets import QApplication

from ross_studio.domain import RotorProject, ShaftSection
from ross_studio.ross_backend import RossModelBuilder
from ross_studio.shaft_geometry import GUIDED_SHAFT_GEOMETRIES, ShaftGeometryType, classify_shaft_geometry, tutorial_contract
from ross_studio.shaft_section_dialog import GuidedShaftSectionEditorDialog


def section_for(geometry: ShaftGeometryType) -> ShaftSection:
    data = {
        ShaftGeometryType.SOLID_CYLINDRICAL: (80.0, 80.0, 0.0, 0.0),
        ShaftGeometryType.SOLID_CONICAL: (80.0, 100.0, 0.0, 0.0),
        ShaftGeometryType.HOLLOW_CYLINDRICAL: (80.0, 80.0, 30.0, 30.0),
        ShaftGeometryType.HOLLOW_CONICAL: (80.0, 100.0, 30.0, 30.0),
    }
    odl, odr, idl, idr = data[geometry]
    return ShaftSection(1, 250.0, odl, odr, idl, idr, "Steel", 1)


def main() -> int:
    native_rows: list[dict[str, object]] = []
    for geometry in GUIDED_SHAFT_GEOMETRIES:
        section = section_for(geometry)
        assert classify_shaft_geometry(section) == geometry
        project = RotorProject(name=f"Qualification {geometry.value}", shaft_sections=[section])
        built = RossModelBuilder().build(project, strict=True)
        if built.unresolved_positions_mm:
            raise RuntimeError(f"{geometry.value}: strict builder has unresolved positions {built.unresolved_positions_mm}")
        native = built.rotor.shaft_elements[0]
        if type(native).__name__ != "ShaftElement":
            raise RuntimeError(f"{geometry.value}: expected native ROSS ShaftElement, got {type(native).__name__}")
        row = {
            "type": geometry.value,
            "tutorial_contract": tutorial_contract(geometry),
            "native_class": type(native).__name__,
            "L_m": float(native.L),
            "odl_m": float(native.odl),
            "odr_m": float(native.odr),
            "idl_m": float(native.idl),
            "idr_m": float(native.idr),
        }
        expected = (
            section.od_left_mm / 1000.0,
            section.odr_mm / 1000.0,
            section.id_left_mm / 1000.0,
            section.idr_mm / 1000.0,
        )
        actual = (row["odl_m"], row["odr_m"], row["idl_m"], row["idr_m"])
        if any(abs(float(a) - float(b)) > 1.0e-12 for a, b in zip(actual, expected)):
            raise RuntimeError(f"{geometry.value}: native diameter mapping mismatch actual={actual} expected={expected}")
        native_rows.append(row)

    app = QApplication.instance() or QApplication([])
    dialog = GuidedShaftSectionEditorDialog(section_for(ShaftGeometryType.SOLID_CYLINDRICAL))
    labels = [dialog.geometry.itemText(i) for i in range(dialog.geometry.count())]
    expected_labels = [item.value for item in GUIDED_SHAFT_GEOMETRIES]
    if labels != expected_labels:
        raise RuntimeError(f"Shaft editor type inventory mismatch: {labels}")

    from ross_studio.app import RossStudioWindow

    window = RossStudioWindow()
    table = window.rotor_page.editor_tables["shaft"]
    headers = [table.horizontalHeaderItem(i).text() for i in range(table.columnCount())]
    if "ROSS Shaft Type" not in headers:
        raise RuntimeError(f"Shaft workspace does not expose geometry classification: {headers}")

    payload = {
        "status": "PASS",
        "guided_types": expected_labels,
        "native_realizations": native_rows,
        "gui": {
            "dialog_type_inventory": labels,
            "length_editable": dialog.length.isEnabled(),
            "material_editable": not dialog.material.isReadOnly(),
            "shaft_table_headers": headers,
            "shaft_add_enabled": window.rotor_page.editor_action_buttons["shaft"]["add"].isEnabled(),
            "shaft_delete_enabled": window.rotor_page.editor_action_buttons["shaft"]["delete"].isEnabled(),
        },
        "topology_policy": (
            "Existing physical sections can change among the four guided ROSS shaft geometries. "
            "Section insertion/deletion remains blocked until an explicit downstream absolute-coordinate remapping policy is qualified."
        ),
        "physics_owner": "ross.ShaftElement",
        "scientific_reimplementation": False,
    }
    if payload["gui"]["length_editable"]:
        raise RuntimeError("Existing shaft-section length unexpectedly became editable.")
    if payload["gui"]["shaft_add_enabled"] or payload["gui"]["shaft_delete_enabled"]:
        raise RuntimeError("Shaft topology add/delete gate was unintentionally opened.")

    output = Path("artifacts/shaft_geometry_018_qualification.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    dialog.close()
    window.close()
    app.processEvents()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
