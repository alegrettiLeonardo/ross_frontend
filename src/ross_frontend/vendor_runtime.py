from __future__ import annotations

import os
import sys
from pathlib import Path


ROSS_PINNED_COMMIT = "631a249adbae414d5f5f986479b58f1a4c47935e"


def vendored_ross_root() -> Path | None:
    """Return the checked-out vendored ROSS repository, if available."""
    explicit = os.environ.get("ROSS_STUDIO_ROSS_SRC", "").strip()
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit).expanduser())
    here = Path(__file__).resolve()
    candidates.extend(parent / "vendor" / "ross" for parent in here.parents)
    for root in candidates:
        if (root / "ross" / "__init__.py").is_file():
            return root.resolve()
    return None


def activate_vendored_ross() -> Path | None:
    """Prefer the ROSS source pinned inside ross_frontend.

    Set ``ROSS_STUDIO_USE_SYSTEM_ROSS=1`` to deliberately use the installed
    package instead.  When the git submodule has not been initialized the
    function is a no-op and the existing PyPI dependency remains the fallback.
    """
    if os.environ.get("ROSS_STUDIO_USE_SYSTEM_ROSS", "").strip().lower() in {"1", "true", "yes", "on"}:
        return None
    root = vendored_ross_root()
    if root is None:
        return None
    text = str(root)
    if text not in sys.path:
        sys.path.insert(0, text)
    return root


__all__ = ["ROSS_PINNED_COMMIT", "activate_vendored_ross", "vendored_ross_root"]
