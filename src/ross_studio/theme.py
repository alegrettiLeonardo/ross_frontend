from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Palette:
    title_bar: str = "#173f5f"
    title_bar_dark: str = "#123652"
    sidebar: str = "#1f3f5d"
    sidebar_dark: str = "#173650"
    sidebar_text: str = "#f2f7fb"
    sidebar_muted: str = "#9fb9cf"
    active: str = "#2186e5"
    active_dark: str = "#1475d2"
    active_light: str = "#e9f4ff"
    background: str = "#f3f8fc"
    surface: str = "#ffffff"
    surface_alt: str = "#f8fbfe"
    border: str = "#c8d8e7"
    border_soft: str = "#dbe6f0"
    text: str = "#173b63"
    text_dark: str = "#0c2f57"
    text_muted: str = "#536f8f"
    success: str = "#1ba85b"
    success_bg: str = "#e8f8ef"
    danger: str = "#d84f57"
    warning: str = "#f29f05"
    console_bg: str = "#09141f"
    console_panel: str = "#10263a"
    console_border: str = "#2b4a64"
    console_text: str = "#e8f0f7"
    grid: str = "#d6e4f0"


COLORS = Palette()

APP_STYLESHEET = f"""
* {{
    font-family: 'Segoe UI', 'Inter', 'Arial';
    font-size: 13px;
    color: {COLORS.text};
}}
QMainWindow, QWidget#appRoot {{ background: {COLORS.background}; }}
QFrame#titleBar {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {COLORS.title_bar}, stop:1 {COLORS.title_bar_dark});
    border: none;
}}
QLabel#brandLabel {{ color: white; font-size: 20px; font-weight: 700; }}
QLabel#projectTitle {{ color: #d9e9f7; font-size: 16px; font-weight: 700; }}
QPushButton#windowButton {{ color: #e4eef7; background: transparent; border: none; border-radius: 4px; min-width: 38px; min-height: 32px; padding: 0px; }}
QPushButton#windowButton:hover {{ background: rgba(255,255,255,0.10); }}
QPushButton#windowCloseButton {{ color: #e4eef7; background: transparent; border: none; min-width: 38px; min-height: 32px; }}
QPushButton#windowCloseButton:hover {{ background: #d84f57; color: white; }}
QFrame#sidebar {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 {COLORS.sidebar}, stop:1 {COLORS.sidebar_dark});
    border: none;
}}
QLabel#navSection {{ color: {COLORS.sidebar_muted}; font-size: 11px; font-weight: 700; letter-spacing: 1.5px; padding: 12px 12px 5px 16px; }}
QPushButton#navButton {{ color: {COLORS.sidebar_text}; background: transparent; border: none; border-radius: 4px; text-align: left; min-height: 38px; padding: 0 12px; font-size: 14px; }}
QPushButton#navButton:hover {{ background: rgba(255,255,255,0.07); }}
QPushButton#navButton:checked {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {COLORS.active_dark}, stop:1 {COLORS.active});
    color: white;
    font-weight: 700;
}}
QFrame#navDivider {{ background: rgba(255,255,255,0.10); min-height: 1px; max-height: 1px; }}
QFrame#toolbar {{ background: {COLORS.surface}; border-bottom: 1px solid {COLORS.border_soft}; }}
QPushButton#toolButton {{ border: none; background: transparent; min-height: 34px; padding: 0 10px; border-radius: 4px; color: {COLORS.text}; }}
QPushButton#toolButton:hover {{ background: {COLORS.active_light}; color: {COLORS.active_dark}; }}
QPushButton#toolButton:disabled {{ color: #a8b9c9; }}
QFrame#toolSeparator {{ background: {COLORS.border}; min-width:1px; max-width:1px; margin: 8px 6px; }}
QComboBox#viewCombo {{ background: {COLORS.surface}; border: 1px solid {COLORS.border}; border-radius: 5px; padding: 6px 12px; min-width: 92px; }}
QFrame#card, QGroupBox#card {{ background: {COLORS.surface}; border: 1px solid {COLORS.border}; border-radius: 6px; }}
QLabel#cardHeader {{ background: transparent; color: {COLORS.text_dark}; font-size: 18px; font-weight: 700; }}
QLabel#panelHeader {{ background: transparent; color: {COLORS.text_dark}; font-size: 17px; font-weight: 700; padding: 2px 0; }}
QLabel#subHeader {{ color: {COLORS.text_dark}; font-weight: 700; font-size: 14px; }}
QLabel#muted {{ color: {COLORS.text_muted}; }}
QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background: white;
    border: 1px solid {COLORS.border};
    border-radius: 5px;
    min-height: 30px;
    padding: 3px 8px;
    selection-background-color: {COLORS.active};
}}
QLineEdit:focus, QTextEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{ border: 1px solid {COLORS.active}; }}
QTableWidget {{
    background: {COLORS.surface};
    alternate-background-color: #f7fbff;
    border: 1px solid {COLORS.border};
    border-radius: 5px;
    gridline-color: {COLORS.border_soft};
    selection-background-color: #dceeff;
    selection-color: {COLORS.text_dark};
}}
QHeaderView::section {{
    background: #eef5fb;
    color: {COLORS.text_dark};
    border: none;
    border-right: 1px solid {COLORS.border_soft};
    border-bottom: 1px solid {COLORS.border_soft};
    padding: 7px 5px;
    font-weight: 700;
}}
QTabWidget::pane {{ background: {COLORS.surface}; border: 1px solid {COLORS.border}; border-radius: 5px; top: -1px; }}
QTabBar::tab {{ background: transparent; color: {COLORS.text_muted}; padding: 10px 18px 8px 18px; border: none; }}
QTabBar::tab:selected {{ color: {COLORS.active_dark}; font-weight: 700; border-bottom: 3px solid {COLORS.active}; }}
QPushButton#outlineButton {{ background: {COLORS.surface}; border: 1px solid {COLORS.border}; border-radius: 5px; min-height: 34px; padding: 0 12px; }}
QPushButton#outlineButton:hover {{ background: {COLORS.active_light}; border-color: {COLORS.active}; }}
QPushButton#primaryButton {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 {COLORS.active_dark}, stop:1 {COLORS.active});
    color: white;
    border: 1px solid {COLORS.active_dark};
    border-radius: 5px;
    min-height: 44px;
    padding: 0 14px;
    font-weight: 700;
}}
QPushButton#primaryButton:hover {{ background: {COLORS.active_dark}; }}
QPushButton#successButton {{ background: {COLORS.success_bg}; color: #137f47; border: 1px solid #96dbb6; border-radius: 5px; min-height: 42px; padding: 0 14px; font-weight: 700; }}
QPushButton#softButton {{ background: #eef5fb; color: {COLORS.text}; border: 1px solid {COLORS.border}; border-radius: 5px; min-height: 42px; padding: 0 14px; font-weight: 700; }}
QPushButton#bearingType {{ background: #f8fbfe; border: 1px solid {COLORS.border}; border-radius: 5px; min-height: 88px; padding: 6px; font-weight: 600; }}
QPushButton#bearingType:hover {{ background: {COLORS.active_light}; border-color: #81baf0; }}
QPushButton#bearingType:checked {{ background: #dceeff; border: 2px solid {COLORS.active}; color: {COLORS.active_dark}; }}
QFrame#statusBar {{ background: {COLORS.surface}; border-top: 1px solid {COLORS.border_soft}; }}
QLabel#statusSuccess {{ color: #158845; font-weight: 600; }}
QFrame#kpiCard {{ background: white; border: 1px solid {COLORS.border}; border-radius: 6px; }}
QLabel#kpiValue {{ color: #0f73db; font-size: 29px; font-weight: 700; }}
QLabel#kpiTitle {{ color: {COLORS.text}; font-size: 13px; }}
QDialog#solverConsole {{ background: {COLORS.console_panel}; border: 1px solid {COLORS.console_border}; }}
QFrame#consoleTitleBar, QFrame#consoleFooter {{ background: #173753; }}
QLabel#consoleTitle {{ color: white; font-size: 17px; font-weight: 700; }}
QPlainTextEdit#consoleOutput {{
    background: {COLORS.console_bg};
    color: {COLORS.console_text};
    border: none;
    border-radius: 0;
    font-family: 'Consolas', 'DejaVu Sans Mono', monospace;
    font-size: 12px;
    padding: 12px;
}}
QFrame#consoleSide {{ background: #10263a; border-left: 1px solid {COLORS.console_border}; }}
QLabel#consoleCompleted {{ color: #4de28b; font-size: 22px; font-weight: 700; }}
QProgressBar {{ background: #18354b; border: 1px solid #2b4a64; border-radius: 4px; text-align: center; color: white; }}
QProgressBar::chunk {{ background: #32d37c; border-radius: 3px; }}
"""
