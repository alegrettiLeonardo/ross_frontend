from __future__ import annotations

from functools import lru_cache


def rotordin_intlag(x_points, y_points, x):
    """Reproduce RotorDin ``matfun.f:intlag``.

    Inside the table range RotorDin selects three neighboring points and applies
    a local quadratic Lagrange polynomial. Outside the range it extrapolates
    linearly from the nearest two points. The algorithm is intentionally not a
    cubic spline.
    """
    import numpy as np

    xp = np.asarray(x_points, dtype=float)
    yp = np.asarray(y_points, dtype=float)
    if xp.ndim != 1 or yp.ndim != 1 or len(xp) != len(yp) or len(xp) < 2:
        raise ValueError("RotorDin TABLE interpolation requires equal 1D vectors with at least two points.")
    if np.any(np.diff(xp) <= 0):
        raise ValueError("RotorDin TABLE interpolation speed points must be strictly increasing.")

    def one(value: float) -> float:
        value = float(value)
        n = len(xp)
        for ii in range(1, n - 1):
            if abs(value - xp[ii]) <= 1e-15:
                return float(yp[ii])
            if xp[ii] > value:
                result = 0.0
                for jj in range(ii - 1, ii + 2):
                    term = float(yp[jj])
                    for kk in range(ii - 1, ii + 2):
                        if kk != jj:
                            term *= (value - xp[kk]) / (xp[jj] - xp[kk])
                    result += term
                return result
        if value < xp[0]:
            return float((value - xp[0]) * (yp[1] - yp[0]) / (xp[1] - xp[0]) + yp[0])
        return float((value - xp[-2]) * (yp[-1] - yp[-2]) / (xp[-1] - xp[-2]) + yp[-2])

    values = np.asarray(x, dtype=float)
    if values.ndim == 0:
        return one(float(values))
    flat = np.asarray([one(v) for v in values.ravel()], dtype=float)
    return flat.reshape(values.shape)


@lru_cache(maxsize=None)
def make_rotordin_legacy_bearing_class(base_cls):
    """Create a ROSS BearingElement using RotorDin TABLE interpolation."""

    class RotorDinLegacyBearingElement(base_cls):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            if self.frequency is None or len(self.frequency) < 2:
                self.rotordin_table_interpolation = False
                return
            self.rotordin_table_interpolation = True
            for name in (
                "kxx", "kyy", "kxy", "kyx", "kzz",
                "cxx", "cyy", "cxy", "cyx", "czz",
                "mxx", "myy", "mxy", "myx", "mzz",
            ):
                coefficient = getattr(self, name)
                if len(coefficient) == len(self.frequency):
                    setattr(
                        self,
                        f"{name}_interpolated",
                        lambda value, xp=self.frequency.copy(), yp=coefficient.copy(): rotordin_intlag(xp, yp, value),
                    )

    RotorDinLegacyBearingElement.__name__ = "RotorDinLegacyBearingElement"
    RotorDinLegacyBearingElement.__qualname__ = "RotorDinLegacyBearingElement"
    RotorDinLegacyBearingElement.__module__ = __name__
    return RotorDinLegacyBearingElement


__all__ = ["make_rotordin_legacy_bearing_class", "rotordin_intlag"]
