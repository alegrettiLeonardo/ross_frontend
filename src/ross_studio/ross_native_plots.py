from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
import inspect
from typing import Any, Mapping


class NativeRossPlotUnavailable(RuntimeError):
    pass


def _require_ross_230() -> Any:
    rs = import_module("ross")
    version = getattr(rs, "__version__", "unknown")
    if version != "2.3.0":
        raise NativeRossPlotUnavailable(f"Native plot adapter is qualified for ROSS 2.3.0; received {version}.")
    return rs


def _call_supported(callable_obj: Any, **kwargs: Any) -> Any:
    """Call a ROSS plot API using only parameters present in the pinned signature."""
    signature = inspect.signature(callable_obj)
    accepted = {name: value for name, value in kwargs.items() if name in signature.parameters}
    return callable_obj(**accepted)


@dataclass(slots=True, frozen=True)
class NativeFigureSet:
    source: str
    figures: Mapping[str, Any]

    @property
    def available(self) -> bool:
        return bool(self.figures)


class RossBearingNativePlotService:
    """Expose plots owned by ROSS BearingElement/BearingResults only."""

    def figures(self, native_element: Any, *, freq_index: int = 0) -> NativeFigureSet:
        _require_ross_230()
        if native_element is None:
            raise NativeRossPlotUnavailable("Bearing calculation has no retained native ROSS element.")

        figures: dict[str, Any] = {}
        coefficient_plot = getattr(native_element, "plot", None)
        if callable(coefficient_plot):
            try:
                fig = _call_supported(
                    coefficient_plot,
                    frequency_units="RPM",
                    stiffness_units="N/m",
                    damping_units="N*s/m",
                )
                if fig is not None and hasattr(fig, "to_html"):
                    figures["Dynamic K/C"] = fig
            except Exception as exc:
                raise NativeRossPlotUnavailable(f"ROSS bearing coefficient plot failed: {exc}") from exc

        plot_results = getattr(native_element, "plot_results", None)
        if callable(plot_results):
            try:
                result = _call_supported(plot_results, show_plots=False, freq_index=int(freq_index))
                if isinstance(result, Mapping):
                    for key, fig in result.items():
                        if fig is not None and hasattr(fig, "to_html"):
                            figures[str(key).replace("_", " ").title()] = fig
            except NotImplementedError:
                # ROSS 2.3.0 SFD intentionally has no pressure/temperature fields.
                pass
            except Exception as exc:
                # A coefficient figure remains scientifically useful; a field plot
                # failure must be visible to the caller rather than replaced by a
                # synthetic Studio chart.
                if not figures:
                    raise NativeRossPlotUnavailable(f"ROSS bearing field plot failed: {exc}") from exc

        # Some 2.3 classes expose bearing-specific native figures in addition to
        # the standardized BearingResults plot_results contract.
        for label, method_name in (
            ("Pressure Distribution", "plot_pressure_distribution"),
            ("Pad Results", "plot_pad_results"),
        ):
            method = getattr(native_element, method_name, None)
            if not callable(method):
                continue
            try:
                fig = _call_supported(method, freq_index=int(freq_index))
            except (NotImplementedError, TypeError, ValueError):
                continue
            if fig is not None and hasattr(fig, "to_html"):
                figures.setdefault(label, fig)

        return NativeFigureSet(type(native_element).__name__, figures)


class RossAnalysisNativePlotService:
    """Map Studio analysis result objects to their native ROSS Plotly methods.

    The service does not reconstruct traces from numpy arrays.  If the pinned ROSS
    result object has no applicable plot method, the plot is reported unavailable.
    """

    def figure(
        self,
        pipeline_result: Any,
        analysis: str,
        *,
        mode: int = 0,
        mode_view: str = "2D",
        response_speed: float | None = None,
        probes: list[Any] | None = None,
        inp: int | None = None,
        out: int | None = None,
    ) -> Any:
        _require_ross_230()
        key = analysis.casefold().replace(" ", "_")

        if key == "static":
            result = pipeline_result.static
            method = getattr(result, "plot_deformation", None)
            if not callable(method):
                raise NativeRossPlotUnavailable("ROSS StaticResults.plot_deformation() is unavailable.")
            return _call_supported(method, deformation_units="um", rotor_length_units="mm")

        if key in {"static_bending", "bending_moment"}:
            result = pipeline_result.static
            method = getattr(result, "plot_bending_moment", None)
            if not callable(method):
                raise NativeRossPlotUnavailable("ROSS StaticResults.plot_bending_moment() is unavailable.")
            return _call_supported(method, moment_units="N*m", rotor_length_units="mm")

        if key in {"static_shear", "shearing_force"}:
            result = pipeline_result.static
            method = getattr(result, "plot_shearing_force", None)
            if not callable(method):
                raise NativeRossPlotUnavailable("ROSS StaticResults.plot_shearing_force() is unavailable.")
            return _call_supported(method, force_units="N", rotor_length_units="mm")

        if key in {"modal", "modal_2d", "modal_3d"}:
            result = pipeline_result.modal
            view = "3D" if key == "modal_3d" else mode_view.upper()
            method_name = "plot_mode_3d" if view == "3D" else "plot_mode_2d"
            method = getattr(result, method_name, None)
            if not callable(method):
                raise NativeRossPlotUnavailable(f"ROSS ModalResults.{method_name}() is unavailable.")
            return _call_supported(
                method,
                mode=int(mode),
                frequency_units="Hz",
                length_units="mm",
                orientation="major",
                animation=False,
            )

        if key == "campbell":
            result = pipeline_result.campbell
            method = getattr(result, "plot", None)
            if not callable(method):
                raise NativeRossPlotUnavailable("ROSS CampbellResults.plot() is unavailable.")
            return _call_supported(
                method,
                harmonics=[1],
                frequency_units="Hz",
                speed_units="RPM",
                damping_parameter="log_dec",
            )

        if key in {"critical", "critical_speed"}:
            result = getattr(pipeline_result, "critical_native", None)
            method = getattr(result, "plot", None) if result is not None else None
            if not callable(method):
                raise NativeRossPlotUnavailable(
                    "The current ROSS critical-speed result has no native plot(); use the native Campbell 1X view for crossings."
                )
            return _call_supported(method, frequency_units="Hz")

        if key in {"unbalance", "forced_response", "response"}:
            result = pipeline_result.unbalance
            if probes:
                method = getattr(result, "plot", None)
                if callable(method):
                    return _call_supported(
                        method,
                        probe=probes,
                        probe_units="deg",
                        frequency_units="RPM",
                        amplitude_units="um",
                        phase_units="deg",
                    )
            method = getattr(result, "plot_deflected_shape", None)
            if callable(method) and response_speed is not None:
                return _call_supported(
                    method,
                    speed=response_speed,
                    frequency_units="RPM",
                    amplitude_units="um",
                    phase_units="deg",
                    rotor_length_units="mm",
                )
            raise NativeRossPlotUnavailable(
                "ROSS ForcedResponseResults requires probes for plot()/plot_bode() or an exact response speed for plot_deflected_shape()."
            )

        # Future Analysis Studio adapters can pass native result objects directly.
        result = getattr(pipeline_result, key, None)
        method = getattr(result, "plot", None) if result is not None else None
        if callable(method):
            kwargs = {}
            if inp is not None:
                kwargs["inp"] = int(inp)
            if out is not None:
                kwargs["out"] = int(out)
            return _call_supported(method, **kwargs)

        raise NativeRossPlotUnavailable(f"No native ROSS plot adapter is qualified for analysis {analysis!r}.")


__all__ = [
    "NativeFigureSet",
    "NativeRossPlotUnavailable",
    "RossAnalysisNativePlotService",
    "RossBearingNativePlotService",
]
