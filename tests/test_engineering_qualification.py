"""Independent ROSS 2.3.0 parity and regressions, without production mocks."""
from copy import deepcopy
from dataclasses import asdict
import numpy as np
import pytest
import ross as rs
from ross_studio.domain import MaterialSpec, ShaftSection, BearingSpec, RotorProject, DiskSpec, SupportSpec
from ross_studio.ross_backend import RossBackend
from ross_studio.models import ProjectModel
from ross_studio.project_io import save_project, load_project


def small_project():
    return RotorProject(name='independent-parity', materials={'Steel': MaterialSpec()},
        shaft_sections=[ShaftSection(1, 300., 40., id_left_mm=10., fe_elements=3),
                        ShaftSection(2, 300., 40., id_left_mm=10., fe_elements=3)],
        bearings=[BearingSpec('B1',0., kxx=1.234567e7, kyy=1.5e7,cxx=123.,cyy=234.),
                  BearingSpec('B2',600.,kxx=1.234567e7,kyy=1.5e7,cxx=123.,cyy=234.)],
        disks=[DiskSpec('D',300.,10.,0.05,0.1)])


def independent_rotor():
    mat=rs.Material(name='Steel',rho=7850.,E=207e9,Poisson=.3)
    return rs.Rotor([rs.ShaftElement(L=.1,idl=.01,odl=.04,material=mat,n=n) for n in range(6)],
        [rs.DiskElement(n=3,m=10.,Id=.05,Ip=.1)],
        [rs.BearingElement(n=n,kxx=1.234567e7,kyy=1.5e7,cxx=123.,cyy=234.) for n in (0,6)])


def test_independent_matrices_modes_response_and_persistence(tmp_path):
    p=small_project()
    model=load_project(save_project(ProjectModel.from_engineering(p),tmp_path/'p.rossproj'))
    assert asdict(model.engineering)==asdict(p)
    actual=RossBackend().build_rotor(model.engineering).rotor
    expected=independent_rotor()
    # Same element equations/mesh: tolerances allow FP accumulation only,
    # not discretization or experimental/model-form error.
    for name in ('M','K','C','G'):
        args=() if name=='G' else (100.,)
        np.testing.assert_allclose(getattr(actual,name)(*args),getattr(expected,name)(*args),rtol=1e-12,atol=1e-10)
    np.testing.assert_allclose(actual.nodes_pos,expected.nodes_pos,rtol=1e-14,atol=1e-15)
    assert actual.m==pytest.approx(expected.m,rel=1e-12)
    np.testing.assert_allclose(actual.run_modal(100.).wn,expected.run_modal(100.).wn,rtol=1e-7,atol=1e-7)
    speed=np.linspace(50.,200.,5)
    a=actual.run_unbalance_response(3,1e-4,.3,speed).forced_resp
    b=expected.run_unbalance_response(3,1e-4,.3,speed).forced_resp
    np.testing.assert_allclose(a,b,rtol=1e-7,atol=1e-13)


@pytest.mark.parametrize('support',[False,True])
def test_explicit_zero_direction_reaches_ross(support):
    p=small_project()
    if support:
        p.supports=[SupportSpec('S',0,10.,kxx=2e7,kyy=0.,cxx=321.,cyy=0.)]
        tag='S / ground'
    else:
        p.bearings[0].kyy=0.
        p.bearings[0].cyy=0.
        tag='B1'
    rotor=RossBackend().build_rotor(p).rotor
    element=next(e for e in rotor.bearing_elements if e.tag==tag)
    assert float(element.kyy[0])==0.
    assert float(element.cyy[0])==0.


def test_physical_invariants():
    p=small_project()
    r=RossBackend().build_rotor(p).rotor
    for m in (r.M(),r.K(0.)):
        np.testing.assert_allclose(m,m.T,rtol=1e-12,atol=1e-9)
    assert np.linalg.eigvalsh(r.M()).min()>0.
    np.testing.assert_allclose(r.G(),-r.G().T,atol=1e-12)
    speed=np.array([50.,100.,200.])
    a=r.run_unbalance_response(3,1e-4,0.,speed).forced_resp
    b=r.run_unbalance_response(3,2e-4,0.,speed).forced_resp
    z=r.run_unbalance_response(3,0.,0.,speed).forced_resp
    np.testing.assert_allclose(b,2*a,rtol=1e-10,atol=1e-14)
    np.testing.assert_allclose(z,0.,atol=1e-14)
    heavy=deepcopy(p); heavy.disks[0].mass_kg*=2
    assert RossBackend().build_rotor(heavy).rotor.run_modal(0.).wn[0]<r.run_modal(0.).wn[0]
    stiff=deepcopy(p)
    for e in stiff.bearings: e.kxx*=2; e.kyy*=2
    assert RossBackend().build_rotor(stiff).rotor.run_modal(0.).wn[0]>r.run_modal(0.).wn[0]


def test_seal_preview_is_invalidated_by_table_edit(qtbot):
    from ross_studio.domain import SealSpec
    from ross_studio.pages.seal_workspace import SealStudioPage
    p=small_project(); p.seals=[SealSpec('S',300.,1e6,2e6,100.,200.)]
    page=SealStudioPage(ProjectModel.from_engineering(p)); qtbot.addWidget(page)
    page._calculate()
    assert page.preview is not None
    assert page.apply.isEnabled()
    row=next(i for i in range(page.parameters.rowCount()) if page.parameters.item(i,0).text()=='kxx')
    page.parameters.item(row,1).setText('1234567')
    assert page.preview is None
    assert not page.apply.isEnabled()


def test_frozen_contract_executes_amb_parity():
    from ross_studio.amb_qualification import qualify_amb_assembly
    from ross_studio.frozen_selftest import run_frozen_self_test
    assert qualify_amb_assembly(rs)['status']=='PASS'
    result=run_frozen_self_test()
    assert result.status=='PASS'
    assert 'MagneticBearingElement' in result.executable_classes
    assert result.blocked_classes==()


@pytest.mark.parametrize('kind',['misalignment','rubbing','crack'])
def test_fault_gui_real_solve_and_input_invalidation(qtbot,kind):
    from ross_studio.pages.faults_workspace import FaultsWorkspace
    from ross_studio.domain import LoadSpec
    p=small_project(); p.loads=[LoadSpec("U", "unbalance", 300., 100.)]
    page=FaultsWorkspace(ProjectModel.from_engineering(p)); qtbot.addWidget(page)
    prefix={'misalignment':'mis','rubbing':'rub','crack':'crack'}[kind]
    getattr(page,prefix+'_duration').setValue(.01)
    getattr(page,prefix+'_samples').setValue(101)
    getattr(page,'_run_'+kind)()
    assert page.result is not None, page.state.text()
    assert np.all(np.isfinite(page.result.native.yout))
    assert page.figures, page.state.text()
    getattr(page,prefix+'_speed').setValue(1234.)
    assert page.result is None
    assert not page.figures


def test_time_frequency_project_edit_invalidates_real_result(qtbot):
    from ross_studio.pages.time_frequency_workspace import TimeFrequencyWorkspacePage
    page=TimeFrequencyWorkspacePage(ProjectModel.from_engineering(small_project())); qtbot.addWidget(page)
    page.fr_points.setValue(3)
    page._run('frequency')
    qtbot.waitUntil(lambda: 'frequency' in page._results, timeout=30000)
    page.project.engineering.bearings[0].kxx*=2
    page.validity_guard.check()
    assert 'frequency' not in page._results
    qtbot.waitUntil(lambda: not getattr(page,'_threads',{}),timeout=30000)


@pytest.mark.parametrize('entity,field',[('material','density_kg_m3'),('shaft','length_mm'),('disk','mass_kg'),('bearing','kxx')])
def test_nonfinite_physical_input_rejected(entity,field):
    from dataclasses import replace
    from ross_studio.domain import EngineeringError
    p=small_project()
    if entity=='material': p.materials['Steel']=replace(p.materials['Steel'],**{field:float('nan')})
    else: setattr({'shaft':p.shaft_sections[0],'disk':p.disks[0],'bearing':p.bearings[0]}[entity],field,float('nan'))
    with pytest.raises(EngineeringError,match='finite'):
        p.validate()


@pytest.mark.parametrize('model_name',['LABYRINTH','HOLE_PATTERN','HYBRID'])
def test_native_seal_230_constructor_and_apply(model_name):
    from ross_studio.pages.seal_workspace import _DEFAULTS
    from ross_studio.seal_studio_service import SealStudioService
    from ross_studio.domain import SealSpec, SealModel
    p=small_project();p.seals=[SealSpec('Seal',300.,1e6,1e6,100.,100.)]
    model=SealModel[model_name];service=SealStudioService()
    result=service.calculate(p,0,model,_DEFAULTS[model])
    assert result.coefficients
    service.apply(p,0,result)
    actual=RossBackend().build_rotor(p).rotor
    element=next(e for e in actual.bearing_elements if e.tag=='Seal')
    assert type(element).__name__=={'LABYRINTH':'LabyrinthSeal','HOLE_PATTERN':'HolePatternSeal','HYBRID':'HybridSeal'}[model_name]
    stages = [element.laby, element.hole_pattern] if model_name == 'HYBRID' else [element]
    for stage in stages:
        assert stage.shaft_radius==pytest.approx(_DEFAULTS[model]['shaft_diameter_mm']/2000.)
    if model_name == 'HYBRID':
        assert element.convergence_history[-1] <= _DEFAULTS[model]['tolerance']
    for point in result.coefficients:
        assert np.all(np.isfinite(element.K(point.rpm*np.pi/30)))


def test_amb_native_sensitivity_and_plots():
    from ross_studio.amb_analysis import AMBSensitivityService, AMBSensitivityRequest
    from test_ross_native_completion_030 import amb_spec
    p=small_project();p.bearings[0]=amb_spec()
    result=AMBSensitivityService().run(p,AMBSensitivityRequest(speed_rpm=1000.,t_max_s=1.,dt_s=.001,min_frequency_hz=5.,max_frequency_hz=50.))
    assert type(result.native).__name__=='SensitivityResults'
    peaks=[v for axes in result.native.max_abs_sensitivities.values() for v in axes.values()]
    assert peaks and all(np.isfinite(v) and v>0 for v in peaks)
    assert len(result.native.plot(frequency_units='Hz',magnitude_scale='decibel',xaxis_type='log').data)>0
    assert len(result.native.plot_time_results().data)>0


def test_frozen_gui_contract_executes_from_source():
    # Isolated process: full application window owns its QApplication lifecycle.
    import subprocess,sys,json,tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as tmp:
        out=Path(tmp)/'gui.json'
        subprocess.run([sys.executable,'-m','ross_studio.frozen_entry','--gui-smoke','--gui-smoke-output',str(out)],check=True,timeout=180)
        data=json.loads(out.read_text())
        assert data['status']=='PASS'
        assert data['model_builder_014']['coupling_native_mapping']=='NATIVE_TWO_NODE_COUPLING'
        assert data['amb_blocked']==[]


def test_multirotor_real_modal_is_invalidated(qtbot):
    from ross_studio.pages.multirotor_workspace import MultiRotorWorkspacePage
    from ross_studio.multirotor.qualification import three_shaft_project
    from ross_studio.multirotor.analysis import MultiRotorAnalysisService, ModalRequest
    page=MultiRotorWorkspacePage(ProjectModel.from_engineering(small_project()));qtbot.addWidget(page)
    page.multirotor=three_shaft_project()
    result=MultiRotorAnalysisService().run_modal(page.multirotor,ModalRequest(1000.,8))
    page._analysis_done(result)
    assert page._result is result
    page.multirotor.rotors[0].bearings[0].kxx*=1.1
    page.validity_guard.check()
    assert page._result is None
    assert page._catalog is None


def test_duplicate_support_names_rejected():
    from ross_studio.domain import EngineeringError
    p=small_project();p.supports=[SupportSpec('S',0,10.),SupportSpec('S',1,10.)]
    with pytest.raises(EngineeringError,match='unique names'):
        p.validate()


@pytest.mark.parametrize('speeds',[(1000.,1000.),(2000.,1000.)])
def test_bearing_frequency_table_requires_strict_order(speeds):
    from ross_studio.domain import EngineeringError, BearingCoefficientPoint
    p=small_project();p.bearings[0].coefficients=[BearingCoefficientPoint(rpm=s,kxx=1e7,kyy=1e7,kxy=0.,kyx=0.,cxx=100.,cyy=100.,cxy=0.,cyx=0.) for s in speeds]
    with pytest.raises(EngineeringError,match='strictly increasing'):
        p.validate()


def test_stochastic_real_build_invalidated_on_model_and_sampling_edit(qtbot):
    from ross_studio.pages.stochastic_workspace import StochasticWorkspacePage
    from ross_studio.stochastic_analysis import StochasticRotorService
    from test_stochastic_native_022 import compact_project, sampling
    page=StochasticWorkspacePage(ProjectModel.from_engineering(compact_project()));qtbot.addWidget(page)
    built=StochasticRotorService().build(page.engineering,sampling())
    page._input_build_complete(built)
    assert page._input_build is built
    page.project.engineering.disks[0].mass_kg*=2
    page.validity_guard.check()
    assert page._input_build is None
    page._input_build_complete(built)
    page.seed.setValue(page.seed.value()+1)
    assert page._input_build is None


def test_engineering_outputs_real_result_invalidated(qtbot):
    from ross_studio.pages.engineering_results import EngineeringAnalysisResultsPage
    from ross_studio.analysis_pipeline import AnalysisPipelineService
    from ross_studio.models import load_reference_project_model
    model=load_reference_project_model()
    page=EngineeringAnalysisResultsPage(model);qtbot.addWidget(page)
    result=AnalysisPipelineService().run(model.engineering)
    page.set_results(result)
    assert page.engineering_snapshot is not None
    model.engineering.bearings[0].kxx+=1.234567e7
    page.validity_guard.check()
    assert page.result is None
    assert page.engineering_snapshot is None
    assert not page.engineering_outputs_button.isEnabled()


def test_hybrid_nonconvergence_cannot_be_applied():
    from ross_studio.pages.seal_workspace import _DEFAULTS
    from ross_studio.seal_studio_service import SealStudioService
    from ross_studio.domain import SealSpec, SealModel, EngineeringError
    p=small_project();p.seals=[SealSpec('Unconverged',300.,1e6,1e6,100.,100.)]
    inputs=dict(_DEFAULTS[SealModel.HYBRID],max_iterations=1)
    with pytest.raises(EngineeringError,match='did not converge'):
        SealStudioService().calculate(p,0,SealModel.HYBRID,inputs)
    assert p.seals[0].model==SealModel.DIRECT


def test_schema_migration_records_every_added_physical_default(tmp_path):
    import json
    model=ProjectModel.from_engineering(small_project())
    target=save_project(model,tmp_path/'old.rossproj')
    raw=json.loads(target.read_text());raw['schema_version']=2
    for shaft in raw['engineering']['shaft_sections']:
        for key in ('shear_effects','rotary_inertia','gyroscopic'): shaft.pop(key)
    target.write_text(json.dumps(raw))
    loaded=load_project(target)
    record=loaded.engineering.warnings[-1]
    assert 'migration 2 -> 3' in record
    for index in range(2):
        for key in ('shear_effects','rotary_inertia','gyroscopic'):
            assert f'engineering.shaft_sections[{index}].{key}=True' in record
    reopened=load_project(save_project(loaded,tmp_path/'new.rossproj'))
    assert reopened.engineering.warnings==loaded.engineering.warnings


def test_seal_plot_failure_is_visible(qtbot,monkeypatch):
    from ross_studio.pages.seal_workspace import SealStudioPage
    page=SealStudioPage(ProjectModel.from_engineering(small_project()));qtbot.addWidget(page)
    native=rs.SealElement(n=0,kxx=1e6,cxx=100.)
    def failure(*args,**kwargs): raise ValueError('injected plotting failure')
    monkeypatch.setattr(native,'plot',failure)
    page._collect_figures(native)
    assert 'injected plotting failure' in page.state.text()
    assert not page.figures
