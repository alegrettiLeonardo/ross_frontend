from math import isclose, pi

from ross_frontend.backends.coordinates import rpm_to_rad_s, rotordin_xz_to_ross_xy


def test_rotordin_xz_maps_to_ross_xy_without_axial_leakage():
    c = rotordin_xz_to_ross_xy(
        kxx=1,
        kzz=2,
        kxz=3,
        kzx=4,
        cxx=5,
        czz=6,
        cxz=7,
        czx=8,
    )
    assert (c.kxx, c.kyy, c.kxy, c.kyx) == (1, 2, 3, 4)
    assert (c.cxx, c.cyy, c.cxy, c.cyx) == (5, 6, 7, 8)
    assert not hasattr(c, "kzz")


def test_rpm_conversion():
    assert isclose(rpm_to_rad_s(60), 2 * pi)
    assert all(isclose(a, b) for a, b in zip(rpm_to_rad_s([0, 60]), [0, 2 * pi]))
