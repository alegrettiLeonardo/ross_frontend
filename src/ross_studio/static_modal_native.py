from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .domain import EngineeringError
from .static_modal_analysis import StaticModalResult
from .static_modal_decoupled import ModalAnalysisResult, StaticAnalysisResult


@dataclass(slots=True, frozen=True)
class NativeStaticModalFigureSpec:
    key: str
    title: str
    source_method: str
    tutorial_basis: str


STATIC_FIGURES: dict[str, NativeStaticModalFigureSpec] = {
    "free_body": NativeStaticModalFigureSpec(
        "free_body", "Free-Body Diagram", "StaticResults.plot_free_body_diagram",
        "ROSS Static and Modal Analyses tutorial: static.plot_free_body_diagram()",
    ),
    "deformation": NativeStaticModalFigureSpec(
        "deformation", "Static Deformation", "StaticResults.plot_deformation",
        "ROSS Static and Modal Analyses tutorial: static.plot_deformation()",
    ),
    "shearing_force": NativeStaticModalFigureSpec(
        "shearing_force", "Shearing Force Diagram", "StaticResults.plot_shearing_force",
        "ROSS Static and Modal Analyses tutorial: static.plot_shearing_force()",
    ),
    "bending_moment": NativeStaticModalFigureSpec(
        "bending_moment", "Bending Moment Diagram", "StaticResults.plot_bending_moment",
        "ROSS Static and Modal Analyses tutorial: static.plot_bending_moment()",
    ),
}


class _NativeFigureExportMixin:
    scientific_recompute = False

    @staticmethod
    def export_html(figure: Any, path: str | Path) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        figure.write_html(str(target), include_plotlyjs=True, full_html=True)
        if not target.is_file() or target.stat().st_size <= 0:
            raise EngineeringError(f"Native ROSS HTML export did not create {target}.")
        return target

    @staticmethod
    def export_png(figure: Any, path: str | Path, *, width: int = 1400, height: int = 850) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        figure.write_image(str(target), format="png", width=width, height=height, scale=1)
        if not target.is_file() or target.stat().st_size <= 0:
            raise EngineeringError(f"Native ROSS PNG export did not create {target}.")
        return target


class StaticNativeFigureCatalog(_NativeFigureExportMixin):
    """Native StaticResults plots from one independent 0.20 Static transaction."""

    solve_owner = "StaticAnalysisService"

    def __init__(self, result: StaticAnalysisResult) -> None:
        self.result = result
        self._cache: dict[tuple[object, ...], Any] = {}

    def static_spec(self, key: str) -> NativeStaticModalFigureSpec:
        if key not in STATIC_FIGURES:
            raise KeyError(key)
        return STATIC_FIGURES[key]

    def static_figure(self, key: str) -> Any:
        cache_key = ("static", key)
        if cache_key in self._cache:
            return self._cache[cache_key]
        method_name = {
            "free_body": "plot_free_body_diagram",
            "deformation": "plot_deformation",
            "shearing_force": "plot_shearing_force",
            "bending_moment": "plot_bending_moment",
        }.get(key)
        if method_name is None:
            raise KeyError(key)
        figure = getattr(self.result.static, method_name)()
        self._cache[cache_key] = figure
        return figure


class ModalNativeFigureCatalog(_NativeFigureExportMixin):
    """Native ModalResults/CampbellResults plots from one independent 0.20 transaction."""

    solve_owner = "ModalAnalysisService"

    def __init__(self, result: ModalAnalysisResult) -> None:
        self.result = result
        self._cache: dict[tuple[object, ...], Any] = {}

    def mode_indices(self, mode_type: str) -> tuple[int, ...]:
        return self.result.mode_indices(mode_type)

    def mode_figure(
        self,
        mode_index: int,
        *,
        dimension: str = "3d",
        animation: bool = False,
        orientation: str = "major",
    ) -> Any:
        dimension = dimension.strip().casefold()
        if dimension not in {"2d", "3d"}:
            raise EngineeringError(f"Mode-shape dimension must be '2d' or '3d'; received {dimension!r}.")
        if animation and dimension != "3d":
            raise EngineeringError("ROSS mode-shape animation is qualified only for the native 3D plot.")
        cache_key = ("mode", int(mode_index), dimension, bool(animation), orientation)
        if cache_key in self._cache:
            return self._cache[cache_key]
        if dimension == "2d":
            figure = self.result.modal.plot_mode_2d(int(mode_index), orientation=orientation)
        else:
            figure = self.result.modal.plot_mode_3d(int(mode_index), animation=bool(animation))
        self._cache[cache_key] = figure
        return figure

    def campbell_figure(self, harmonics: Iterable[float] = (1.0,)) -> Any:
        values = tuple(float(value) for value in harmonics)
        if not values or any(value <= 0 for value in values):
            raise EngineeringError(f"Campbell harmonics must be positive; received {values!r}.")
        cache_key = ("campbell", values)
        if cache_key not in self._cache:
            self._cache[cache_key] = self.result.campbell.plot(harmonics=list(values))
        return self._cache[cache_key]


class StaticModalNativeFigureCatalog(_NativeFigureExportMixin):
    """0.19 compatibility catalog for retained combined result objects.

    New 0.20 user-facing workspaces use ``StaticNativeFigureCatalog`` and
    ``ModalNativeFigureCatalog`` so Static and Modal/Campbell caches can be invalidated
    independently. This class remains for qualification/backward compatibility only.
    """

    def __init__(self, result: StaticModalResult) -> None:
        self.result = result
        self._cache: dict[tuple[object, ...], Any] = {}

    @property
    def solve_owner(self) -> str:
        return "StaticModalAnalysisService"

    def static_spec(self, key: str) -> NativeStaticModalFigureSpec:
        if key not in STATIC_FIGURES:
            raise KeyError(key)
        return STATIC_FIGURES[key]

    def static_figure(self, key: str) -> Any:
        if self.result.static is None:
            raise EngineeringError("Static results were not requested for this Static & Modal result.")
        cache_key = ("static", key)
        if cache_key in self._cache:
            return self._cache[cache_key]
        method_name = {
            "free_body": "plot_free_body_diagram",
            "deformation": "plot_deformation",
            "shearing_force": "plot_shearing_force",
            "bending_moment": "plot_bending_moment",
        }.get(key)
        if method_name is None:
            raise KeyError(key)
        figure = getattr(self.result.static, method_name)()
        self._cache[cache_key] = figure
        return figure

    def mode_indices(self, mode_type: str) -> tuple[int, ...]:
        return self.result.mode_indices(mode_type)

    def mode_figure(
        self,
        mode_index: int,
        *,
        dimension: str = "3d",
        animation: bool = False,
        orientation: str = "major",
    ) -> Any:
        dimension = dimension.strip().casefold()
        if dimension not in {"2d", "3d"}:
            raise EngineeringError(f"Mode-shape dimension must be '2d' or '3d'; received {dimension!r}.")
        if animation and dimension != "3d":
            raise EngineeringError("ROSS mode-shape animation is qualified only for the native 3D plot.")
        cache_key = ("mode", int(mode_index), dimension, bool(animation), orientation)
        if cache_key in self._cache:
            return self._cache[cache_key]
        if dimension == "2d":
            figure = self.result.modal.plot_mode_2d(int(mode_index), orientation=orientation)
        else:
            figure = self.result.modal.plot_mode_3d(int(mode_index), animation=bool(animation))
        self._cache[cache_key] = figure
        return figure

    def campbell_figure(self, harmonics: Iterable[float] = (1.0,)) -> Any:
        values = tuple(float(value) for value in harmonics)
        if not values or any(value <= 0 for value in values):
            raise EngineeringError(f"Campbell harmonics must be positive; received {values!r}.")
        cache_key = ("campbell", values)
        if cache_key not in self._cache:
            self._cache[cache_key] = self.result.campbell.plot(harmonics=list(values))
        return self._cache[cache_key]


__all__ = [
    "ModalNativeFigureCatalog",
    "NativeStaticModalFigureSpec",
    "STATIC_FIGURES",
    "StaticModalNativeFigureCatalog",
    "StaticNativeFigureCatalog",
]
