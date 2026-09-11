from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QIcon

from .icons import engineering_icon


ASSET_ROOT = Path(__file__).resolve().parent / "assets" / "bearings"

FALLBACKS = {
    "ball_bearing.svg": "ball_bearing",
    "roller_bearing.svg": "roller_bearing",
    "cylindrical_bearing.svg": "cylindrical_bearing",
    "plain_journal.svg": "plain_journal",
    "tilting_pad.svg": "tilting_pad",
    "thrust_pad.svg": "thrust_pad",
    "squeeze_film_damper.svg": "sfd",
    "magnetic_bearing.svg": "amb",
}


def bearing_icon(asset_name: str, size: int = 56) -> QIcon:
    """Load the deterministic Bearing Studio asset shipped with the application.

    Frozen builds resolve assets relative to ``__file__`` after PyInstaller collects
    the directory. The QPainter engineering icon remains a defensive fallback only;
    the public Bearing Studio selector is expected to use the local SVG assets.
    """

    path = ASSET_ROOT / asset_name
    icon = QIcon(str(path)) if path.is_file() else QIcon()
    if not icon.isNull():
        return icon
    return engineering_icon(FALLBACKS.get(asset_name, "bearing"), size)


__all__ = ["ASSET_ROOT", "bearing_icon"]
