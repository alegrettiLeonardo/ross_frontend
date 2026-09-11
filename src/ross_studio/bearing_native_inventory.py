from __future__ import annotations

from dataclasses import asdict, dataclass
import inspect
from typing import Any

from .ross_native_plots import RossBearingNativePlotService


@dataclass(slots=True, frozen=True)
class NativeOutputMethod:
    """One public ROSS bearing output method discovered at runtime."""

    name: str
    kind: str
    route: str
    required_parameters: tuple[str, ...]
    studio_callable: bool

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["required_parameters"] = list(self.required_parameters)
        return data


@dataclass(slots=True, frozen=True)
class NativeOutputInventory:
    """Runtime inventory used to keep Bearing Studio aligned with pinned ROSS 2.3."""

    source: str
    ross_version: str
    methods: tuple[NativeOutputMethod, ...]

    @property
    def uncovered(self) -> tuple[NativeOutputMethod, ...]:
        return tuple(method for method in self.methods if method.route == "unmapped")

    @property
    def signature_blocked(self) -> tuple[NativeOutputMethod, ...]:
        return tuple(method for method in self.methods if method.route != "unmapped" and not method.studio_callable)

    @property
    def fully_covered(self) -> bool:
        return not self.uncovered and not self.signature_blocked

    def to_dict(self) -> dict[str, object]:
        return {
            "source": self.source,
            "ross_version": self.ross_version,
            "fully_covered": self.fully_covered,
            "methods": [method.to_dict() for method in self.methods],
            "uncovered": [method.name for method in self.uncovered],
            "signature_blocked": [method.name for method in self.signature_blocked],
        }


def _required_parameters(method: Any) -> tuple[str, ...]:
    try:
        signature = inspect.signature(method)
    except (TypeError, ValueError):
        return ()
    required = []
    for parameter in signature.parameters.values():
        if parameter.kind in {parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD}:
            continue
        if parameter.default is inspect.Parameter.empty:
            required.append(parameter.name)
    return tuple(required)


def _route_for(name: str) -> str:
    if name == "plot":
        return "K/C"
    if name == "plot_results":
        return "Dimensional"
    extra = {method_name for _label, method_name in RossBearingNativePlotService.EXTRA_DIMENSIONAL_PLOTS}
    text = {method_name for _label, method_name, _kwargs in RossBearingNativePlotService.TEXT_OUTPUTS}
    if name in extra:
        return "Dimensional"
    if name in text:
        return "Text"
    return "unmapped"


def _supported_required_parameters(name: str) -> set[str]:
    """Parameters that Bearing Studio can provide from the solved-result context."""

    if name == "plot_results":
        return {"freq_index", "show_plots"}
    if name == "show_optimization_convergence":
        return {"show_plots", "by"}
    # Extra dimensional methods are called through _call_supported with the
    # solved frequency index; optional unit parameters retain ROSS defaults.
    return {"freq_index"}


def inventory_native_outputs(native_element: Any) -> NativeOutputInventory:
    """Discover every public ``plot*``/``show_*`` output on a solved THD object.

    The inventory is intentionally derived from the installed pinned ROSS package,
    not from a duplicated static list.  CI fails when ROSS exposes a public output
    that has no Bearing Studio route, making output drift visible immediately.
    """

    if native_element is None:
        raise ValueError("A solved native ROSS bearing object is required.")

    methods: list[NativeOutputMethod] = []
    for name in sorted(dir(native_element)):
        if not (name == "plot" or name.startswith("plot_") or name.startswith("show_")):
            continue
        if name.startswith("_"):
            continue
        member = getattr(native_element, name, None)
        if not callable(member):
            continue
        route = _route_for(name)
        required = _required_parameters(member)
        supported = _supported_required_parameters(name)
        studio_callable = route != "unmapped" and all(parameter in supported for parameter in required)
        methods.append(
            NativeOutputMethod(
                name=name,
                kind="plot" if name == "plot" or name.startswith("plot_") else "show",
                route=route,
                required_parameters=required,
                studio_callable=studio_callable,
            )
        )

    try:
        import ross as rs

        version = str(getattr(rs, "__version__", "unknown"))
    except Exception:
        version = "unknown"

    return NativeOutputInventory(
        source=type(native_element).__name__,
        ross_version=version,
        methods=tuple(methods),
    )


__all__ = [
    "NativeOutputInventory",
    "NativeOutputMethod",
    "inventory_native_outputs",
]
