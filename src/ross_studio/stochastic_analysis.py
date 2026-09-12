from __future__ import annotations

from dataclasses import dataclass, field
from math import pi
from time import perf_counter
from typing import Any, Callable, Literal

import numpy as np

from .domain import EngineeringError, RotorProject
from .ross_backend import RossBuildResult, RossModelBuilder


DistributionName = Literal["normal", "uniform"]
ScaleMode = Literal["relative", "absolute"]
TargetFamily = Literal["material", "shaft", "disk", "bearing", "point_mass"]


@dataclass(slots=True, frozen=True)
class RandomInputSpec:
    """Sampling rule used at the ROSS stochastic boundary.

    ``relative`` values are percentages. For a normal distribution ``a`` is the
    mean percentage deviation and ``b`` is the standard deviation in percent.
    For a uniform distribution they are the lower/upper percentage deviations.
    ``absolute`` values use the SI unit of the target parameter.
    """

    distribution: DistributionName = "normal"
    scale: ScaleMode = "relative"
    a: float = 0.0
    b: float = 5.0

    def validate(self) -> None:
        if self.distribution not in {"normal", "uniform"}:
            raise EngineeringError(f"Unsupported stochastic distribution {self.distribution!r}.")
        if self.scale not in {"relative", "absolute"}:
            raise EngineeringError(f"Unsupported stochastic scale {self.scale!r}.")
        if not np.isfinite(self.a) or not np.isfinite(self.b):
            raise EngineeringError("Stochastic distribution parameters must be finite.")
        if self.distribution == "normal" and self.b < 0:
            raise EngineeringError("Normal-distribution standard deviation cannot be negative.")
        if self.distribution == "uniform" and self.b <= self.a:
            raise EngineeringError("Uniform-distribution upper bound must be greater than lower bound.")


@dataclass(slots=True, frozen=True)
class StochasticVariableSpec:
    family: TargetFamily
    index: int
    parameter: str
    sampling: RandomInputSpec = RandomInputSpec()

    @property
    def key(self) -> str:
        return f"{self.family}:{self.index}:{self.parameter}"

    def validate(self) -> None:
        if self.index < 0:
            raise EngineeringError(f"Stochastic target index must be >= 0; received {self.index}.")
        if not self.parameter:
            raise EngineeringError("Stochastic parameter cannot be empty.")
        self.sampling.validate()


@dataclass(slots=True, frozen=True)
class StochasticSamplingConfig:
    samples: int = 20
    seed: int = 12345
    variables: tuple[StochasticVariableSpec, ...] = ()

    def validate(self) -> None:
        if isinstance(self.samples, bool) or self.samples < 2 or self.samples > 10000:
            raise EngineeringError(f"Stochastic sample count must be between 2 and 10000; received {self.samples!r}.")
        if isinstance(self.seed, bool) or self.seed < 0:
            raise EngineeringError(f"Stochastic seed must be a non-negative integer; received {self.seed!r}.")
        if not self.variables:
            raise EngineeringError(
                "At least one structural ST_* random variable is required. ROSS 2.3 ST_Rotor uses an ST_* element to establish RV_size."
            )
        keys: set[str] = set()
        for variable in self.variables:
            variable.validate()
            if variable.key in keys:
                raise EngineeringError(f"Duplicate stochastic variable {variable.key!r}.")
            keys.add(variable.key)


@dataclass(slots=True, frozen=True)
class StochasticTarget:
    family: TargetFamily
    index: int
    parameter: str
    label: str
    nominal: float
    units: str
    randomizable: bool = True
    reason: str = ""

    @property
    def key(self) -> str:
        return f"{self.family}:{self.index}:{self.parameter}"


@dataclass(slots=True)
class StochasticInputWrapper:
    label: str
    family: str
    index: int
    native: Any
    variables: tuple[str, ...]


@dataclass(slots=True)
class StochasticBuildResult:
    deterministic: RossBuildResult
    stochastic_rotor: Any
    sampling: StochasticSamplingConfig
    input_wrappers: tuple[StochasticInputWrapper, ...]
    sampled_values: dict[str, np.ndarray]
    warnings: tuple[str, ...] = ()

    @property
    def sample_count(self) -> int:
        return int(self.stochastic_rotor.RV_size)


@dataclass(slots=True, frozen=True)
class StochasticCampbellRequest:
    min_rpm: float
    max_rpm: float
    points: int = 21
    frequencies: int = 6
    frequency_type: str = "wd"

    def validate(self) -> None:
        if self.min_rpm < 0 or self.max_rpm <= self.min_rpm:
            raise EngineeringError("Stochastic Campbell requires 0 <= min_rpm < max_rpm.")
        if not 3 <= self.points <= 401:
            raise EngineeringError("Stochastic Campbell points must be between 3 and 401.")
        if not 1 <= self.frequencies <= 32:
            raise EngineeringError("Stochastic Campbell frequency count must be between 1 and 32.")
        if self.frequency_type not in {"wd", "wn"}:
            raise EngineeringError("Stochastic Campbell frequency_type must be 'wd' or 'wn'.")


@dataclass(slots=True, frozen=True)
class StochasticFrequencyRequest:
    min_rpm: float
    max_rpm: float
    points: int
    input_node: int
    input_dof: int
    output_node: int
    output_dof: int
    modes: tuple[int, ...] = ()

    def validate(self) -> None:
        if self.min_rpm < 0 or self.max_rpm <= self.min_rpm:
            raise EngineeringError("Stochastic frequency response requires 0 <= min_rpm < max_rpm.")
        if not 3 <= self.points <= 2001:
            raise EngineeringError("Stochastic frequency-response points must be between 3 and 2001.")
        if min(self.input_node, self.output_node) < 0:
            raise EngineeringError("Stochastic frequency-response nodes must be non-negative.")
        if min(self.input_dof, self.output_dof) < 0:
            raise EngineeringError("Stochastic local DOF indices must be non-negative.")


@dataclass(slots=True, frozen=True)
class StochasticUnbalanceRequest:
    min_rpm: float
    max_rpm: float
    points: int
    node: int
    magnitude_kg_m: float
    phase_deg: float = 0.0
    magnitude_random: RandomInputSpec | None = None
    phase_random: RandomInputSpec | None = None
    modes: tuple[int, ...] = ()

    def validate(self) -> None:
        if self.min_rpm < 0 or self.max_rpm <= self.min_rpm:
            raise EngineeringError("Stochastic unbalance response requires 0 <= min_rpm < max_rpm.")
        if not 3 <= self.points <= 2001:
            raise EngineeringError("Stochastic unbalance points must be between 3 and 2001.")
        if self.node < 0 or self.magnitude_kg_m < 0:
            raise EngineeringError("Stochastic unbalance node and magnitude must be non-negative.")
        if self.magnitude_random is not None:
            self.magnitude_random.validate()
        if self.phase_random is not None:
            self.phase_random.validate()


@dataclass(slots=True, frozen=True)
class StochasticTimeRequest:
    speed_rpm: float
    duration_s: float
    points: int
    force_node: int
    force_amplitude_n: float
    force_frequency_hz: float
    force_random: RandomInputSpec | None = None

    def validate(self) -> None:
        if self.speed_rpm < 0 or self.duration_s <= 0:
            raise EngineeringError("Stochastic time response requires speed >= 0 and duration > 0.")
        if not 8 <= self.points <= 200000:
            raise EngineeringError("Stochastic time-response points must be between 8 and 200000.")
        if self.force_node < 0 or self.force_frequency_hz < 0:
            raise EngineeringError("Stochastic force node and excitation frequency must be non-negative.")
        if self.force_random is not None:
            self.force_random.validate()


@dataclass(slots=True)
class StochasticAnalysisResult:
    kind: str
    build: StochasticBuildResult
    request: Any
    native: Any
    stage_elapsed_s: dict[str, float] = field(default_factory=dict)

    @property
    def total_elapsed_s(self) -> float:
        return float(sum(self.stage_elapsed_s.values()))


class StochasticRotorService:
    """Native ROSS 2.3 stochastic adapter.

    ROSS Studio only creates the sample arrays and maps deterministic ROSS elements
    to the matching ``ross.stochastic.ST_*`` containers. The Monte-Carlo rotor loop,
    modal/frequency/time integration and result statistics stay inside ``ST_Rotor``.
    """

    BEARING_PARAMETERS = ("kxx", "kxy", "kyx", "kyy", "cxx", "cxy", "cyx", "cyy")
    SHAFT_PARAMETERS = ("L", "idl", "odl", "idr", "odr")
    DISK_PARAMETERS = ("m", "Id", "Ip")
    MATERIAL_PARAMETERS = ("rho", "E", "G_s", "Poisson")

    def __init__(self, builder: RossModelBuilder | None = None) -> None:
        self.builder = builder or RossModelBuilder()

    @staticmethod
    def _draw(rule: RandomInputSpec, samples: int, rng: np.random.Generator) -> np.ndarray:
        rule.validate()
        if rule.distribution == "normal":
            return np.asarray(rng.normal(rule.a, rule.b, samples), dtype=float)
        return np.asarray(rng.uniform(rule.a, rule.b, samples), dtype=float)

    @classmethod
    def _sample_parameter(
        cls,
        nominal: float | np.ndarray,
        rule: RandomInputSpec,
        samples: int,
        rng: np.random.Generator,
    ) -> np.ndarray:
        base = np.asarray(nominal, dtype=float)
        draws = cls._draw(rule, samples, rng)
        if rule.scale == "relative":
            factors = 1.0 + draws / 100.0
            if base.ndim == 0:
                return np.asarray(float(base) * factors, dtype=float)
            return np.asarray(base[..., np.newaxis] * factors, dtype=float)
        if base.ndim == 0:
            return draws
        return np.broadcast_to(draws, (*base.shape, samples)).copy()

    @staticmethod
    def _coefficient_array(element: Any, name: str) -> np.ndarray:
        return np.asarray(getattr(element, name), dtype=float).reshape(-1)

    @staticmethod
    def _is_nonzero(values: Any) -> bool:
        data = np.asarray(values, dtype=float)
        return bool(data.size and np.any(np.abs(data) > 1e-14))

    def available_targets(self, project: RotorProject) -> tuple[StochasticTarget, ...]:
        build = self.builder.build(project, strict=True)
        rotor = build.rotor
        targets: list[StochasticTarget] = []

        for index, (name, material) in enumerate(project.materials.items()):
            values = {
                "rho": (material.density_kg_m3, "kg/m^3"),
                "E": (material.young_pa, "Pa"),
                "G_s": (material.shear_pa, "Pa"),
                "Poisson": (material.poisson, "1"),
            }
            for parameter, (nominal, units) in values.items():
                targets.append(StochasticTarget("material", index, parameter, f"Material {name}", float(nominal), units))

        for index, element in enumerate(rotor.shaft_elements):
            label = str(getattr(element, "tag", None) or f"Shaft element {index}")
            for parameter, units in (("L", "m"), ("idl", "m"), ("odl", "m"), ("idr", "m"), ("odr", "m")):
                targets.append(StochasticTarget("shaft", index, parameter, label, float(getattr(element, parameter)), units))

        for index, element in enumerate(rotor.disk_elements):
            label = str(getattr(element, "tag", None) or f"Disk element {index}")
            native_disk = element.__class__.__name__ == "DiskElement"
            reason = "" if native_disk else (
                "Blocked: this disk is the qualified concentrated rigid-body adapter. ST_DiskElement would lose independent Ix/Iy/Iz."
            )
            for parameter, units in (("m", "kg"), ("Id", "kg*m^2"), ("Ip", "kg*m^2")):
                targets.append(
                    StochasticTarget(
                        "disk", index, parameter, label, float(getattr(element, parameter)), units,
                        randomizable=native_disk, reason=reason,
                    )
                )

        for index, element in enumerate(rotor.bearing_elements):
            label = str(getattr(element, "tag", None) or f"Bearing/Seal element {index}")
            axial = any(self._is_nonzero(getattr(element, name, [0.0])) for name in ("kzz", "czz", "mzz"))
            reason = "" if not axial else (
                "Blocked: ROSS 2.3 ST_BearingElement has no kzz/czz/mzz contract; stochastic conversion would drop axial physics."
            )
            for parameter in self.BEARING_PARAMETERS:
                nominal_values = self._coefficient_array(element, parameter)
                nominal = float(np.mean(nominal_values))
                units = "N/m" if parameter.startswith("k") else "N*s/m"
                targets.append(
                    StochasticTarget(
                        "bearing", index, parameter, label, nominal, units,
                        randomizable=not axial, reason=reason,
                    )
                )

        for index, element in enumerate(rotor.point_mass_elements):
            label = str(getattr(element, "tag", None) or f"Point mass {index}")
            isotropic = getattr(element, "m", None) is not None
            targets.append(
                StochasticTarget(
                    "point_mass", index, "m", label,
                    float(element.m if isotropic else element.mx), "kg",
                    randomizable=isotropic,
                    reason="" if isotropic else "Blocked: ROSS 2.3 ST_PointMass cannot preserve a general mx/my/mz point-mass tensor.",
                )
            )
        return tuple(targets)

    @staticmethod
    def _target_map(targets: tuple[StochasticTarget, ...]) -> dict[str, StochasticTarget]:
        return {target.key: target for target in targets}

    def build(self, project: RotorProject, sampling: StochasticSamplingConfig) -> StochasticBuildResult:
        import ross.stochastic as srs

        project.validate()
        sampling.validate()
        deterministic = self.builder.build(project, strict=True)
        if deterministic.unresolved_positions_mm:
            raise EngineeringError("Stochastic ROSS requires an exact deterministic FE topology before sampling.")

        targets = self._target_map(self.available_targets(project))
        for variable in sampling.variables:
            target = targets.get(variable.key)
            if target is None:
                raise EngineeringError(f"Unknown stochastic target {variable.key!r}.")
            if not target.randomizable:
                raise EngineeringError(target.reason or f"Target {variable.key!r} is blocked.")

        rng = np.random.default_rng(sampling.seed)
        sampled: dict[str, np.ndarray] = {}
        for variable in sampling.variables:
            target = targets[variable.key]
            sampled[variable.key] = self._sample_parameter(target.nominal, variable.sampling, sampling.samples, rng)

        rotor = deterministic.rotor
        shaft_elements: list[Any] = list(rotor.shaft_elements)
        disk_elements: list[Any] = list(rotor.disk_elements)
        bearing_elements: list[Any] = list(rotor.bearing_elements)
        point_mass_elements: list[Any] = list(rotor.point_mass_elements)
        wrappers: list[StochasticInputWrapper] = []
        warnings: list[str] = []

        variables_by_owner: dict[tuple[str, int], dict[str, StochasticVariableSpec]] = {}
        for variable in sampling.variables:
            variables_by_owner.setdefault((variable.family, variable.index), {})[variable.parameter] = variable

        material_items = list(project.materials.items())
        stochastic_materials: dict[str, Any] = {}
        for (family, index), variables in variables_by_owner.items():
            if family != "material":
                continue
            if index >= len(material_items):
                raise EngineeringError(f"Material stochastic index {index} is out of range.")
            name, spec = material_items[index]
            elastic_random = {key for key in variables if key in {"E", "G_s", "Poisson"}}
            if len(elastic_random) > 2:
                raise EngineeringError(
                    f"Material {name!r}: ROSS ST_Material requires exactly two of E/G_s/Poisson; all three cannot be independently randomized."
                )
            elastic_pair = set(elastic_random)
            if len(elastic_pair) < 2:
                if "Poisson" in elastic_pair:
                    elastic_pair.add("E")
                else:
                    elastic_pair.update({"E", "G_s"})
            elastic_pair = set(list(elastic_pair)[:2]) if len(elastic_pair) > 2 else elastic_pair

            kwargs: dict[str, Any] = {"name": spec.name, "rho": spec.density_kg_m3, "color": "#525252"}
            nominal_elastic = {"E": spec.young_pa, "G_s": spec.shear_pa, "Poisson": spec.poisson}
            if "rho" in variables:
                kwargs["rho"] = sampled[f"material:{index}:rho"]
            for key in ("E", "G_s", "Poisson"):
                if key not in elastic_pair:
                    kwargs[key] = None
                elif key in variables:
                    kwargs[key] = sampled[f"material:{index}:{key}"]
                else:
                    kwargs[key] = nominal_elastic[key]
            st_material = srs.ST_Material(**kwargs)
            stochastic_materials[name] = st_material
            wrappers.append(StochasticInputWrapper(f"Material {name}", "material", index, st_material, tuple(variables)))

        for index, element in enumerate(rotor.shaft_elements):
            local = variables_by_owner.get(("shaft", index), {})
            material_name = str(getattr(element.material, "name", ""))
            st_material = stochastic_materials.get(material_name)
            if not local and st_material is None:
                continue
            values: dict[str, Any] = {
                "L": float(element.L), "idl": float(element.idl), "odl": float(element.odl),
                "idr": float(element.idr), "odr": float(element.odr),
            }
            is_random: list[str] = []
            for parameter in self.SHAFT_PARAMETERS:
                variable = local.get(parameter)
                if variable is not None:
                    values[parameter] = sampled[variable.key]
                    is_random.append(parameter)
            if st_material is not None:
                is_random.append("material")
            if not is_random:
                continue

            def series(name: str) -> np.ndarray:
                value = values[name]
                arr = np.asarray(value, dtype=float)
                if arr.ndim == 0:
                    return np.full(sampling.samples, float(arr))
                return arr

            if np.any(series("L") <= 0) or np.any(series("odl") <= 0) or np.any(series("odr") <= 0):
                raise EngineeringError(f"Shaft element {index}: stochastic samples produced non-positive length/OD.")
            if np.any(series("idl") < 0) or np.any(series("idr") < 0):
                raise EngineeringError(f"Shaft element {index}: stochastic samples produced negative ID.")
            if np.any(series("idl") >= series("odl")) or np.any(series("idr") >= series("odr")):
                raise EngineeringError(f"Shaft element {index}: stochastic samples violate ID < OD.")

            st_element = srs.ST_ShaftElement(
                L=values["L"], idl=values["idl"], odl=values["odl"],
                idr=values["idr"], odr=values["odr"],
                material=st_material or element.material,
                n=element.n,
                axial_force=getattr(element, "axial_force", 0.0),
                torque=getattr(element, "torque", 0.0),
                shear_effects=getattr(element, "shear_effects", True),
                rotary_inertia=getattr(element, "rotary_inertia", True),
                gyroscopic=getattr(element, "gyroscopic", True),
                shear_method_calc=getattr(element, "shear_method_calc", "cowper"),
                is_random=is_random,
            )
            shaft_elements[index] = st_element
            wrappers.append(
                StochasticInputWrapper(
                    str(getattr(element, "tag", None) or f"Shaft element {index}"),
                    "shaft", index, st_element, tuple(is_random),
                )
            )

        for index, element in enumerate(rotor.disk_elements):
            local = variables_by_owner.get(("disk", index), {})
            if not local:
                continue
            if element.__class__.__name__ != "DiskElement":
                raise EngineeringError(
                    f"Disk element {index} uses the concentrated rigid-body adapter; stochastic conversion is blocked to preserve Ix/Iy/Iz."
                )
            values: dict[str, Any] = {"m": float(element.m), "Id": float(element.Id), "Ip": float(element.Ip)}
            for parameter, variable in local.items():
                values[parameter] = sampled[variable.key]
                if np.any(np.asarray(values[parameter], dtype=float) < 0):
                    raise EngineeringError(f"Disk element {index}: {parameter} samples cannot be negative.")
            st_element = srs.ST_DiskElement(
                n=element.n, m=values["m"], Id=values["Id"], Ip=values["Ip"],
                tag=getattr(element, "tag", None), color=getattr(element, "color", "Firebrick"),
                is_random=list(local),
            )
            disk_elements[index] = st_element
            wrappers.append(StochasticInputWrapper(str(getattr(element, "tag", None) or f"Disk {index}"), "disk", index, st_element, tuple(local)))

        for index, element in enumerate(rotor.bearing_elements):
            local = variables_by_owner.get(("bearing", index), {})
            if not local:
                continue
            if any(self._is_nonzero(getattr(element, name, [0.0])) for name in ("kzz", "czz", "mzz")):
                raise EngineeringError(
                    f"Bearing element {index}: ROSS 2.3 ST_BearingElement cannot preserve non-zero axial kzz/czz/mzz."
                )
            frequency = None if getattr(element, "frequency", None) is None else np.asarray(element.frequency, dtype=float)
            values: dict[str, Any] = {}
            for parameter in self.BEARING_PARAMETERS:
                nominal = self._coefficient_array(element, parameter)
                if parameter in local:
                    variable = local[parameter]
                    if variable.sampling.scale == "relative":
                        draws = self._draw(variable.sampling, sampling.samples, rng)
                        factors = 1.0 + draws / 100.0
                        data = nominal[:, np.newaxis] * factors[np.newaxis, :]
                    else:
                        data = np.broadcast_to(self._draw(variable.sampling, sampling.samples, rng), (nominal.size, sampling.samples)).copy()
                    sampled[variable.key] = np.squeeze(data) if nominal.size == 1 else data
                    values[parameter] = np.squeeze(data) if nominal.size == 1 else data
                else:
                    values[parameter] = float(nominal[0]) if frequency is None else nominal
            mass_values: dict[str, Any] = {}
            for parameter in ("mxx", "myy", "mxy", "myx"):
                nominal = self._coefficient_array(element, parameter)
                mass_values[parameter] = float(nominal[0]) if frequency is None else nominal
            st_element = srs.ST_BearingElement(
                n=element.n,
                kxx=values["kxx"], cxx=values["cxx"],
                mxx=mass_values["mxx"],
                kyy=values["kyy"], kxy=values["kxy"], kyx=values["kyx"],
                cyy=values["cyy"], cxy=values["cxy"], cyx=values["cyx"],
                myy=mass_values["myy"], mxy=mass_values["mxy"], myx=mass_values["myx"],
                frequency=frequency,
                tag=getattr(element, "tag", None), n_link=getattr(element, "n_link", None),
                scale_factor=getattr(element, "scale_factor", 1.0),
                is_random=list(local),
            )
            bearing_elements[index] = st_element
            wrappers.append(StochasticInputWrapper(str(getattr(element, "tag", None) or f"Bearing/Seal {index}"), "bearing", index, st_element, tuple(local)))

        for index, element in enumerate(rotor.point_mass_elements):
            local = variables_by_owner.get(("point_mass", index), {})
            if not local:
                continue
            if set(local) != {"m"} or getattr(element, "m", None) is None:
                raise EngineeringError(
                    f"Point mass {index}: only isotropic m is qualified through ROSS 2.3 ST_PointMass."
                )
            values = sampled[local["m"].key]
            if np.any(values < 0):
                raise EngineeringError(f"Point mass {index}: mass samples cannot be negative.")
            # ROSS 2.3 ST_PointMass does not carry mz/tag in its wrapper signature.
            # Using isotropic m preserves the M matrix exactly for the qualified support mass.
            st_element = srs.ST_PointMass(n=element.n, m=values, is_random=["m"])
            point_mass_elements[index] = st_element
            wrappers.append(StochasticInputWrapper(str(getattr(element, "tag", None) or f"Point mass {index}"), "point_mass", index, st_element, ("m",)))
            warnings.append("ROSS 2.3 ST_PointMass preserves isotropic mass physics but not the original point-mass tag metadata.")

        st_rotor = srs.ST_Rotor(
            shaft_elements=shaft_elements,
            disk_elements=disk_elements or None,
            bearing_elements=bearing_elements or None,
            point_mass_elements=point_mass_elements or None,
            min_w=getattr(rotor, "min_w", None),
            max_w=getattr(rotor, "max_w", None),
            rated_w=getattr(rotor, "rated_w", None),
            tag=project.name,
        )
        if int(st_rotor.RV_size) != sampling.samples:
            raise EngineeringError(
                f"ROSS ST_Rotor sample size mismatch: requested {sampling.samples}, got {st_rotor.RV_size}. All random variables must have the same size."
            )
        return StochasticBuildResult(
            deterministic=deterministic,
            stochastic_rotor=st_rotor,
            sampling=sampling,
            input_wrappers=tuple(wrappers),
            sampled_values=sampled,
            warnings=tuple(dict.fromkeys(warnings)),
        )

    @staticmethod
    def _stage(name: str, fn: Callable[[], Any], elapsed: dict[str, float]) -> Any:
        start = perf_counter()
        try:
            return fn()
        finally:
            elapsed[name] = perf_counter() - start

    def run_campbell(
        self, project: RotorProject, sampling: StochasticSamplingConfig, request: StochasticCampbellRequest
    ) -> StochasticAnalysisResult:
        request.validate()
        elapsed: dict[str, float] = {}
        build = self._stage("Stochastic Rotor", lambda: self.build(project, sampling), elapsed)
        speed = np.linspace(request.min_rpm, request.max_rpm, request.points) * 2.0 * pi / 60.0
        native = self._stage(
            "ST_Rotor.run_campbell",
            lambda: build.stochastic_rotor.run_campbell(speed, frequencies=request.frequencies, frequency_type=request.frequency_type),
            elapsed,
        )
        return StochasticAnalysisResult("campbell", build, request, native, elapsed)

    def run_frequency_response(
        self, project: RotorProject, sampling: StochasticSamplingConfig, request: StochasticFrequencyRequest
    ) -> StochasticAnalysisResult:
        request.validate()
        elapsed: dict[str, float] = {}
        build = self._stage("Stochastic Rotor", lambda: self.build(project, sampling), elapsed)
        rotor = build.stochastic_rotor
        if request.input_dof >= rotor.number_dof or request.output_dof >= rotor.number_dof:
            raise EngineeringError(f"Local DOF must be in [0, {rotor.number_dof - 1}].")
        valid_nodes = set(int(value) for value in rotor.nodes)
        if request.input_node not in valid_nodes or request.output_node not in valid_nodes:
            raise EngineeringError("Frequency-response input/output must reference exact ROSS shaft nodes.")
        inp = request.input_node * rotor.number_dof + request.input_dof
        out = request.output_node * rotor.number_dof + request.output_dof
        speed = np.linspace(request.min_rpm, request.max_rpm, request.points) * 2.0 * pi / 60.0
        modes = list(request.modes) or None
        native = self._stage(
            "ST_Rotor.run_freq_response",
            lambda: rotor.run_freq_response(inp, out, speed, modes),
            elapsed,
        )
        return StochasticAnalysisResult("frequency_response", build, request, native, elapsed)

    def run_unbalance_response(
        self, project: RotorProject, sampling: StochasticSamplingConfig, request: StochasticUnbalanceRequest
    ) -> StochasticAnalysisResult:
        request.validate()
        elapsed: dict[str, float] = {}
        build = self._stage("Stochastic Rotor", lambda: self.build(project, sampling), elapsed)
        rotor = build.stochastic_rotor
        if request.node not in set(int(value) for value in rotor.nodes):
            raise EngineeringError("Stochastic unbalance must reference an exact ROSS shaft node.")
        rng = np.random.default_rng(sampling.seed + 100003)
        magnitude: float | np.ndarray = request.magnitude_kg_m
        phase: float | np.ndarray = request.phase_deg * pi / 180.0
        if request.magnitude_random is not None:
            magnitude = self._sample_parameter(request.magnitude_kg_m, request.magnitude_random, sampling.samples, rng)
            if np.any(np.asarray(magnitude) < 0):
                raise EngineeringError("Random unbalance magnitude samples cannot be negative.")
        if request.phase_random is not None:
            phase_deg = self._sample_parameter(request.phase_deg, request.phase_random, sampling.samples, rng)
            phase = np.asarray(phase_deg, dtype=float) * pi / 180.0
        speed = np.linspace(request.min_rpm, request.max_rpm, request.points) * 2.0 * pi / 60.0
        modes = list(request.modes) or None
        native = self._stage(
            "ST_Rotor.run_unbalance_response",
            lambda: rotor.run_unbalance_response(request.node, magnitude, phase, speed, modes),
            elapsed,
        )
        return StochasticAnalysisResult("unbalance_response", build, request, native, elapsed)

    def run_time_response(
        self, project: RotorProject, sampling: StochasticSamplingConfig, request: StochasticTimeRequest
    ) -> StochasticAnalysisResult:
        request.validate()
        elapsed: dict[str, float] = {}
        build = self._stage("Stochastic Rotor", lambda: self.build(project, sampling), elapsed)
        rotor = build.stochastic_rotor
        if request.force_node not in set(int(value) for value in rotor.nodes):
            raise EngineeringError("Stochastic time force must reference an exact ROSS shaft node.")
        t = np.linspace(0.0, request.duration_s, request.points)
        dofx = request.force_node * rotor.number_dof
        dofy = dofx + 1
        omega = 2.0 * pi * request.force_frequency_hz
        if request.force_random is None:
            force = np.zeros((request.points, rotor.ndof))
            force[:, dofx] = request.force_amplitude_n * np.cos(omega * t)
            force[:, dofy] = request.force_amplitude_n * np.sin(omega * t)
        else:
            # ROSS 2.3 implementation iterates over force's first axis for random force.
            # Shape is therefore (RV_size, time, ndof), despite the old docstring wording.
            rng = np.random.default_rng(sampling.seed + 200003)
            amplitudes = self._sample_parameter(request.force_amplitude_n, request.force_random, sampling.samples, rng)
            force = np.zeros((sampling.samples, request.points, rotor.ndof))
            for index, amplitude in enumerate(np.asarray(amplitudes, dtype=float)):
                force[index, :, dofx] = amplitude * np.cos(omega * t)
                force[index, :, dofy] = amplitude * np.sin(omega * t)
        speed = request.speed_rpm * 2.0 * pi / 60.0
        native = self._stage(
            "ST_Rotor.run_time_response",
            lambda: rotor.run_time_response(speed, force, t),
            elapsed,
        )
        return StochasticAnalysisResult("time_response", build, request, native, elapsed)


__all__ = [
    "RandomInputSpec",
    "StochasticAnalysisResult",
    "StochasticBuildResult",
    "StochasticCampbellRequest",
    "StochasticFrequencyRequest",
    "StochasticInputWrapper",
    "StochasticRotorService",
    "StochasticSamplingConfig",
    "StochasticTarget",
    "StochasticTimeRequest",
    "StochasticUnbalanceRequest",
    "StochasticVariableSpec",
]
