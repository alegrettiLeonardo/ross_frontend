"""Executable Core adapter qualification, shared by source and frozen runtimes.

This is a test harness, not a production solver or a replacement of ROSS physics.
"""
from dataclasses import asdict, dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
import numpy as np
import ross as rs
from PySide6.QtWidgets import QApplication, QTableWidgetItem
from .domain import RotorProject, ShaftSection, BearingSpec, DiskSpec, PointMassSpec, LoadSpec, ProbeSpec, OperatingCase
from .models import ProjectModel
from .model_builder_service import RotorModelMutationService
from .model_entity_dialogs import MaterialEditorDialog, DiskEditorDialog, PointMassEditorDialog, LoadEditorDialog
from .shaft_section_dialog import GuidedShaftSectionEditorDialog
from .bearing_input_dialog import BearingInputDialog
from .bearing_studio_service import BearingStudioService
from .ross_backend import RossBackend
from .analysis_pipeline import AnalysisPipelineService, AnalysisPolicy
from .pages.engineering_results import EngineeringAnalysisResultsPage
from .project_io import save_project, load_project


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
    mutation=RotorModelMutationService(); widgets=[]
    for i in range(2):
        dialog=GuidedShaftSectionEditorDialog(p.shaft_sections[i]);widgets.append(dialog)
        dialog.resize_section.setChecked(True);dialog.length.setValue(length)
        dialog.od_left.setValue(41.234567);dialog.id_left.setValue(11.234567)
        dialog.fe_elements.setValue(3)
        for key in ('shear_effects','rotary_inertia','gyroscopic'): getattr(dialog,key).setChecked(True)
        mutation.commit(p,mutation.preview_update(p,'shaft',i,dialog.changes()))
    material=MaterialEditorDialog(p.materials['Steel']);widgets.append(material)
    material.density.setValue(7912.345678);material.young.setValue(203456700000.);material.poisson.setValue(.287654)
    mutation.commit(p,mutation.preview_material_update(p,'Steel',material.record()))
    disk=DiskEditorDialog(p.disks[0],total_length_mm=total);widgets.append(disk)
    for key,value in [('position',200.246),('mass',12.345678),('id',.054321),('ip',.098765)]: getattr(disk,key).setValue(value)
    mutation.commit(p,mutation.preview_update(p,'disk',0,disk.changes()))
    concent=PointMassEditorDialog(p.point_masses[0],total_length_mm=total);widgets.append(concent)
    for key,value in [('position',400.492),('mass',2.345678),('ix',.012345),('iy',.034567),('iz',.023456)]:getattr(concent,key).setValue(value)
    mutation.commit(p,mutation.preview_update(p,'point_mass',0,concent.changes()))
    # Non-round coefficients, including cross terms, are entered into the real table.
    coefficients=[12345670.,23456.,-34567.,14567890.,123.456,2.345,-3.456,234.567]
    for i in range(2):
        dialog=BearingInputDialog(p,i,'BearingElement');widgets.append(dialog)
        dialog.kc_table.setRowCount(2)
        for row,rpm in enumerate((100.,12000.)):
            for col,value in enumerate([rpm,*coefficients]):dialog.kc_table.setItem(row,col,QTableWidgetItem(str(value)))
        service=BearingStudioService();service.apply(p,i,service.calculate(p,i,'BearingElement',dialog.values()))
    model=ProjectModel.from_engineering(p)
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
    result=AnalysisPipelineService(policy=policy).run(p)
    direct_modal=reference.run_modal(1234.56*np.pi/30,num_modes=12)
    compare('natural frequencies',result.modal.wn,direct_modal.wn,1e-7,1e-7)
    v=result.modal.evectors[:actual.ndof,:len(result.modal.wn)];w=direct_modal.evectors[:reference.ndof,:len(direct_modal.wn)]
    mac=abs(np.sum(v.conj()*w,axis=0))**2/(np.sum(abs(v)**2,axis=0)*np.sum(abs(w)**2,axis=0))
    compare('MAC',mac,np.ones_like(mac),1e-7,1e-9)
    direct_static=reference.run_static();compare('static deflection',result.static.deformation,direct_static.deformation,1e-8,1e-13)
    direct_campbell=reference.run_campbell(result.campbell.speed_range,frequencies=4)
    compare('Campbell',result.campbell.wd,direct_campbell.wd,1e-7,1e-7)
    # Separate native critical result; GUI pipeline explicitly uses interpolated 1X crossings.
    compare('native critical',actual.run_critical_speed(num_modes=4)._wd,reference.run_critical_speed(num_modes=4)._wd,1e-6,1e-6)
    direct_ub=reference.run_unbalance_response(2,.000123456,23.456789*np.pi/180,result.speed_rpm*np.pi/30)
    compare('unbalance complex',result.unbalance.forced_resp,direct_ub.forced_resp,1e-7,1e-13)
    compare('unbalance amplitude',abs(result.unbalance.forced_resp),abs(direct_ub.forced_resp),1e-7,1e-13)
    mask=abs(direct_ub.forced_resp)>1e-12
    compare('unbalance phase wrapped',np.angle(result.unbalance.forced_resp[mask]/direct_ub.forced_resp[mask]),np.zeros(mask.sum()),0.,1e-7)
    page=EngineeringAnalysisResultsPage(model);widgets.append(page);page.set_results(result)
    page._select_analysis('modal')
    for row,freq in enumerate(direct_modal.wn):assert page.table.item(row,1).text()==f'{freq/(2*np.pi):.3f}'
    compare('GUI Campbell frequencies Hz',page.campbell_chart._frequency_hz,direct_campbell.wd/(2*np.pi),1e-7,1e-7)
    compare('GUI Campbell speed rpm',page.campbell_chart._speed_rpm,direct_campbell.speed_range*30/np.pi)
    page._select_analysis('static')
    assert page.table.item(0,1).text()==f'{np.max(abs(direct_static.deformation))*1e6:.6g}'
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
        saved=save_project(model,Path(directory)/'core.rossproj');reopened=load_project(saved)
        assert asdict(reopened.engineering)==asdict(p)
        again=AnalysisPipelineService(policy=policy).run(reopened.engineering)
        compare('reopened modal',again.modal.wn,result.modal.wn,1e-7,1e-7)
        compare('reopened unbalance',again.unbalance.forced_resp,result.unbalance.forced_resp,1e-7,1e-13)
    p.materials['Steel']=type(p.materials['Steel'])('Steel',8000.,203456700000.,.287654)
    page.validity_guard.check();assert page.result is None
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
        scope='Existing two-section hollow linear rotor; GUI material/shaft/disk/concent/KC adaptation; native solver parity; modal table; save/recompute and material stale invalidation.',
        gaps=['New-project shaft/bearing creation journey','Complete GUI plots/tables for all analyses','Critical GUI 1X crossing versus native root distinction','Full unit-editor matrix beyond core SI fields','All-entity stale mutation matrix']))
