from __future__ import annotations

import pytest

from ross_studio.domain import EngineeringError, RotorProject, ShaftSection
from ross_studio.shaft_geometry import (
    GUIDED_SHAFT_GEOMETRIES,
    ShaftGeometryType,
    classify_shaft_geometry,
    guided_diameters,
)


def _section(geometry: ShaftGeometryType) -> ShaftSection:
    values = {
        ShaftGeometryType.SOLID_CYLINDRICAL: (80.0, 80.0, 0.0, 0.0),
        ShaftGeometryType.SOLID_CONICAL: (80.0, 100.0, 0.0, 0.0),
        ShaftGeometryType.HOLLOW_CYLINDRICAL: (80.0, 80.0, 30.0, 30.0),
        ShaftGeometryType.HOLLOW_CONICAL: (80.0, 100.0, 30.0, 30.0),
    }
    odl, odr, idl, idr = values[geometry]
    return ShaftSection(
        section=1,
        length_mm=250.0,
        od_left_mm=odl,
        od_right_mm=odr,
        id_left_mm=idl,
        id_right_mm=idr,
        material="Steel",
        fe_elements=1,
    )


def test_guided_shaft_inventory_matches_ross_tutorial_names() -> None:
    assert tuple(item.value for item in GUIDED_SHAFT_GEOMETRIES) == (
        "Solid cylindrical shaft element",
        "Solid conical shaft element",
        "Hollow cylindrical shaft element",
        "Hollow conical shaft element",
    )


def test_four_guided_geometries_classify_exactly() -> None:
    for geometry in GUIDED_SHAFT_GEOMETRIES:
        section = _section(geometry)
        section.validate()
        assert classify_shaft_geometry(section) == geometry


def test_guided_diameters_enforce_tutorial_contracts_without_reimplementing_physics() -> None:
    assert guided_diameters(
        ShaftGeometryType.SOLID_CYLINDRICAL,
        od_left_mm=80.0,
        od_right_mm=95.0,
        id_left_mm=20.0,
        id_right_mm=10.0,
    ) == pytest.approx((80.0, 80.0, 0.0, 0.0))

    assert guided_diameters(
        ShaftGeometryType.SOLID_CONICAL,
        od_left_mm=80.0,
        od_right_mm=100.0,
        id_left_mm=20.0,
        id_right_mm=10.0,
    ) == pytest.approx((80.0, 100.0, 0.0, 0.0))

    assert guided_diameters(
        ShaftGeometryType.HOLLOW_CYLINDRICAL,
        od_left_mm=80.0,
        od_right_mm=95.0,
        id_left_mm=30.0,
        id_right_mm=10.0,
    ) == pytest.approx((80.0, 80.0, 30.0, 30.0))

    assert guided_diameters(
        ShaftGeometryType.HOLLOW_CONICAL,
        od_left_mm=80.0,
        od_right_mm=100.0,
        id_left_mm=30.0,
        id_right_mm=10.0,
    ) == pytest.approx((80.0, 100.0, 30.0, 30.0))

    with pytest.raises(EngineeringError, match="requires different left/right outer diameters"):
        guided_diameters(
            ShaftGeometryType.SOLID_CONICAL,
            od_left_mm=80.0,
            od_right_mm=80.0,
            id_left_mm=0.0,
            id_right_mm=0.0,
        )
    with pytest.raises(EngineeringError, match="requires a positive inner diameter"):
        guided_diameters(
            ShaftGeometryType.HOLLOW_CYLINDRICAL,
            od_left_mm=80.0,
            od_right_mm=80.0,
            id_left_mm=0.0,
            id_right_mm=0.0,
        )


def test_strict_builder_realizes_each_guided_type_as_native_ross_shaft_element() -> None:
    pytest.importorskip("ross")
    from ross_studio.ross_backend import RossModelBuilder

    for geometry in GUIDED_SHAFT_GEOMETRIES:
        section = _section(geometry)
        project = RotorProject(name=f"shaft-{geometry.name.lower()}", shaft_sections=[section])
        built = RossModelBuilder().build(project, strict=True)
        assert built.unresolved_positions_mm == []
        assert len(built.rotor.shaft_elements) == 1
        native = built.rotor.shaft_elements[0]
        assert type(native).__name__ == "ShaftElement"
        assert float(native.odl) == pytest.approx(section.od_left_mm / 1000.0)
        assert float(native.odr) == pytest.approx(section.odr_mm / 1000.0)
        assert float(native.idl) == pytest.approx(section.id_left_mm / 1000.0)
        assert float(native.idr) == pytest.approx(section.idr_mm / 1000.0)


def test_shaft_editor_exposes_exact_four_guided_types_and_preserves_transaction_contract(qtbot) -> None:
    pytest.importorskip("ross")
    from ross_studio.shaft_section_dialog import GuidedShaftSectionEditorDialog

    section = _section(ShaftGeometryType.SOLID_CYLINDRICAL)
    dialog = GuidedShaftSectionEditorDialog(section)
    qtbot.addWidget(dialog)

    labels = tuple(dialog.geometry.itemText(i) for i in range(dialog.geometry.count()))
    assert labels == GuidedShaftSectionEditorDialog.guided_labels()
    assert not dialog.length.isEnabled()
    assert dialog.material.isReadOnly()

    index = dialog.geometry.findData(ShaftGeometryType.HOLLOW_CONICAL.value)
    assert index >= 0
    dialog.geometry.setCurrentIndex(index)
    dialog.od_left.setValue(80.0)
    dialog.od_right.setValue(100.0)
    dialog.id_left.setValue(30.0)
    changes = dialog.changes()
    assert changes["od_left_mm"] == pytest.approx(80.0)
    assert changes["od_right_mm"] == pytest.approx(100.0)
    assert changes["id_left_mm"] == pytest.approx(30.0)
    assert changes["id_right_mm"] == pytest.approx(30.0)


def test_shaft_workspace_shows_guided_type_without_changing_legacy_mesh_columns(qtbot) -> None:
    pytest.importorskip("ross")
    from ross_studio.app import RossStudioWindow

    window = RossStudioWindow()
    qtbot.addWidget(window)
    table = window.rotor_page.editor_tables["shaft"]
    headers = [table.horizontalHeaderItem(i).text() for i in range(table.columnCount())]
    assert headers[:9] == [
        "Section",
        "Length (mm)",
        "OD Left (mm)",
        "OD Right (mm)",
        "ID Left (mm)",
        "ID Right (mm)",
        "Base FE Elements",
        "Effective ROSS Elements",
        "Material",
    ]
    assert headers[-1] == "ROSS Shaft Type"
    # Existing FE mesh automation remains byte-compatible at columns 6/7.
    assert table.item(0, 6).text().isdigit()
    assert table.item(0, 7).text().isdigit()
    assert table.item(0, table.columnCount() - 1).text()
