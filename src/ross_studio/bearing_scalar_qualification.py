import numpy as np
import ross as rs
from ross_studio.app import RossStudioWindow
from ross_studio.domain import RotorProject, ShaftSection, BearingSpec, DiskSpec, LoadSpec, ProbeSpec, OperatingCase
from ross_studio.models import ProjectModel
from ross_studio.project_file_controller import ProjectFileController
from ross_studio.project_file_service import ProjectOpenResult
from ross_studio.project_io import save_project
from ross_studio.ross_backend import RossBackend


from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from ross_studio.analysis_pipeline import AnalysisPipelineService, AnalysisPolicy
from ross_studio.solver_console import SolverConsole
from tempfile import TemporaryDirectory
from pathlib import Path


def _run_window_analysis(window):
    """Invoke the real application handler; only reduce the requested grid size."""
    errors=[]
    watch=QTimer();watch.setInterval(20)
    timeout=QTimer();timeout.setSingleShot(True)
    def configure():
        console=QApplication.activeModalWidget()
        if not isinstance(console,SolverConsole):
            errors.append('Expected the real SolverConsole')
            if console:console.reject()
            return
        console.service=AnalysisPipelineService(policy=AnalysisPolicy(
            modal_num_modes=12,campbell_frequencies=4,campbell_points=7,response_points=7))
        def finish():
            if console._thread is None:
                if console.analysis_result is None:errors.append(console.status_detail.text())
                console.open_results.click() if console.analysis_result is not None else console.reject()
        def expired():
            errors.append('Native GUI analysis exceeded 120 s')
            console._stop()
        watch.timeout.connect(finish);timeout.timeout.connect(expired)
        watch.start();timeout.start(120000)
    QTimer.singleShot(0,configure)
    try:
        window.run_analysis()
    finally:
        watch.stop();timeout.stop()
    assert not errors,errors
    assert window.results_page.result is not None
    assert window.stack.currentWidget() is window.results_page
    return window.results_page.result


def run_scalar_bearing_case(model, tmp_path):
    app = QApplication.instance() or QApplication([])
    if model == 'BallBearingElement':
        size_key,count_key,native_size,native_count='d_balls_mm','n_balls','d_balls','n_balls'
    elif model == 'RollerBearingElement':
        size_key,count_key,native_size,native_count='roller_length_mm','n_rollers','l_rollers','n_rollers'
    elif model == 'CylindricalBearing':
        pass
    else:
        raise ValueError(f'Unsupported qualification model {model}')
    p=RotorProject(name='scalar display',shaft_sections=[ShaftSection(1,500.,40.,fe_elements=4)],
        bearings=[BearingSpec('L',0.,kxx=1e7,kyy=1e7,cxx=100.,cyy=100.),BearingSpec('R',500.,kxx=2e7,kyy=3e7,cxx=200.,cyy=300.)],
        disks=[DiskSpec('D',250.,5.123456,.023456,.034567)],
        loads=[LoadSpec('U','unbalance',250.,.000012345678,12.345678)],
        probes=[ProbeSpec('P',250.,1,34.56789)],
        operating_cases=[OperatingCase('B',1800.345,900.123,4500.789,30.)])
    window=RossStudioWindow()
    try:
        controller=ProjectFileController(window)
        assert controller.new()
        assert window.project.engineering is None
        controller._replace_project(ProjectOpenResult(ProjectModel.from_engineering(p),tmp_path/'fixture.rossproj',None,'qualification',False),clean=False)
        window._refresh_bearing_page(selected_class=model)
        if model == 'CylindricalBearing':
            values={'speed_min_rpm':900.123,'speed_max_rpm':4500.789,'speed_points':5,
                'weight_n':525.123456,'bearing_length_mm':30.123456,'journal_diameter_mm':100.234567,
                'radial_clearance_mm':.123456789,'oil_viscosity_pa_s':.123456789}
            expected=rs.CylindricalBearing(n=0,speed=np.linspace(900.123,4500.789,5)*np.pi/30,
                weight=525.123456,bearing_length=.030123456,journal_diameter=.100234567,
                radial_clearance=.000123456789,oil_viscosity=.123456789)
        else:
            values={size_key:23.456789,count_key:9,'static_load_n':1234.56789,'contact_angle_deg':13.456789}
            expected=getattr(rs,model)(n=0,**{native_size:.023456789,native_count:9},fs=1234.56789,alpha=13.456789*np.pi/180)
        for key,value in values.items():window.bearing_page.input_panel.fields[key].setValue(value)
        window._calculate_bearing()
        assert window.bearing_calculation is not None
        # A changed visible input must invalidate preview before a user can Apply.
        changed_key='weight_n' if model == 'CylindricalBearing' else 'static_load_n'
        field=window.bearing_page.input_panel.fields[changed_key]
        field.setValue(values[changed_key]+1.)
        assert not window.bearing_page.apply_button.isEnabled(), 'Changed input leaves stale Apply enabled'
        window._apply_bearing()
        assert p.bearings[0].ross_class=='BearingElement', 'Stale calculation was committed'
        field.setValue(0.)
        window._calculate_bearing()
        assert window.bearing_calculation is None
        assert not window.bearing_page.apply_button.isEnabled()
        assert p.bearings[0].ross_class=='BearingElement'
        field.setValue(values[changed_key])
        window._calculate_bearing()
        assert window.bearing_calculation is not None
        # The Apply boundary must also reject changed inputs if notifications
        # were suppressed by another UI operation; no scientific solver is mocked.
        field.blockSignals(True)
        field.setValue(values[changed_key]+2.)
        window._apply_bearing()
        assert p.bearings[0].ross_class=='BearingElement'
        field.blockSignals(False)
        field.setValue(values[changed_key])
        window._calculate_bearing()
        assert window.bearing_calculation is not None
        window._apply_bearing()
        assert p.bearings[0].ross_class==model
        parameters=({'speed_rpm':np.linspace(900.123,4500.789,5),'weight_n':525.123456,
            'bearing_length_m':.030123456,'journal_diameter_m':.100234567,
            'radial_clearance_m':.000123456789,'oil_viscosity_pa_s':.123456789}
            if model=='CylindricalBearing' else {count_key:9,
                ('d_balls_m' if model=='BallBearingElement' else 'roller_length_m'):.023456789,
                'static_load_n':1234.56789,'contact_angle_rad':13.456789*np.pi/180})
        for key,value in parameters.items():
            np.testing.assert_allclose(p.bearings[0].metadata[key],value,rtol=1e-14,atol=1e-15,err_msg=key)
        rotor=RossBackend().build_rotor(p).rotor
        applied=rotor.bearing_elements[0]
        assert type(applied).__name__==model
        np.testing.assert_allclose(applied.K(123.456),expected.K(123.456),rtol=1e-12,atol=1e-12)
        np.testing.assert_allclose(applied.C(123.456),expected.C(123.456),rtol=1e-12,atol=1e-12)
        def check_coefficient_table():
            speeds=np.linspace(900.123,4500.789,5) if model=='CylindricalBearing' else [1800.345]
            table=window.bearing_page.kc_table
            assert table.rowCount()==len(speeds)
            for row,rpm in enumerate(speeds):
                k,c=expected.K(rpm*np.pi/30),expected.C(rpm*np.pi/30)
                assert table.item(row,0).text()==f'{rpm:g}'
                for col,value in enumerate([k[0,0],k[0,1],k[1,0],k[1,1],c[0,0],c[0,1],c[1,0],c[1,1]],1):
                    assert table.item(row,col).text()==f'{value:.2e}'
        check_coefficient_table()
        reference=rs.Rotor(
            [rs.ShaftElement(L=.125,idl=0.,odl=.04,n=n,
                material=rs.Material(name='Steel',rho=7850.,E=207e9,Poisson=.3)) for n in range(4)],
            [rs.DiskElement(n=2,m=5.123456,Id=.023456,Ip=.034567)],
            [expected,rs.BearingElement(n=4,kxx=2e7,kyy=3e7,cxx=200.,cyy=300.)])
        evidence=[]
        def compare(name,a,b,rtol=1e-7,atol=1e-10):
            a,b=np.asarray(a),np.asarray(b)
            np.testing.assert_allclose(a,b,rtol=rtol,atol=atol,err_msg=model+' '+name)
            evidence.append(dict(quantity=name,max_absolute_error=float(np.max(abs(a-b))),
                reference_max_abs=float(np.max(abs(b))),rtol=rtol,atol=atol,status='PASS'))
        for omega in np.linspace(900.123,4500.789,9)*np.pi/30:
            compare(f'element K {omega}',applied.K(omega),expected.K(omega),1e-12,1e-9)
            compare(f'element C {omega}',applied.C(omega),expected.C(omega),1e-12,1e-9)
            compare(f'assembled K {omega}',rotor.K(omega),reference.K(omega),1e-12,1e-8)
            compare(f'assembled C {omega}',rotor.C(omega),reference.C(omega),1e-12,1e-8)
        result=_run_window_analysis(window)
        native=reference.run_modal(1800.345*np.pi/30,num_modes=12)
        compare('modal wn',result.modal.wn,native.wn,1e-7,1e-7)
        ub=reference.run_unbalance_response(2,.000012345678,12.345678*np.pi/180,result.speed_rpm*np.pi/30)
        compare('unbalance complex',result.unbalance.forced_resp,ub.forced_resp,1e-7,1e-13)
        page=window.results_page;page._select_analysis('modal')
        for row,freq in enumerate(native.wn):
            assert page.table.item(row,1).text()==f'{freq/(2*np.pi):.3f}'
        saved=save_project(window.project,tmp_path/'saved.rossproj')
        assert controller.open_path(saved)
        check_coefficient_table()
        reopened=RossBackend().build_rotor(window.project.engineering).rotor.bearing_elements[0]
        np.testing.assert_array_equal(reopened.K(123.456),applied.K(123.456))
        np.testing.assert_array_equal(reopened.C(123.456),applied.C(123.456))
        again=_run_window_analysis(window)
        compare('reopened modal',again.modal.wn,result.modal.wn,1e-7,1e-7)
        compare('reopened unbalance',again.unbalance.forced_resp,result.unbalance.forced_resp,1e-7,1e-13)
        return {'comparisons':evidence,'status':'PASS','model':model,'kxx':float(expected.kxx[0]),'cxx':float(expected.cxx[0]),
                'scope':'Existing station: GUI Calculate/Apply, native element and assembly K/C, main-window solver, modal table, complex unbalance, controller reopen/recompute'}
    finally:
        window.close()
        window.deleteLater()
        QApplication.instance().processEvents()


def run_scalar_bearing_qualification():
    with TemporaryDirectory() as directory:
        cases=[run_scalar_bearing_case(model,Path(directory)) for model in ('BallBearingElement','RollerBearingElement','CylindricalBearing')]
    return {'status':'PASS','ross_version':rs.__version__,'cases':cases,
            'feature_status':'Source scope tested; require exact frozen Linux/Windows evidence; other bearing models and flexible support excluded'}
