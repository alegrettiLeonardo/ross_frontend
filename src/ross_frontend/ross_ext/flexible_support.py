from __future__ import annotations

from functools import lru_cache


def _coefficient_matrix(element, family: str, frequency: float):
    """Return a native ROSS 3x3 translational coefficient matrix lazily.

    NumPy stays out of module import time so the lightweight core CI can still
    exercise the fake ROSS adapter without installing the scientific stack.
    """

    import numpy as np

    if family == "k":
        xx = element.kxx_interpolated(frequency)
        yy = element.kyy_interpolated(frequency)
        xy = element.kxy_interpolated(frequency)
        yx = element.kyx_interpolated(frequency)
        zz = element.kzz_interpolated(frequency)
    elif family == "c":
        xx = element.cxx_interpolated(frequency)
        yy = element.cyy_interpolated(frequency)
        xy = element.cxy_interpolated(frequency)
        yx = element.cyx_interpolated(frequency)
        zz = element.czz_interpolated(frequency)
    elif family == "m":
        xx = element.mxx_interpolated(frequency)
        yy = element.myy_interpolated(frequency)
        xy = element.mxy_interpolated(frequency)
        yx = element.myx_interpolated(frequency)
        zz = element.mzz_interpolated(frequency)
    else:
        raise ValueError(f"Unsupported coefficient family: {family}")

    return np.asarray(
        [
            [xx, xy, 0.0],
            [yx, yy, 0.0],
            [0.0, 0.0, zz],
        ],
        dtype=float,
    )


def _link_ground_block(matrix):
    """Embed a 3x3 housing-to-ground matrix in the link-node block.

    ROSS orders a linked bearing as ``[rotor xyz, link xyz]``. A support to
    ground must therefore act only on the lower-right block. This is different
    from a regular BearingElement with ``n_link``, which creates the relative
    coupling matrix ``[[A, -A], [-A, A]]``.
    """

    import numpy as np

    zeros = np.zeros_like(matrix)
    return np.block([[zeros, zeros], [zeros, matrix]])


@lru_cache(maxsize=None)
def make_flexible_support_element_class(bearing_element_class):
    """Create a ROSS-compatible support element without changing upstream.

    The element deliberately keeps ``n`` on the physical shaft/bearing station
    because ROSS 2.3.0 only permits out-of-shaft nodes as ``n_link`` targets.
    Its matrices act exclusively on those linked housing DOFs:

    ``M_h = diag(m_h, m_h, 0)``
    ``C_h = C_support``
    ``K_h = K_support``

    Combined with the regular rotor-bearing ``BearingElement(n, n_link=...)``
    this produces the intended topology

    rotor -- Kb/Cb -- housing(Mh) -- Ks/Cs -- ground

    while retaining the housing DOFs in the native ROSS global system.
    """

    class FlexibleSupportElement(bearing_element_class):
        _legend_group = "Bearing"

        def __init__(
            self,
            *,
            n: int,
            n_link: int,
            kxx,
            kyy,
            kxy=0.0,
            kyx=0.0,
            cxx=0.0,
            cyy=0.0,
            cxy=0.0,
            cyx=0.0,
            housing_mass_kg: float = 0.0,
            tag: str | None = None,
        ):
            self.housing_mass_kg = float(housing_mass_kg)
            super().__init__(
                n=n,
                n_link=n_link,
                kxx=kxx,
                kyy=kyy,
                kxy=kxy,
                kyx=kyx,
                cxx=cxx,
                cyy=cyy,
                cxy=cxy,
                cyx=cyx,
                mxx=self.housing_mass_kg,
                myy=self.housing_mass_kg,
                mzz=0.0,
                tag=tag,
            )

        def K(self, frequency):
            return _link_ground_block(_coefficient_matrix(self, "k", frequency))

        def C(self, frequency):
            return _link_ground_block(_coefficient_matrix(self, "c", frequency))

        def M(self, frequency):
            return _link_ground_block(_coefficient_matrix(self, "m", frequency))

    FlexibleSupportElement.__name__ = "RossFlexibleSupportElement"
    FlexibleSupportElement.__qualname__ = "RossFlexibleSupportElement"
    FlexibleSupportElement.__module__ = __name__
    return FlexibleSupportElement


__all__ = ["make_flexible_support_element_class"]
