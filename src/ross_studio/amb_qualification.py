"""Executed AMB coefficient/assembly parity gate for the pinned production API."""
from math import pi
import numpy as np
from .domain import BearingSpec, BearingGroup, MaterialSpec, RotorProject, ShaftSection
from .bearing_studio_service import BearingStudioService
from .ross_backend import RossBackend


def qualify_amb_assembly(rs):
    inputs = dict(speed_rpm=[500.,1000.,3000.],g0_m=1e-3,i0_a=1.,ag_m2=1e-4,
                  nw=200.,alpha_rad=pi/8,k_amp=1.,k_sense=1.,kp_pid=1500.,
                  kd_pid=10.,ki_pid=100.,n_f_rad_s=10000.,sensors_axis_rotation_rad=pi/4)
    p=RotorProject(name='AMB parity',materials={'Steel':MaterialSpec()},
        shaft_sections=[ShaftSection(1,300.,40.,fe_elements=1)],
        bearings=[BearingSpec('AMB',0.,group=BearingGroup.AMB,ross_class='MagneticBearingElement')])
    service=BearingStudioService(rs)
    calculated=service.calculate(p,0,'MagneticBearingElement',inputs)
    service.apply(p,0,calculated)
    rotor=RossBackend(rs).build_rotor(p).rotor
    actual=rotor.bearing_elements[0]
    expected=rs.MagneticBearingElement(n=0,g0=.001,i0=1.,ag=.0001,nw=200.,
        frequency=np.array([500.,1000.,3000.])*2*pi/60,alpha=pi/8,
        k_amp=1.,k_sense=1.,kp_pid=1500.,kd_pid=10.,ki_pid=100.,n_f=10000.,sensors_axis_rotation=pi/4)
    if type(actual).__name__!='MagneticBearingElement':
        raise AssertionError('AMB was not materialized as MagneticBearingElement')
    maximum=0.
    for rpm in inputs['speed_rpm']:
        for name in ('K','C'):
            a=getattr(actual,name)(rpm*2*pi/60)
            b=getattr(expected,name)(rpm*2*pi/60)
            np.testing.assert_allclose(a,b,rtol=1e-12,atol=1e-12)
            maximum=max(maximum,float(np.max(np.abs(a-b))))
    return {'status':'PASS','native_class':type(actual).__name__,'max_absolute_kc_error':maximum,
            'scope':'calculate/apply/native element K/C parity; full AMB sensitivity separately required'}
