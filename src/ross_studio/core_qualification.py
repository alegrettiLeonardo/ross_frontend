"""Executable Core adapter qualification, shared by source and frozen runtimes.

This is a test harness, not a production solver or a replacement of ROSS physics.
"""
from dataclasses import asdict, dataclass, replace
from copy import deepcopy
from PySide6.QtCore import QTimer, QEventLoop
from .pages.rotor_workspace import RotorModelPage
from pathlib import Path
from tempfile import TemporaryDirectory
import numpy as np
import ross as rs
from PySide6.QtWidgets import QApplication, QTableWidgetItem
from .domain import RotorProject, ShaftSection, BearingSpec, DiskSpec, PointMassSpec, LoadSpec, ProbeSpec, OperatingCase
from .models import ProjectModel
from .ross_backend import RossBackend
from .analysis_pipeline import AnalysisPipelineService, AnalysisPolicy
from .pages.engineering_results import EngineeringAnalysisResultsPage
from .project_io import save_project


@dataclass
class CoreEvidence:
    records: dict
    def to_dict(self):
        return self.records


def run_core_qualification():
    app = QApplication.instance() or QApplication([])
    assert rs.__version__ == '2.3.0'
    rows = []
    def compare(name, actual, expected, rtol=1e-10, atol=1e-12):
        a, b = np.asarray(actual), np.asarray(expected)
        np.testing.assert_allclose(a,b,rtol=rtol,atol=atol,err_msg=name)
        delta=float(np.max(np.abs(a-b))) if a.size else 0.
        rows.append(dict(quantity=name, studio_max_abs=float(np.max(abs(a))) if a.size else 0., reference_max_abs=float(np.max(abs(b))) if b.size else 0., max_absolute_error=delta, rtol=rtol, atol=atol, status='PASS'))
    # Literal fixture independent of the Studio serialization/builder.
    length=300.369; total=600.738
    p=RotorProject(name='Core sentinel',shaft_sections=[ShaftSection(1,300.5,40.,id_left_mm=10.,fe_elements=3),ShaftSection(2,300.5,40.,id_left_mm=10.,fe_elements=3)],
        bearings=[BearingSpec('B1',0.,kxx=1e7,kyy=1e7,cxx=100.,cyy=100.),BearingSpec('B2',total,kxx=1e7,kyy=1e7,cxx=100.,cyy=100.)],
        disks=[DiskSpec('Disk',200.246,10.,.05,.1)],point_masses=[PointMassSpec('Concent',400.492,2.,.01,.03,.02)],
        loads=[LoadSpec('U','unbalance',200.246,.000123456,23.456789)],probes=[ProbeSpec('P',200.246,1,13.456789)],
        operating_cases=[OperatingCase('Core',1234.56,100.,12000.,20.576)])
    model=ProjectModel.from_engineering(p)
    editor=RotorModelPage(model);widgets=[editor]
    def edit(key,row,values,material=False):
        editor.editor_tables[key].selectRow(row)
        errors=[]
        def enter():
            dialog=QApplication.activeModalWidget()
            try:
                for name,value in values.items():
                    field=getattr(dialog,name)
                    if isinstance(value,bool):field.setChecked(value)
                    elif isinstance(value,str):field.setText(value)
                    else:field.setValue(value)
            except Exception as exc:errors.append(exc)
            finally:dialog.accept()
        QTimer.singleShot(0,enter)
        if material:editor._edit_material()
        else:editor._edit_entity(key)
        if errors:raise errors[0]
    for i in range(2):
        edit('shaft',i,dict(resize_section=True,length=300.369,od_left=41.234567,id_left=11.234567,fe_elements=3,shear_effects=True,rotary_inertia=True,gyroscopic=True))
    edit('shaft',0,dict(density=7912.345678,young=203456700000.,poisson=.287654),material=True)
    edit('disks',0,dict(position=200.246,mass=12.345678,id=.054321,ip=.098765))
    edit('disks',1,dict(position=400.492,mass=2.345678,ix=.012345,iy=.034567,iz=.023456))
    edit('loads',0,dict(position=200.246,magnitude=.000123456,phase=23.456789))
    assert p.loads[0].magnitude==.000123456
    edit('probes',0,dict(position=200.246,orientation=13.456789))
    # Non-round coefficients, including cross terms, are entered into the real table.
    coefficients=[12345670.,23456.,-34567.,14567890.,123.456,2.345,-3.456,234.567]
    from .app import RossStudioWindow
    from .project_file_controller import ProjectFileController
    from .project_file_service import ProjectOpenResult
    from .models import BearingModel
    window=RossStudioWindow();widgets.append(window)
    controller=ProjectFileController(window)
    controller._replace_project(ProjectOpenResult(model,Path('core.rossproj'),None,'qualification',False),clean=False)
    for i in range(2):
        window.bearing_index=i;window.bearing=BearingModel.from_project(p,i)
        window._refresh_bearing_page(selected_class='BearingElement')
        table=window.bearing_page.input_panel.kc_table;table.setRowCount(2)
        for row,rpm in enumerate((100.,12000.)):
            for col,value in enumerate([rpm,*coefficients]):table.setItem(row,col,QTableWidgetItem(str(value)))
        window._calculate_bearing()
        assert window.bearing_calculation is not None
        assert window.bearing_page.apply_button.isEnabled()
        window._apply_bearing()
        assert p.bearings[i].coefficients[0].kxx==12345670.
    actual=RossBackend().build_rotor(p).rotor
    mat=rs.Material(name='Steel',rho=7912.345678,E=203456700000.,Poisson=.287654)
    class IndependentConcent(rs.DiskElement):
        def M(self):return np.diag([2.345678]*3+[.012345,.023456,.034567])
    reference=rs.Rotor([rs.ShaftElement(L=.100123,idl=.011234567,odl=.041234567,material=mat,n=n,shear_effects=True,rotary_inertia=True,gyroscopic=True) for n in range(6)],
        [rs.DiskElement(n=2,m=12.345678,Id=.054321,Ip=.098765),IndependentConcent(n=4,m=2.345678,Id=0.,Ip=.034567)],
        [rs.BearingElement(n=n,frequency=np.array([100.,12000.])*np.pi/30,**{key:[value,value] for key,value in zip(('kxx','kxy','kyx','kyy','cxx','cxy','cyx','cyy'),coefficients)}) for n in (0,6)])
    for i,e in enumerate(actual.shaft_elements):
        for name,expected in [('L',.100123),('idl',.011234567),('odl',.041234567)]:compare(f'shaft[{i}].{name}',getattr(e,name),expected,atol=1e-15)
        compare(f'shaft[{i}].rho',e.material.rho,7912.345678)
        compare(f'shaft[{i}].E',e.material.E,203456700000.)
        compare(f'shaft[{i}].Poisson',e.material.Poisson,.287654)
    for i,e in enumerate(actual.bearing_elements):
        compare(f'bearing[{i}].frequency',e.frequency,np.array([100.,12000.])*np.pi/30)
        for key,value in zip(('kxx','kxy','kyx','kyy','cxx','cxy','cyx','cyy'),coefficients):compare(f'bearing[{i}].{key}',getattr(e,key),[value,value])
    for name in ('M','C','K','G'):
        args=() if name=='G' else (1234.56*np.pi/30,)
        expected=getattr(reference,name)(*args)
        # Adjacent FE contributions cancel near zero. Coordinate subtraction in
        # the Studio mesh rounds differently from literal independent lengths.
        # Eight machine epsilons of the assembly scale bound that roundoff;
        # this absolute floor is not a model-form/engineering uncertainty.
        floor=8*np.finfo(float).eps*max(1.,float(np.max(abs(expected))))
        compare(name,getattr(actual,name)(*args),expected,1e-12,floor)
    compare('mass',actual.m,reference.m);compare('nodes',actual.nodes_pos,reference.nodes_pos)
    policy=AnalysisPolicy(modal_num_modes=12,campbell_frequencies=4,campbell_points=17,response_points=11)
    from .solver_console import SolverConsole
    def gui_solve(project_model):
        console=SolverConsole(project_model,service=AnalysisPipelineService(policy=policy),autostart=False)
        widgets.append(console);console.show()
        loop=QEventLoop();watch=QTimer();watch.setInterval(20)
        watch.timeout.connect(lambda:loop.quit() if console._thread is None else None)
        timeout=QTimer();timeout.setSingleShot(True);timeout.timeout.connect(loop.quit)
        console.start();watch.start();timeout.start(120000);loop.exec()
        expired=not timeout.isActive();timeout.stop();watch.stop()
        if expired:
            console._stop();raise RuntimeError('Core GUI solver exceeded 120 s')
        assert console.analysis_result is not None,console.status_detail.text()
        console.open_results.click()
        return console.analysis_result
    result=gui_solve(model)
    direct_modal=reference.run_modal(1234.56*np.pi/30,num_modes=12)
    compare('natural frequencies',result.modal.wn,direct_modal.wn,1e-7,1e-7)
    v=result.modal.evectors[:actual.ndof,:len(result.modal.wn)];w=direct_modal.evectors[:reference.ndof,:len(direct_modal.wn)]
    mac=abs(np.sum(v.conj()*w,axis=0))**2/(np.sum(abs(v)**2,axis=0)*np.sum(abs(w)**2,axis=0))
    compare('MAC',mac,np.ones_like(mac),1e-7,1e-9)
    direct_static=reference.run_static();compare('static deflection',result.static.deformation,direct_static.deformation,1e-8,1e-13)
    direct_campbell=reference.run_campbell(result.campbell.speed_range,frequencies=4)
    compare('Campbell',result.campbell.wd,direct_campbell.wd,1e-7,1e-7)
    roots=[]
    omega=direct_campbell.speed_range
    for branch in range(direct_campbell.wd.shape[1]):
        residual=direct_campbell.wd[:,branch]-omega
        for idx in np.flatnonzero(residual[:-1]*residual[1:]<0):
            a,b=residual[idx:idx+2]
            roots.append((omega[idx]*b-omega[idx+1]*a)/(b-a)*30/np.pi)
    roots.sort()
    assert roots
    assert min(np.diff(roots),default=100)>policy.critical_dedup_rpm
    compare('critical interpolated 1X crossings',[c.speed_rpm for c in result.critical_speeds],roots,1e-7,1e-6)
    # Separate native critical result; GUI pipeline explicitly uses interpolated 1X crossings.
    compare('native critical',actual.run_critical_speed(num_modes=4)._wd,reference.run_critical_speed(num_modes=4)._wd,1e-6,1e-6)
    direct_ub=reference.run_unbalance_response(2,.000123456,23.456789*np.pi/180,result.speed_rpm*np.pi/30)
    compare('unbalance complex',result.unbalance.forced_resp,direct_ub.forced_resp,1e-7,1e-13)
    compare('unbalance amplitude',abs(result.unbalance.forced_resp),abs(direct_ub.forced_resp),1e-7,1e-13)
    mask=abs(direct_ub.forced_resp)>1e-12
    compare('unbalance phase wrapped',np.angle(result.unbalance.forced_resp[mask]/direct_ub.forced_resp[mask]),np.zeros(mask.sum()),0.,1e-7)
    page=window.results_page;assert isinstance(page,EngineeringAnalysisResultsPage);page.set_results(result)
    page._select_analysis('modal')
    for row,freq in enumerate(direct_modal.wn):assert page.table.item(row,1).text()==f'{freq/(2*np.pi):.3f}'
    compare('GUI Campbell frequencies Hz',page.campbell_chart._frequency_hz,direct_campbell.wd/(2*np.pi),1e-7,1e-7)
    compare('GUI Campbell speed rpm',page.campbell_chart._speed_rpm,direct_campbell.speed_range*30/np.pi)
    page._select_analysis('static')
    assert page.table.item(0,1).text()==f'{np.max(abs(direct_static.deformation))*1e6:.6g}'
    compare('static bearing reactions',list(result.static.bearing_forces.values()),list(direct_static.bearing_forces.values()),1e-8,1e-8)
    for row,force in enumerate(direct_static.bearing_forces.values(),1):
        assert page.table.item(row,1).text()==f'{force:.6g}'
    for row,c in enumerate(result.critical_speeds):
        page._select_analysis('critical')
        assert page.table.item(row,1).text()==f'{c.speed_rpm:.2f}'
    angle=13.456789*np.pi/180
    projected=direct_ub.forced_resp[12]*np.cos(angle)+direct_ub.forced_resp[13]*np.sin(angle)
    compare('GUI probe numeric amplitude',result.probe_responses[0].amplitude_m,abs(projected),1e-7,1e-13)
    compare('GUI probe numeric phase',result.probe_responses[0].phase_deg,np.angle(projected)*180/np.pi,1e-7,1e-7)
    page._select_analysis('unbalance')
    assert page.table.item(0,8).text()==f'{result.probe_responses[0].rated_phase_deg:.2f}' 
    with TemporaryDirectory() as directory:
        saved=save_project(model,Path(directory)/'core.rossproj')
        assert controller.open_path(saved)
        reopened=window.project
        assert isinstance(window.results_page,EngineeringAnalysisResultsPage)
        assert asdict(reopened.engineering)==asdict(p)
        again=gui_solve(reopened)
        compare('reopened modal',again.modal.wn,result.modal.wn,1e-7,1e-7)
        compare('reopened unbalance',again.unbalance.forced_resp,result.unbalance.forced_resp,1e-7,1e-13)
        compare('reopened Campbell',again.campbell.wd,result.campbell.wd,1e-7,1e-7)
        compare('reopened static',again.static.deformation,result.static.deformation,1e-8,1e-13)
        model=reopened;page=window.results_page;page.set_results(again)
    baseline=deepcopy(p)
    mutations={
        'material':lambda e:e.materials.update(Steel=replace(e.materials['Steel'],density_kg_m3=8000.)),
        'shaft':lambda e:setattr(e.shaft_sections[0],'od_left_mm',42.),
        'disk':lambda e:setattr(e.disks[0],'mass_kg',13.),
        'concent':lambda e:setattr(e.point_masses[0],'ix_kg_m2',.015),
        'bearing':lambda e:e.bearings[0].coefficients.__setitem__(0,replace(e.bearings[0].coefficients[0],kxx=1.3e7)),
        'unbalance':lambda e:setattr(e.loads[0],'phase_deg',25.),
        'probe':lambda e:setattr(e.probes[0],'orientation_deg',15.)}
    for name,mutate in mutations.items():
        model.engineering=deepcopy(baseline);page.validity_guard.check();page.set_results(result)
        mutate(model.engineering);page.validity_guard.check()
        assert page.result is None and page.campbell_chart._frequency_hz is None,name
        rows.append(dict(quantity=f'stale {name}',status='PASS'))
    from ross.units import Q_
    for value,source,target,expected in [
        (123.456789,'mm','m',.123456789),
        (1234.56789,'RPM','rad/s',1234.56789*np.pi/30),
        (23.456789,'Hz','rad/s',23.456789*2*np.pi),
        (12345.6789,'N/mm','N/m',12345678.9),
        (123.456789,'N*s/mm','N*s/m',123456.789),
        (12345.6789,'kg*mm**2','kg*m**2',.0123456789),
        (23.456789,'degree','rad',23.456789*np.pi/180),
        (12.3456789,'bar','Pa',1234567.89),
        (23.456789,'degC','kelvin',296.606789)]:
        converted=Q_(value,source).to(target)
        compare(f'unit {source}->{target}',converted.m,expected,1e-13,1e-13)
        compare(f'unit {target}->{source}',converted.to(source).m,value,1e-13,1e-13)
    for widget in widgets:widget.close();widget.deleteLater()
    app.processEvents()
    return CoreEvidence(dict(status='PASS',ross_version=rs.__version__,comparisons=rows,
        scope='Existing two-section hollow linear rotor; real GUI editing, K/C Calculate/Apply, SolverConsole, result tables and Campbell data, controller reopen/recompute and seven-entity stale invalidation.',
        gaps=['New-project shaft/bearing creation journey outside existing-model scope','Separate analysis request/settings editors','Full unit-editor matrix beyond core SI fields']))
