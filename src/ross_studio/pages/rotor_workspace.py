from __future__ import annotations

from ..workspace_commands import WORKSPACE_COMMANDS
from .rotor_model import RotorModelPage as _LegacyRotorModelPage


class RotorModelPage(_LegacyRotorModelPage):
    """Unified Rotor/Shaft engineering workspace.

    The page owns only the physical/model-driven editor view.  Strict ROSS
    construction and ``Rotor.plot_rotor`` are intentionally removed from this
    normal editing page and live exclusively behind ``Rotor Completo``'s explicit
    discretization toggle.
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        # The inherited 0.14 page connected the obsolete global view selector.
        # Remove that route before deleting the old native-view host.
        try:
            WORKSPACE_COMMANDS.view_mode_requested.disconnect(self.set_view_mode)
        except (RuntimeError, TypeError):
            pass

        native = getattr(self, "native_view", None)
        if native is not None:
            self.view_stack.removeWidget(native)
            native.close()
            native.deleteLater()
        self.native_view = None
        self.view_stack.setCurrentWidget(self.sketch)
        self.sketch.set_mesh_visible(False)

    def set_view_mode(self, mode: str) -> None:
        # Compatibility shim for stale programmatic callers.  There is no longer a
        # model-view state: the editor is always the physical RotorDin-style model.
        # ROSS visualization must go through FullRotorDialog.
        del mode
        self.view_stack.setCurrentWidget(self.sketch)


__all__ = ["RotorModelPage"]
