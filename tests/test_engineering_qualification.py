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
