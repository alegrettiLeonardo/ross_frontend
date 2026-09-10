from __future__ import annotations

import pytest
from PySide6.QtWidgets import QDialog, QMessageBox

from ross_studio.domain import CouplingSpec, DiskSpec, DistributedMassSpec, LoadSpec, PointMassSpec, SealSpec
from ross_studio.ross_backend import RossModelBuilder
from ross_studio.topology import NodeInsertionService


def test_complete_model_builder_toolbar_exposes_only_qualified_actions(qtbot) -> None:
    pytest.importorskip("ross")
    from ross_studio.app import RossStudioWindow

    window = RossStudioWindow()
    qtbot.addWidget(window)
    buttons = window.rotor_page.editor_action_buttons

    assert buttons["shaft"]["edit"].isEnabled()
    assert not buttons["shaft"]["add"].isEnabled()
    assert not buttons["shaft"]["delete"].isEnabled()
    assert buttons["supports"]["edit"].isEnabled()
    assert not buttons["supports"]["add"].isEnabled()
    assert not buttons["supports"]["delete"].isEnabled()
    for key in ("disks", "seals", "couplings", "loads", "probes"):
        assert buttons[key]["add"].isEnabled()
        assert buttons[key]["edit"].isEnabled()
        assert buttons[key]["delete"].isEnabled()
        assert not buttons[key]["import"].isEnabled()
    assert all(not button.isEnabled() for button in buttons["ump"].values())


def test_concent_is_drawn_and_selectable_in_same_composite_disk_index_space(qtbot) -> None:
    pytest.importorskip("ross")
    from ross_studio.app import RossStudioWindow

    window = RossStudioWindow()
    qtbot.addWidget(window)
    page = window.rotor_page
    engineering = window.project.engineering
    assert engineering is not None and engineering.point_masses

    # The sketch is a child of the main stacked workspace. Show the real top-level
    # window so Qt actually delivers its paint event under the offscreen platform.
    window.resize(1400, 850)
    window.show()
    qtbot.wait(25)
    page.sketch.repaint()
    qtbot.wait(10)

    hits = [hit for hit in page.sketch._hits if "[Concent]" in hit.tooltip]
    assert len(hits) == len(engineering.point_masses)
    hit = hits[0]
    expected_index = len(engineering.distributed_masses) + len(engineering.disks)
    assert hit.ref.kind == "disks"
    assert hit.ref.index == expected_index
    assert "Ix =" in hit.tooltip and "Iy =" in hit.tooltip and "Iz =" in hit.tooltip
    assert "qualified concentrated DiskElement" in hit.tooltip

    page.selection.select(hit.ref)
    qtbot.wait(1)
    assert page.editor_tables["disks"].currentRow() == expected_index


def test_mass_workspace_adds_all_three_body_types_transactionally(qtbot, monkeypatch) -> None:
    pytest.importorskip("ross")
    import ross_studio.pages.rotor_model as module
    from ross_studio.app import RossStudioWindow

    kinds = iter(("distributed_mass", "disk", "point_mass"))

    class FakeChooser:
        def __init__(self, parent=None):
            self.kind = next(kinds)
        def exec(self):
            return QDialog.DialogCode.Accepted
        def selected_kind(self):
            return self.kind

    class FakeDistributed:
        def __init__(self, mass=None, *, total_length_mm, parent=None):
            self.value = mass or DistributedMassSpec("GUI-MASSAS", 1010.125, 30.0, 9.0, 160.0, 20.0)
        def exec(self):
            return QDialog.DialogCode.Accepted
        def record(self):
            return self.value
        def changes(self):
            record = self.value
            return {name: getattr(record, name) for name in (
                "name", "start_mm", "length_mm", "mass_kg", "od_mm", "id_mm", "is_package", "ump_enabled", "ump_value"
            )}

    class FakeDisk:
        def __init__(self, disk=None, *, total_length_mm, parent=None):
            self.value = disk or DiskSpec("GUI-DISK", 1110.250, 8.0, 0.03, 0.06)
        def exec(self):
            return QDialog.DialogCode.Accepted
        def record(self):
            return self.value
        def changes(self):
            record = self.value
            return {name: getattr(record, name) for name in ("name", "position_mm", "mass_kg", "id_kg_m2", "ip_kg_m2")}

    class FakePoint:
        def __init__(self, mass=None, *, total_length_mm, parent=None):
            self.value = mass or PointMassSpec("GUI-CONCENT", 1210.375, 7.0, 0.011, 0.022, 0.033)
        def exec(self):
            return QDialog.DialogCode.Accepted
        def record(self):
            return self.value
        def changes(self):
            record = self.value
            return {name: getattr(record, name) for name in (
                "name", "position_mm", "mass_kg", "ix_kg_m2", "iy_kg_m2", "iz_kg_m2"
            )}

    monkeypatch.setattr(module, "MassTypeDialog", FakeChooser)
    monkeypatch.setattr(module, "DistributedMassEditorDialog", FakeDistributed)
    monkeypatch.setattr(module, "DiskEditorDialog", FakeDisk)
    monkeypatch.setattr(module, "PointMassEditorDialog", FakePoint)

    window = RossStudioWindow()
    qtbot.addWidget(window)
    page = window.rotor_page
    engineering = window.project.engineering
    assert engineering is not None
    before = (len(engineering.distributed_masses), len(engineering.disks), len(engineering.point_masses))

    page._add_entity("disks")
    page._add_entity("disks")
    page._add_entity("disks")

    assert len(engineering.distributed_masses) == before[0] + 1
    assert len(engineering.disks) == before[1] + 1
    assert len(engineering.point_masses) == before[2] + 1
    plan = NodeInsertionService.plan(engineering)
    assert plan.node_for(engineering.distributed_masses[-1].center_mm) is not None
    assert plan.node_for(engineering.disks[-1].position_mm) is not None
    assert plan.node_for(engineering.point_masses[-1].position_mm) is not None
    built = RossModelBuilder().build(engineering, strict=True)
    assert built.unresolved_positions_mm == []
    assert any(item.name == "GUI-CONCENT" for item in built.equivalent_point_masses)


def test_seal_coupling_and_load_gui_add_delete_use_strict_transactions(qtbot, monkeypatch) -> None:
    pytest.importorskip("ross")
    import ross_studio.pages.rotor_model as module
    from ross_studio.app import RossStudioWindow

    class FakeSeal:
        def __init__(self, seal=None, *, total_length_mm, parent=None):
            self.value = seal or SealSpec("GUI-SEAL", 1320.125, 1.0e6, 1.1e6, 100.0, 110.0, -2.0e5, 2.1e5, -20.0, 21.0)
        def exec(self): return QDialog.DialogCode.Accepted
        def record(self): return self.value
        def changes(self):
            return {name: getattr(self.value, name) for name in ("name", "position_mm", "kxx", "kyy", "kxy", "kyx", "cxx", "cyy", "cxy", "cyx")}

    class FakeCoupling:
        def __init__(self, coupling=None, *, total_length_mm, parent=None):
            self.value = coupling or CouplingSpec("GUI-COUPLING", 1420.250, 2.0, 3.0, 0.04, 0.05, kr_z_n_m_rad=2.0e6)
        def exec(self): return QDialog.DialogCode.Accepted
        def record(self): return self.value
        def changes(self):
            return {name: getattr(self.value, name) for name in (
                "name", "position_mm", "left_mass_kg", "right_mass_kg", "left_ip_kg_m2", "right_ip_kg_m2",
                "kt_x_n_m", "kt_y_n_m", "kt_z_n_m", "kr_x_n_m_rad", "kr_y_n_m_rad", "kr_z_n_m_rad",
                "ct_x_n_s_m", "ct_y_n_s_m", "ct_z_n_s_m"
            )}

    class FakeLoad:
        def __init__(self, load=None, *, total_length_mm, parent=None):
            self.value = load or LoadSpec("GUI-LOAD", "harmonic", 1520.375, 100.0, 15.0, {"order": 1})
        def exec(self): return QDialog.DialogCode.Accepted
        def record(self): return self.value
        def changes(self):
            return {
                "name": self.value.name, "kind": self.value.kind, "position_mm": self.value.position_mm,
                "magnitude": self.value.magnitude, "phase_deg": self.value.phase_deg,
                "metadata": dict(self.value.metadata),
            }

    monkeypatch.setattr(module, "SealEditorDialog", FakeSeal)
    monkeypatch.setattr(module, "CouplingEditorDialog", FakeCoupling)
    monkeypatch.setattr(module, "LoadEditorDialog", FakeLoad)
    monkeypatch.setattr(module.QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes)

    window = RossStudioWindow()
    qtbot.addWidget(window)
    page = window.rotor_page
    engineering = window.project.engineering
    assert engineering is not None

    for key, collection_name in (("seals", "seals"), ("couplings", "couplings"), ("loads", "loads")):
        before = len(getattr(engineering, collection_name))
        page._add_entity(key)
        collection = getattr(engineering, collection_name)
        assert len(collection) == before + 1
        record = collection[-1]
        assert NodeInsertionService.plan(engineering).node_for(record.position_mm) is not None
        page.editor_tables[key].selectRow(len(collection) - 1)
        page._delete_entity(key)
        assert len(getattr(engineering, collection_name)) == before

    assert RossModelBuilder().build(engineering, strict=True).unresolved_positions_mm == []
