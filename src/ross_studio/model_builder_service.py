from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, fields, is_dataclass
from typing import Any

from .domain import (
    CouplingSpec,
    DiskSpec,
    DistributedMassSpec,
    EngineeringError,
    LoadSpec,
    PointMassSpec,
    ProbeSpec,
    RotorProject,
    SealSpec,
    ShaftSection,
    SupportSpec,
)
from .ross_backend import RossBuildResult, RossModelBuilder
from .services import EngineeringValidationService


@dataclass(slots=True, frozen=True)
class MutationAudit:
    entity_kind: str
    operation: str
    index: int | None
    before_count: int
    after_count: int
    shaft_elements: int
    shaft_nodes: int
    support_links: tuple[tuple[str, int], ...]


@dataclass(slots=True)
class RotorMutationPreview:
    """Qualified, unapplied mutation of a :class:`RotorProject`.

    The source snapshot provides the same stale-input protection used by Bearing
    Studio: a preview may only be committed while the live project is byte-for-byte
    equivalent at the dataclass level to the project from which it was calculated.
    """

    source_snapshot: RotorProject
    candidate: RotorProject
    audit: MutationAudit


class RotorModelMutationService:
    """Transactional engineering editor for non-bearing rotor model entities.

    Every mutation follows the production contract::

        live project -> deepcopy -> mutate -> domain validation
                     -> engineering validation -> strict ROSS build -> preview
                     -> stale check -> commit

    Bearings deliberately stay outside this service because Bearing Studio owns the
    qualified Calculate -> Preview -> Apply workflow and its THD/axial semantics.
    """

    _COLLECTIONS: dict[str, tuple[str, type[Any]]] = {
        "shaft": ("shaft_sections", ShaftSection),
        "distributed_mass": ("distributed_masses", DistributedMassSpec),
        "point_mass": ("point_masses", PointMassSpec),
        "disk": ("disks", DiskSpec),
        "support": ("supports", SupportSpec),
        "seal": ("seals", SealSpec),
        "coupling": ("couplings", CouplingSpec),
        "load": ("loads", LoadSpec),
        "probe": ("probes", ProbeSpec),
    }

    def __init__(self, ross_module: Any | None = None) -> None:
        self.builder = RossModelBuilder(ross_module)
        self.validation = EngineeringValidationService()

    @classmethod
    def supported_kinds(cls) -> tuple[str, ...]:
        return tuple(cls._COLLECTIONS)

    @classmethod
    def _collection(cls, project: RotorProject, kind: str) -> tuple[list[Any], type[Any]]:
        if kind == "bearing":
            raise EngineeringError(
                "Bearing mutations are owned by Bearing Studio; use its qualified Calculate -> Preview -> Apply transaction."
            )
        try:
            attribute, expected_type = cls._COLLECTIONS[kind]
        except KeyError as exc:
            raise EngineeringError(
                f"Unsupported model-builder entity kind {kind!r}; expected one of {', '.join(cls.supported_kinds())}."
            ) from exc
        return getattr(project, attribute), expected_type

    @staticmethod
    def _field_names(record: Any) -> set[str]:
        if not is_dataclass(record):
            raise EngineeringError(f"Model-builder record {type(record).__name__} is not a dataclass engineering entity.")
        return {field.name for field in fields(record)}

    @staticmethod
    def _renumber_shaft(project: RotorProject) -> None:
        for section_number, section in enumerate(project.shaft_sections, start=1):
            section.section = section_number

    def _qualify(
        self,
        source: RotorProject,
        candidate: RotorProject,
        *,
        kind: str,
        operation: str,
        index: int | None,
        before_count: int,
        after_count: int,
    ) -> RotorMutationPreview:
        try:
            candidate.validate()
        except Exception as exc:
            raise EngineeringError(f"{kind} {operation} rejected by engineering domain: {exc}") from exc

        errors = [issue for issue in self.validation.validate(candidate) if issue.severity == "error"]
        if errors:
            detail = "; ".join(f"{issue.code}: {issue.message}" for issue in errors)
            raise EngineeringError(f"{kind} {operation} rejected by engineering validation: {detail}")

        try:
            built: RossBuildResult = self.builder.build(candidate, strict=True)
        except Exception as exc:
            raise EngineeringError(f"{kind} {operation} rejected by strict ROSS assembly: {exc}") from exc

        if built.unresolved_positions_mm:
            raise EngineeringError(
                f"{kind} {operation} produced unresolved physical node positions: {built.unresolved_positions_mm}."
            )

        audit = MutationAudit(
            entity_kind=kind,
            operation=operation,
            index=index,
            before_count=before_count,
            after_count=after_count,
            shaft_elements=len(built.shaft_plan),
            shaft_nodes=len(built.node_positions_mm),
            support_links=tuple(sorted(built.support_link_nodes.items())),
        )
        return RotorMutationPreview(deepcopy(source), candidate, audit)

    def preview_update(
        self,
        project: RotorProject,
        kind: str,
        index: int,
        changes: dict[str, Any],
    ) -> RotorMutationPreview:
        candidate = deepcopy(project)
        live_collection, _ = self._collection(project, kind)
        collection, _ = self._collection(candidate, kind)
        if not 0 <= index < len(collection):
            raise EngineeringError(f"{kind} index {index} is outside [0, {len(collection) - 1}].")
        if not changes:
            raise EngineeringError(f"{kind} update contains no changed fields.")

        record = collection[index]
        allowed = self._field_names(record)
        unknown = sorted(set(changes) - allowed)
        if unknown:
            raise EngineeringError(f"{kind} update contains unsupported field(s): {', '.join(unknown)}.")
        if kind == "shaft" and "section" in changes:
            raise EngineeringError("Shaft section numbering is topology-owned and cannot be edited directly.")

        for name, value in changes.items():
            setattr(record, name, value)
        if kind == "shaft":
            self._renumber_shaft(candidate)

        return self._qualify(
            project,
            candidate,
            kind=kind,
            operation="update",
            index=index,
            before_count=len(live_collection),
            after_count=len(collection),
        )

    def preview_add(
        self,
        project: RotorProject,
        kind: str,
        record: Any,
        *,
        index: int | None = None,
    ) -> RotorMutationPreview:
        candidate = deepcopy(project)
        live_collection, expected_type = self._collection(project, kind)
        collection, _ = self._collection(candidate, kind)
        if kind == "shaft":
            raise EngineeringError(
                "Shaft-section insertion is not enabled until downstream absolute-coordinate remapping is explicitly chosen by the user."
            )
        if not isinstance(record, expected_type):
            raise EngineeringError(
                f"Cannot add {type(record).__name__} to {kind}; expected {expected_type.__name__}."
            )
        insert_at = len(collection) if index is None else int(index)
        if not 0 <= insert_at <= len(collection):
            raise EngineeringError(f"{kind} insertion index {insert_at} is outside [0, {len(collection)}].")
        collection.insert(insert_at, deepcopy(record))

        return self._qualify(
            project,
            candidate,
            kind=kind,
            operation="add",
            index=insert_at,
            before_count=len(live_collection),
            after_count=len(collection),
        )

    def preview_delete(self, project: RotorProject, kind: str, index: int) -> RotorMutationPreview:
        candidate = deepcopy(project)
        live_collection, _ = self._collection(project, kind)
        collection, _ = self._collection(candidate, kind)
        if not 0 <= index < len(collection):
            raise EngineeringError(f"{kind} index {index} is outside [0, {len(collection) - 1}].")
        if kind == "shaft":
            raise EngineeringError(
                "Shaft-section deletion is not enabled until downstream absolute-coordinate remapping is explicitly chosen by the user."
            )
        del collection[index]

        return self._qualify(
            project,
            candidate,
            kind=kind,
            operation="delete",
            index=index,
            before_count=len(live_collection),
            after_count=len(collection),
        )

    @staticmethod
    def commit(project: RotorProject, preview: RotorMutationPreview) -> MutationAudit:
        if project != preview.source_snapshot:
            raise EngineeringError(
                "Rotor model inputs changed after preview; discard this preview and recalculate the model-builder transaction."
            )
        # Keep object identity stable because ProjectModel, open widgets and services
        # can all hold the same engineering-domain instance.
        for field in fields(RotorProject):
            setattr(project, field.name, deepcopy(getattr(preview.candidate, field.name)))
        return preview.audit


__all__ = ["MutationAudit", "RotorMutationPreview", "RotorModelMutationService"]
