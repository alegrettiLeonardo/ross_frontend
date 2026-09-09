from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol

from ..domain import RotorProject

ProgressCallback = Callable[[str], None]


@dataclass(slots=True)
class CriticalSpeedPoint:
    rpm: float
    hz: float
    damping_ratio: float | None = None
    log_dec: float | None = None
    whirl: str = ""


@dataclass(slots=True)
class AnalysisResult:
    backend: str
    backend_version: str
    run_dir: Path
    returncode: int = 0
    stdout: str = ""
    stderr: str = ""
    sections: dict[str, str] = field(default_factory=dict)
    data: dict[str, Any] = field(default_factory=dict)
    critical_speeds: list[CriticalSpeedPoint] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.returncode == 0


class AnalysisBackend(Protocol):
    name: str

    def run(self, project: RotorProject, progress: ProgressCallback | None = None) -> AnalysisResult: ...

    def render_input(self, project: RotorProject) -> str: ...
