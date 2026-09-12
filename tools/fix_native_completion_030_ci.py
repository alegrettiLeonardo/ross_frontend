from __future__ import annotations

from pathlib import Path

path = Path("tests/test_runtime_optional_080.py")
text = path.read_text(encoding="utf-8")
old = '''    for key, (_title, ross_class, _group) in window.bearing_page.type_metadata.items():\n        window.bearing_page._select_type(key, announce=False)\n        if ross_class == "MagneticBearingElement":\n            assert not window.bearing_page.calculate_button.isEnabled()\n        else:\n            assert window.bearing_page.calculate_button.isEnabled()\n        assert not window.bearing_page.apply_button.isEnabled()\n'''
new = '''    for key, (_title, _ross_class, _group) in window.bearing_page.type_metadata.items():\n        window.bearing_page._select_type(key, announce=False)\n        assert window.bearing_page.calculate_button.isEnabled()\n        assert not window.bearing_page.apply_button.isEnabled()\n'''
count = text.count(old)
if count != 1:
    raise RuntimeError(f"{path}: expected one remaining legacy AMB assertion block, found {count}")
path.write_text(text.replace(old, new), encoding="utf-8")
print("Remaining ROSS Studio 0.30 AMB runtime assertion aligned")
