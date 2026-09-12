from __future__ import annotations

from typing import Any

from ..domain import EngineeringError
from .analysis import MultiRotorAnalysisResult


class MultiRotorNativeCatalog:
    """Thin plot-only adapter over retained native ROSS result objects."""

    def __init__(self, result: MultiRotorAnalysisResult) -> None:
        self.result = result

    def plot_rotor(self):
        return self.result.build.rotor.plot_rotor()

    def available(self) -> tuple[str, ...]:
        native = self.result.native_result
        kind = self.result.kind
        if kind == "modal":
            return ("mode_3d", "mode_2d", "orbit")
        if kind == "campbell":
            values = ["campbell"]
            if hasattr(native, "plot_with_mode_shape"):
                values.append("campbell_mode_shape")
            return tuple(values)
        if kind == "frequency_response":
            return ("bode", "magnitude", "phase", "polar")
        if kind == "unbalance_response":
            return ("bode", "magnitude", "phase", "polar", "deflected_2d", "deflected_3d", "bending_moment")
        if kind == "time_response":
            values = ["time_1d", "orbit_2d", "orbits_3d", "dfft"]
            if hasattr(native, "mesh_dynamics"):
                values.extend(["transmission_error", "backlash", "mesh_force", "mesh_stiffness", "center_distance", "pressure_angle", "contact_ratio"])
            return tuple(values)
        if kind == "harmonic_balance":
            return ("hbm", "deflected_shape")
        return ()

    def figure(self, key: str, **kwargs: Any):
        native = self.result.native_result
        if key == "rotor":
            return self.plot_rotor()
        if self.result.kind == "modal":
            mode = int(kwargs.get("mode", 0))
            if key == "mode_3d":
                return native.plot_mode_3d(mode=mode, animation=bool(kwargs.get("animation", False)))
            if key == "mode_2d":
                return native.plot_mode_2d(mode=mode, orientation=kwargs.get("orientation", "major"))
            if key == "orbit":
                return native.shapes[mode].plot_orbit()
        if self.result.kind == "campbell":
            if key == "campbell":
                harmonics = kwargs.get("harmonics", self.result.metadata.get("harmonics", [1.0]))
                return native.plot(harmonics=harmonics)
            if key == "campbell_mode_shape" and hasattr(native, "plot_with_mode_shape"):
                return native.plot_with_mode_shape(harmonics=kwargs.get("harmonics", [1.0]))
        if self.result.kind == "frequency_response":
            inp = int(kwargs.get("inp", 0)); out = int(kwargs.get("out", inp))
            if key == "bode": return native.plot(inp=inp, out=out)
            if key == "magnitude": return native.plot_magnitude(inp=inp, out=out)
            if key == "phase": return native.plot_phase(inp=inp, out=out)
            if key == "polar": return native.plot_polar_bode(inp=inp, out=out)
        if self.result.kind == "unbalance_response":
            probe = kwargs.get("probe")
            if key == "bode": return native.plot(probe=probe)
            if key == "magnitude": return native.plot_magnitude(probe=probe)
            if key == "phase": return native.plot_phase(probe=probe)
            if key == "polar": return native.plot_polar_bode(probe=probe)
            speed = kwargs.get("speed")
            if key == "deflected_2d": return native.plot_deflected_shape_2d(speed=speed)
            if key == "deflected_3d": return native.plot_deflected_shape_3d(speed=speed)
            if key == "bending_moment": return native.plot_bending_moment(speed=speed)
        if self.result.kind == "time_response":
            probes = kwargs.get("probes", [])
            if key == "time_1d": return native.plot_1d(probe=probes)
            if key == "orbit_2d": return native.plot_2d(node=int(kwargs.get("node", 0)))
            if key == "orbits_3d": return native.plot_3d()
            if key == "dfft": return native.plot_dfft(probe=probes)
            mesh_methods = {"transmission_error":"plot_transmission_error","backlash":"plot_backlash","mesh_force":"plot_mesh_force","mesh_stiffness":"plot_mesh_stiffness","center_distance":"plot_center_distance","pressure_angle":"plot_pressure_angle","contact_ratio":"plot_contact_ratio"}
            method = mesh_methods.get(key)
            if method is not None and hasattr(native, method): return getattr(native, method)(domain=kwargs.get("domain", "time"))
        if self.result.kind == "harmonic_balance":
            if key == "hbm": return native.plot(probe=kwargs.get("probe"))
            if key == "deflected_shape": return native.plot_deflected_shape(speed=kwargs.get("speed"), harmonic=int(kwargs.get("harmonic", 1)))
        raise EngineeringError(f"Native MultiRotor figure {key!r} is unavailable for result kind {self.result.kind!r}.")


__all__ = ["MultiRotorNativeCatalog"]
