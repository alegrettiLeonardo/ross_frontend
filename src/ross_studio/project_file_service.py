from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .dyrobes_import import load_dyrobes_project
from .legacy_import import load_irdin_project
from .models import ProjectModel
from .project_io import NATIVE_EXTENSION, ProjectFormatError, load_project, save_project


class ProjectOpenError(ValueError):
    """User-facing project-file loading error."""


@dataclass(slots=True, frozen=True)
class ProjectOpenResult:
    model: ProjectModel
    source_path: Path
    native_path: Path | None
    source_format: str
    imported: bool


class ProjectFileService:
    OPEN_FILTER = (
        "Supported Projects (*.rossproj *.txt *.irdin *.rot *.ou0);;"
        "ROSS Studio Project (*.rossproj);;"
        "RotorDin / iRdin (*.txt *.irdin);;"
        "DyRoBeS Rotor / Model Summary (*.rot *.ou0);;"
        "All Files (*)"
    )
    LEGACY_FILTER = (
        "Legacy Rotor Projects (*.txt *.irdin *.rot *.ou0);;"
        "RotorDin / iRdin (*.txt *.irdin);;"
        "DyRoBeS Rotor / Model Summary (*.rot *.ou0);;"
        "All Files (*)"
    )
    SAVE_FILTER = "ROSS Studio Project (*.rossproj)"

    @staticmethod
    def _sample_text(path: Path, limit: int = 65536) -> str:
        raw = path.read_bytes()[:limit]
        for encoding in ("utf-8-sig", "cp1252", "latin-1"):
            try:
                return raw.decode(encoding)
            except UnicodeDecodeError:
                continue
        return ""

    def open_path(self, path: str | Path) -> ProjectOpenResult:
        source = Path(path).expanduser().resolve()
        if not source.is_file():
            raise ProjectOpenError(f"Project file does not exist: {source}")
        suffix = source.suffix.casefold()
        try:
            if suffix == NATIVE_EXTENSION:
                model = load_project(source)
                return ProjectOpenResult(model, source, source, "ROSS Studio", False)

            sample = self._sample_text(source)
            upper = sample.upper()
            if "[IRDIN]" in upper or ("[DADOS]" in upper and "[SECOES]" in upper):
                model = ProjectModel.from_engineering(load_irdin_project(source))
                model.created = f"Imported from {source.name}"
                model.modified = model.created
                return ProjectOpenResult(model, source, None, "RotorDin / iRdin", True)

            if suffix in {".rot", ".ou0"} or "DYROBES" in upper or "MODEL SUMMARY" in upper:
                model = ProjectModel.from_engineering(load_dyrobes_project(source))
                model.created = f"Imported from DyRoBeS: {source.name}"
                model.modified = model.created
                return ProjectOpenResult(model, source, None, "DyRoBeS", True)
        except Exception as exc:
            if isinstance(exc, ProjectOpenError):
                raise
            raise ProjectOpenError(str(exc)) from exc
        raise ProjectOpenError(
            f"Unsupported project format: {source.name}. Expected .rossproj, RotorDin/iRdin text, or DyRoBeS .rot/.ou0."
        )

    def import_legacy_path(self, path: str | Path) -> ProjectOpenResult:
        result = self.open_path(path)
        if result.source_format == "ROSS Studio":
            raise ProjectOpenError("Use Open for a native .rossproj file; Import Legacy is for RotorDin/iRdin or DyRoBeS.")
        return result

    @staticmethod
    def save_native(model: ProjectModel, path: str | Path) -> Path:
        try:
            return save_project(model, path)
        except (OSError, ProjectFormatError) as exc:
            raise ProjectOpenError(str(exc)) from exc


__all__ = ["ProjectFileService", "ProjectOpenError", "ProjectOpenResult"]
