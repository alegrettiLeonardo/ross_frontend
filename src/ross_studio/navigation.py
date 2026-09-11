from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .icons import engineering_icon
from .navigation_registry import (
    NavigationNode,
    canonical_route,
    children,
    sections,
)
from .workspace_commands import WORKSPACE_COMMANDS


class Sidebar(QFrame):
    """Hierarchical, registry-driven primary navigation.

    The sidebar renders architecture only. It never owns scientific routing rules;
    emitted ids are stable canonical routes consumed by the application/page registry.
    Legacy flat keys remain accepted only as compatibility aliases in ``set_active``.
    """

    page_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setFixedWidth(286)

        self.route_buttons: dict[str, QPushButton] = {}
        self.buttons: dict[str, QPushButton] = {}  # canonical routes + selected legacy button aliases
        self.group_buttons: dict[str, QPushButton] = {}
        self.group_children: dict[str, list[QWidget]] = {}
        self._active_route: str | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        scroll = QScrollArea()
        scroll.setObjectName("navScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; } QScrollArea QWidget { background: transparent; }")
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        content = QWidget()
        content.setObjectName("navContent")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(9, 10, 9, 10)
        layout.setSpacing(2)

        for section in sections():
            self._add_section(layout, section)
            for node in children(section.id):
                self._render_node(layout, node, depth=0)
            self._divider(layout)

        layout.addStretch(1)
        scroll.setWidget(content)
        root.addWidget(scroll)

        # Keep the pre-0.17 frozen/runtime smoke contract available without making
        # legacy names public navigation states. ``shaft`` deliberately stays absent:
        # the former duplicate Shaft button must not return.
        legacy_button_aliases = {
            "rotor": "model.shaft",
            "disks": "model.masses",
            "bearings": "model.bearings.general",
            "seals": "model.seals",
            "supports": "model.supports.flexible",
            "couplings": "model.couplings",
            "loads": "model.loads.unbalance",
            "ump": "model.loads.electromagnetic",
            "probes": "model.probes",
        }
        for alias, route in legacy_button_aliases.items():
            self.buttons[alias] = self.route_buttons[route]

        WORKSPACE_COMMANDS.navigate_requested.connect(self.set_active)

    @property
    def active_route(self) -> str | None:
        return self._active_route

    def _add_section(self, layout: QVBoxLayout, node: NavigationNode) -> None:
        label = QLabel(node.title)
        label.setObjectName("navSection")
        layout.addWidget(label)

    def _divider(self, layout: QVBoxLayout) -> None:
        line = QFrame()
        line.setObjectName("navDivider")
        layout.addWidget(line)

    @staticmethod
    def _indented(button: QPushButton, depth: int) -> QWidget:
        wrapper = QWidget()
        wrapper.setObjectName("navRow")
        wrapper.setStyleSheet("background: transparent;")
        row = QHBoxLayout(wrapper)
        row.setContentsMargins(depth * 16, 0, 0, 0)
        row.setSpacing(0)
        row.addWidget(button)
        return wrapper

    def _render_node(self, layout: QVBoxLayout, node: NavigationNode, *, depth: int) -> QWidget:
        if node.kind == "group":
            button = QPushButton()
            button.setObjectName("navButton")
            button.setIcon(engineering_icon(node.icon, 20, "#b9d2e7"))
            button.setIconSize(QSize(20, 20))
            self.group_buttons[node.id] = button
            self.group_children[node.id] = []
            button.clicked.connect(lambda checked=False, nid=node.id: self._toggle_group(nid))
            self._set_group_text(node.id, node.title, node.expanded)
            wrapper = self._indented(button, depth)
            layout.addWidget(wrapper)

            child_widgets: list[QWidget] = []
            for child in children(node.id):
                child_wrapper = self._render_node(layout, child, depth=depth + 1)
                child_widgets.append(child_wrapper)
            self.group_children[node.id].extend(child_widgets)
            if not node.expanded:
                for child_widget in child_widgets:
                    child_widget.hide()
            return wrapper

        if node.kind != "route":
            raise ValueError(f"Unsupported navigation node kind {node.kind!r}")

        text = node.title + ("  [blocked]" if node.locked else "")
        button = QPushButton(text)
        button.setObjectName("navButton")
        button.setCheckable(True)
        button.setIcon(engineering_icon(node.icon, 20, "#b9d2e7"))
        button.setIconSize(QSize(20, 20))
        button.setEnabled(node.enabled and not node.locked)
        if node.tooltip:
            button.setToolTip(node.tooltip)
        button.clicked.connect(lambda checked=False, route=node.id: self.set_active(route))
        self.route_buttons[node.id] = button
        self.buttons[node.id] = button
        wrapper = self._indented(button, depth)
        layout.addWidget(wrapper)
        return wrapper

    def _set_group_text(self, group_id: str, title: str, expanded: bool) -> None:
        button = self.group_buttons[group_id]
        marker = "▾" if expanded else "▸"
        button.setText(f"{marker}  {title}")
        button.setProperty("expanded", expanded)

    def _toggle_group(self, group_id: str) -> None:
        button = self.group_buttons[group_id]
        expanded = not bool(button.property("expanded"))
        title = button.text().split("  ", 1)[-1]
        self._set_group_text(group_id, title, expanded)
        for child in self.group_children[group_id]:
            child.setVisible(expanded)

    def _expand_ancestors(self, route_id: str) -> None:
        # Parent ids can be derived from dotted stable ids. Only registered group
        # ancestors have buttons, so section ids are naturally skipped.
        parts = route_id.split(".")
        for end in range(1, len(parts)):
            candidate = ".".join(parts[:end])
            button = self.group_buttons.get(candidate)
            if button is None:
                continue
            if not bool(button.property("expanded")):
                self._toggle_group(candidate)

    def set_active(self, key: str) -> None:
        route = canonical_route(key)
        self._expand_ancestors(route)
        for route_id, button in self.route_buttons.items():
            button.setChecked(route_id == route)
        self._active_route = route
        self.page_requested.emit(route)


__all__ = ["Sidebar"]
