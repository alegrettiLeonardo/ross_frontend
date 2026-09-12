from __future__ import annotations

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one exact match, found {count}: {old[:120]!r}")
    target.write_text(text.replace(old, new), encoding="utf-8")


def replace_between(path: str, start: str, end: str, replacement: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    i = text.find(start)
    if i < 0:
        raise RuntimeError(f"{path}: start marker not found: {start!r}")
    j = text.find(end, i)
    if j < 0:
        raise RuntimeError(f"{path}: end marker not found: {end!r}")
    target.write_text(text[:i] + replacement + text[j:], encoding="utf-8")


# Preserve the 0.21 route-introduction phase while keeping the 0.30 extensions in its note.
replace(
    "src/ross_studio/page_registry.py",
    '        "analysis.time_frequency", "analysis", title="Time & Frequency", implementation_phase="0.30.0", operational=True,\n',
    '        "analysis.time_frequency", "analysis", title="Time & Frequency", implementation_phase="0.21.0", operational=True,\n',
)

# AMB outputs are a conditional extension of native TimeResponseResults.  Do not advertise
# them on ordinary non-AMB time responses where ROSS correctly has no AMB output methods.
replace(
    "src/ross_studio/time_frequency_native.py",
    '''TIME_PLOT_LABELS = {\n    "time_1d": "Time Response · probes",\n    "orbit_2d": "Orbit · selected node",\n    "orbits_3d": "Orbits · all nodes 3D",\n    "dfft": "DFFT · probes",\n    "amb_disps": "AMB · sensor displacements",\n    "amb_currents": "AMB · control currents",\n    "amb_forces": "AMB · magnetic forces",\n}\n''',
    '''TIME_PLOT_LABELS = {\n    "time_1d": "Time Response · probes",\n    "orbit_2d": "Orbit · selected node",\n    "orbits_3d": "Orbits · all nodes 3D",\n    "dfft": "DFFT · probes",\n}\n\nAMB_TIME_PLOT_LABELS = {\n    "amb_disps": "AMB · sensor displacements",\n    "amb_currents": "AMB · control currents",\n    "amb_forces": "AMB · magnetic forces",\n}\n''',
)
replace(
    "src/ross_studio/time_frequency_native.py",
    '''__all__ = [\n    "ClearanceNativeCatalog",\n''',
    '''__all__ = [\n    "AMB_TIME_PLOT_LABELS",\n    "ClearanceNativeCatalog",\n''',
)
replace(
    "src/ross_studio/pages/time_frequency_workspace.py",
    '''from ..time_frequency_native import (\n    ClearanceNativeCatalog,\n''',
    '''from ..time_frequency_native import (\n    AMB_TIME_PLOT_LABELS,\n    ClearanceNativeCatalog,\n''',
)
replace(
    "src/ross_studio/pages/time_frequency_workspace.py",
    '''        self.tr_output = QComboBox()\n        for key, label in TIME_PLOT_LABELS.items(): self.tr_output.addItem(label, key)\n        self.tr_node = self._spin(0, 0, 100000)\n''',
    '''        self.tr_output = QComboBox()\n        for key, label in TIME_PLOT_LABELS.items():\n            self.tr_output.addItem(label, key)\n        engineering = self._engineering()\n        if engineering is not None and any(\n            bearing.ross_class == "MagneticBearingElement" for bearing in engineering.bearings\n        ):\n            for key, label in AMB_TIME_PLOT_LABELS.items():\n                self.tr_output.addItem(label, key)\n        self.tr_node = self._spin(0, 0, 100000)\n''',
)

# 0.30 intentionally promotes native MagneticBearingElement; THD remains separately owned.
replace_between(
    "tests/test_bearing_studio_090.py",
    "def test_thd_and_amb_are_not_silently_enabled_by_general_service() -> None:\n",
    "def test_qt_bearing_studio_hides_direct_kc_as_calculation_model_but_preserves_imported_kc(qtbot) -> None:\n",
    '''def test_thd_models_remain_separately_owned_by_their_native_services() -> None:\n    project = load_irdin_project(FIXTURE)\n    service = BearingStudioService()\n    for ross_class in ("PlainJournal", "TiltingPad", "ThrustPad", "SqueezeFilmDamper"):\n        with pytest.raises(Exception):\n            service.calculate(project, 0, ross_class, {})\n\n\n''',
)
replace(
    "tests/test_bearing_studio_inline_ui_0141.py",
    '''    qtbot.mouseClick(page.type_buttons["amb"], Qt.MouseButton.LeftButton)\n    assert window._selected_bearing_class() == "MagneticBearingElement"\n    assert not page.calculate_button.isEnabled()\n    assert "blocked" in page.input_panel.description.text().lower()\n    assert window.project.engineering == original\n''',
    '''    qtbot.mouseClick(page.type_buttons["amb"], Qt.MouseButton.LeftButton)\n    assert window._selected_bearing_class() == "MagneticBearingElement"\n    assert page.calculate_button.isEnabled()\n    assert {"speed_rpm", "g0_mm", "i0_a", "ag_mm2", "nw", "kp_pid", "kd_pid", "ki_pid"} <= set(\n        page.input_panel.fields\n    )\n    assert "native ross active magnetic bearing" in page.input_panel.description.text().lower()\n    assert window.project.engineering == original\n''',
)
replace(
    "tests/test_engineering_080.py",
    '''    amb = catalog.entries(BearingGroup.AMB)[0]\n    assert amb["status"] == AdapterStatus.BLOCKED.value\n''',
    '''    amb = catalog.entries(BearingGroup.AMB)[0]\n    assert amb["status"] == AdapterStatus.VALIDATED.value\n    assert amb["can_execute"] is True\n''',
)
replace(
    "tests/test_foundation_project_io_024.py",
    '''def test_foundation_schema_is_v2_and_native_saves_use_v2(tmp_path: Path) -> None:\n    assert SCHEMA_VERSION == 2\n    model = load_reference_project_model()\n    target = save_project(model, tmp_path / "schema2.rossproj")\n    payload = json.loads(target.read_text(encoding="utf-8"))\n    assert payload["format"] == FORMAT_NAME\n    assert payload["schema_version"] == 2\n    assert payload["engineering"]["foundations"] == []\n''',
    '''def test_foundation_schema_is_v3_and_native_saves_use_v3(tmp_path: Path) -> None:\n    assert SCHEMA_VERSION == 3\n    model = load_reference_project_model()\n    target = save_project(model, tmp_path / "schema3.rossproj")\n    payload = json.loads(target.read_text(encoding="utf-8"))\n    assert payload["format"] == FORMAT_NAME\n    assert payload["schema_version"] == 3\n    assert payload["engineering"]["foundations"] == []\n''',
)
replace(
    "tests/test_interactive_workspace_012.py",
    '''        "SqueezeFilmDamper",\n    }\n''',
    '''        "SqueezeFilmDamper",\n        "MagneticBearingElement",\n    }\n''',
)
replace(
    "tests/test_interactive_workspace_012.py",
    '''    assert rows["MagneticBearingElement"]["status"] == AdapterStatus.BLOCKED.value\n    assert rows["MagneticBearingElement"]["can_execute"] is False\n''',
    '''    assert rows["MagneticBearingElement"]["status"] == AdapterStatus.VALIDATED.value\n    assert rows["MagneticBearingElement"]["can_execute"] is True\n''',
)

# Old GUI fixtures now provide the second physical coupling station required by native ROSS.
replace(
    "tests/test_model_builder_complete_desktop_014.py",
    '''            self.value = coupling or CouplingSpec("GUI-COUPLING", 1420.250, 2.0, 3.0, 0.04, 0.05, kr_z_n_m_rad=2.0e6)\n''',
    '''            self.value = coupling or CouplingSpec(\n                "GUI-COUPLING", 1420.250, 2.0, 3.0, 0.04, 0.05, length_mm=0.001, kr_z_n_m_rad=2.0e6\n            )\n''',
)
replace_between(
    "tests/test_model_builder_entities_014.py",
    "def test_legacy_single_station_coupling_is_transactional_but_not_silently_mapped_to_two_node_element() -> None:\n",
    "def test_load_transaction_preserves_metadata_and_exact_analysis_station() -> None:\n",
    '''def test_legacy_single_station_coupling_fails_closed_before_transaction() -> None:\n    _rs, project, service = _project_and_service()\n    baseline = deepcopy(project)\n    record = CouplingSpec(\n        "COUPLING-014",\n        1300.654,\n        left_mass_kg=3.0,\n        right_mass_kg=4.0,\n        left_ip_kg_m2=0.05,\n        right_ip_kg_m2=0.06,\n        kt_x_n_m=1.0e7,\n        kt_y_n_m=1.1e7,\n        kt_z_n_m=1.2e7,\n        kr_x_n_m_rad=2.0e6,\n        kr_y_n_m_rad=2.1e6,\n        kr_z_n_m_rad=2.2e6,\n        ct_x_n_s_m=100.0,\n        ct_y_n_s_m=110.0,\n        ct_z_n_s_m=120.0,\n    )\n\n    with pytest.raises(EngineeringError, match="positive length|single-station|COUPLING_TWO_NODE_REQUIRED"):\n        service.preview_add(project, "coupling", record)\n    assert project == baseline\n\n\n''',
)

# AMB navigation is intentionally operational in 0.30.
replace_between(
    "tests/test_navigation_architecture_017.py",
    "def test_amb_route_is_visible_but_locked() -> None:\n",
    "def test_foundation_has_distinct_owner_from_flexible_support() -> None:\n",
    '''def test_amb_route_is_visible_and_operational_030() -> None:\n    node = navigation_node("model.bearings.amb")\n    spec = route_spec(node.id)\n    assert node.kind == "route"\n    assert node.locked is False\n    assert spec.owner == "bearing"\n    assert spec.bearing_group == "AMB"\n    assert spec.operational is True\n\n\n''',
)
replace(
    "tests/test_navigation_architecture_017.py",
    '''    assert window.sidebar.route_buttons["model.bearings.amb"].isEnabled() is False\n''',
    '''    assert window.sidebar.route_buttons["model.bearings.amb"].isEnabled() is True\n''',
)

# Seals moved from the legacy rotor editor alias to the dedicated 0.30 Seal Studio.
replace(
    "tests/test_runtime_optional_080.py",
    '''        "supports": 2,\n        "seals": 3,\n        "couplings": 4,\n''',
    '''        "supports": 2,\n        "couplings": 4,\n''',
)
replace(
    "tests/test_runtime_optional_080.py",
    '''    assert not hasattr(window, "bearing_groups_page")\n    assert window.bearing_page.__class__.__module__.endswith("bearing_workspace_page")\n''',
    '''    assert not hasattr(window, "bearing_groups_page")\n\n    window._navigate("seals")\n    assert window.stack.currentWidget().__class__.__module__.endswith("seal_workspace")\n    assert window.stack.count() == 4\n    window._navigate("bearings")\n    assert window.stack.currentWidget() is window.bearing_page\n    assert window.bearing_page.__class__.__module__.endswith("bearing_workspace_page")\n''',
)

replace(
    "tests/test_thd_desktop_010.py",
    '''def test_production_registry_promotes_qualified_thd_and_blocks_amb():\n    registry = RossCapabilityRegistry(rs)\n    for model in THDBearingStudioService.SUPPORTED_CLASSES:\n        status, _reason = registry.effective_status(model)\n        assert status == AdapterStatus.VALIDATED\n    assert registry.effective_status("ThrustPad")[0] == AdapterStatus.VALIDATED\n    assert registry.effective_status("MagneticBearingElement")[0] == AdapterStatus.BLOCKED\n''',
    '''def test_production_registry_promotes_qualified_thd_and_amb():\n    registry = RossCapabilityRegistry(rs)\n    for model in THDBearingStudioService.SUPPORTED_CLASSES:\n        status, _reason = registry.effective_status(model)\n        assert status == AdapterStatus.VALIDATED\n    assert registry.effective_status("ThrustPad")[0] == AdapterStatus.VALIDATED\n    assert registry.effective_status("MagneticBearingElement")[0] == AdapterStatus.VALIDATED\n''',
)
replace(
    "tests/test_thd_desktop_010.py",
    '''    window._open_bearing_group("AMB")\n    assert not window.bearing_page.calculate_button.isEnabled()\n''',
    '''    window._open_bearing_group("AMB")\n    assert window.bearing_page.calculate_button.isEnabled()\n''',
)

replace(
    "tests/test_time_frequency_native_021.py",
    '''def test_time_frequency_workspace_has_six_independent_analysis_tabs(qtbot) -> None:\n''',
    '''def test_time_frequency_workspace_has_eight_native_analysis_tabs_after_030_extensions(qtbot) -> None:\n''',
)
replace(
    "tests/test_time_frequency_native_021.py",
    '''    assert page.tabs.count() == 6\n    assert [page.tabs.tabText(i) for i in range(page.tabs.count())] == [\n        "Frequency Response", "Unbalance Response", "Time Response",\n        "Harmonic Balance", "UCS Map", "Clearance",\n    ]\n''',
    '''    assert page.tabs.count() == 8\n    assert [page.tabs.tabText(i) for i in range(page.tabs.count())] == [\n        "Frequency Response", "Unbalance Response", "Time Response",\n        "Harmonic Balance", "UCS Map", "Clearance", "Faults", "AMB Sensitivity",\n    ]\n''',
)

# Explicit regression guard: AMB-only plots extend, rather than pollute, generic time outputs.
replace(
    "tests/test_ross_native_completion_030.py",
    '''from ross_studio.time_frequency_analysis import TimeResponseRequest, TimeResponseService\n''',
    '''from ross_studio.time_frequency_analysis import TimeResponseRequest, TimeResponseService\nfrom ross_studio.time_frequency_native import AMB_TIME_PLOT_LABELS, TIME_PLOT_LABELS\n''',
)
replace(
    "tests/test_ross_native_completion_030.py",
    '''def test_schema3_round_trip_keeps_native_contracts(tmp_path) -> None:\n''',
    '''def test_amb_time_outputs_extend_the_generic_time_plot_contract() -> None:\n    assert set(TIME_PLOT_LABELS) == {"time_1d", "orbit_2d", "orbits_3d", "dfft"}\n    assert set(AMB_TIME_PLOT_LABELS) == {"amb_disps", "amb_currents", "amb_forces"}\n    assert set(TIME_PLOT_LABELS).isdisjoint(AMB_TIME_PLOT_LABELS)\n\n\ndef test_schema3_round_trip_keeps_native_contracts(tmp_path) -> None:\n''',
)

print("ROSS Studio 0.30 CI alignment patch applied")
