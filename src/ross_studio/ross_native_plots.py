from __future__ import annotations

from contextlib import redirect_stdout
from dataclasses import dataclass, field
from importlib import import_module
from io import StringIO
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
    """Call a ROSS API using only parameters present in the pinned 2.3 signature."""
    signature = inspect.signature(callable_obj)
    accepted = {name: value for name, value in kwargs.items() if name in signature.parameters}
    return callable_obj(**accepted)


def _capture_console(callable_obj: Any, **kwargs: Any) -> str:
    buffer = StringIO()
    with redirect_stdout(buffer):
        _call_supported(callable_obj, **kwargs)
    return buffer.getvalue().strip()


def _capture_native_shown_figures(callable_obj: Any, **kwargs: Any) -> tuple[Any, ...]:
    """Capture figures that ROSS 2.3 creates internally and sends to ``Figure.show``.

    ``BearingResults.show_optimization_convergence(show_plots=True)`` builds the
    native Plotly figure inside ROSS, calls ``fig.show()`` and returns ``None``.
    Reimplementing that graph in ROSS Studio would duplicate solver post-processing.
    Instead, for the duration of this synchronous UI call only, intercept Plotly's
    ``Figure.show`` and retain the exact native figures that ROSS produced.
    """
    from plotly import graph_objects as go

    captured: list[Any] = []
    original_show = go.Figure.show

    def retain(figure, *args, **show_kwargs):
        del args, show_kwargs
        captured.append(figure)
        return None

    go.Figure.show = retain
    try:
        _call_supported(callable_obj, **kwargs)
    finally:
        go.Figure.show = original_show
    return tuple(captured)


def _append_figures(target: dict[str, Any], label: str, value: Any) -> None:
    """Normalize one ROSS Plotly figure, a mapping or a list of native figures."""
    if value is None:
        return
    if hasattr(value, "to_html"):
        target.setdefault(label, value)
        return
    if isinstance(value, Mapping):
        for key, figure in value.items():
            _append_figures(target, str(key).replace("_", " ").title(), figure)
        return
    if isinstance(value, (list, tuple)):
        for index, figure in enumerate(value, 1):
            _append_figures(target, f"{label} · {index}", figure)


@dataclass(slots=True, frozen=True)
class NativeFigureSet:
    source: str
    figures: Mapping[str, Any]
    text_outputs: Mapping[str, str] = field(default_factory=dict)
    diagnostics: tuple[str, ...] = ()

    @property
    def available(self) -> bool:
        return bool(self.figures or self.text_outputs)


class RossBearingNativePlotService:
    """Expose post-processing owned by the pinned ROSS BearingResults implementation.

    ROSS Studio does not recreate THD pressure/temperature/convergence semantics.
    It hosts the Plotly figures returned or displayed by ROSS 2.3.0 and captures
    the formatted ``show_*`` output produced by the same retained native object.
    """

    THD_CLASSES = {"PlainJournal", "TiltingPad", "ThrustPad", "SqueezeFilmDamper"}

    EXTRA_DIMENSIONAL_PLOTS = (
        ("Bearing Representation", "plot_bearing_representation"),
        ("Pressure Distribution", "plot_pressure_distribution"),
        ("Pad Pressure", "plot_pad_pressure"),
        ("Film Temperature", "plot_film_temperature_results"),
        ("Solid Pad Temperature", "plot_solid_pad_results"),
        ("Film Average Temperature", "plot_film_average_temperature"),
        ("Babbitt Surface Temperature", "plot_babbitt_surface_temperature"),
        # Forward-compatible names are dynamically gated. They are used only if
        # they exist on the pinned native object; no Studio-side substitute exists.
        ("Film Thickness", "plot_film_thickness_2d"),
        ("Pad Temperature 3D", "plot_pad_temperature_3d"),
        ("SFD Coefficients", "plot_coefficients"),
    )

    TEXT_OUTPUTS = (
        ("Results Summary", "show_results", {}),
        ("K/C Comparison", "show_coefficients_comparison", {}),
        ("Execution Time", "show_execution_time", {}),
        ("Optimization Convergence", "show_optimization_convergence", {"show_plots": False, "by": "value"}),
    )

    def kc_figure(self, native_element: Any) -> Any | None:
        """Return the native BearingElement K/C figure when ROSS exposes one."""
        _require_ross_230()
        if native_element is None:
            return None
        coefficient_plot = getattr(native_element, "plot", None)
        if not callable(coefficient_plot):
            return None
        try:
            figure = _call_supported(
                coefficient_plot,
                frequency_units="RPM",
                stiffness_units="N/m",
                damping_units="N*s/m",
            )
        except Exception as exc:
            raise NativeRossPlotUnavailable(f"ROSS bearing coefficient plot failed: {exc}") from exc
        return figure if figure is not None and hasattr(figure, "to_html") else None

    def dimensional_outputs(self, native_element: Any, *, freq_index: int = 0) -> NativeFigureSet:
        """Return every qualified native dimensional output available for one THD bearing."""
        _require_ross_230()
        if native_element is None:
            raise NativeRossPlotUnavailable("Bearing calculation has no retained native ROSS element.")
        source = type(native_element).__name__
        if source not in self.THD_CLASSES:
            raise NativeRossPlotUnavailable(
                f"Dimensional bearing post-processing is THD-only; received {source}."
            )

        figures: dict[str, Any] = {}
        text_outputs: dict[str, str] = {}
        diagnostics: list[str] = []

        plot_results = getattr(native_element, "plot_results", None)
        if callable(plot_results):
            try:
                result = _call_supported(plot_results, show_plots=False, freq_index=int(freq_index))
                _append_figures(figures, "ROSS Results", result)
            except NotImplementedError:
                diagnostics.append(f"{source}: plot_results is not defined for this analytical model.")
            except Exception as exc:
                diagnostics.append(f"{source}: plot_results unavailable: {exc}")

        for label, method_name in self.EXTRA_DIMENSIONAL_PLOTS:
            method = getattr(native_element, method_name, None)
            if not callable(method):
                continue
            try:
                result = _call_supported(method, freq_index=int(freq_index))
            except (NotImplementedError, TypeError, ValueError, AttributeError) as exc:
                diagnostics.append(f"{method_name}: {exc}")
                continue
            except Exception as exc:
                diagnostics.append(f"{method_name}: {type(exc).__name__}: {exc}")
                continue
            _append_figures(figures, label, result)

        # In ROSS 2.3 this method owns the convergence plot but calls fig.show()
        # instead of returning the figure. Capture that exact native figure rather
        # than recreating residual history in the Studio.
        convergence_method = getattr(native_element, "show_optimization_convergence", None)
        if callable(convergence_method):
            try:
                convergence_figures = _capture_native_shown_figures(
                    convergence_method,
                    show_plots=True,
                    by="value",
                )
                _append_figures(figures, "Optimization Convergence", convergence_figures)
            except (NotImplementedError, TypeError, ValueError, AttributeError) as exc:
                diagnostics.append(f"show_optimization_convergence plot: {exc}")
            except Exception as exc:
                diagnostics.append(
                    f"show_optimization_convergence plot: {type(exc).__name__}: {exc}"
                )

        for label, method_name, kwargs in self.TEXT_OUTPUTS:
            method = getattr(native_element, method_name, None)
            if not callable(method):
                continue
            try:
                text = _capture_console(method, **kwargs)
            except (NotImplementedError, TypeError, ValueError, AttributeError) as exc:
                diagnostics.append(f"{method_name}: {exc}")
                continue
            except Exception as exc:
                diagnostics.append(f"{method_name}: {type(exc).__name__}: {exc}")
                continue
            if text:
                text_outputs[label] = text

        return NativeFigureSet(source, figures, text_outputs, tuple(diagnostics))

    def figures(self, native_element: Any, *, freq_index: int = 0) -> NativeFigureSet:
        """Compatibility facade: native K/C plus THD dimensional figures/text."""
        _require_ross_230()
        if native_element is None:
            raise NativeRossPlotUnavailable("Bearing calculation has no retained native ROSS element.")
        figures: dict[str, Any] = {}
        kc = self.kc_figure(native_element)
        if kc is not None:
            figures["Dynamic K/C"] = kc
        source = type(native_element).__name__
        if source in self.THD_CLASSES:
            dimensional = self.dimensional_outputs(native_element, freq_index=freq_index)
            figures.update(dimensional.figures)
            return NativeFigureSet(source, figures, dimensional.text_outputs, dimensional.diagnostics)
        return NativeFigureSet(source, figures)


class RossAnalysisNativePlotService:
    """Map Studio analysis result objects to their native ROSS Plotly methods.

    The service does not reconstruct traces from numpy arrays. If the pinned ROSS
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
