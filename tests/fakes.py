from __future__ import annotations

from math import pi
from types import SimpleNamespace


class Captured:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        for key, value in kwargs.items():
            setattr(self, key, value)


class FakeMaterial(Captured):
    pass


class FakeShaftElement(Captured):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.n_l = self.n
        self.n_r = self.n + 1
        odl = float(self.odl)
        odr = float(self.odr)
        idl = float(self.idl)
        idr = float(self.idr)
        od = 0.5 * (odl + odr)
        inner = 0.5 * (idl + idr)
        self.Ie = pi * (od**4 - inner**4) / 64.0
        self.dof_global_index = None


class FakeDiskElement(Captured):
    pass


class FakePointMass(Captured):
    pass


class FakeBearingElement(Captured):
    pass


class FakeBallBearingElement(Captured):
    pass


class FakeRollerBearingElement(Captured):
    pass


class FakeCylindricalBearing(Captured):
    pass


class FakePlainJournal(Captured):
    pass


class FakeTiltingPad(Captured):
    pass


class ArrayLike(list):
    def tolist(self):
        return list(self)


class MatrixLike(list):
    def tolist(self):
        return [list(row) for row in self]


class ModalResult:
    speed = 0.0
    wd = ArrayLike([100.0, 200.0])
    wn = ArrayLike([101.0, 201.0])
    damping_ratio = ArrayLike([0.01, 0.02])
    log_dec = ArrayLike([0.063, 0.126])


class CriticalResult:
    damping_ratio = ArrayLike([0.01, 0.02])
    log_dec = ArrayLike([0.063, 0.126])
    whirl_direction = ArrayLike(["Forward", "Backward"])

    def wd(self, units="rad/s"):
        return ArrayLike([600.0, 1200.0]) if units == "rpm" else ArrayLike([62.83, 125.66])

    def wn(self, units="rad/s"):
        return ArrayLike([610.0, 1210.0]) if units == "rpm" else ArrayLike([63.88, 126.71])


class CampbellResult:
    speed_range = ArrayLike([0.0, 100.0])
    wd = MatrixLike([[100.0, 200.0], [110.0, 210.0]])
    log_dec = MatrixLike([[0.1, 0.2], [0.11, 0.21]])
    damping_ratio = MatrixLike([[0.01, 0.02], [0.011, 0.021]])
    whirl_values = MatrixLike([[1.0, 0.0], [1.0, 0.0]])


class StaticResult:
    nodes = ArrayLike([0, 1])
    nodes_pos = ArrayLike([0.0, 1.0])
    deformation = ArrayLike([0.0, -1e-5])
    bearing_forces = {0: 100.0}
    disk_forces = {0: -50.0}


class FakeRotor:
    number_dof = 6

    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self.shaft_elements = list(kwargs.get("shaft_elements", []))
        self.disk_elements = list(kwargs.get("disk_elements", []))
        self.bearing_elements = list(kwargs.get("bearing_elements", []))
        self.point_mass_elements = list(kwargs.get("point_mass_elements", []))
        nodes = [0]
        for element in self.shaft_elements:
            nodes.extend([int(element.n), int(element.n) + 1])
        for element in [*self.disk_elements, *self.bearing_elements, *self.point_mass_elements]:
            if hasattr(element, "n"):
                nodes.append(int(element.n))
            linked = getattr(element, "n_link", None)
            if linked is not None:
                nodes.append(int(linked))
        self.ndof = (max(nodes) + 1) * self.number_dof
        self.calls = []

    def K(self, frequency):
        import numpy as np
        return np.zeros((self.ndof, self.ndof), dtype=float)

    def run_modal(self, **kwargs):
        self.calls.append(("modal", kwargs))
        result = ModalResult()
        result.speed = kwargs["speed"]
        return result

    def run_critical_speed(self, **kwargs):
        self.calls.append(("critical", kwargs))
        return CriticalResult()

    def run_campbell(self, **kwargs):
        self.calls.append(("campbell", kwargs))
        result = CampbellResult()
        result.speed_range = ArrayLike(kwargs["speed_range"])
        return result

    def run_static(self):
        self.calls.append(("static", {}))
        return StaticResult()


class FakeRoss(SimpleNamespace):
    __version__ = "2.3.0-test"
    Material = FakeMaterial
    ShaftElement = FakeShaftElement
    DiskElement = FakeDiskElement
    PointMass = FakePointMass
    BearingElement = FakeBearingElement
    BallBearingElement = FakeBallBearingElement
    RollerBearingElement = FakeRollerBearingElement
    CylindricalBearing = FakeCylindricalBearing
    PlainJournal = FakePlainJournal
    TiltingPad = FakeTiltingPad
    Rotor = FakeRotor
