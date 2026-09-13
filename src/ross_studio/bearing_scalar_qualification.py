import numpy as np
import ross as rs
from ross_studio.app import RossStudioWindow
from ross_studio.domain import RotorProject, ShaftSection, BearingSpec
from ross_studio.models import ProjectModel
from ross_studio.project_file_controller import ProjectFileController
from ross_studio.project_file_service import ProjectOpenResult
from ross_studio.project_io import save_project
from ross_studio.ross_backend import RossBackend


from PySide6.QtWidgets import QApplication
from tempfile import TemporaryDirectory
from pathlib import Path


def run_scalar_bearing_case(model, tmp_path):
    app = QApplication.instance() or QApplication([])
    if model == 'BallBearingElement':
        size_key,count_key,native_size,native_count='d_balls_mm','n_balls','d_balls','n_balls'
    elif model == 'RollerBearingElement':
        size_key,count_key,native_size,native_count='roller_length_mm','n_rollers','l_rollers','n_rollers'
    else:
        raise ValueError(f'Unsupported qualification model {model}')
    p=RotorProject(name='scalar display',shaft_sections=[ShaftSection(1,500.,40.,fe_elements=4)],
        bearings=[BearingSpec('L',0.,kxx=1e7,kyy=1e7,cxx=100.,cyy=100.),BearingSpec('R',500.,kxx=2e7,kyy=3e7,cxx=200.,cyy=300.)])
    window=RossStudioWindow()
    try:
        controller=ProjectFileController(window)
        controller._replace_project(ProjectOpenResult(ProjectModel.from_engineering(p),tmp_path/'fixture.rossproj',None,'qualification',False),clean=False)
        window._refresh_bearing_page(selected_class=model)
        values={size_key:23.456789,count_key:9,'static_load_n':1234.56789,'contact_angle_deg':13.456789}
        for key,value in values.items():window.bearing_page.input_panel.fields[key].setValue(value)
        window._calculate_bearing()
        assert window.bearing_calculation is not None
        expected=getattr(rs,model)(n=0,**{native_size:.023456789,native_count:9},fs=1234.56789,alpha=13.456789*np.pi/180)
        window._apply_bearing()
        assert p.bearings[0].ross_class==model
        applied=RossBackend().build_rotor(p).rotor.bearing_elements[0]
        assert type(applied).__name__==model
        np.testing.assert_allclose(applied.K(123.456),expected.K(123.456),rtol=1e-12,atol=1e-12)
        np.testing.assert_allclose(applied.C(123.456),expected.C(123.456),rtol=1e-12,atol=1e-12)
        assert window.bearing_page.kc_table.rowCount()==1
        assert window.bearing_page.kc_table.item(0,1).text()==f'{expected.kxx[0]:.2e}'
        saved=save_project(window.project,tmp_path/'saved.rossproj')
        assert controller.open_path(saved)
        assert window.bearing_page.kc_table.rowCount()==1
        assert window.bearing_page.kc_table.item(0,1).text()==f'{expected.kxx[0]:.2e}'
        reopened=RossBackend().build_rotor(window.project.engineering).rotor.bearing_elements[0]
        np.testing.assert_array_equal(reopened.K(123.456),applied.K(123.456))
        np.testing.assert_array_equal(reopened.C(123.456),applied.C(123.456))
        return {'status':'PASS','model':model,'kxx':float(expected.kxx[0]),'cxx':float(expected.cxx[0]),
                'scope':'GUI input, native K/C at 123.456 rad/s, Apply and controller reopen display; no complete solver/result journey'}
    finally:
        window.close()
        window.deleteLater()
        QApplication.instance().processEvents()


def run_scalar_bearing_qualification():
    with TemporaryDirectory() as directory:
        cases=[run_scalar_bearing_case(model,Path(directory)) for model in ('BallBearingElement','RollerBearingElement')]
    return {'status':'PASS','ross_version':rs.__version__,'cases':cases,
            'feature_status':'GAP: complete solver/result journey and remaining bearing models pending'}
