from __future__ import annotations

from dataclasses import asdict, dataclass
from math import isfinite, sqrt
from typing import Iterable, Sequence

from ..domain import UmpFormulation, UMPRegionSpec

LEGACY_KGF_MM2_TO_N_M2 = 9.80665e6
ROTORDIN_LEGACY_THRESHOLD_N_M2 = 0.1
ROTORDIN_LEGACY_MAX_REGIONS = 5


@dataclass(frozen=True, slots=True)
class UMPElementSpan:
    """One native ROSS shaft element span used for global UMP assembly."""

    node: int
    start_mm: float
    end_mm: float

    @property
    def length_m(self) -> float:
        return (self.end_mm - self.start_mm) / 1000.0

    @property
    def midpoint_mm(self) -> float:
        return 0.5 * (self.start_mm + self.end_mm)


@dataclass(frozen=True, slots=True)
class UMPElementContribution:
    """Audit record for one UMP region contribution to one shaft element."""

    node: int
    start_mm: float
    end_mm: float
    region_tag: str
    formulation: str
    kxx_prime_n_m2: float
    kyy_prime_n_m2: float
    kxy_prime_n_m2: float
    kyx_prime_n_m2: float
    legacy_rotary_term: bool
    matrix_frobenius_norm: float

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class UMPAssembly:
    matrix: object
    contributions: list[UMPElementContribution]

    def audit_dict(self) -> dict:
        formulations = sorted({item.formulation for item in self.contributions})
        return {
            "active": bool(self.contributions),
            "formulations": formulations,
            "element_contributions": [item.to_dict() for item in self.contributions],
            "rotordin_legacy_contract": {
                "threshold_n_m2": ROTORDIN_LEGACY_THRESHOLD_N_M2,
                "max_regions": ROTORDIN_LEGACY_MAX_REGIONS,
                "undefined_region_pointer_bug_emulated": False,
                "mkb_contamination_bug_emulated": False,
            },
        }


def legacy_ump_to_si(value: float) -> float:
    """Explicitly convert kgf/mm² to N/m² for externally documented data.

    RotorDin project import does *not* call this conversion unless the source unit
    is explicitly declared as kgf/mm².  The historical UI label is not sufficient
    evidence for an automatic conversion.
    """

    value = float(value)
    if not isfinite(value) or value < 0:
        raise ValueError("Legacy UMP value must be a finite non-negative number.")
    return value * LEGACY_KGF_MM2_TO_N_M2


def _zero_matrix(size: int) -> list[list[float]]:
    return [[0.0 for _ in range(size)] for _ in range(size)]


def _shape_matrix(length_m: float) -> list[list[float]]:
    r"""Return \int N^T N dz for cubic Hermite interpolation."""

    length = float(length_m)
    if not isfinite(length) or length <= 0:
        raise ValueError("UMP element length must be finite and positive.")
    l2 = length * length
    raw = [
        [156.0, 22.0 * length, 54.0, -13.0 * length],
        [22.0 * length, 4.0 * l2, 13.0 * length, -3.0 * l2],
        [54.0, 13.0 * length, 156.0, -22.0 * length],
        [-13.0 * length, -3.0 * l2, -22.0 * length, 4.0 * l2],
    ]
    scale = length / 420.0
    return [[scale * value for value in row] for row in raw]


def _legacy_rotary_shape_matrix(length_m: float) -> list[list[float]]:
    """Return RotorDin ``coemas`` ln2 block for one bending plane.

    This is the historical rotary-inertia mass block that is inadvertently added
    to the UMP matrix when ``coemas(..., ie(r), su)`` is called in ``matrizes.f``.
    """

    length = float(length_m)
    if not isfinite(length) or length <= 0:
        raise ValueError("UMP element length must be finite and positive.")
    l2 = length * length
    return [
        [36.0, 3.0 * length, -36.0, 3.0 * length],
        [3.0 * length, 4.0 * l2, -3.0 * length, -1.0 * l2],
        [-36.0, -3.0 * length, 36.0, -3.0 * length],
        [3.0 * length, -1.0 * l2, -3.0 * length, 4.0 * l2],
    ]


def _validate_tensor(kxx: float, kyy: float, kxy: float, kyx: float) -> None:
    values = (kxx, kyy, kxy, kyx)
    if not all(isfinite(float(value)) for value in values):
        raise ValueError("UMP stiffness tensor values must be finite.")
    if kxx < 0 or kyy < 0:
        raise ValueError("UMP direct stiffness magnitudes kxx' and kyy' cannot be negative.")


def consistent_ump_matrix(
    kxx_prime_n_m2: float,
    length_m: float,
    kyy_prime_n_m2: float | None = None,
    kxy_prime_n_m2: float = 0.0,
    kyx_prime_n_m2: float = 0.0,
) -> list[list[float]]:
    r"""Return the 12x12 corrected consistent UMP matrix.

    The lateral force density is ``f = K'_EM u``.  ROSS uses local DOFs
    ``[x, y, z, alpha, beta, theta]`` at each node.  The y-plane Hermite slope
    is ``-alpha``, hence the sign transform in the y blocks.
    """

    kxx = float(kxx_prime_n_m2)
    kyy = kxx if kyy_prime_n_m2 is None else float(kyy_prime_n_m2)
    kxy = float(kxy_prime_n_m2)
    kyx = float(kyx_prime_n_m2)
    _validate_tensor(kxx, kyy, kxy, kyx)

    h = _shape_matrix(length_m)
    out = _zero_matrix(12)
    x_dofs = (0, 4, 6, 10)
    y_dofs = (1, 3, 7, 9)
    signs = (1.0, -1.0, 1.0, -1.0)

    for i in range(4):
        for j in range(4):
            hij = h[i][j]
            out[x_dofs[i]][x_dofs[j]] += kxx * hij
            out[x_dofs[i]][y_dofs[j]] += kxy * hij * signs[j]
            out[y_dofs[i]][x_dofs[j]] += kyx * signs[i] * hij
            out[y_dofs[i]][y_dofs[j]] += kyy * signs[i] * hij * signs[j]
    return out


def rotordin_legacy_ump_matrix(
    stiffness_per_length_n_m2: float,
    length_m: float,
    density_kg_m3: float,
    second_moment_area_m4: float,
) -> list[list[float]]:
    r"""Return deterministic RotorDin legacy-compatible UMP matrix.

    It reproduces the *defined* historical ``coemas`` behavior:

    ``k'L/420 A(L) + rho*I/(30L) B(L)`` for ``k' > 0.1``.

    The undefined ``nup`` region-pointer behavior and ``mkb`` contamination are
    intentionally not emulated.
    """

    k = float(stiffness_per_length_n_m2)
    length = float(length_m)
    rho = float(density_kg_m3)
    inertia = float(second_moment_area_m4)
    if not all(isfinite(value) for value in (k, length, rho, inertia)):
        raise ValueError("RotorDin legacy UMP parameters must be finite.")
    if k < 0 or length <= 0 or rho <= 0 or inertia < 0:
        raise ValueError("RotorDin legacy UMP parameters are outside their physical ranges.")
    if k <= ROTORDIN_LEGACY_THRESHOLD_N_M2:
        return _zero_matrix(12)

    out = consistent_ump_matrix(k, length)
    b = _legacy_rotary_shape_matrix(length)
    scale = rho * inertia / (30.0 * length)
    x_dofs = (0, 4, 6, 10)
    y_dofs = (1, 3, 7, 9)
    signs = (1.0, -1.0, 1.0, -1.0)
    for i in range(4):
        for j in range(4):
            value = scale * b[i][j]
            out[x_dofs[i]][x_dofs[j]] += value
            out[y_dofs[i]][y_dofs[j]] += signs[i] * value * signs[j]
    return out


def _matrix_norm(matrix: Sequence[Sequence[float]]) -> float:
    return sqrt(sum(float(value) ** 2 for row in matrix for value in row))


def _active_regions(regions: Sequence[UMPRegionSpec], midpoint_mm: float) -> list[UMPRegionSpec]:
    return [
        region
        for region in regions
        if region.start_mm - 1e-9 <= midpoint_mm <= region.end_mm + 1e-9
    ]


def _local_matrix_for_region(region: UMPRegionSpec, shaft_element, length_m: float) -> tuple[list[list[float]], bool]:
    if region.formulation == UmpFormulation.PHYSICAL_CORRECTED:
        return (
            consistent_ump_matrix(
                region.kxx_prime_n_m2,
                length_m,
                region.kyy_prime_n_m2,
                region.kxy_prime_n_m2,
                region.kyx_prime_n_m2,
            ),
            False,
        )

    if region.formulation == UmpFormulation.ROTORDIN_LEGACY_COMPAT:
        material = getattr(shaft_element, "material", None)
        rho = getattr(material, "rho", None)
        inertia = getattr(shaft_element, "Ie", None)
        if rho is None or inertia is None:
            raise ValueError("RotorDin legacy UMP assembly requires shaft material density and Ie from ROSS.")
        return (
            rotordin_legacy_ump_matrix(
                region.kxx_prime_n_m2,
                length_m,
                rho,
                inertia,
            ),
            region.kxx_prime_n_m2 > ROTORDIN_LEGACY_THRESHOLD_N_M2,
        )

    raise ValueError(f"Unsupported UMP formulation: {region.formulation}")


def assemble_ump_global(
    rotor,
    regions: Sequence[UMPRegionSpec],
    element_spans: Sequence[UMPElementSpan],
) -> UMPAssembly:
    """Assemble frequency-independent ``K_UMP`` in native ROSS global DOFs."""

    import numpy as np

    regions = tuple(regions)
    legacy_regions = [region for region in regions if region.formulation == UmpFormulation.ROTORDIN_LEGACY_COMPAT]
    if len(legacy_regions) > ROTORDIN_LEGACY_MAX_REGIONS:
        raise ValueError(
            f"RotorDin legacy compatibility accepts at most {ROTORDIN_LEGACY_MAX_REGIONS} UMP regions."
        )

    matrix = np.zeros((int(rotor.ndof), int(rotor.ndof)), dtype=float)
    contributions: list[UMPElementContribution] = []
    shaft_by_node = {int(element.n): element for element in rotor.shaft_elements}

    for span in element_spans:
        active = _active_regions(regions, span.midpoint_mm)
        if not active:
            continue
        shaft = shaft_by_node.get(int(span.node))
        if shaft is None:
            raise ValueError(f"UMP span node {span.node} has no matching ROSS ShaftElement.")
        dof_global_index = getattr(shaft, "dof_global_index", None)
        if dof_global_index is None:
            dofs = [6 * span.node + i for i in range(6)] + [6 * (span.node + 1) + i for i in range(6)]
        else:
            dofs = list(dof_global_index.values())
        if len(dofs) != 12:
            raise ValueError("UMP assembly is verified only for 12-DOF ROSS shaft elements.")

        for region in active:
            local, legacy_rotary = _local_matrix_for_region(region, shaft, span.length_m)
            local_array = np.asarray(local, dtype=float)
            matrix[np.ix_(dofs, dofs)] += local_array
            if np.linalg.norm(local_array) <= 0.0:
                continue
            contributions.append(
                UMPElementContribution(
                    node=span.node,
                    start_mm=span.start_mm,
                    end_mm=span.end_mm,
                    region_tag=region.tag,
                    formulation=region.formulation.value,
                    kxx_prime_n_m2=region.kxx_prime_n_m2,
                    kyy_prime_n_m2=region.kyy_prime_n_m2,
                    kxy_prime_n_m2=region.kxy_prime_n_m2,
                    kyx_prime_n_m2=region.kyx_prime_n_m2,
                    legacy_rotary_term=legacy_rotary,
                    matrix_frobenius_norm=_matrix_norm(local),
                )
            )

    return UMPAssembly(matrix=matrix, contributions=contributions)


__all__ = [
    "LEGACY_KGF_MM2_TO_N_M2",
    "ROTORDIN_LEGACY_MAX_REGIONS",
    "ROTORDIN_LEGACY_THRESHOLD_N_M2",
    "UMPAssembly",
    "UMPElementContribution",
    "UMPElementSpan",
    "assemble_ump_global",
    "consistent_ump_matrix",
    "legacy_ump_to_si",
    "rotordin_legacy_ump_matrix",
]
