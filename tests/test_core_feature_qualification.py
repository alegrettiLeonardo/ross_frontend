from ross_studio.core_qualification import run_core_qualification


def test_core_gui_adapters_independent_ross_and_reopen():
    result=run_core_qualification().to_dict()
    assert result['status']=='PASS'
    assert len(result['comparisons'])>=50


def test_unit_conversion_matrix_round_trip():
    import numpy as np
    from ross.units import Q_
    cases=[(123.456789,'mm','m',.123456789),
           (1234.56789,'RPM','rad/s',1234.56789*np.pi/30),
           (23.456789,'Hz','rad/s',23.456789*2*np.pi),
           (12345.6789,'N/mm','N/m',12345678.9),
           (123.456789,'N*s/mm','N*s/m',123456.789),
           (12345.6789,'kg*mm**2','kg*m**2',.0123456789),
           (23.456789,'degree','rad',23.456789*np.pi/180),
           (12.3456789,'bar','Pa',1234567.89),
           (23.456789,'degC','kelvin',296.606789)]
    for value,source,target,expected in cases:
        converted=Q_(value,source).to(target)
        np.testing.assert_allclose(converted.m,expected,rtol=1e-13,atol=1e-13,err_msg=f'{source}->{target}')
        np.testing.assert_allclose(converted.to(source).m,value,rtol=1e-13,atol=1e-13)


def test_material_page_commit_and_resize_rejection(qtbot):
    from copy import deepcopy
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication
    from ross_studio.pages.rotor_workspace import RotorModelPage
    from ross_studio.models import ProjectModel
    from ross_studio.domain import RotorProject,ShaftSection,BearingSpec,EngineeringError
    from ross_studio.ross_backend import RossBackend
    import pytest
    p=RotorProject(name='material transaction',shaft_sections=[ShaftSection(1,321.123456,41.,fe_elements=3)],
        bearings=[BearingSpec('L',0.,kxx=1e7,kyy=1e7),BearingSpec('R',321.123456,kxx=1e7,kyy=1e7)])
    page=RotorModelPage(ProjectModel.from_engineering(p));qtbot.addWidget(page)
    page.editor_tables['shaft'].selectRow(0)
    def fill():
        dialog=QApplication.activeModalWidget()
        dialog.density.setValue(7987.654321)
        dialog.young.setValue(198765432100.)
        dialog.poisson.setValue(.298765)
        dialog.accept()
    QTimer.singleShot(0,fill)
    page._edit_material()
    material=RossBackend().build_rotor(p).rotor.shaft_elements[0].material
    assert material.rho==7987.654321
    assert material.E==198765432100.
    assert p.materials["Steel"].poisson==.298765
    # ROSS reconstructs nu from E/G; allow roundoff, not a changed input.
    assert material.Poisson==pytest.approx(.298765,rel=0,abs=2e-16)
    before=deepcopy(p)
    with pytest.raises(EngineeringError,match='outside'):
        page.model_builder.preview_update(p,'shaft',0,{'length_mm':300.})
    assert p==before


def test_small_load_and_inertia_survive_gui_precision(qtbot):
    from ross_studio.model_entity_dialogs import LoadEditorDialog, DiskEditorDialog, PointMassEditorDialog
    dialogs=[LoadEditorDialog(total_length_mm=1000.),DiskEditorDialog(total_length_mm=1000.),PointMassEditorDialog(total_length_mm=1000.)]
    for dialog in dialogs:qtbot.addWidget(dialog)
    load,disk,mass=dialogs
    load.magnitude.setValue(.000123456789)
    disk.id.setValue(.000000123456);disk.ip.setValue(.000000234567)
    mass.ix.setValue(.000000345678);mass.iy.setValue(.000000456789);mass.iz.setValue(.000000567891)
    assert load.record().magnitude==.000123456789
    assert disk.record().id_kg_m2==.000000123456
    assert disk.record().ip_kg_m2==.000000234567
    assert mass.record().ix_kg_m2==.000000345678
    assert mass.record().iy_kg_m2==.000000456789
    assert mass.record().iz_kg_m2==.000000567891
