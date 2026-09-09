from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(slots=True)
class ShaftSegment:
    section: int
    length_mm: float
    od_left_mm: float
    od_right_mm: float
    id_left_mm: float = 0.0
    id_right_mm: float = 0.0
    material: str = "Steel (AISI 4140)"


@dataclass(slots=True)
class ProjectModel:
    name: str = "WGM20"
    description: str = "Wind generator main rotor\n(20 MW class)"
    created: str = "Apr 25, 2025  10:24"
    modified: str = "Apr 25, 2025  14:17"
    speed_rpm: int = 1800
    material: str = "Steel (AISI 4140)"
    total_mass_kg: float = 286.4
    dof: int = 12
    disks: int = 2
    bearings: int = 2
    supports: int = 2
    segments: list[ShaftSegment] = field(default_factory=lambda: [
        ShaftSegment(1, 200, 50, 50),
        ShaftSegment(2, 150, 50, 60),
        ShaftSegment(3, 250, 60, 60),
        ShaftSegment(4, 250, 60, 50),
        ShaftSegment(5, 200, 50, 50),
        ShaftSegment(6, 150, 50, 50),
    ])

    @property
    def total_length_mm(self) -> float:
        return sum(s.length_mm for s in self.segments)

    def touch(self) -> None:
        self.modified = datetime.now().strftime("%b %d, %Y  %H:%M")


@dataclass(slots=True)
class BearingCoefficientRow:
    rpm: int
    kxx: float
    kxy: float
    kyx: float
    kyy: float
    cxx: float
    cxy: float
    cyx: float
    cyy: float


@dataclass(slots=True)
class BearingModel:
    name: str = "DE Journal Bearing"
    bearing_type: str = "Tilting Pad"
    node_position: str = "Node 2 (Disk 1 - Left)"
    connected_shaft: str = "Shaft 1"
    shaft_diameter_mm: float = 100.0
    pad_length_mm: float = 80.0
    radial_clearance_mm: float = 0.10
    pad_arc_deg: float = 60.0
    preload: float = 0.50
    number_of_pads: int = 5
    speed_min_rpm: int = 500
    speed_max_rpm: int = 10000
    load_x_n: float = 5000.0
    load_y_n: float = 0.0
    oil_inlet_temperature_c: float = 40.0
    supply_pressure_bar: float = 2.0
    lubricant_grade: str = "ISO VG 32"
    thermal_model: str = "Energy Equation"
    viscosity_model: str = "Roelands"
    mesh: str = "Medium (60 × 30)"
    operating_rpm: int = 6000
    eccentricity_ratio: float = 0.342
    attitude_angle_deg: float = 53.2
    min_film_thickness_mm: float = 0.067
    power_loss_kw: float = 1.86
    flow_rate_l_min: float = 32.4
    max_temperature_c: float = 78.6
    coefficients: list[BearingCoefficientRow] = field(default_factory=lambda: [
        BearingCoefficientRow(500, 1.20e7, -0.32e7, 0.28e7, 1.10e7, 3.10e4, -0.20e4, 0.18e4, 2.90e4),
        BearingCoefficientRow(1000, 1.35e7, -0.38e7, 0.34e7, 1.28e7, 3.80e4, -0.28e4, 0.25e4, 3.60e4),
        BearingCoefficientRow(2000, 1.72e7, -0.51e7, 0.48e7, 1.64e7, 5.60e4, -0.42e4, 0.39e4, 5.10e4),
        BearingCoefficientRow(4000, 2.28e7, -0.71e7, 0.66e7, 2.18e7, 8.40e4, -0.63e4, 0.58e4, 7.90e4),
        BearingCoefficientRow(6000, 2.85e7, -0.92e7, 0.86e7, 2.74e7, 1.10e5, -0.82e4, 0.77e4, 1.05e5),
        BearingCoefficientRow(8000, 3.41e7, -1.10e7, 1.03e7, 3.28e7, 1.34e5, -1.00e4, 0.95e4, 1.29e5),
        BearingCoefficientRow(10000, 3.95e7, -1.27e7, 1.19e7, 3.80e7, 1.56e5, -1.16e4, 1.10e4, 1.50e5),
    ])


@dataclass(slots=True)
class CampbellMode:
    mode: int
    speed_rpm: int
    freq_hz: float
    damping_pct: float
    whirl: str


CAMPBELL_MODES: list[CampbellMode] = [
    CampbellMode(1, 1050, 62.3, 0.42, "BW"),
    CampbellMode(2, 2840, 153.6, 0.31, "FW"),
    CampbellMode(3, 3120, 176.4, 0.28, "BW"),
    CampbellMode(4, 4310, 238.7, 0.35, "FW"),
    CampbellMode(5, 5020, 281.9, 0.33, "BW"),
    CampbellMode(6, 6520, 332.8, 0.27, "FW"),
    CampbellMode(7, 7140, 366.1, 0.29, "BW"),
    CampbellMode(8, 7980, 401.5, 0.31, "FW"),
    CampbellMode(9, 8760, 438.2, 0.36, "BW"),
    CampbellMode(10, 9240, 468.9, 0.38, "FW"),
    CampbellMode(11, 9680, 495.3, 0.41, "BW"),
    CampbellMode(12, 10000, 520.7, 0.45, "FW"),
]
