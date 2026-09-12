from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

import numpy as np

from .domain import EngineeringError
from .stochastic_analysis import StochasticAnalysisResult, StochasticBuildResult


# Explicit ROSS 2.3 stochastic output inventory. Qualification asserts this list so
# future UI refactors cannot silently remove a native result or raw scientific array.
STOCHASTIC_NATIVE_OUTPUTS: dict[str, tuple[str, ...]] = {
    "random_variables": (
        "ST_Material.plot_random_var",
        "ST_ShaftElement.plot_random_var",
        "ST_DiskElement.plot_random_var",
        "ST_BearingElement.plot_random_var",
        "ST_PointMass.plot_random_var",
        "sample_arrays",
    ),
    "campbell": (
        "plot", "plot_nat_freq", "plot_log_dec",
        "speed_range", "wd", "log_dec", "mode_type", "save", "load",
    ),
    "frequency_response": (
        "plot", "plot_magnitude", "plot_phase", "plot_polar_bode",
        "speed_range", "freq_resp", "velc_resp", "accl_resp", "save", "load",
    ),
    "unbalance_response": (
        "plot", "plot_magnitude", "plot_phase", "plot_polar_bode",
        "frequency_range", "forced_resp", "velc_resp", "accl_resp",
        "number_dof", "nodes", "link_nodes", "save", "load",
    ),
    "time_response": (
        "plot_1d", "plot_2d", "plot_3d",
        "t", "yout", "xout", "nodes", "link_nodes", "nodes_pos", "number_dof",
        "save", "load",
    ),
}


STOCHASTIC_PLOT_LABELS = {
    "campbell": {
        "combined": "Campbell · Natural Frequency + Log Dec",
        "natural_frequency": "Natural Frequency",
        "log_dec": "Logarithmic Decrement",
    },
    "frequency_response": {
        "combined": "Bode + Polar",
        "magnitude": "Magnitude",
        "phase": "Phase",
        "polar": "Polar Bode",
    },
    "unbalance_response": {
        "combined": "Magnitude + Phase + Polar",
        "magnitude": "Magnitude",
        "phase": "Phase",
        "polar": "Polar Bode",
    },
    "time_response": {
        "time_1d": "Time Response · probes",
        "orbit_2d": "Orbit · selected node",
        "orbits_3d": "Orbits · all nodes 3D",
    },
}


def _validate_statistics(percentile: Iterable[float], conf_interval: Iterable[float]) -> tuple[list[float], list[float]]:
    p = [float(value) for value in percentile]
    c = [float(value) for value in conf_interval]
    if any(value < 0 or value > 100 for value in [*p, *c]):
        raise EngineeringError("Percentiles and confidence intervals must be inside [0, 100].")
    return p, c


class _NativeStochasticCatalog:
    def __init__(self, result: StochasticAnalysisResult) -> None:
        self.result = result
        self._cache: dict[tuple[object, ...], Any] = {}

    @property
    def scientific_recompute(self) -> bool:
        return False

    @staticmethod
    def export_html(figure: Any, path: str | Path) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        figure.write_html(str(target), include_plotlyjs=True, full_html=True)
        if not target.is_file() or target.stat().st_size <= 0:
            raise EngineeringError(f"Stochastic ROSS HTML export did not create {target}.")
        return target

    @staticmethod
    def export_png(figure: Any, path: str | Path, *, width: int = 1400, height: int = 850) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        figure.write_image(str(target), format="png", width=width, height=height, scale=1)
        if not target.is_file() or target.stat().st_size <= 0:
            raise EngineeringError(f"Stochastic ROSS PNG export did not create {target}.")
        return target

    def export_native_result(self, path: str | Path) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.suffix.casefold() not in {".json", ".toml"}:
            raise EngineeringError("Native stochastic results can be saved as .json or .toml.")
        self.result.native.save(target)
        if not target.is_file() or target.stat().st_size <= 0:
            raise EngineeringError(f"ROSS stochastic native save did not create {target}.")
        return target


class StochasticInputCatalog:
    def __init__(self, build: StochasticBuildResult) -> None:
        self.build = build
        self._cache: dict[tuple[int, tuple[str, ...]], Any] = {}

    @property
    def wrappers(self):
        return self.build.input_wrappers

    @property
    def sample_arrays(self) -> dict[str, np.ndarray]:
        return self.build.sampled_values

    def figure(self, wrapper_index: int, variables: Iterable[str] | None = None) -> Any:
        if not 0 <= wrapper_index < len(self.build.input_wrappers):
            raise IndexError(wrapper_index)
        wrapper = self.build.input_wrappers[wrapper_index]
        selected = tuple(variables or wrapper.variables)
        # ST_ShaftElement cannot plot material itself; material has its own wrapper.
        selected = tuple(value for value in selected if value != "material")
        if not selected:
            raise EngineeringError(
                f"{wrapper.label}: this wrapper has no directly plottable random variable. Use the ST_Material input result instead."
            )
        cache_key = (wrapper_index, selected)
        if cache_key not in self._cache:
            self._cache[cache_key] = wrapper.native.plot_random_var(list(selected))
        return self._cache[cache_key]


class StochasticCampbellCatalog(_NativeStochasticCatalog):
    def figure(
        self,
        key: str,
        *,
        percentile: Iterable[float] = (),
        conf_interval: Iterable[float] = (90.0,),
        harmonics: Iterable[float] = (1.0,),
        frequency_units: str = "rad/s",
    ) -> Any:
        p, c = _validate_statistics(percentile, conf_interval)
        h = tuple(float(value) for value in harmonics)
        key = key.strip().casefold()
        cache_key = (key, tuple(p), tuple(c), h, frequency_units)
        if cache_key in self._cache:
            return self._cache[cache_key]
        native = self.result.native
        if key == "combined":
            figure = native.plot(percentile=p, conf_interval=c, harmonics=list(h), frequency_units=frequency_units)
        elif key == "natural_frequency":
            figure = native.plot_nat_freq(percentile=p, conf_interval=c, harmonics=list(h), frequency_units=frequency_units)
        elif key == "log_dec":
            figure = native.plot_log_dec(percentile=p, conf_interval=c, frequency_units=frequency_units)
        else:
            raise KeyError(key)
        self._cache[cache_key] = figure
        return figure

    def raw_arrays(self) -> dict[str, np.ndarray]:
        native = self.result.native
        return {
            "speed_range_rad_s": np.asarray(native.speed_range),
            "natural_frequency_rad_s": np.asarray(native.wd),
            "logarithmic_decrement": np.asarray(native.log_dec),
            "mode_type": np.asarray(native.mode_type),
        }


class StochasticFrequencyCatalog(_NativeStochasticCatalog):
    def figure(
        self,
        key: str,
        *,
        percentile: Iterable[float] = (),
        conf_interval: Iterable[float] = (90.0,),
        frequency_units: str = "rad/s",
        amplitude_units: str = "m/N",
        phase_units: str = "rad",
        line_shape: str = "linear",
    ) -> Any:
        p, c = _validate_statistics(percentile, conf_interval)
        key = key.strip().casefold()
        cache_key = (key, tuple(p), tuple(c), frequency_units, amplitude_units, phase_units, line_shape)
        if cache_key in self._cache:
            return self._cache[cache_key]
        native = self.result.native
        kwargs = dict(percentile=p, conf_interval=c, frequency_units=frequency_units, amplitude_units=amplitude_units)
        if key == "combined":
            figure = native.plot(**kwargs, phase_units=phase_units)
        elif key == "magnitude":
            figure = native.plot_magnitude(**kwargs, line_shape=line_shape)
        elif key == "phase":
            figure = native.plot_phase(**kwargs, phase_units=phase_units)
        elif key == "polar":
            figure = native.plot_polar_bode(**kwargs, phase_units=phase_units)
        else:
            raise KeyError(key)
        self._cache[cache_key] = figure
        return figure

    def raw_arrays(self) -> dict[str, np.ndarray]:
        native = self.result.native
        return {
            "speed_range_rad_s": np.asarray(native.speed_range),
            "displacement_frf": np.asarray(native.freq_resp),
            "velocity_frf": np.asarray(native.velc_resp),
            "acceleration_frf": np.asarray(native.accl_resp),
        }


class StochasticUnbalanceCatalog(_NativeStochasticCatalog):
    def _probes(self) -> list[Any]:
        import ross as rs

        project = self.result.build.deterministic
        # Native stochastic forced-response plotting needs probes. Use the exact
        # project probe stations if available through the deterministic rotor model.
        rotor = project.rotor
        nodes = list(rotor.nodes)
        if not nodes:
            raise EngineeringError("ROSS stochastic rotor has no shaft nodes for probe plotting.")
        request = self.result.request
        node = int(getattr(request, "node", nodes[len(nodes) // 2]))
        return [rs.Probe(node, rs.Q_(0.0, "deg"), tag=f"Node {node} X"), rs.Probe(node, rs.Q_(90.0, "deg"), tag=f"Node {node} Y")]

    def figure(
        self,
        key: str,
        *,
        percentile: Iterable[float] = (),
        conf_interval: Iterable[float] = (90.0,),
        frequency_units: str = "rad/s",
        amplitude_units: str = "m",
        phase_units: str = "rad",
        line_shape: str = "linear",
    ) -> Any:
        p, c = _validate_statistics(percentile, conf_interval)
        key = key.strip().casefold()
        cache_key = (key, tuple(p), tuple(c), frequency_units, amplitude_units, phase_units, line_shape)
        if cache_key in self._cache:
            return self._cache[cache_key]
        native = self.result.native
        probes = self._probes()
        kwargs = dict(
            probe=probes, percentile=p, conf_interval=c,
            frequency_units=frequency_units, amplitude_units=amplitude_units,
        )
        if key == "combined":
            figure = native.plot(**kwargs, phase_units=phase_units)
        elif key == "magnitude":
            figure = native.plot_magnitude(**kwargs, line_shape=line_shape)
        elif key == "phase":
            figure = native.plot_phase(**kwargs, phase_units=phase_units)
        elif key == "polar":
            figure = native.plot_polar_bode(**kwargs, phase_units=phase_units)
        else:
            raise KeyError(key)
        self._cache[cache_key] = figure
        return figure

    def raw_arrays(self) -> dict[str, np.ndarray]:
        native = self.result.native
        return {
            "frequency_range_rad_s": np.asarray(native.frequency_range),
            "displacement_response": np.asarray(native.forced_resp),
            "velocity_response": np.asarray(native.velc_resp),
            "acceleration_response": np.asarray(native.accl_resp),
            "nodes": np.asarray(native.nodes),
            "link_nodes": np.asarray(native.link_nodes),
        }


class StochasticTimeCatalog(_NativeStochasticCatalog):
    def _probes(self) -> list[Any]:
        import ross as rs

        nodes = list(self.result.native.nodes)
        request = self.result.request
        node = int(getattr(request, "force_node", nodes[len(nodes) // 2]))
        return [rs.Probe(node, rs.Q_(0.0, "deg"), tag=f"Node {node} X"), rs.Probe(node, rs.Q_(90.0, "deg"), tag=f"Node {node} Y")]

    def figure(
        self,
        key: str,
        *,
        node: int | None = None,
        percentile: Iterable[float] = (),
        conf_interval: Iterable[float] = (90.0,),
        displacement_units: str = "m",
        time_units: str = "s",
        rotor_length_units: str = "m",
    ) -> Any:
        p, c = _validate_statistics(percentile, conf_interval)
        nodes = list(self.result.native.nodes)
        selected_node = int(node if node is not None else getattr(self.result.request, "force_node", nodes[len(nodes) // 2]))
        key = key.strip().casefold()
        cache_key = (key, selected_node, tuple(p), tuple(c), displacement_units, time_units, rotor_length_units)
        if cache_key in self._cache:
            return self._cache[cache_key]
        native = self.result.native
        if key == "time_1d":
            figure = native.plot_1d(
                probe=self._probes(), percentile=p, conf_interval=c,
                displacement_units=displacement_units, time_units=time_units,
            )
        elif key == "orbit_2d":
            figure = native.plot_2d(
                node=selected_node, percentile=p, conf_interval=c,
                displacement_units=displacement_units,
            )
        elif key == "orbits_3d":
            figure = native.plot_3d(
                percentile=p, conf_interval=c,
                displacement_units=displacement_units, rotor_length_units=rotor_length_units,
            )
        else:
            raise KeyError(key)
        self._cache[cache_key] = figure
        return figure

    def raw_arrays(self) -> dict[str, np.ndarray]:
        native = self.result.native
        return {
            "time_s": np.asarray(native.t),
            "displacement_time": np.asarray(native.yout),
            "state_time": np.asarray(native.xout),
            "nodes": np.asarray(native.nodes),
            "link_nodes": np.asarray(native.link_nodes),
            "nodes_pos_m": np.asarray(native.nodes_pos),
        }


def catalog_for(result: StochasticAnalysisResult) -> _NativeStochasticCatalog:
    if result.kind == "campbell":
        return StochasticCampbellCatalog(result)
    if result.kind == "frequency_response":
        return StochasticFrequencyCatalog(result)
    if result.kind == "unbalance_response":
        return StochasticUnbalanceCatalog(result)
    if result.kind == "time_response":
        return StochasticTimeCatalog(result)
    raise KeyError(result.kind)


__all__ = [
    "STOCHASTIC_NATIVE_OUTPUTS",
    "STOCHASTIC_PLOT_LABELS",
    "StochasticCampbellCatalog",
    "StochasticFrequencyCatalog",
    "StochasticInputCatalog",
    "StochasticTimeCatalog",
    "StochasticUnbalanceCatalog",
    "catalog_for",
]
