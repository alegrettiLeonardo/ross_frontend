from __future__ import annotations

from copy import deepcopy

import pytest
from PySide6.QtWidgets import QDialog, QMessageBox

from ross_studio.domain import ProbeSpec
from ross_studio.ross_backend import RossModelBuilder
from ross_studio.topology import NodeInsertionService


def test_mesh_cell_edit_uses_strict_transaction_and_refreshes_node_tables(qtbot) -> None:
    pytest.importorskip("ross")
    from ross_studio.app import RossStudioWindow

    window = RossStudioWindow()
    qtbot.addWidget(window)
    page = window.rotor_page
    engineering = window.project.engineering
    assert engineering is not None

    before = deepcopy(engineering)
    row = 7
    old_count = engineering.shaft_sections[row].fe_elements
    page.segment_table.item(row, 6).setText(str(old_count + 2))
    qtbot.wait(1)

    assert engineering != before
    assert engineering.shaft_sections[row].fe_elements == old_count + 2
    assert page.fem_label.text() == f"ROSS ShaftElements  {window.project.ross_shaft_elements}"
    built = RossModelBuilder().build(engineering, strict=True)
    assert built.unresolved_positions_mm == []
    assert page.editor_tables["supports"].item(0, 3).text() == str(
        NodeInsertionService.plan(engineering).node_for(engineering.bearings[engineering.supports[0].bearing_index].position_mm)
    )


def test_shaft_edit_dialog_commits_od_and_mesh_only_after_accept(qtbot, monkeypatch) -> None:
    pytest.importorskip("ross")
    import ross_studio.pages.rotor_model as module
    from ross_studio.app import RossStudioWindow

    class FakeShaftDialog:
        def __init__(self, section, parent=None):
            self.section = section

        def exec(self):
            return QDialog.DialogCode.Accepted

        def changes(self):
            return {
                "od_left_mm": self.section.od_left_mm + 1.0,
                "od_right_mm": self.section.odr_mm + 1.0,
                "id_left_mm": self.section.id_left_mm,
                "id_right_mm": self.section.idr_mm,
                "fe_elements": self.section.fe_elements + 1,
            }

    monkeypatch.setattr(module, "ShaftSectionEditorDialog", FakeShaftDialog)
    window = RossStudioWindow()
    qtbot.addWidget(window)
    page = window.rotor_page
    engineering = window.project.engineering
    assert engineering is not None
    row = 6
    before_length = engineering.shaft_sections[row].length_mm
    before_od = engineering.shaft_sections[row].od_left_mm
    page.editor_tables["shaft"].selectRow(row)

    page._edit_entity("shaft")

    assert engineering.shaft_sections[row].length_mm == before_length
    assert engineering.shaft_sections[row].od_left_mm == pytest.approx(before_od + 1.0)
    assert RossModelBuilder().build(engineering, strict=True).unresolved_positions_mm == []


def test_support_edit_isolated_to_selected_support_and_preserves_bearing_link(qtbot, monkeypatch) -> None:
    pytest.importorskip("ross")
    import ross_studio.pages.rotor_model as module
    from ross_studio.app import RossStudioWindow

    class FakeSupportDialog:
        def __init__(self, support, bearing_name, parent=None):
            self.support = support

        def exec(self):
            return QDialog.DialogCode.Accepted

        def changes(self):
            return {
                "mass_kg": self.support.mass_kg,
                "kxx": self.support.kxx * 1.02,
                "kyy": self.support.kyy,
                "kxy": self.support.kxy,
                "kyx": self.support.kyx,
                "cxx": self.support.cxx,
                "cyy": self.support.cyy,
                "cxy": self.support.cxy,
                "cyx": self.support.cyx,
            }

    monkeypatch.setattr(module, "SupportEditorDialog", FakeSupportDialog)
    window = RossStudioWindow()
    qtbot.addWidget(window)
    page = window.rotor_page
    engineering = window.project.engineering
    assert engineering is not None
    before = deepcopy(engineering.supports)
    before_bearings = deepcopy(engineering.bearings)
    page.editor_tables["supports"].selectRow(1)

    page._edit_entity("supports")

    assert engineering.supports[0] == before[0]
    assert engineering.supports[1].bearing_index == before[1].bearing_index
    assert engineering.supports[1].kxx == pytest.approx(before[1].kxx * 1.02)
    assert engineering.bearings == before_bearings
    built = RossModelBuilder().build(engineering, strict=True)
    assert built.support_link_nodes == {"Support 1": 28, "Support 2": 29}


def test_probe_add_edit_delete_are_exact_node_strict_transactions(qtbot, monkeypatch) -> None:
    pytest.importorskip("ross")
    import ross_studio.pages.rotor_model as module
    from ross_studio.app import RossStudioWindow

    new_probe = ProbeSpec("Engineering P5", 1111.111, 2, 30.0)

    class FakeAddProbeDialog:
        def __init__(self, probe=None, *, total_length_mm, parent=None):
            self.probe = probe

        def exec(self):
            return QDialog.DialogCode.Accepted

        def record(self):
            return new_probe

        def changes(self):
            assert self.probe is not None
            return {
                "name": self.probe.name,
                "position_mm": 1222.222,
                "coordinate": self.probe.coordinate,
                "orientation_deg": 60.0,
            }

    monkeypatch.setattr(module, "ProbeEditorDialog", FakeAddProbeDialog)
    monkeypatch.setattr(
        module.QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )

    window = RossStudioWindow()
    qtbot.addWidget(window)
    page = window.rotor_page
    engineering = window.project.engineering
    assert engineering is not None
    before_count = len(engineering.probes)

    page._add_entity("probes")
    assert len(engineering.probes) == before_count + 1
    assert engineering.probes[-1].name == new_probe.name
    assert NodeInsertionService.plan(engineering).node_for(new_probe.position_mm) is not None
    assert RossModelBuilder().build(engineering, strict=True).unresolved_positions_mm == []
    assert page.editor_tables["probes"].rowCount() == len(engineering.probes)

    page.editor_tables["probes"].selectRow(len(engineering.probes) - 1)
    page._edit_entity("probes")
    assert engineering.probes[-1].position_mm == pytest.approx(1222.222)
    assert engineering.probes[-1].orientation_deg == pytest.approx(60.0)
    assert NodeInsertionService.plan(engineering).node_for(1222.222) is not None

    page.editor_tables["probes"].selectRow(len(engineering.probes) - 1)
    page._delete_entity("probes")
    assert len(engineering.probes) == before_count
    assert all(probe.name != new_probe.name for probe in engineering.probes)
    assert RossModelBuilder().build(engineering, strict=True).unresolved_positions_mm == []


def test_concentrated_mass_is_visible_as_first_class_engineering_body(qtbot) -> None:
    pytest.importorskip("ross")
    from ross_studio.app import RossStudioWindow

    window = RossStudioWindow()
    qtbot.addWidget(window)
    page = window.rotor_page
    engineering = window.project.engineering
    assert engineering is not None
    assert engineering.point_masses

    table = page.editor_tables["disks"]
    bodies = [table.item(row, 1).text() for row in range(table.rowCount())]
    assert "Concentrated mass [Concent]" in bodies
    row = bodies.index("Concentrated mass [Concent]")
    mass = engineering.point_masses[0]
    assert table.item(row, 3).text() == f"{mass.position_mm:g}"
    assert table.item(row, 8).text() == f"{mass.ix_kg_m2:.6g}"
    assert table.item(row, 9).text() == f"{mass.iy_kg_m2:.6g}"
    assert table.item(row, 10).text() == f"{mass.iz_kg_m2:.6g}"
    assert "qualified concentrated DiskElement" in table.item(row, 11).text()
