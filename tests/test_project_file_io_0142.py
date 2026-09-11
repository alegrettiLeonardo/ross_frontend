from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence

from ross_studio.app import RossStudioWindow
from ross_studio.dyrobes_import import DyrobesImportError, load_dyrobes_project
from ross_studio.models import load_reference_project_model
from ross_studio.project_file_controller import ProjectFileController
from ross_studio.project_file_service import ProjectFileService, ProjectOpenError
from ross_studio.project_io import load_project, new_project_model, save_project


ROOT = Path(__file__).parents[1]
IRDIN = ROOT / "src" / "ross_studio" / "resources" / "OP-W60-500-60Hz-IC611-P3.txt"


def test_native_rossproj_roundtrip_is_lossless_for_qualified_op_w60(tmp_path: Path) -> None:
    source = load_reference_project_model()
    target = save_project(source, tmp_path / "op-w60.rossproj")
    restored = load_project(target)

    assert restored.engineering == source.engineering
    assert restored.name == source.name
    assert restored.created == source.created
    assert restored.modified == source.modified
    assert restored.physical_sections == 15
    assert restored.ross_shaft_elements == 27
    assert restored.engineering is not None
    assert len(restored.engineering.bearings) == 2
    assert len(restored.engineering.supports) == 2
    assert len(restored.engineering.point_masses) == 1
    assert restored.engineering.point_masses[0].mass_kg == pytest.approx(34.0)
    assert len(restored.engineering.bearings[0].coefficients) == 11


def test_empty_native_project_roundtrip_does_not_invent_rotor_geometry(tmp_path: Path) -> None:
    blank = new_project_model()
    assert blank.engineering is None
    assert blank.segments == []
    target = save_project(blank, tmp_path / "blank")
    restored = load_project(target)
    assert restored.name == "Untitled"
    assert restored.engineering is None
    assert restored.segments == []


def test_open_dispatcher_imports_real_irdin_resource_and_never_marks_source_as_native() -> None:
    result = ProjectFileService().open_path(IRDIN)
    assert result.source_format == "RotorDin / iRdin"
    assert result.imported is True
    assert result.native_path is None
    assert result.model.name == "OP-W60-500-60Hz-IC611-P3"
    assert result.model.physical_sections == 15
    assert result.model.ross_shaft_elements == 27
    assert result.model.bearings == 2
    assert result.model.supports == 2


def test_imported_irdin_can_be_saved_as_native_without_changing_engineering(tmp_path: Path) -> None:
    result = ProjectFileService().open_path(IRDIN)
    target = ProjectFileService.save_native(result.model, tmp_path / "converted.rossproj")
    restored = load_project(target)
    assert restored.engineering == result.model.engineering


def _dyrobes_summary() -> str:
    return """FileName: C:\\DYROBES\\Example\\SMASS_6ST_COMP_Sect4.rot
***** Unit System = 2 *****
Engineering English Units (s, in, Lbf, Lbm)
MODEL SUMMARY
************************System Parameters************************
1 Shafts
4 Elements
8 SubElements
1 Materials
1 Rigid Disks
0 Unbalances
0 Linear Bearings
5 Stations
20 Degrees of Freedom
*********************** Description Headers************************
JEFFCOTT ROTOR TEST
*************************Material Properties*********************************
1 .28300 .30000E+08 .12000E+08
************************* Shaft Elements*************************************
1 1 .000 9.0000 .0000 6.5000 .0000 6.5000 1
1 2 9.000 9.0000 .0000 6.5000 .0000 6.5000 1
2 1 18.000 9.0000 .0000 6.5000 .0000 6.5000 1
2 2 27.000 9.0000 .0000 6.5000 .0000 6.5000 1
3 1 36.000 9.0000 .0000 6.5000 .0000 6.5000 1
3 2 45.000 9.0000 .0000 6.5000 .0000 6.5000 1
4 1 54.000 9.0000 .0000 6.5000 .0000 6.5000 1
4 2 63.000 9.0000 .0000 6.5000 .0000 6.5000 1
******************************* Rigid Disks ********************************
3 474.00 .00000 .00000 .0000 .0000
****************** Rotor Equivalent Rigid Body Properties ******************
"""


def test_dyrobes_labelled_ascii_model_summary_imports_units_mesh_and_disk(tmp_path: Path) -> None:
    path = tmp_path / "SMASS_6ST_COMP_Sect4.rot"
    path.write_text(_dyrobes_summary(), encoding="utf-8")
    project = load_dyrobes_project(path)

    assert project.reference == "DyRoBeS"
    assert len(project.shaft_sections) == 4
    assert sum(section.fe_elements for section in project.shaft_sections) == 8
    assert project.total_length_mm == pytest.approx(72.0 * 25.4)
    assert project.shaft_sections[0].od_left_mm == pytest.approx(6.5 * 25.4)
    assert project.materials["DyRoBeS Material 1"].density_kg_m3 == pytest.approx(7832.897, rel=2e-3)
    assert len(project.disks) == 1
    assert project.disks[0].position_mm == pytest.approx(36.0 * 25.4)
    assert project.disks[0].mass_kg == pytest.approx(474.0 * 0.45359237)

    result = ProjectFileService().open_path(path)
    assert result.source_format == "DyRoBeS"
    assert result.imported
    assert result.native_path is None
    assert result.model.engineering == project


def test_unknown_raw_dyrobes_layout_fails_closed_instead_of_guessing(tmp_path: Path) -> None:
    path = tmp_path / "unknown.rot"
    path.write_text("Unit System = 2\n1 2 3 4 5 6 7 8 9\n", encoding="utf-8")
    with pytest.raises(DyrobesImportError, match="not yet qualified"):
        load_dyrobes_project(path)
    with pytest.raises(ProjectOpenError, match="not yet qualified"):
        ProjectFileService().open_path(path)


def test_arquivo_menu_and_toolbar_expose_required_commands_and_shortcuts(qtbot, monkeypatch) -> None:
    import ross_studio.file_toolbar as file_toolbar

    calls: list[str] = []
    monkeypatch.setattr(file_toolbar, "_dispatch", calls.append)

    window = RossStudioWindow()
    qtbot.addWidget(window)
    window.show()
    toolbar = window.toolbar

    assert toolbar.file_menu.title() == "Arquivo"
    assert set(toolbar.file_actions) == {"new", "open", "import", "save", "save_as", "exit"}
    assert toolbar.file_actions["new"].shortcut() == QKeySequence(QKeySequence.StandardKey.New)
    assert toolbar.file_actions["open"].shortcut() == QKeySequence(QKeySequence.StandardKey.Open)
    assert toolbar.file_actions["import"].shortcut().toString() == "Ctrl+I"
    assert toolbar.file_actions["save"].shortcut() == QKeySequence(QKeySequence.StandardKey.Save)
    assert toolbar.file_actions["save_as"].shortcut() == QKeySequence(QKeySequence.StandardKey.SaveAs)

    qtbot.mouseClick(toolbar.buttons["new"], Qt.MouseButton.LeftButton)
    qtbot.mouseClick(toolbar.buttons["open"], Qt.MouseButton.LeftButton)
    qtbot.mouseClick(toolbar.buttons["save"], Qt.MouseButton.LeftButton)
    toolbar.file_actions["import"].trigger()
    toolbar.file_actions["save_as"].trigger()
    assert calls == ["new", "open", "save", "import", "save_as"]


def test_controller_open_path_rebuilds_workspace_and_updates_identity(qtbot) -> None:
    window = RossStudioWindow()
    qtbot.addWidget(window)
    window.show()
    controller = ProjectFileController(window)

    assert controller.open_path(IRDIN)
    assert window.project.name == "OP-W60-500-60Hz-IC611-P3"
    assert window.rotor_page.project is window.project
    assert window.bearing_page.project is window.project
    assert window.results_page.project is window.project
    assert window.status.project_label.text() == window.project.name
    assert window.windowTitle().endswith(window.project.name)
    assert controller.state.native_path is None
    assert controller.state.source_format == "RotorDin / iRdin"


def test_controller_new_creates_truthful_empty_workspace(qtbot) -> None:
    window = RossStudioWindow()
    qtbot.addWidget(window)
    window.show()
    controller = ProjectFileController(window)
    assert controller.new()
    assert window.project.name == "Untitled"
    assert window.project.engineering is None
    assert window.project.segments == []
    assert window.rotor_page.project is window.project
    assert window.bearing_page.bearing_selector.count() == 0
