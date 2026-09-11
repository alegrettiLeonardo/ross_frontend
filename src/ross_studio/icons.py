from __future__ import annotations

import math

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


def _ring(p: QPainter, s: float, outer: float = 0.70, inner: float = 0.34) -> None:
    o = (1.0 - outer) / 2.0
    i = (1.0 - inner) / 2.0
    p.drawEllipse(QRectF(s * o, s * o, s * outer, s * outer))
    p.drawEllipse(QRectF(s * i, s * i, s * inner, s * inner))


def _ball_bearing(p: QPainter, s: float) -> None:
    _ring(p, s, 0.74, 0.34)
    for angle in range(0, 360, 45):
        r = 0.265 * s
        a = math.radians(angle)
        x = 0.5 * s + r * math.cos(a)
        y = 0.5 * s + r * math.sin(a)
        p.drawEllipse(QRectF(x - 0.045 * s, y - 0.045 * s, 0.09 * s, 0.09 * s))


def engineering_icon(name: str, size: int = 22, color: str = BLUE) -> QIcon:
    """Draw scalable engineering icons used throughout the desktop application.

    Icons are deliberately vector-like QPainter geometry rather than font glyphs so
    the Windows/Linux frozen builds render the same symbols without external fonts.
    """

    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    s = float(size)
    c = QColor(color)
    _pen(p, color, max(1.4, s * 0.065))

    if name == "brand":
        p.setBrush(QColor("#46aafa")); p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QRectF(s*0.08, s*0.08, s*0.84, s*0.84))
        p.setBrush(QColor("#154c78")); p.drawEllipse(QRectF(s*0.26, s*0.26, s*0.48, s*0.48))
        p.setBrush(QColor("#b6e1ff")); p.drawEllipse(QRectF(s*0.42, s*0.42, s*0.16, s*0.16))
    elif name == "home":
        path = QPainterPath(); path.moveTo(s*.14,s*.48); path.lineTo(s*.5,s*.17); path.lineTo(s*.86,s*.48)
        p.drawPath(path); p.drawRoundedRect(QRectF(s*.24,s*.45,s*.52,s*.39),s*.03,s*.03); p.drawRect(QRectF(s*.45,s*.62,s*.12,s*.22))
    elif name == "rotor":
        p.drawLine(QPointF(s*.08,s*.50),QPointF(s*.92,s*.50))
        p.drawRoundedRect(QRectF(s*.22,s*.39,s*.24,s*.22),s*.03,s*.03)
        p.drawRoundedRect(QRectF(s*.54,s*.36,s*.27,s*.28),s*.03,s*.03)
        p.drawLine(QPointF(s*.30,s*.25),QPointF(s*.30,s*.75)); p.drawLine(QPointF(s*.72,s*.22),QPointF(s*.72,s*.78))
    elif name == "shaft":
        p.drawRoundedRect(QRectF(s*.12,s*.40,s*.76,s*.20),s*.04,s*.04)
        p.drawLine(QPointF(s*.27,s*.31),QPointF(s*.27,s*.69)); p.drawLine(QPointF(s*.68,s*.31),QPointF(s*.68,s*.69))
        p.drawLine(QPointF(s*.08,s*.50),QPointF(s*.92,s*.50))
    elif name == "disk":
        p.drawEllipse(QRectF(s*.27,s*.12,s*.46,s*.76)); p.drawEllipse(QRectF(s*.43,s*.37,s*.14,s*.26)); p.drawLine(QPointF(s*.07,s*.5),QPointF(s*.93,s*.5))
    elif name in {"bearing", "ball_bearing"}:
        _ball_bearing(p, s)
    elif name == "roller_bearing":
        _ring(p, s, 0.75, 0.33)
        for angle in range(0, 360, 60):
            r = 0.265 * s
            a = math.radians(angle)
            x = 0.5 * s + r * math.cos(a)
            y = 0.5 * s + r * math.sin(a)
            p.save(); p.translate(x, y); p.rotate(angle + 90)
            p.drawRoundedRect(QRectF(-s*.035,-s*.075,s*.07,s*.15),s*.015,s*.015); p.restore()
    elif name == "bearing_kc":
        # Spring and viscous damper in parallel, the conventional direct K/C symbol.
        p.drawLine(QPointF(s*.16,s*.18),QPointF(s*.16,s*.82)); p.drawLine(QPointF(s*.84,s*.18),QPointF(s*.84,s*.82))
        spring = QPainterPath(); spring.moveTo(s*.16,s*.36); spring.lineTo(s*.28,s*.36); spring.lineTo(s*.34,s*.27); spring.lineTo(s*.42,s*.45); spring.lineTo(s*.50,s*.27); spring.lineTo(s*.58,s*.45); spring.lineTo(s*.66,s*.36); spring.lineTo(s*.84,s*.36); p.drawPath(spring)
        p.drawLine(QPointF(s*.16,s*.66),QPointF(s*.39,s*.66)); p.drawRect(QRectF(s*.39,s*.57,s*.20,s*.18)); p.drawLine(QPointF(s*.49,s*.57),QPointF(s*.49,s*.48)); p.drawLine(QPointF(s*.49,s*.48),QPointF(s*.72,s*.48)); p.drawLine(QPointF(s*.72,s*.48),QPointF(s*.72,s*.66)); p.drawLine(QPointF(s*.59,s*.66),QPointF(s*.84,s*.66))
    elif name == "cylindrical_bearing":
        p.drawEllipse(QRectF(s*.15,s*.25,s*.28,s*.50)); p.drawEllipse(QRectF(s*.57,s*.25,s*.28,s*.50))
        p.drawLine(QPointF(s*.29,s*.25),QPointF(s*.71,s*.25)); p.drawLine(QPointF(s*.29,s*.75),QPointF(s*.71,s*.75))
        p.drawEllipse(QRectF(s*.23,s*.36,s*.18,s*.28)); p.drawEllipse(QRectF(s*.59,s*.36,s*.18,s*.28))
    elif name == "plain_journal":
        p.drawEllipse(QRectF(s*.12,s*.12,s*.76,s*.76)); p.drawEllipse(QRectF(s*.28,s*.28,s*.44,s*.44))
        p.setBrush(QColor(LIGHT)); p.drawEllipse(QRectF(s*.38,s*.35,s*.29,s*.29)); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawLine(QPointF(s*.22,s*.18),QPointF(s*.78,s*.82))
    elif name == "tilting_pad":
        p.drawEllipse(QRectF(s*.34,s*.34,s*.32,s*.32))
        for angle in range(0, 360, 72):
            p.save(); p.translate(s*.5,s*.5); p.rotate(angle)
            p.drawArc(QRectF(-s*.36,-s*.36,s*.72,s*.72), 68*16, 42*16)
            p.drawEllipse(QRectF(-s*.025,-s*.34,s*.05,s*.05)); p.restore()
    elif name == "thrust_pad":
        p.drawEllipse(QRectF(s*.14,s*.14,s*.72,s*.72)); p.drawEllipse(QRectF(s*.38,s*.38,s*.24,s*.24))
        for angle in range(0, 360, 45):
            a = math.radians(angle)
            p.drawLine(QPointF(s*(.5+.12*math.cos(a)),s*(.5+.12*math.sin(a))), QPointF(s*(.5+.36*math.cos(a)),s*(.5+.36*math.sin(a))))
    elif name == "sfd":
        p.drawEllipse(QRectF(s*.13,s*.13,s*.74,s*.74)); p.drawEllipse(QRectF(s*.28,s*.28,s*.44,s*.44))
        path=QPainterPath(); path.moveTo(s*.18,s*.50); path.cubicTo(s*.27,s*.38,s*.33,s*.62,s*.41,s*.50); path.cubicTo(s*.49,s*.38,s*.56,s*.62,s*.64,s*.50); path.cubicTo(s*.72,s*.38,s*.78,s*.60,s*.84,s*.50); p.drawPath(path)
    elif name == "amb":
        p.drawEllipse(QRectF(s*.38,s*.38,s*.24,s*.24))
        for angle in (0,90,180,270):
            p.save(); p.translate(s*.5,s*.5); p.rotate(angle)
            p.drawRoundedRect(QRectF(s*.16,-s*.12,s*.24,s*.24),s*.03,s*.03)
            p.drawLine(QPointF(s*.08,-s*.12),QPointF(s*.08,s*.12)); p.drawLine(QPointF(s*.12,-s*.12),QPointF(s*.12,s*.12)); p.restore()
    elif name == "seal":
        p.drawLine(QPointF(s*.10,s*.50),QPointF(s*.90,s*.50)); p.drawRect(QRectF(s*.22,s*.22,s*.14,s*.56)); p.drawRect(QRectF(s*.64,s*.22,s*.14,s*.56))
        p.drawLine(QPointF(s*.36,s*.36),QPointF(s*.52,s*.36)); p.drawLine(QPointF(s*.48,s*.64),QPointF(s*.64,s*.64))
    elif name == "support":
        p.drawRoundedRect(QRectF(s*.35,s*.14,s*.30,s*.23),s*.04,s*.04); p.drawLine(QPointF(s*.42,s*.37),QPointF(s*.27,s*.73)); p.drawLine(QPointF(s*.58,s*.37),QPointF(s*.73,s*.73)); p.drawLine(QPointF(s*.18,s*.76),QPointF(s*.82,s*.76))
        for x in (.27,.39,.51,.63,.75): p.drawLine(QPointF(s*x,s*.76),QPointF(s*(x-.08),s*.86))
    elif name == "coupling":
        p.drawLine(QPointF(s*.07,s*.50),QPointF(s*.93,s*.50)); p.drawRoundedRect(QRectF(s*.18,s*.28,s*.24,s*.44),s*.03,s*.03); p.drawRoundedRect(QRectF(s*.58,s*.28,s*.24,s*.44),s*.03,s*.03); p.drawLine(QPointF(s*.47,s*.30),QPointF(s*.47,s*.70)); p.drawLine(QPointF(s*.53,s*.30),QPointF(s*.53,s*.70))
    elif name == "loads":
        p.drawLine(QPointF(s*.50,s*.12),QPointF(s*.50,s*.70)); path=QPainterPath(); path.moveTo(s*.36,s*.55); path.lineTo(s*.50,s*.74); path.lineTo(s*.64,s*.55); p.drawPath(path); p.drawLine(QPointF(s*.20,s*.82),QPointF(s*.80,s*.82))
    elif name == "probe":
        p.drawLine(QPointF(s*.18,s*.82),QPointF(s*.64,s*.36)); p.drawRoundedRect(QRectF(s*.10,s*.68,s*.22,s*.20),s*.03,s*.03); p.drawEllipse(QRectF(s*.60,s*.32,s*.14,s*.14)); p.drawArc(QRectF(s*.49,s*.21,s*.36,s*.36),20*16,110*16)
    elif name in {"wave", "transient", "amplification"}:
        path=QPainterPath(); path.moveTo(s*.08,s*.56); path.lineTo(s*.24,s*.56); path.lineTo(s*.34,s*.26); path.lineTo(s*.48,s*.76); path.lineTo(s*.62,s*.38); path.lineTo(s*.72,s*.56); path.lineTo(s*.92,s*.56); p.drawPath(path)
    elif name == "response":
        for i,h in enumerate((.28,.55,.74,.42)):
            x=s*(.18+i*.18); p.drawLine(QPointF(x,s*.78),QPointF(x,s*(.78-h)))
        p.drawLine(QPointF(s*.12,s*.80),QPointF(s*.88,s*.80))
    elif name == "shield":
        path=QPainterPath(); path.moveTo(s*.5,s*.13); path.lineTo(s*.8,s*.25); path.lineTo(s*.76,s*.58); path.quadTo(s*.7,s*.78,s*.5,s*.88); path.quadTo(s*.3,s*.78,s*.24,s*.58); path.lineTo(s*.2,s*.25); path.closeSubpath(); p.drawPath(path)
    elif name == "fault":
        path=QPainterPath(); path.moveTo(s*.5,s*.13); path.lineTo(s*.88,s*.82); path.lineTo(s*.12,s*.82); path.closeSubpath(); p.drawPath(path); p.drawLine(QPointF(s*.5,s*.38),QPointF(s*.5,s*.59)); p.drawEllipse(QRectF(s*.48,s*.67,s*.04,s*.04))
    elif name == "stochastic":
        p.drawRoundedRect(QRectF(s*.18,s*.18,s*.64,s*.64),s*.08,s*.08)
        for x,y in ((.34,.34),(.66,.34),(.5,.5),(.34,.66),(.66,.66)):
            p.setBrush(c); p.drawEllipse(QRectF(s*(x-.035),s*(y-.035),s*.07,s*.07)); p.setBrush(Qt.BrushStyle.NoBrush)
    elif name == "results":
        p.drawRect(QRectF(s*.15,s*.18,s*.7,s*.64)); p.drawLine(QPointF(s*.25,s*.7),QPointF(s*.39,s*.56)); p.drawLine(QPointF(s*.39,s*.56),QPointF(s*.52,s*.62)); p.drawLine(QPointF(s*.52,s*.62),QPointF(s*.72,s*.36))
    elif name == "new":
        p.drawRect(QRectF(s*.28,s*.14,s*.44,s*.72)); p.drawLine(QPointF(s*.58,s*.14),QPointF(s*.72,s*.28)); p.drawLine(QPointF(s*.58,s*.14),QPointF(s*.58,s*.28)); p.drawLine(QPointF(s*.58,s*.28),QPointF(s*.72,s*.28))
    elif name == "open":
        path=QPainterPath(); path.moveTo(s*.13,s*.36); path.lineTo(s*.38,s*.36); path.lineTo(s*.46,s*.25); path.lineTo(s*.82,s*.25); path.lineTo(s*.88,s*.42); path.lineTo(s*.25,s*.79); path.lineTo(s*.12,s*.64); path.closeSubpath(); p.drawPath(path)
    elif name == "save":
        p.drawRoundedRect(QRectF(s*.2,s*.15,s*.6,s*.7),s*.03,s*.03); p.drawRect(QRectF(s*.32,s*.17,s*.32,s*.22)); p.drawRect(QRectF(s*.34,s*.56,s*.32,s*.24))
    elif name in {"undo","redo"}:
        if name == "undo":
            path=QPainterPath(); path.moveTo(s*.37,s*.28); path.lineTo(s*.18,s*.43); path.lineTo(s*.37,s*.58); p.drawPath(path); p.drawArc(QRectF(s*.26,s*.26,s*.56,s*.5),-75*16,230*16)
        else:
            path=QPainterPath(); path.moveTo(s*.63,s*.28); path.lineTo(s*.82,s*.43); path.lineTo(s*.63,s*.58); p.drawPath(path); p.drawArc(QRectF(s*.18,s*.26,s*.56,s*.5),25*16,230*16)
    elif name in {"zoom_in","zoom_out"}:
        p.drawEllipse(QRectF(s*.16,s*.16,s*.48,s*.48)); p.drawLine(QPointF(s*.58,s*.58),QPointF(s*.84,s*.84)); p.drawLine(QPointF(s*.28,s*.4),QPointF(s*.52,s*.4))
        if name == "zoom_in": p.drawLine(QPointF(s*.4,s*.28),QPointF(s*.4,s*.52))
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
        p.drawEllipse(QRectF(s*.32,s*.32,s*.36,s*.36)); p.drawEllipse(QRectF(s*.44,s*.44,s*.12,s*.12))
        for a in range(0,360,45):
            x1=s*(.5+.26*math.cos(math.radians(a))); y1=s*(.5+.26*math.sin(math.radians(a))); x2=s*(.5+.37*math.cos(math.radians(a))); y2=s*(.5+.37*math.sin(math.radians(a))); p.drawLine(QPointF(x1,y1),QPointF(x2,y2))
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
    elif name == "minus":
        p.drawLine(QPointF(s*.24,s*.5),QPointF(s*.76,s*.5))
    else:
        p.drawEllipse(QRectF(s*.18,s*.18,s*.64,s*.64)); p.drawLine(QPointF(s*.32,s*.5),QPointF(s*.68,s*.5))

    p.end()
    return QIcon(pm)
