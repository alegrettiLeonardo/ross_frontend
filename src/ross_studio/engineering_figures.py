from __future__ import annotations

from dataclasses import dataclass
from math import pi, radians
from typing import Any, Callable

import ross

from .analysis_pipeline import AnalysisPipelineResult
from .domain import EngineeringError
from .models import ProjectModel


@dataclass(slots=True, frozen=True)
class NativeRossFigureSpec:
    key: str
    title: str
    category: str
    source_method: str
    tutorial_basis: str
    description: str

    def to_dict(self) -> dict[str, str]:
        return {
            "key": self.key,
            "title": self.title,
            "category": self.category,
            "source_method": self.source_method,
            "tutorial_basis": self.tutorial_basis,
            "description": self.description,
        }


class EngineeringFigureCatalog:
    """Lazy registry of figures created by native ROSS result plot methods.

    The catalog is deliberately post-processing-only: it receives an already solved
    :class:`AnalysisPipelineResult` and calls only ``plot_*`` methods on the retained
    ROSS rotor/results. It never calls a ``run_*`` method and therefore cannot change
    or silently recompute the scientific solution shown in Engineering Outputs.
    """

    def __init__(self, project: ProjectModel, result: AnalysisPipelineResult) -> None:
        if project.engineering is None:
            raise EngineeringError("Native Engineering Outputs requires a populated RotorProject.")
        if result.project_name != project.name:
            raise EngineeringError(
                f"Native figure result/project mismatch: result={result.project_name!r}, project={project.name!r}."
            )
        self.project = project
        self.result = result
        self._factories: dict[str, Callable[[], Any]] = {}
        self._specs: list[NativeRossFigureSpec] = []
        self._cache: dict[str, Any] = {}
        self._register_core_figures()

    def _register(
        self,
        key: str,
        title: str,
        category: str,
        source_method: str,
        tutorial_basis: str,
        description: str,
        factory: Callable[[], Any],
    ) -> None:
        if key in self._factories:
            raise RuntimeError(f"Duplicate native ROSS Engineering Output figure key {key!r}.")
        self._specs.append(
            NativeRossFigureSpec(
                key=key,
                title=title,
                category=category,
                source_method=source_method,
                tutorial_basis=tutorial_basis,
                description=description,
            )
        )
        self._factories[key] = factory

    def _register_core_figures(self) -> None:
        result = self.result
        rotor = result.build.rotor

        self._register(
            "rotor_model",
            "Rotor Model",
            "Model",
            "Rotor.plot_rotor",
            "ROSS Modeling tutorial · §6.4 Visualizing the rotor model",
            "Exact strict ROSS rotor assembled for the qualified analysis.",
            lambda: rotor.plot_rotor(nodes=1),
        )

        static_basis = "ROSS Static and Modal Analyses tutorial · §1.1.2 Plotting results"
        self._register(
            "static_free_body",
            "Static Free-Body Diagram",
            "Static",
            "StaticResults.plot_free_body_diagram",
            static_basis,
            "Native ROSS self-weight, disk loads and bearing reactions.",
            lambda: result.static.plot_free_body_diagram(force_units="N", rotor_length_units="m"),
        )
        self._register(
            "static_deformation",
            "Static Deformation",
            "Static",
            "StaticResults.plot_deformation",
            static_basis,
            "Native ROSS gravity deformation of the solved rotor.",
            lambda: result.static.plot_deformation(deformation_units="um", rotor_length_units="m"),
        )
        self._register(
            "static_shearing_force",
            "Static Shearing Force",
            "Static",
            "StaticResults.plot_shearing_force",
            static_basis,
            "Native ROSS static shearing-force diagram.",
            lambda: result.static.plot_shearing_force(force_units="N", rotor_length_units="m"),
        )
        self._register(
            "static_bending_moment",
            "Static Bending Moment",
            "Static",
            "StaticResults.plot_bending_moment",
            static_basis,
            "Native ROSS static bending-moment diagram.",
            lambda: result.static.plot_bending_moment(moment_units="N*m", rotor_length_units="m"),
        )

        modal_basis = "ROSS Static and Modal Analyses tutorial · §1.2.2 Plotting results"
        shapes = list(getattr(result.modal, "shapes", ()))
        for index in range(len(shapes)):
            number = index + 1
            self._register(
                f"modal_mode_{number:02d}_2d",
                f"Mode {number} — 2D",
                "Modal",
                "ModalResults.plot_mode_2d",
                modal_basis,
                f"Native ROSS 2D mode shape for solved mode index {index}.",
                lambda i=index: result.modal.plot_mode_2d(
                    i,
                    frequency_units="Hz",
                    damping_parameter="log_dec",
                ),
            )
            self._register(
                f"modal_mode_{number:02d}_3d",
                f"Mode {number} — 3D",
                "Modal",
                "ModalResults.plot_mode_3d",
                modal_basis,
                f"Native ROSS 3D mode shape for solved mode index {index}.",
                lambda i=index: result.modal.plot_mode_3d(
                    i,
                    frequency_units="Hz",
                    damping_parameter="log_dec",
                    animation=False,
                ),
            )

        self._register(
            "campbell",
            "Campbell Diagram",
            "Campbell",
            "CampbellResults.plot",
            "ROSS Static and Modal Analyses tutorial · §1.3 Campbell Diagram",
            "Native ROSS whirl-speed map from the retained qualified Campbell result.",
            lambda: result.campbell.plot(
                harmonics=[1],
                frequency_units="Hz",
                speed_units="RPM",
                damping_parameter="log_dec",
            ),
        )

        probes = [
            ross.Probe(
                node=item.node,
                angle=radians(float(item.orientation_deg)),
                direction="radial",
                tag=item.name,
            )
            for item in result.probe_responses
        ]
        if probes:
            response_basis = "ROSS Time and Frequency Analyses tutorial · §1.2 Unbalance Response"
            self._register(
                "unbalance_bode",
                "Unbalance Response — Bode / Polar",
                "Unbalance",
                "ForcedResponseResults.plot",
                response_basis + " · §1.2.2 Bode Plot",
                "Native ROSS probe amplitude, phase and polar response.",
                lambda: result.unbalance.plot(
                    probe=probes,
                    probe_units="deg",
                    frequency_units="RPM",
                    amplitude_units="um",
                    phase_units="deg",
                ),
            )
            rated_omega = float(self.project.speed_rpm) * 2.0 * pi / 60.0
            self._register(
                "unbalance_deflected_shape",
                "Unbalance Deflected Shape",
                "Unbalance",
                "ForcedResponseResults.plot_deflected_shape",
                response_basis + " · §1.2.3 Deflected shape",
                "Native ROSS deflected-shape package at rated speed, including bending moment.",
                lambda: result.unbalance.plot_deflected_shape(
                    speed=rated_omega,
                    frequency_units="RPM",
                    amplitude_units="um",
                    phase_units="deg",
                    rotor_length_units="m",
                    moment_units="N*m",
                ),
            )
            self._register(
                "unbalance_bending_moment",
                "Unbalance Bending Moment",
                "Unbalance",
                "ForcedResponseResults.plot_bending_moment",
                response_basis + " · deflected-shape outputs",
                "Native ROSS dynamic bending moment at rated speed.",
                lambda: result.unbalance.plot_bending_moment(
                    speed=rated_omega,
                    moment_units="N*m",
                    rotor_length_units="m",
                ),
            )

    @property
    def specs(self) -> tuple[NativeRossFigureSpec, ...]:
        return tuple(self._specs)

    @property
    def keys(self) -> tuple[str, ...]:
        return tuple(spec.key for spec in self._specs)

    def spec(self, key: str) -> NativeRossFigureSpec:
        for spec in self._specs:
            if spec.key == key:
                return spec
        raise KeyError(key)

    def figure(self, key: str) -> Any:
        if key in self._cache:
            return self._cache[key]
        try:
            factory = self._factories[key]
        except KeyError as exc:
            raise KeyError(key) from exc
        try:
            figure = factory()
        except Exception as exc:
            spec = self.spec(key)
            raise EngineeringError(
                f"ROSS native plot {spec.source_method} failed for Engineering Output {key!r}: {exc}"
            ) from exc
        if figure is None or not hasattr(figure, "to_html"):
            spec = self.spec(key)
            raise EngineeringError(
                f"ROSS native plot {spec.source_method} did not return a Plotly Figure for {key!r}."
            )
        self._cache[key] = figure
        return figure

    def inventory(self) -> list[dict[str, str]]:
        return [spec.to_dict() for spec in self._specs]


__all__ = ["EngineeringFigureCatalog", "NativeRossFigureSpec"]
