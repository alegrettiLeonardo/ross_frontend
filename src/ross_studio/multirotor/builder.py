from __future__ import annotations

from dataclasses import dataclass, field
from math import pi
from typing import Any

from ..domain import EngineeringError
from ..ross_backend import RossBuildResult, RossModelBuilder
from .domain import GearConnection, GearModel, GearSpec, MultiRotorProject


@dataclass(slots=True)
class MultiRotorBuildResult:
    project: MultiRotorProject
    rotor: Any
    rotor_builds: tuple[RossBuildResult, ...]
    local_to_global_nodes: dict[tuple[int, int], int]
    gear_local_nodes: dict[int, int]
    connection_ratios: tuple[float, ...]
    audits: list[str] = field(default_factory=list)

    def global_node(self, rotor_index: int, local_node: int) -> int:
        try:
            return self.local_to_global_nodes[(rotor_index, local_node)]
        except KeyError as exc:
            raise EngineeringError(
                f"No MultiRotor global-node mapping for rotor {rotor_index}, local node {local_node}."
            ) from exc


class MultiRotorBuilder:
    """Build native ROSS 2.3 ``MultiRotor`` objects from strict rotors.

    Each single rotor is first created by the already-qualified strict builder.
    Gear placement is exact-node only. The adapter intentionally follows the
    public v2.3.0 ``MultiRotor`` constructor rather than unreleased/newer source
    parameters; unsupported backlash requests are blocked instead of discarded.
    """

    def __init__(self, rotor_builder: RossModelBuilder | None = None, ross_module: Any | None = None) -> None:
        self.rotor_builder = rotor_builder or RossModelBuilder(ross_module)
        self._ross_module = ross_module

    def _ross(self):
        if self._ross_module is not None:
            return self._ross_module
        import ross as rs
        return rs

    @staticmethod
    def _exact_node(build: RossBuildResult, spec: GearSpec) -> int:
        matches = [
            index
            for index, position in enumerate(build.node_positions_mm)
            if abs(float(position) - float(spec.position_mm)) <= 1e-8
        ]
        if len(matches) != 1:
            available = ", ".join(f"{float(value):g}" for value in build.node_positions_mm)
            raise EngineeringError(
                f"Gear {spec.name!r} requires exact ROSS node at x={spec.position_mm:g} mm; "
                f"available shaft nodes are [{available}] mm. Nearest-node mapping is prohibited."
            )
        return int(matches[0])

    def _material(self, project, name: str):
        try:
            spec = project.materials[name]
        except KeyError as exc:
            raise EngineeringError(f"TVMS gear references unknown material {name!r}.") from exc
        rs = self._ross()
        return rs.Material(
            name=f"MR_{spec.name}",
            rho=spec.density_kg_m3,
            E=spec.young_pa,
            G_s=spec.shear_pa,
        )

    def _gear(self, project, spec: GearSpec, node: int):
        rs = self._ross()
        if spec.model == GearModel.SIMPLE:
            kwargs: dict[str, Any] = {
                "n": node,
                "m": spec.mass_kg,
                "Id": spec.id_kg_m2,
                "Ip": spec.ip_kg_m2,
                "n_teeth": spec.n_teeth,
                "pr_angle": spec.pressure_angle_deg * pi / 180.0,
                "helix_angle": spec.helix_angle_deg * pi / 180.0,
                "tag": spec.name,
            }
            if spec.pitch_diameter_m is not None:
                kwargs["pitch_diameter"] = spec.pitch_diameter_m
            else:
                kwargs["base_diameter"] = spec.base_diameter_m
            return rs.GearElement(**kwargs)

        if spec.model == GearModel.TVMS:
            if not hasattr(rs, "GearElementTVMS"):
                raise EngineeringError("Pinned ROSS runtime does not expose GearElementTVMS; TVMS is blocked.")
            return rs.GearElementTVMS(
                n=node,
                material=self._material(project, spec.material_name),
                width=spec.width_m,
                bore_diameter=spec.bore_diameter_m,
                module=spec.module_m,
                n_teeth=spec.n_teeth,
                pr_angle=spec.pressure_angle_deg * pi / 180.0,
                helix_angle=spec.helix_angle_deg * pi / 180.0,
                addendum_coeff=spec.addendum_coeff,
                tip_clearance_coeff=spec.tip_clearance_coeff,
                tag=spec.name,
            )
        raise EngineeringError(f"Unsupported MultiRotor gear model {spec.model!r}.")

    def _rotor_with_gears(self, project, build: RossBuildResult, gears: list[tuple[int, GearSpec]]):
        rs = self._ross()
        rotor = build.rotor
        if rotor.__class__ is not rs.Rotor:
            raise EngineeringError(
                f"MultiRotor 0.23 cannot safely insert GearElement into custom rotor class "
                f"{rotor.__class__.__name__!r}; an explicit physics-preserving adapter is required."
            )
        native_gears = []
        node_by_gear: dict[int, int] = {}
        for gear_index, spec in gears:
            node = self._exact_node(build, spec)
            native_gears.append(self._gear(project, spec, node))
            node_by_gear[gear_index] = node
        rebuilt = rs.Rotor(
            shaft_elements=list(rotor.shaft_elements),
            disk_elements=[*native_gears, *list(rotor.disk_elements)] or None,
            bearing_elements=list(rotor.bearing_elements) or None,
            point_mass_elements=list(rotor.point_mass_elements) or None,
            tag=rotor.tag,
        )
        return rebuilt, node_by_gear

    @staticmethod
    def _connection_kwargs(connection: GearConnection) -> dict[str, Any]:
        # Public ROSS 2.3.0 signature:
        # gear_mesh_stiffness, update_mesh_stiffness, square_varying_stiffness,
        # square_stiffness_amplitude_ratio, orientation_angle, position, tag.
        if connection.backlash_enable or connection.backlash_initial_value_m or connection.backlash_error_amp_m:
            raise EngineeringError(
                "Backlash/mesh-error dynamics are not exposed by the pinned public ROSS 2.3.0 MultiRotor constructor; "
                "the request is blocked rather than silently ignored."
            )
        return {
            "gear_mesh_stiffness": connection.gear_mesh_stiffness,
            "update_mesh_stiffness": connection.update_mesh_stiffness,
            "square_varying_stiffness": connection.square_varying_stiffness_enable,
            "square_stiffness_amplitude_ratio": connection.square_varying_stiffness_amplitude_ratio,
            "orientation_angle": connection.orientation_angle_deg * pi / 180.0,
            "position": connection.position,
        }

    def build(self, project: MultiRotorProject) -> MultiRotorBuildResult:
        project.validate()
        rs = self._ross()

        rotor_builds = tuple(self.rotor_builder.build(rotor_project, strict=True) for rotor_project in project.rotors)
        for index, build in enumerate(rotor_builds):
            if build.unresolved_positions_mm:
                raise EngineeringError(
                    f"Rotor {index} strict build has unresolved positions {build.unresolved_positions_mm}."
                )

        gears_by_rotor: dict[int, list[tuple[int, GearSpec]]] = {index: [] for index in range(len(project.rotors))}
        for gear_index, gear in enumerate(project.gears):
            gears_by_rotor[gear.rotor_index].append((gear_index, gear))

        native_rotors: list[Any] = []
        gear_local_nodes: dict[int, int] = {}
        for rotor_index, (rotor_project, build) in enumerate(zip(project.rotors, rotor_builds)):
            native, local_gears = self._rotor_with_gears(rotor_project, build, gears_by_rotor[rotor_index])
            native_rotors.append(native)
            gear_local_nodes.update(local_gears)

        first = project.connections[0]
        aggregate = native_rotors[first.driving_rotor_index]
        node_map: dict[tuple[int, int], int] = {
            (first.driving_rotor_index, int(node)): int(node) for node in aggregate.nodes
        }
        attached = {first.driving_rotor_index}
        ratios: list[float] = []
        audits: list[str] = []

        for order, connection in enumerate(project.connections):
            driving_local_node = gear_local_nodes[connection.driving_gear_index]
            driving_global_node = driving_local_node if order == 0 else node_map[(connection.driving_rotor_index, driving_local_node)]
            driven_rotor = native_rotors[connection.driven_rotor_index]
            driven_local_node = gear_local_nodes[connection.driven_gear_index]
            before_driven_nodes = list(driven_rotor.nodes)

            aggregate = rs.MultiRotor(
                aggregate,
                driven_rotor,
                coupled_nodes=(driving_global_node, driven_local_node),
                tag=project.name if order == len(project.connections) - 1 else f"{project.name} / stage {order + 1}",
                **self._connection_kwargs(connection),
            )
            ratios.append(float(aggregate.mesh.gear_ratio))
            attached.add(connection.driven_rotor_index)
            node_map.update(
                {
                    (connection.driven_rotor_index, int(local)): int(global_)
                    for local, global_ in zip(before_driven_nodes, aggregate.driven_nodes)
                }
            )
            audits.append(
                f"stage={order + 1}; driving_rotor={connection.driving_rotor_index}; "
                f"driven_rotor={connection.driven_rotor_index}; driving_node={driving_global_node}; "
                f"driven_local_node={driven_local_node}; gear_ratio={aggregate.mesh.gear_ratio:.12g}"
            )

        if attached != set(range(len(project.rotors))):
            raise EngineeringError("Nested MultiRotor assembly did not attach every rotor.")

        return MultiRotorBuildResult(
            project=project,
            rotor=aggregate,
            rotor_builds=rotor_builds,
            local_to_global_nodes=node_map,
            gear_local_nodes=gear_local_nodes,
            connection_ratios=tuple(ratios),
            audits=audits,
        )


__all__ = ["MultiRotorBuildResult", "MultiRotorBuilder"]
