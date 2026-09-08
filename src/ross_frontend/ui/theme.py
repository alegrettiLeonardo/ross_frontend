from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Palette:
    navy: str = "#103B5D"
    navy_dark: str = "#0B2E49"
    sidebar: str = "#123A59"
    sidebar_dark: str = "#0F304B"
    blue: str = "#137FF1"
    blue_dark: str = "#0B69D2"
    blue_soft: str = "#EAF4FF"
    text: str = "#123A64"
    text_dark: str = "#082E56"
    muted: str = "#60768E"
    border: str = "#CFDDEA"
    border_soft: str = "#DEE8F2"
    background: str = "#F4F8FC"
    card: str = "#FFFFFF"
    row_alt: str = "#F8FBFE"
    selected_row: str = "#E5F2FF"
    success: str = "#16A66B"
    success_soft: str = "#E6F8F0"
    warning: str = "#E9A23B"
    danger: str = "#E2575A"
    terminal: str = "#071B2B"
    terminal_panel: str = "#0E2639"
    terminal_line: str = "#1A3B51"
    terminal_text: str = "#E7F0F7"


P = Palette()


def application_stylesheet() -> str:
    return f"""
    * {{ font-family: "Segoe UI", "Inter", "Arial"; font-size: 13px; color: {P.text}; }}
    QMainWindow, QWidget#AppRoot {{ background: {P.background}; }}
    QWidget#ContentHost {{ background: {P.background}; }}
    QFrame#TitleBar {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 {P.navy}, stop:1 {P.navy_dark}); border: none; }}
    QLabel#AppTitle {{ color: white; font-size: 19px; font-weight: 700; letter-spacing: 0.5px; }}
    QLabel#ProjectTitle {{ color: #D9E8F5; font-size: 15px; font-weight: 600; }}
    QToolButton#WindowButton {{ color: white; background: transparent; border: none; border-radius: 0; }}
    QToolButton#WindowButton:hover {{ background: rgba(255,255,255,0.10); }}
    QToolButton#CloseButton {{ color: white; background: transparent; border: none; }}
    QToolButton#CloseButton:hover {{ background: #C42B1C; }}
    QFrame#Sidebar {{ background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 {P.sidebar}, stop:1 {P.sidebar_dark}); border: none; }}
    QLabel#SidebarSection {{ color: #AFC7DA; font-size: 11px; font-weight: 700; letter-spacing: 1.3px; }}
    QToolButton#NavButton {{ color: #EAF2F8; background: transparent; border: none; border-radius: 5px; text-align: left; padding: 7px 10px; font-size: 13px; }}
    QToolButton#NavButton:hover {{ background: rgba(255,255,255,0.07); }}
    QToolButton#NavButton:checked {{ background: {P.blue}; color: white; font-weight: 600; }}
    QFrame#TopToolbar {{ background: white; border-bottom: 1px solid {P.border_soft}; }}
    QToolButton#ToolbarButton {{ color: {P.text}; background: transparent; border: none; border-radius: 5px; padding: 7px 8px; }}
    QToolButton#ToolbarButton:hover {{ background: {P.blue_soft}; }}
    QToolButton#ToolbarButton:disabled {{ color: #A5B3C1; }}
    QFrame#Card {{ background: white; border: 1px solid {P.border}; border-radius: 7px; }}
    QFrame#FlatCard {{ background: white; border: 1px solid {P.border}; border-radius: 5px; }}
    QLabel#CardTitle {{ color: {P.text_dark}; font-size: 16px; font-weight: 700; }}
    QLabel#SectionTitle {{ color: {P.text_dark}; font-size: 15px; font-weight: 700; }}
    QLabel#SmallHeader {{ color: {P.text_dark}; font-size: 12px; font-weight: 700; }}
    QLabel#Muted {{ color: {P.muted}; }}
    QLabel#KpiValue {{ color: {P.blue}; font-size: 24px; font-weight: 700; }}
    QLabel#KpiLabel {{ color: {P.text}; font-size: 12px; font-weight: 600; }}
    QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QTextEdit {{ background: white; border: 1px solid {P.border}; border-radius: 5px; padding: 5px 7px; selection-background-color: {P.blue}; }}
    QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QTextEdit:focus {{ border: 1px solid {P.blue}; }}
    QComboBox::drop-down {{ border: none; width: 24px; }}
    QPushButton {{ background: #F7FAFD; color: {P.text}; border: 1px solid {P.border}; border-radius: 5px; padding: 7px 12px; font-weight: 600; }}
    QPushButton:hover {{ background: {P.blue_soft}; border-color: #AFCBE8; }}
    QPushButton#PrimaryButton {{ background: {P.blue}; color: white; border-color: {P.blue}; }}
    QPushButton#PrimaryButton:hover {{ background: {P.blue_dark}; }}
    QPushButton#SuccessButton {{ background: {P.success_soft}; color: {P.text}; border-color: #A7E1C8; }}
    QTableWidget {{ background: white; alternate-background-color: {P.row_alt}; border: 1px solid {P.border}; border-radius: 5px; gridline-color: {P.border_soft}; selection-background-color: {P.selected_row}; selection-color: {P.text_dark}; }}
    QHeaderView::section {{ background: #F6FAFE; color: {P.text_dark}; border: none; border-right: 1px solid {P.border_soft}; border-bottom: 1px solid {P.border}; padding: 7px 6px; font-weight: 700; }}
    QTableWidget::item {{ padding: 5px; }}
    QTabBar::tab {{ background: transparent; color: {P.text}; padding: 10px 20px; border: none; border-bottom: 2px solid transparent; }}
    QTabBar::tab:selected {{ color: {P.blue}; font-weight: 700; border-bottom: 3px solid {P.blue}; }}
    QTabWidget::pane {{ border: none; }}
    QCheckBox {{ spacing: 7px; }}
    QCheckBox::indicator {{ width: 16px; height: 16px; border: 1px solid {P.border}; border-radius: 3px; background: white; }}
    QCheckBox::indicator:checked {{ background: {P.blue}; border-color: {P.blue}; }}
    QProgressBar {{ border: none; background: #18394D; border-radius: 5px; height: 10px; text-align:center; color: transparent; }}
    QProgressBar::chunk {{ background: #28D783; border-radius: 5px; }}
    QStatusBar {{ background: white; border-top: 1px solid {P.border_soft}; }}
    QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
    QScrollBar::handle:vertical {{ background: #C9D7E4; border-radius: 5px; min-height: 30px; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    """
