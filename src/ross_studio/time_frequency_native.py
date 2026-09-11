from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

import numpy as np

from .domain import EngineeringError
from .time_frequency_analysis import (
    ClearanceAnalysisResult,
    FrequencyResponseAnalysisResult,
    HarmonicBalanceAnalysisResult,
    NativeProbe,
    TimeResponseAnalysisResult,
    UCSAnalysisResult,
    UnbalanceResponseAnalysisResult,
)


# Scientific inventory is deliberately explicit. It is used by qualification to stop
# future UI refactors from silently dropping a native ROSS 2.3.0 result family.
TIME_FREQUENCY_NATIVE_OUTPUTS: dict[str, tuple[str, ...]] = {
    "frequency_response": (
        "plot", "plot_magnitude", "plot_phase", "plot_polar_bode",
        "freq_resp", "velc_resp", "accl_resp", "speed_range",
    ),
    "unbalance_response": (
        "plot", "plot_magnitude", "plot_phase", "plot_bode", "plot_polar_bode",
        "plot_deflected_shape", "plot_deflected_shape_2d", "plot_deflected_shape_3d",
        "plot_bending_moment", "data_magnitude", "data_phase",
        "forced_resp", "velc_resp", "accl_resp", "speed_range",
    ),
    "time_response": (
        "plot_1d", "plot_2d", "plot_3d", "plot_dfft", "data_time_response",
        "t", "yout", "xout",
    ),
    "harmonic_balance": (
        "plot", "plot_deflected_shape", "data", "get_time_response",
        "time.plot_1d", "time.plot_2d", "time.plot_3d", "time.plot_dfft",
    ),
    "ucs": (
        "plot", "plot_mode_2d", "plot_mode_3d",
        "wn", "intersection_points", "critical_points_modal",
    ),
    "clearance": (
        "plot", "bearing_nodes", "magnitudes", "clearance", "clearance_75", "speed_rpm",
    ),
}


FREQUENCY_PLOT_LABELS = {
    "all": "Bode + Polar",
    "magnitude": "Magnitude",
    "phase": "Phase",
    "polar": "Polar Bode",
}

UNBALANCE_PLOT_LABELS = {
    "all": "Bode + Polar",
    "magnitude": "Magnitude",
    "phase": "Phase",
    "bode": "Bode",
    "polar": "Polar Bode",
    "deflected": "Deflected Shape · combined",
    "deflected_2d": "Deflected Shape · 2D",
    "deflected_3d": "Deflected Shape · 3D",
    "bending_moment": "Bending Moment",
}

TIME_PLOT_LABELS = {
    "time_1d": "Time Response · probes",
    "orbit_2d": "Orbit · selected node",
    "orbits_3d": "Orbits · all nodes 3D",
    "dfft": "DFFT · probes",
}

HBM_PLOT_LABELS = {
    "frequency": "HBM Frequency-Domain Response",
    "deflected": "HBM Deflected Shape",
    "time_1d": "HBM reconstructed time response",
    "orbit_2d": "HBM reconstructed orbit · 2D",
    "orbits_3d": "HBM reconstructed orbits · 3D",
    "dfft": "HBM reconstructed DFFT",
}

UCS_PLOT_LABELS = {
    "map": "Undamped Critical Speed Map",
    "mode_2d": "Critical Mode · 2D",
    "mode_3d": "Critical Mode · 3D",
}


class _NativeCatalogBase:
    def __init__(self, result: Any) -> None:
        self.result = result
        self._cache: dict[tuple[object, ...], Any] = {}

    @property
    def scientific_recompute(self) -> bool:
        return False

    @staticmethod
    def _ross_probes(probes: Iterable[NativeProbe]) -> list[Any]:
        import ross as rs

        return [
            rs.Probe(int(item.node), rs.Q_(float(item.orientation_deg), "deg"), tag=item.tag)
            for item in probes
        ]

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


class FrequencyResponseNativeCatalog(_NativeCatalogBase):
    def __init__(self, result: FrequencyResponseAnalysisResult) -> None:
        super().__init__(result)

    def figure(
        self,
        key: str,
        *,
        frequency_units: str = "RPM",
        amplitude_units: str = "m/N",
        phase_units: str = "deg",
        line_shape: str = "linear",
    ) -> Any:
        key = key.strip().casefold()
        cache_key = (key, frequency_units, amplitude_units, phase_units, line_shape)
        if cache_key in self._cache:
            return self._cache[cache_key]
        native = self.result.native
        kwargs = dict(
            inp=self.result.input_global_dof,
            out=self.result.output_global_dof,
            frequency_units=frequency_units,
            amplitude_units=amplitude_units,
        )
        if key == "all":
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
            "frequency_rad_s": np.asarray(native.speed_range),
            "displacement_frf": np.asarray(native.freq_resp),
            "velocity_frf": np.asarray(native.velc_resp),
            "acceleration_frf": np.asarray(native.accl_resp),
        }


class UnbalanceResponseNativeCatalog(_NativeCatalogBase):
    def __init__(self, result: UnbalanceResponseAnalysisResult) -> None:
        super().__init__(result)

    def _probes(self) -> list[Any]:
        if not self.result.probes:
            raise EngineeringError("No project probes are available for native ROSS response plotting.")
        return self._ross_probes(self.result.probes)

    def speed_rad_s(self, speed_rpm: float | None = None) -> float:
        speed = np.asarray(self.result.native.speed_range, dtype=float)
        if speed.size == 0:
            raise EngineeringError("ROSS unbalance result contains an empty speed range.")
        if speed_rpm is None:
            return float(speed[len(speed) // 2])
        target = float(speed_rpm) * 2.0 * np.pi / 60.0
        return float(speed[int(np.argmin(np.abs(speed - target)))])

    def figure(
        self,
        key: str,
        *,
        speed_rpm: float | None = None,
        frequency_units: str = "RPM",
        amplitude_units: str = "m",
        phase_units: str = "deg",
        rotor_length_units: str = "m",
        moment_units: str = "N*m",
        line_shape: str = "linear",
    ) -> Any:
        key = key.strip().casefold()
        snapped = self.speed_rad_s(speed_rpm)
        cache_key = (
            key, snapped, frequency_units, amplitude_units, phase_units,
            rotor_length_units, moment_units, line_shape,
        )
        if cache_key in self._cache:
            return self._cache[cache_key]
        native = self.result.native
        probes = self._probes()
        common = dict(
            probe=probes,
            frequency_units=frequency_units,
            amplitude_units=amplitude_units,
        )
        if key == "all":
            figure = native.plot(**common, phase_units=phase_units)
        elif key == "magnitude":
            figure = native.plot_magnitude(**common, line_shape=line_shape)
        elif key == "phase":
            figure = native.plot_phase(**common, phase_units=phase_units)
        elif key == "bode":
            figure = native.plot_bode(**common, phase_units=phase_units)
        elif key == "polar":
            figure = native.plot_polar_bode(**common, phase_units=phase_units)
        elif key == "deflected":
            figure = native.plot_deflected_shape(
                speed=snapped,
                frequency_units=frequency_units,
                amplitude_units=amplitude_units,
                phase_units=phase_units,
                rotor_length_units=rotor_length_units,
                moment_units=moment_units,
            )
        elif key == "deflected_2d":
            figure = native.plot_deflected_shape_2d(
                speed=snapped,
                amplitude_units=amplitude_units,
                phase_units=phase_units,
                rotor_length_units=rotor_length_units,
            )
        elif key == "deflected_3d":
            figure = native.plot_deflected_shape_3d(
                speed=snapped,
                amplitude_units=amplitude_units,
                phase_units=phase_units,
                rotor_length_units=rotor_length_units,
            )
        elif key == "bending_moment":
            figure = native.plot_bending_moment(
                speed=snapped,
                moment_units=moment_units,
                rotor_length_units=rotor_length_units,
            )
        else:
            raise KeyError(key)
        self._cache[cache_key] = figure
        return figure

    def data_magnitude(self, *, frequency_units: str = "RPM", amplitude_units: str = "m") -> Any:
        return self.result.native.data_magnitude(
            probe=self._probes(), frequency_units=frequency_units, amplitude_units=amplitude_units
        )

    def data_phase(
        self,
        *,
        frequency_units: str = "RPM",
        amplitude_units: str = "m",
        phase_units: str = "deg",
    ) -> Any:
        return self.result.native.data_phase(
            probe=self._probes(),
            frequency_units=frequency_units,
            amplitude_units=amplitude_units,
            phase_units=phase_units,
        )

    def raw_arrays(self) -> dict[str, np.ndarray]:
        native = self.result.native
        return {
            "frequency_rad_s": np.asarray(native.speed_range),
            "displacement_response": np.asarray(native.forced_resp),
            "velocity_response": np.asarray(native.velc_resp),
            "acceleration_response": np.asarray(native.accl_resp),
        }


class TimeResponseNativeCatalog(_NativeCatalogBase):
    def __init__(self, result: TimeResponseAnalysisResult) -> None:
        super().__init__(result)

    def _probes(self) -> list[Any]:
        if not self.result.probes:
            raise EngineeringError("No project probes are available for native ROSS time-response plotting.")
        return self._ross_probes(self.result.probes)

    def default_node(self) -> int:
        if self.result.probes:
            return int(self.result.probes[0].node)
        return int(self.result.build.rotor.nodes[len(self.result.build.rotor.nodes) // 2])

    def figure(
        self,
        key: str,
        *,
        node: int | None = None,
        displacement_units: str = "m",
        time_units: str = "s",
        frequency_units: str = "Hz",
        frequency_range: tuple[float, float] | None = None,
        rotor_length_units: str = "m",
    ) -> Any:
        key = key.strip().casefold()
        selected_node = self.default_node() if node is None else int(node)
        cache_key = (
            key, selected_node, displacement_units, time_units,
            frequency_units, frequency_range, rotor_length_units,
        )
        if cache_key in self._cache:
            return self._cache[cache_key]
        native = self.result.native
        if key == "time_1d":
            figure = native.plot_1d(
                probe=self._probes(), displacement_units=displacement_units, time_units=time_units
            )
        elif key == "orbit_2d":
            figure = native.plot_2d(node=selected_node, displacement_units=displacement_units)
        elif key == "orbits_3d":
            figure = native.plot_3d(
                displacement_units=displacement_units, rotor_length_units=rotor_length_units
            )
        elif key == "dfft":
            figure = native.plot_dfft(
                probe=self._probes(),
                displacement_units=displacement_units,
                frequency_units=frequency_units,
                frequency_range=frequency_range,
            )
        else:
            raise KeyError(key)
        self._cache[cache_key] = figure
        return figure

    def data(self, *, displacement_units: str = "m", time_units: str = "s") -> Any:
        return self.result.native.data_time_response(
            probe=self._probes(), displacement_units=displacement_units, time_units=time_units
        )

    def raw_arrays(self) -> dict[str, np.ndarray]:
        return {
            "time_s": np.asarray(self.result.native.t),
            "displacement_time": np.asarray(self.result.native.yout),
            "state_time": np.asarray(self.result.native.xout),
        }


class HarmonicBalanceNativeCatalog(_NativeCatalogBase):
    def __init__(self, result: HarmonicBalanceAnalysisResult) -> None:
        super().__init__(result)
        self._time_result: Any | None = None

    def _probes(self) -> list[Any]:
        if not self.result.probes:
            raise EngineeringError("No project probes are available for native ROSS HBM plotting.")
        return self._ross_probes(self.result.probes)

    def reconstructed_time(self) -> Any:
        if self._time_result is None:
            self._time_result = self.result.native.get_time_response()
        return self._time_result

    def default_node(self) -> int:
        if self.result.probes:
            return int(self.result.probes[0].node)
        return int(self.result.build.rotor.nodes[len(self.result.build.rotor.nodes) // 2])

    def figure(
        self,
        key: str,
        *,
        node: int | None = None,
        amplitude_units: str = "m",
        frequency_units: str = "Hz",
        phase_units: str = "deg",
        rotor_length_units: str = "m",
        moment_units: str = "N*m",
    ) -> Any:
        key = key.strip().casefold()
        selected_node = self.default_node() if node is None else int(node)
        cache_key = (
            key, selected_node, amplitude_units, frequency_units,
            phase_units, rotor_length_units, moment_units,
        )
        if cache_key in self._cache:
            return self._cache[cache_key]
        native = self.result.native
        probes = self._probes()
        if key == "frequency":
            figure = native.plot(
                probe=probes, amplitude_units=amplitude_units, frequency_units=frequency_units
            )
        elif key == "deflected":
            figure = native.plot_deflected_shape(
                frequency_units=frequency_units,
                amplitude_units=amplitude_units,
                phase_units=phase_units,
                rotor_length_units=rotor_length_units,
                moment_units=moment_units,
            )
        else:
            time_result = self.reconstructed_time()
            if key == "time_1d":
                figure = time_result.plot_1d(probe=probes, displacement_units=amplitude_units)
            elif key == "orbit_2d":
                figure = time_result.plot_2d(node=selected_node, displacement_units=amplitude_units)
            elif key == "orbits_3d":
                figure = time_result.plot_3d(
                    displacement_units=amplitude_units, rotor_length_units=rotor_length_units
                )
            elif key == "dfft":
                figure = time_result.plot_dfft(
                    probe=probes,
                    displacement_units=amplitude_units,
                    frequency_units=frequency_units,
                )
            else:
                raise KeyError(key)
        self._cache[cache_key] = figure
        return figure

    def data(self, *, amplitude_units: str = "m", frequency_units: str = "Hz") -> Any:
        return self.result.native.data(
            probe=self._probes(), amplitude_units=amplitude_units, frequency_units=frequency_units
        )


class UCSNativeCatalog(_NativeCatalogBase):
    def __init__(self, result: UCSAnalysisResult) -> None:
        super().__init__(result)

    @property
    def critical_mode_count(self) -> int:
        return len(self.result.native.critical_points_modal)

    def figure(
        self,
        key: str,
        *,
        critical_mode: int = 0,
        stiffness_units: str = "N/m",
        frequency_units: str = "rad/s",
        length_units: str = "m",
        frequency_type: str = "wd",
    ) -> Any:
        key = key.strip().casefold()
        cache_key = (
            key, int(critical_mode), stiffness_units,
            frequency_units, length_units, frequency_type,
        )
        if cache_key in self._cache:
            return self._cache[cache_key]
        native = self.result.native
        if key == "map":
            figure = native.plot(stiffness_units=stiffness_units, frequency_units=frequency_units)
        else:
            if self.critical_mode_count == 0:
                raise EngineeringError(
                    "ROSS UCS found no bearing-stiffness intersection; critical-mode shapes are unavailable for this range."
                )
            mode = min(max(int(critical_mode), 0), self.critical_mode_count - 1)
            if key == "mode_2d":
                figure = native.plot_mode_2d(
                    mode,
                    frequency_type=frequency_type,
                    length_units=length_units,
                    frequency_units=frequency_units,
                )
            elif key == "mode_3d":
                figure = native.plot_mode_3d(
                    mode,
                    frequency_type=frequency_type,
                    length_units=length_units,
                    frequency_units=frequency_units,
                )
            else:
                raise KeyError(key)
        self._cache[cache_key] = figure
        return figure

    def raw_arrays(self) -> dict[str, Any]:
        native = self.result.native
        return {
            "wn": np.asarray(native.wn),
            "intersection_points": native.intersection_points,
            "critical_points_modal": native.critical_points_modal,
        }


class ClearanceNativeCatalog(_NativeCatalogBase):
    def __init__(self, result: ClearanceAnalysisResult) -> None:
        super().__init__(result)

    def figure(self) -> Any:
        key = ("clearance",)
        if key not in self._cache:
            self._cache[key] = self.result.native.plot()
        return self._cache[key]

    def rows(self) -> tuple[tuple[int, float, float, float], ...]:
        native = self.result.native
        return tuple(
            (int(node), float(mag), float(clearance), float(clearance75))
            for node, mag, clearance, clearance75 in zip(
                native.bearing_nodes, native.magnitudes, native.clearance, native.clearance_75
            )
        )

    def raw_arrays(self) -> dict[str, Any]:
        native = self.result.native
        return {
            "speed_rpm": float(native.speed_rpm),
            "bearing_nodes": np.asarray(native.bearing_nodes, dtype=int),
            "magnitudes_um_pkpk": np.asarray(native.magnitudes, dtype=float),
            "clearance_um": np.asarray(native.clearance, dtype=float),
            "clearance_75_um": np.asarray(native.clearance_75, dtype=float),
        }


__all__ = [
    "ClearanceNativeCatalog",
    "FREQUENCY_PLOT_LABELS",
    "FrequencyResponseNativeCatalog",
    "HBM_PLOT_LABELS",
    "HarmonicBalanceNativeCatalog",
    "TIME_FREQUENCY_NATIVE_OUTPUTS",
    "TIME_PLOT_LABELS",
    "TimeResponseNativeCatalog",
    "UCSNativeCatalog",
    "UCS_PLOT_LABELS",
    "UNBALANCE_PLOT_LABELS",
    "UnbalanceResponseNativeCatalog",
]
