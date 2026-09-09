from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap


BLUE = "#184f7d"
LIGHT = "#d9ebf8"
WHITE = "#f4f9fd"
GREEN = "#1ba85b"
RED = "#d84f57"


def _pen(p: QPainter, color: str, width: float = 1.8) -> None:
    pen = QPen(QColor(color), width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)


def engineering_icon(name: str, size: int = 22, color: str = BLUE) -> QIcon:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    s = float(size)
    c = QColor(color)
    _pen(p, color, max(1.4, s * 0.075))

    if name == "brand":
        p.setBrush(QColor("#39a4ff")); p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QRectF(s*0.08, s*0.08, s*0.84, s*0.84))
        p.setBrush(QColor("#154c78")); p.drawEllipse(QRectF(s*0.26, s*0.26, s*0.48, s*0.48))
        p.setBrush(QColor("#9ed6ff")); p.drawEllipse(QRectF(s*0.42, s*0.42, s*0.16, s*0.16))
    elif name == "home":
        path=QPainterPath(); path.moveTo(s*.15,s*.48); path.lineTo(s*.5,s*.18); path.lineTo(s*.85,s*.48)
        p.drawPath(path); p.drawRect(QRectF(s*.25,s*.45,s*.5,s*.38)); p.drawRect(QRectF(s*.45,s*.62,s*.12,s*.21))
    elif name == "rotor":
        p.drawLine(QPointF(s*.18,s*.52),QPointF(s*.82,s*.52)); p.drawEllipse(QRectF(s*.19,s*.34,s*.17,s*.36)); p.drawEllipse(QRectF(s*.64,s*.30,s*.18,s*.44)); p.drawEllipse(QRectF(s*.43,s*.45,s*.12,s*.14))
    elif name == "shaft":
        p.drawRoundedRect(QRectF(s*.14,s*.38,s*.72,s*.26),s*.05,s*.05); p.drawLine(QPointF(s*.28,s*.3),QPointF(s*.28,s*.72)); p.drawLine(QPointF(s*.68,s*.3),QPointF(s*.68,s*.72))
    elif name == "disk":
        p.drawEllipse(QRectF(s*.22,s*.16,s*.56,s*.68)); p.drawEllipse(QRectF(s*.43,s*.38,s*.14,s*.24)); p.drawLine(QPointF(s*.08,s*.5),QPointF(s*.92,s*.5))
    elif name in {"bearing","seal"}:
        p.drawEllipse(QRectF(s*.18,s*.18,s*.64,s*.64)); p.drawEllipse(QRectF(s*.32,s*.32,s*.36,s*.36));
        if name=="bearing":
            for dx,dy in ((.5,.23),(.76,.5),(.5,.77),(.24,.5)): p.drawEllipse(QRectF(s*(dx-.04),s*(dy-.04),s*.08,s*.08))
    elif name == "support":
        p.drawEllipse(QRectF(s*.4,s*.16,s*.2,s*.18)); p.drawLine(QPointF(s*.5,s*.34),QPointF(s*.26,s*.72)); p.drawLine(QPointF(s*.5,s*.34),QPointF(s*.74,s*.72)); p.drawLine(QPointF(s*.2,s*.76),QPointF(s*.8,s*.76))
    elif name == "coupling":
        p.drawRect(QRectF(s*.18,s*.32,s*.24,s*.36)); p.drawRect(QRectF(s*.58,s*.32,s*.24,s*.36)); p.drawLine(QPointF(s*.42,s*.5),QPointF(s*.58,s*.5))
    elif name == "loads":
        p.drawRoundedRect(QRectF(s*.16,s*.32,s*.68,s*.48),s*.08,s*.08); p.drawArc(QRectF(s*.34,s*.18,s*.32,s*.28),0*16,180*16)
    elif name in {"wave","transient"}:
        path=QPainterPath(); path.moveTo(s*.08,s*.56); path.lineTo(s*.24,s*.56); path.lineTo(s*.34,s*.26); path.lineTo(s*.48,s*.76); path.lineTo(s*.62,s*.38); path.lineTo(s*.72,s*.56); path.lineTo(s*.92,s*.56); p.drawPath(path)
    elif name == "response":
        for i,h in enumerate((.28,.55,.74,.42)):
            x=s*(.18+i*.18); p.drawLine(QPointF(x,s*.78),QPointF(x,s*(.78-h)))
    elif name == "shield":
        path=QPainterPath(); path.moveTo(s*.5,s*.13); path.lineTo(s*.8,s*.25); path.lineTo(s*.76,s*.58); path.quadTo(s*.7,s*.78,s*.5,s*.88); path.quadTo(s*.3,s*.78,s*.24,s*.58); path.lineTo(s*.2,s*.25); path.closeSubpath(); p.drawPath(path)
    elif name == "fault":
        path=QPainterPath(); path.moveTo(s*.5,s*.13); path.lineTo(s*.88,s*.82); path.lineTo(s*.12,s*.82); path.closeSubpath(); p.drawPath(path); p.drawLine(QPointF(s*.5,s*.38),QPointF(s*.5,s*.59)); p.drawEllipse(QRectF(s*.48,s*.67,s*.04,s*.04))
    elif name == "stochastic":
        p.drawRoundedRect(QRectF(s*.18,s*.18,s*.64,s*.64),s*.08,s*.08)
        for x,y in ((.34,.34),(.66,.34),(.5,.5),(.34,.66),(.66,.66)): p.setBrush(c); p.drawEllipse(QRectF(s*(x-.035),s*(y-.035),s*.07,s*.07)); p.setBrush(Qt.BrushStyle.NoBrush)
    elif name == "results":
        p.drawRect(QRectF(s*.15,s*.18,s*.7,s*.64)); p.drawLine(QPointF(s*.25,s*.7),QPointF(s*.39,s*.56)); p.drawLine(QPointF(s*.39,s*.56),QPointF(s*.52,s*.62)); p.drawLine(QPointF(s*.52,s*.62),QPointF(s*.72,s*.36))
    elif name == "new":
        p.drawRect(QRectF(s*.28,s*.14,s*.44,s*.72)); p.drawLine(QPointF(s*.58,s*.14),QPointF(s*.72,s*.28)); p.drawLine(QPointF(s*.58,s*.14),QPointF(s*.58,s*.28)); p.drawLine(QPointF(s*.58,s*.28),QPointF(s*.72,s*.28))
    elif name == "open":
        path=QPainterPath(); path.moveTo(s*.13,s*.36); path.lineTo(s*.38,s*.36); path.lineTo(s*.46,s*.25); path.lineTo(s*.82,s*.25); path.lineTo(s*.88,s*.42); path.lineTo(s*.25,s*.79); path.lineTo(s*.12,s*.64); path.closeSubpath(); p.drawPath(path)
    elif name == "save":
        p.drawRoundedRect(QRectF(s*.2,s*.15,s*.6,s*.7),s*.03,s*.03); p.drawRect(QRectF(s*.32,s*.17,s*.32,s*.22)); p.drawRect(QRectF(s*.34,s*.56,s*.32,s*.24))
    elif name in {"undo","redo"}:
        if name=="undo":
            path=QPainterPath(); path.moveTo(s*.37,s*.28); path.lineTo(s*.18,s*.43); path.lineTo(s*.37,s*.58); p.drawPath(path); p.drawArc(QRectF(s*.26,s*.26,s*.56,s*.5),-75*16,230*16)
        else:
            path=QPainterPath(); path.moveTo(s*.63,s*.28); path.lineTo(s*.82,s*.43); path.lineTo(s*.63,s*.58); p.drawPath(path); p.drawArc(QRectF(s*.18,s*.26,s*.56,s*.5),25*16,230*16)
    elif name in {"zoom_in","zoom_out"}:
        p.drawEllipse(QRectF(s*.16,s*.16,s*.48,s*.48)); p.drawLine(QPointF(s*.58,s*.58),QPointF(s*.84,s*.84)); p.drawLine(QPointF(s*.28,s*.4),QPointF(s*.52,s*.4));
        if name=="zoom_in": p.drawLine(QPointF(s*.4,s*.28),QPointF(s*.4,s*.52))
    elif name == "fit":
        for a,b in [((.18,.38),(.18,.18)),((.18,.18),(.38,.18)),((.62,.18),(.82,.18)),((.82,.18),(.82,.38)),((.18,.62),(.18,.82)),((.18,.82),(.38,.82)),((.62,.82),(.82,.82)),((.82,.82),(.82,.62))]: p.drawLine(QPointF(s*a[0],s*a[1]),QPointF(s*b[0],s*b[1]))
    elif name == "plus":
        p.drawLine(QPointF(s*.2,s*.5),QPointF(s*.8,s*.5)); p.drawLine(QPointF(s*.5,s*.2),QPointF(s*.5,s*.8))
    elif name == "trash":
        p.drawRect(QRectF(s*.28,s*.32,s*.44,s*.5)); p.drawLine(QPointF(s*.22,s*.28),QPointF(s*.78,s*.28)); p.drawLine(QPointF(s*.4,s*.2),QPointF(s*.6,s*.2))
    elif name == "import":
        p.drawRect(QRectF(s*.2,s*.55,s*.6,s*.28)); p.drawLine(QPointF(s*.5,s*.12),QPointF(s*.5,s*.6)); p.drawLine(QPointF(s*.34,s*.28),QPointF(s*.5,s*.12)); p.drawLine(QPointF(s*.66,s*.28),QPointF(s*.5,s*.12))
    elif name == "check":
        p.setBrush(QColor(GREEN)); p.setPen(Qt.PenStyle.NoPen); p.drawEllipse(QRectF(s*.1,s*.1,s*.8,s*.8)); _pen(p,WHITE,max(1.8,s*.09)); path=QPainterPath(); path.moveTo(s*.28,s*.5); path.lineTo(s*.43,s*.65); path.lineTo(s*.72,s*.34); p.drawPath(path)
    elif name == "play":
        p.setBrush(c); p.setPen(Qt.PenStyle.NoPen); path=QPainterPath(); path.moveTo(s*.28,s*.18); path.lineTo(s*.78,s*.5); path.lineTo(s*.28,s*.82); path.closeSubpath(); p.drawPath(path)
    elif name == "gear":
        p.drawEllipse(QRectF(s*.32,s*.32,s*.36,s*.36)); p.drawEllipse(QRectF(s*.44,s*.44,s*.12,s*.12));
        for a in range(0,360,45):
            import math; x1=s*(.5+.26*math.cos(math.radians(a))); y1=s*(.5+.26*math.sin(math.radians(a))); x2=s*(.5+.37*math.cos(math.radians(a))); y2=s*(.5+.37*math.sin(math.radians(a))); p.drawLine(QPointF(x1,y1),QPointF(x2,y2))
    elif name == "export":
        p.drawRect(QRectF(s*.18,s*.34,s*.64,s*.5)); p.drawLine(QPointF(s*.5,s*.12),QPointF(s*.5,s*.58)); p.drawLine(QPointF(s*.34,s*.28),QPointF(s*.5,s*.12)); p.drawLine(QPointF(s*.66,s*.28),QPointF(s*.5,s*.12))
    elif name == "image":
        p.drawRect(QRectF(s*.15,s*.18,s*.7,s*.64)); p.drawEllipse(QRectF(s*.26,s*.28,s*.12,s*.12)); path=QPainterPath(); path.moveTo(s*.22,s*.72); path.lineTo(s*.42,s*.48); path.lineTo(s*.55,s*.6); path.lineTo(s*.68,s*.42); path.lineTo(s*.8,s*.72); p.drawPath(path)
    elif name == "table":
        p.drawRect(QRectF(s*.15,s*.18,s*.7,s*.64)); p.drawLine(QPointF(s*.15,s*.38),QPointF(s*.85,s*.38)); p.drawLine(QPointF(s*.15,s*.58),QPointF(s*.85,s*.58)); p.drawLine(QPointF(s*.42,s*.18),QPointF(s*.42,s*.82)); p.drawLine(QPointF(s*.64,s*.18),QPointF(s*.64,s*.82))
    elif name == "report":
        p.drawRect(QRectF(s*.24,s*.12,s*.52,s*.76)); p.drawLine(QPointF(s*.34,s*.34),QPointF(s*.66,s*.34)); p.drawLine(QPointF(s*.34,s*.48),QPointF(s*.66,s*.48)); p.drawLine(QPointF(s*.34,s*.62),QPointF(s*.6,s*.62))
    elif name == "speed":
        p.drawArc(QRectF(s*.15,s*.2,s*.7,s*.7),0,180*16); p.drawLine(QPointF(s*.5,s*.55),QPointF(s*.68,s*.34)); p.drawEllipse(QRectF(s*.46,s*.51,s*.08,s*.08))
    elif name == "amplification":
        path=QPainterPath(); path.moveTo(s*.08,s*.56); path.lineTo(s*.22,s*.56); path.lineTo(s*.31,s*.22); path.lineTo(s*.44,s*.78); path.lineTo(s*.57,s*.35); path.lineTo(s*.7,s*.56); path.lineTo(s*.92,s*.56); p.drawPath(path)
    elif name == "minus":
        p.drawLine(QPointF(s*.24,s*.5),QPointF(s*.76,s*.5))
    else:
        p.drawEllipse(QRectF(s*.18,s*.18,s*.64,s*.64)); p.drawLine(QPointF(s*.32,s*.5),QPointF(s*.68,s*.5))

    p.end()
    return QIcon(pm)
