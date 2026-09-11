from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Palette:
    # The shell keeps the approved ROSS Studio blue identity, while all engineering
    # work surfaces use a substantially lighter palette for long desktop sessions.
    title_bar: str = "#20597f"
    title_bar_dark: str = "#174965"
    sidebar: str = "#245372"
    sidebar_dark: str = "#1d4662"
    sidebar_text: str = "#f7fbff"
    sidebar_muted: str = "#c3d8e8"
    active: str = "#2589df"
    active_dark: str = "#1979c8"
    active_light: str = "#edf6ff"
    background: str = "#f8fbfe"
    surface: str = "#ffffff"
    surface_alt: str = "#fbfdff"
    border: str = "#d3e1ec"
    border_soft: str = "#e5edf4"
    text: str = "#163b5d"
    text_dark: str = "#0d3153"
    text_muted: str = "#4d6d89"
    success: str = "#1ba85b"
    success_bg: str = "#ecf9f1"
    danger: str = "#d84f57"
    warning: str = "#f29f05"
    console_bg: str = "#09141f"
    console_panel: str = "#10263a"
    console_border: str = "#2b4a64"
    console_text: str = "#e8f0f7"
    grid: str = "#deebf4"


COLORS = Palette()

APP_STYLESHEET = f"""
* {{
    font-family: 'Segoe UI', 'Inter', 'Arial';
    font-size: 13px;
    color: {COLORS.text};
}}
QMainWindow, QWidget#appRoot {{ background: {COLORS.background}; }}
QDialog {{ background: {COLORS.surface}; color: {COLORS.text}; }}
QDialog QLabel {{ background: transparent; color: {COLORS.text}; }}
QFrame#titleBar {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {COLORS.title_bar}, stop:1 {COLORS.title_bar_dark});
    border: none;
}}
QLabel#brandLabel {{ color: white; font-size: 20px; font-weight: 700; }}
QLabel#projectTitle {{ color: #edf6fd; font-size: 16px; font-weight: 700; }}
QPushButton#windowButton {{ color: #f1f7fc; background: transparent; border: none; border-radius: 4px; min-width: 38px; min-height: 32px; padding: 0px; }}
QPushButton#windowButton:hover {{ background: rgba(255,255,255,0.12); }}
QPushButton#windowCloseButton {{ color: #f1f7fc; background: transparent; border: none; min-width: 38px; min-height: 32px; }}
QPushButton#windowCloseButton:hover {{ background: #d84f57; color: white; }}
QFrame#sidebar {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 {COLORS.sidebar}, stop:1 {COLORS.sidebar_dark});
    border: none;
}}
QLabel#navSection {{ color: {COLORS.sidebar_muted}; font-size: 11px; font-weight: 700; letter-spacing: 1.5px; padding: 12px 12px 5px 16px; }}
QPushButton#navButton {{ color: {COLORS.sidebar_text}; background: transparent; border: none; border-radius: 4px; text-align: left; min-height: 38px; padding: 0 12px; font-size: 14px; }}
QPushButton#navButton:hover {{ background: rgba(255,255,255,0.09); }}
QPushButton#navButton:checked {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {COLORS.active_dark}, stop:1 {COLORS.active});
    color: white;
    font-weight: 700;
}}
QFrame#navDivider {{ background: rgba(255,255,255,0.12); min-height: 1px; max-height: 1px; }}
QFrame#toolbar {{ background: {COLORS.surface}; border-bottom: 1px solid {COLORS.border_soft}; }}
QPushButton#toolButton {{ border: none; background: transparent; min-height: 34px; padding: 0 10px; border-radius: 4px; color: {COLORS.text}; }}
QPushButton#toolButton:hover {{ background: {COLORS.active_light}; color: {COLORS.active_dark}; }}
QPushButton#toolButton:disabled {{ color: #9fb3c3; }}
QFrame#toolSeparator {{ background: {COLORS.border}; min-width:1px; max-width:1px; margin: 8px 6px; }}
QComboBox#viewCombo {{ background: {COLORS.surface}; border: 1px solid {COLORS.border}; border-radius: 5px; padding: 6px 12px; min-width: 110px; }}
QFrame#card, QGroupBox#card {{ background: {COLORS.surface}; border: 1px solid {COLORS.border}; border-radius: 6px; }}
QLabel#cardHeader {{ background: transparent; color: {COLORS.text_dark}; font-size: 18px; font-weight: 700; }}
QLabel#panelHeader {{ background: transparent; color: {COLORS.text_dark}; font-size: 17px; font-weight: 700; padding: 2px 0; }}
QLabel#subHeader {{ color: {COLORS.text_dark}; font-weight: 700; font-size: 14px; }}
QLabel#muted {{ color: {COLORS.text_muted}; }}
QLabel#bearingEditorNote, QLabel#bearingInputDescription {{
    color: {COLORS.text_muted};
    background: {COLORS.surface_alt};
    border: 1px solid {COLORS.border_soft};
    border-radius: 5px;
    padding: 7px 9px;
}}
QLabel#bearingInputSummary {{ color: {COLORS.text_muted}; padding: 3px 2px; }}
QLabel#validationError {{ color: {COLORS.danger}; background: #fff3f4; border: 1px solid #f2c8cc; border-radius: 5px; padding: 7px; }}
QFrame#bearingInputSection {{
    background: {COLORS.surface};
    border: 1px solid {COLORS.border};
    border-radius: 6px;
}}
QLabel#bearingInputSectionTitle {{
    background: transparent;
    color: {COLORS.text_dark};
    border-bottom: 1px solid {COLORS.border_soft};
    padding: 4px 2px 6px 2px;
    font-size: 14px;
    font-weight: 700;
}}
QScrollArea#bearingWorkspaceScroll, QWidget#bearingWorkspaceContent {{ background: transparent; border: none; }}
QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background: white;
    color: {COLORS.text_dark};
    border: 1px solid {COLORS.border};
    border-radius: 5px;
    min-height: 28px;
    padding: 2px 7px;
    selection-background-color: {COLORS.active};
    selection-color: white;
}}
QLineEdit:focus, QTextEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{ border: 1px solid {COLORS.active}; }}
QComboBox QAbstractItemView {{
    background: #ffffff;
    color: {COLORS.text_dark};
    border: 1px solid {COLORS.border};
    outline: 0;
    selection-background-color: {COLORS.active_light};
    selection-color: {COLORS.text_dark};
    padding: 4px;
}}
QComboBox QAbstractItemView::item {{ min-height: 28px; padding: 4px 8px; }}
QCheckBox {{ color: {COLORS.text}; spacing: 7px; }}
QCheckBox::indicator {{ width: 16px; height: 16px; }}
QToolTip {{ background: #ffffff; color: {COLORS.text_dark}; border: 1px solid {COLORS.border}; padding: 5px; }}
QTableWidget, QTableView {{
    background: {COLORS.surface};
    color: {COLORS.text};
    alternate-background-color: #f9fcff;
    border: 1px solid {COLORS.border};
    border-radius: 5px;
    gridline-color: {COLORS.border_soft};
    selection-background-color: #deefff;
    selection-color: {COLORS.text_dark};
}}
QHeaderView::section {{
    background: #f1f7fb;
    color: {COLORS.text_dark};
    border: none;
    border-right: 1px solid {COLORS.border_soft};
    border-bottom: 1px solid {COLORS.border_soft};
    padding: 7px 5px;
    font-weight: 700;
}}
QTabWidget::pane {{ background: {COLORS.surface}; border: 1px solid {COLORS.border}; border-radius: 5px; top: -1px; }}
QTabBar::tab {{ background: transparent; color: {COLORS.text_muted}; padding: 8px 14px 7px 14px; border: none; }}
QTabBar::tab:selected {{ color: {COLORS.active_dark}; font-weight: 700; border-bottom: 3px solid {COLORS.active}; }}
QTabBar::tab:disabled {{ color: #a9b8c5; }}
QPushButton#outlineButton {{ background: {COLORS.surface}; color: {COLORS.text}; border: 1px solid {COLORS.border}; border-radius: 5px; min-height: 30px; padding: 0 10px; }}
QPushButton#outlineButton:hover {{ background: {COLORS.active_light}; border-color: {COLORS.active}; }}
QPushButton#primaryButton {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 {COLORS.active_dark}, stop:1 {COLORS.active});
    color: white;
    border: 1px solid {COLORS.active_dark};
    border-radius: 5px;
    min-height: 36px;
    padding: 0 14px;
    font-weight: 700;
}}
QPushButton#primaryButton:hover {{ background: {COLORS.active_dark}; }}
QPushButton#primaryButton:disabled {{ background: #b8c7d4; border-color: #a8bac8; color: #eef4f8; }}
QPushButton#successButton {{ background: {COLORS.success_bg}; color: #137f47; border: 1px solid #a8dfc0; border-radius: 5px; min-height: 34px; padding: 0 12px; font-weight: 700; }}
QPushButton#successButton:disabled {{ background: #f2f5f7; color: #9badba; border-color: #d9e2e9; }}
QPushButton#softButton {{ background: #f3f8fc; color: {COLORS.text}; border: 1px solid {COLORS.border}; border-radius: 5px; min-height: 38px; padding: 0 14px; font-weight: 700; }}
QPushButton#softButton:hover {{ background: {COLORS.active_light}; border-color: #a9cfea; }}
QPushButton#bearingType {{ background: #fbfdff; color: {COLORS.text_dark}; border: 1px solid {COLORS.border}; border-radius: 6px; min-height: 92px; padding: 8px 10px; font-weight: 600; }}
QPushButton#bearingType:hover {{ background: {COLORS.active_light}; border-color: #8abfec; }}
QPushButton#bearingType:checked {{ background: #e3f1ff; border: 2px solid {COLORS.active}; color: {COLORS.active_dark}; font-weight: 700; }}

/* Bearing Studio 0.16 golden visual */
QLabel#bearingStudioTitle {{ color: #0d3761; font-size: 20px; font-weight: 700; padding: 1px 8px 1px 4px; }}
QFrame#bearingFamilyPanel {{ background: #ffffff; border: 1px solid #cfe0ee; border-radius: 6px; }}
QLabel#bearingFamilyTitle {{ color: #0752a1; font-weight: 700; font-size: 13px; padding: 1px 2px; }}
QPushButton#bearingModelCard {{
    background: #fbfdff;
    color: #0d3761;
    border: 1px solid #caddeb;
    border-radius: 5px;
    padding: 5px 6px;
    font-weight: 700;
}}
QPushButton#bearingModelCard:hover {{ background: #f0f7ff; border-color: #78b7ea; }}
QPushButton#bearingModelCard:checked {{ background: #eef7ff; color: #0752a1; border: 2px solid #2589df; }}
QPushButton#bearingModelCard[blocked="true"] {{ color: #879aa9; background: #f6f8fa; border-color: #d9e1e7; }}
QFrame#bearingMetricPanel, QFrame#additionalResultsPanel {{ background: #ffffff; border: 1px solid #cfe0ee; border-radius: 6px; }}
QFrame#bearingActionBar {{ background: #eef7ff; border: 1px solid #bcdcf5; border-radius: 5px; }}
QLabel#bearingStateLabel {{ color: #168345; font-weight: 600; padding: 0 6px; }}
QLabel#bearingStateLabel[state="STALE"], QLabel#bearingStateLabel[state="ERROR"] {{ color: #b65a00; }}
QFrame#bearingResultsArea {{ background: #ffffff; border: 1px solid #cfe0ee; border-radius: 6px; }}
QPushButton#bearingResultTile {{
    background: #ffffff;
    color: #0d3761;
    border: 1px solid #cfe0ee;
    border-radius: 5px;
    padding: 6px;
    font-size: 12px;
    font-weight: 600;
}}
QPushButton#bearingResultTile:hover {{ background: #eef7ff; border-color: #78b7ea; }}
QPushButton#bearingResultTile:disabled {{ color: #a6b4bf; background: #f8fafb; border-color: #e0e7ec; }}
QTableView#bearingCoefficientTable {{ selection-background-color: #d9ecfb; selection-color: #0d3153; }}

QFrame#statusBar {{ background: {COLORS.surface}; border-top: 1px solid {COLORS.border_soft}; }}
QLabel#statusSuccess {{ color: #158845; font-weight: 600; }}
QFrame#kpiCard {{ background: white; border: 1px solid {COLORS.border}; border-radius: 6px; }}
QLabel#kpiValue {{ color: #0f73db; font-size: 29px; font-weight: 700; }}
QLabel#kpiTitle {{ color: {COLORS.text}; font-size: 13px; }}
QDialog#solverConsole {{ background: {COLORS.console_panel}; border: 1px solid {COLORS.console_border}; }}
QDialog#solverConsole QLabel {{ color: {COLORS.console_text}; }}
QFrame#consoleTitleBar, QFrame#consoleFooter {{ background: #173753; }}
QLabel#consoleTitle {{ color: white; font-size: 17px; font-weight: 700; }}
QPlainTextEdit#consoleOutput {{ background: {COLORS.console_bg}; color: {COLORS.console_text}; border: none; border-radius: 0; font-family: 'Consolas', 'DejaVu Sans Mono', monospace; font-size: 12px; padding: 12px; }}
QFrame#consoleSide {{ background: #10263a; border-left: 1px solid {COLORS.console_border}; }}
QLabel#consoleCompleted {{ color: #4de28b; font-size: 22px; font-weight: 700; }}
QProgressBar {{ background: #18354b; border: 1px solid #2b4a64; border-radius: 4px; text-align: center; color: white; }}
QProgressBar::chunk {{ background: #32d37c; border-radius: 3px; }}
"""
