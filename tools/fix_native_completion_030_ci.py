from __future__ import annotations

from pathlib import Path

path = Path("tools/qualify_model_builder_014.py")
text = path.read_text(encoding="utf-8")
start = '    before = deepcopy(project)\n    coupling = CouplingSpec(\n        "QUAL-014 coupling",\n'
end = '    before = deepcopy(project)\n    load = LoadSpec('
i = text.find(start)
if i < 0:
    raise RuntimeError("Legacy coupling qualification block start not found")
j = text.find(end, i)
if j < 0:
    raise RuntimeError("Legacy coupling qualification block end not found")
replacement = '''    before = deepcopy(project)\n    coupling = CouplingSpec(\n        "QUAL-014 coupling",\n        1350.567,\n        left_mass_kg=3.0,\n        right_mass_kg=4.0,\n        left_ip_kg_m2=0.05,\n        right_ip_kg_m2=0.06,\n        kt_x_n_m=1.0e7,\n        kt_y_n_m=1.1e7,\n        kt_z_n_m=1.2e7,\n        kr_x_n_m_rad=2.0e6,\n        kr_y_n_m_rad=2.1e6,\n        kr_z_n_m_rad=2.2e6,\n        ct_x_n_s_m=100.0,\n        ct_y_n_s_m=110.0,\n        ct_z_n_s_m=120.0,\n    )\n    try:\n        service.preview_add(project, "coupling", coupling)\n    except Exception as exc:\n        coupling_error = str(exc)\n    else:\n        raise RuntimeError("Legacy single-station coupling no longer failed closed")\n    require_preview_only(project, before, "Coupling")\n    transactions["coupling"] = {\n        "preview_only": True,\n        "position_mm": coupling.position_mm,\n        "legacy_single_station_rejected": True,\n        "error": coupling_error,\n        "realization": "legacy one-station contract fails closed; native two-node ROSS CouplingElement is qualified by the 0.30 gate",\n    }\n\n'''
text = text[:i] + replacement + text[j:]
text = text.replace(
    '            "coupling_native_mapping": "requires explicit two-node coupling contract",\n',
    '            "coupling_native_mapping": "legacy single-station input fails closed; explicit two-node CouplingElement contract is qualified in 0.30",\n',
)
path.write_text(text, encoding="utf-8")
print("Model Builder 0.14 qualifier aligned with the strict two-node CouplingElement contract")
