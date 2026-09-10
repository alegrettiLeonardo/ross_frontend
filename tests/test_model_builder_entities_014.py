from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from ross_studio.domain import (
    CouplingSpec,
    DistributedMassSpec,
    EngineeringError,
    LoadSpec,
    PointMassSpec,
    SealSpec,
)
from ross_studio.legacy_import import load_irdin_project
from ross_studio.model_builder_service import RotorModelMutationService
from ross_studio.ross_backend import RossModelBuilder
from ross_studio.topology import NodeInsertionService


FIXTURE = Path(__file__).parents[1] / "src" / "ross_studio" / "resources" / "OP-W60-500-60Hz-IC611-P3.txt"


def _project_and_service():
    rs = pytest.importorskip("ross")
    return rs, load_irdin_project(FIXTURE), RotorModelMutationService(rs)


def test_distributed_mass_add_update_delete_is_exact_node_and_equivalent_disk_transaction() -> None:
    rs, project, service = _project_and_service()
    baseline = deepcopy(project)
    record = DistributedMassSpec("MASS-014", 1000.123, 40.0, 20.0, 200.0, 20.0)

    preview = service.preview_add(project, "distributed_mass", record)
    assert project == baseline
    plan = NodeInsertionService.plan(preview.candidate)
    assert plan.node_for(record.start_mm) is not None
    assert plan.node_for(record.center_mm) is not None
    assert plan.node_for(record.end_mm) is not None
    built = RossModelBuilder(rs).build(preview.candidate, strict=True)
    equivalent = next(item for item in built.equivalent_disks if item.name == record.name)
    expected_id, expected_ip = record.equivalent_disk_inertias_kg_m2()
    assert equivalent.id_kg_m2 == pytest.approx(expected_id)
    assert equivalent.ip_kg_m2 == pytest.approx(expected_ip)

    service.commit(project, preview)
    index = len(project.distributed_masses) - 1
    update = service.preview_update(project, "distributed_mass", index, {"mass_kg": 22.0})
    service.commit(project, update)
    assert project.distributed_masses[index].mass_kg == pytest.approx(22.0)

    delete = service.preview_delete(project, "distributed_mass", index)
    service.commit(project, delete)
    assert project == baseline


def test_concent_add_update_delete_preserves_independent_principal_inertias() -> None:
    rs, project, service = _project_and_service()
    baseline = deepcopy(project)
    record = PointMassSpec("CONCENT-014", 1100.456, 5.0, 0.011, 0.022, 0.033)

    preview = service.preview_add(project, "point_mass", record)
    assert project == baseline
    built = RossModelBuilder(rs).build(preview.candidate, strict=True)
    equivalent = next(item for item in built.equivalent_point_masses if item.name == record.name)
    assert equivalent.node == NodeInsertionService.plan(preview.candidate).node_for(record.position_mm)
    assert equivalent.ix_kg_m2 == pytest.approx(0.011)
    assert equivalent.iy_kg_m2 == pytest.approx(0.022)
    assert equivalent.iz_kg_m2 == pytest.approx(0.033)

    service.commit(project, preview)
    index = len(project.point_masses) - 1
    update = service.preview_update(project, "point_mass", index, {"iy_kg_m2": 0.044})
    service.commit(project, update)
    assert project.point_masses[index].iy_kg_m2 == pytest.approx(0.044)

    delete = service.preview_delete(project, "point_mass", index)
    service.commit(project, delete)
    assert project == baseline


def test_native_seal_element_is_realized_with_direct_and_cross_coupled_coefficients() -> None:
    rs, project, service = _project_and_service()
    record = SealSpec(
        "SEAL-014",
        1200.321,
        kxx=1.10e6,
        kyy=1.20e6,
        cxx=101.0,
        cyy=102.0,
        kxy=-2.10e5,
        kyx=2.20e5,
        cxy=-21.0,
        cyx=22.0,
    )

    preview = service.preview_add(project, "seal", record)
    assert project.seals == []
    built = RossModelBuilder(rs).build(preview.candidate, strict=True)
    candidates = [*getattr(built.rotor, "seal_elements", []), *getattr(built.rotor, "bearing_elements", [])]
    seal = next(element for element in candidates if getattr(element, "tag", None) == record.name)
    assert type(seal).__name__ == "SealElement"
    assert seal.n == NodeInsertionService.plan(preview.candidate).node_for(record.position_mm)
    assert float(seal.K(0.0)[0, 0]) == pytest.approx(record.kxx)
    assert float(seal.K(0.0)[0, 1]) == pytest.approx(record.kxy)
    assert float(seal.K(0.0)[1, 0]) == pytest.approx(record.kyx)
    assert float(seal.K(0.0)[1, 1]) == pytest.approx(record.kyy)
    assert float(seal.C(0.0)[0, 0]) == pytest.approx(record.cxx)
    assert float(seal.C(0.0)[0, 1]) == pytest.approx(record.cxy)
    assert float(seal.C(0.0)[1, 0]) == pytest.approx(record.cyx)
    assert float(seal.C(0.0)[1, 1]) == pytest.approx(record.cyy)

    service.commit(project, preview)
    update = service.preview_update(project, "seal", 0, {"kxy": -3.0e5})
    service.commit(project, update)
    assert project.seals[0].kxy == pytest.approx(-3.0e5)
    delete = service.preview_delete(project, "seal", 0)
    service.commit(project, delete)
    assert project.seals == []


def test_legacy_single_station_coupling_is_transactional_but_not_silently_mapped_to_two_node_element() -> None:
    rs, project, service = _project_and_service()
    baseline = deepcopy(project)
    record = CouplingSpec(
        "COUPLING-014",
        1300.654,
        left_mass_kg=3.0,
        right_mass_kg=4.0,
        left_ip_kg_m2=0.05,
        right_ip_kg_m2=0.06,
        kt_x_n_m=1.0e7,
        kt_y_n_m=1.1e7,
        kt_z_n_m=1.2e7,
        kr_x_n_m_rad=2.0e6,
        kr_y_n_m_rad=2.1e6,
        kr_z_n_m_rad=2.2e6,
        ct_x_n_s_m=100.0,
        ct_y_n_s_m=110.0,
        ct_z_n_s_m=120.0,
    )

    preview = service.preview_add(project, "coupling", record)
    assert project == baseline
    assert NodeInsertionService.plan(preview.candidate).node_for(record.position_mm) is not None
    built = RossModelBuilder(rs).build(preview.candidate, strict=True)
    assert all(type(element).__name__ != "CouplingElement" for element in built.rotor.shaft_elements)

    service.commit(project, preview)
    index = len(project.couplings) - 1
    update = service.preview_update(project, "coupling", index, {"kr_z_n_m_rad": 2.5e6})
    service.commit(project, update)
    assert project.couplings[index].kr_z_n_m_rad == pytest.approx(2.5e6)
    delete = service.preview_delete(project, "coupling", index)
    service.commit(project, delete)
    assert project == baseline


def test_load_transaction_preserves_metadata_and_exact_analysis_station() -> None:
    rs, project, service = _project_and_service()
    baseline = deepcopy(project)
    record = LoadSpec("LOAD-014", "harmonic", 1400.987, 250.0, 35.0, {"order": 2, "unit": "N"})

    preview = service.preview_add(project, "load", record)
    assert project == baseline
    assert NodeInsertionService.plan(preview.candidate).node_for(record.position_mm) is not None
    service.commit(project, preview)
    index = len(project.loads) - 1
    update = service.preview_update(project, "load", index, {"magnitude": 275.0})
    service.commit(project, update)
    assert project.loads[index].magnitude == pytest.approx(275.0)
    assert project.loads[index].metadata == record.metadata
    assert RossModelBuilder(rs).build(project, strict=True).unresolved_positions_mm == []

    delete = service.preview_delete(project, "load", index)
    service.commit(project, delete)
    assert project == baseline


def test_invalid_new_mass_and_out_of_range_load_fail_closed() -> None:
    rs, project, service = _project_and_service()
    baseline = deepcopy(project)

    with pytest.raises(EngineeringError):
        service.preview_add(project, "distributed_mass", DistributedMassSpec("BAD", 100.0, 20.0, 1.0, 50.0, 50.0))
    with pytest.raises(EngineeringError, match="outside the shaft"):
        service.preview_add(project, "load", LoadSpec("BAD LOAD", "force", project.total_length_mm + 1.0, 1.0))

    assert project == baseline
