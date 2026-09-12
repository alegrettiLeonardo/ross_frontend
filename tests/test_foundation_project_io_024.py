from __future__ import annotations

import json
from pathlib import Path

from ross_studio.models import load_reference_project_model
from ross_studio.project_io import FORMAT_NAME, SCHEMA_VERSION, load_project, save_project


def test_foundation_schema_is_v3_and_native_saves_use_v3(tmp_path: Path) -> None:
    assert SCHEMA_VERSION == 3
    model = load_reference_project_model()
    target = save_project(model, tmp_path / "schema3.rossproj")
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["format"] == FORMAT_NAME
    assert payload["schema_version"] == 3
    assert payload["engineering"]["foundations"] == []


def test_schema1_native_project_migrates_to_empty_foundations_without_reclassifying_supports(tmp_path: Path) -> None:
    model = load_reference_project_model()
    schema2 = save_project(model, tmp_path / "source.rossproj")
    payload = json.loads(schema2.read_text(encoding="utf-8"))
    original_supports = payload["engineering"]["supports"]
    payload["schema_version"] = 1
    payload["app_version"] = "0.23.0"
    payload["engineering"].pop("foundations", None)

    legacy = tmp_path / "legacy-schema1.rossproj"
    legacy.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    restored = load_project(legacy)

    assert restored.engineering is not None
    assert restored.engineering.foundations == []
    assert len(restored.engineering.supports) == len(original_supports)
    assert [support.name for support in restored.engineering.supports] == [row["name"] for row in original_supports]
