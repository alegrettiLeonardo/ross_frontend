"""Independent numerical parity ledger and reproducible size benchmarks."""
from pathlib import Path
import csv, json, os, runpy, tempfile, time, resource
import numpy as np
import ross as rs
from PySide6.QtWidgets import QApplication
from ross_studio.pages.rotor_workspace import RotorModelPage
from ross_studio.models import ProjectModel
from ross_studio.project_io import save_project, load_project
from ross_studio.ross_backend import RossBackend
fixture=runpy.run_path(str(Path(__file__).resolve().parents[1]/'tests/test_engineering_qualification.py'))
p=fixture['small_project'](); a=RossBackend().build_rotor(p).rotor; b=fixture['independent_rotor']()
rows=[]
def compare(name,x,y,rtol,atol):
 x=np.asarray(x);y=np.asarray(y);delta=np.abs(x-y)
 absolute=float(delta.max()); scale=float(np.max(np.abs(y)))
 ok=bool(np.allclose(x,y,rtol=rtol,atol=atol))
 rows.append(dict(quantity=name,studio_max_abs=float(np.max(np.abs(x))),ross_direct_max_abs=scale,
                  max_absolute_error=absolute,relative_infinity_error=absolute/scale if scale else 0.,rtol=rtol,atol=atol,status='PASS' if ok else 'FAIL'))
 if not ok: raise AssertionError(name)
for name in ('M','K','C','G'):
 args=() if name=='G' else (100.,)
 compare(name,getattr(a,name)(*args),getattr(b,name)(*args),1e-12,1e-10)
compare('mass',a.m,b.m,1e-12,1e-12)
compare('node_positions',a.nodes_pos,b.nodes_pos,1e-14,1e-15)
ma=a.run_modal(100.);mb=b.run_modal(100.)
compare('natural_frequencies',ma.wn,mb.wn,1e-7,1e-7)
# Complex modal vectors have arbitrary phase; use normalized MAC rather than raw entries.
va=ma.evectors[:a.ndof,:len(ma.wn)]; vb=mb.evectors[:b.ndof,:len(mb.wn)]
mac=np.abs(np.sum(va.conj()*vb,axis=0))**2/(np.sum(abs(va)**2,axis=0)*np.sum(abs(vb)**2,axis=0))
compare('modal_MAC',mac,np.ones_like(mac),1e-7,1e-9)
speed=np.linspace(50,200,5)
compare('unbalance',a.run_unbalance_response(3,1e-4,.3,speed).forced_resp,b.run_unbalance_response(3,1e-4,.3,speed).forced_resp,1e-7,1e-13)
compare('critical_speed',a.run_critical_speed(num_modes=4)._wd,b.run_critical_speed(num_modes=4)._wd,1e-6,1e-6)
out=Path('artifacts/engineering');out.mkdir(parents=True,exist_ok=True)
with (out/'independent_parity.csv').open('w') as f:
 w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
app=QApplication.instance() or QApplication([])
bench=[]
for label,n in [('SMALL',3),('MEDIUM',12),('LARGE',30)]:
 p=fixture['small_project']()
 for s in p.shaft_sections: s.fe_elements=n
 row={'size':label,'shaft_elements':2*n}
 def timed(name,fn):
  t=time.perf_counter();r=fn();row[name+'_s']=time.perf_counter()-t;return r
 r=timed('build',lambda: RossBackend().build_rotor(p).rotor);row['dof']=r.ndof
 timed('modal',lambda:r.run_modal(100.,num_modes=12))
 timed('campbell',lambda:r.run_campbell(np.linspace(0,200,5),frequencies=4))
 timed('unbalance',lambda:r.run_unbalance_response(n,1e-4,0.,np.linspace(50,200,5)))
 t=np.linspace(0,.01,21);force=np.zeros((len(t),r.ndof));force[:,0]=1.
 timed('time_response',lambda:r.run_time_response(100.,force,t))
 model=ProjectModel.from_engineering(p)
 with tempfile.TemporaryDirectory() as d:
  target=timed('save',lambda:save_project(model,Path(d)/'p.rossproj'))
  timed('load',lambda:load_project(target))
 page=timed('gui_load',lambda:RotorModelPage(model));page.close();page.deleteLater();app.processEvents()
 row['process_peak_rss_mib']=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024
 bench.append(row)
 (out/'benchmarks.json').write_text(json.dumps(bench,indent=2))
 print(json.dumps(row),flush=True)
print('Independent parity PASS')
