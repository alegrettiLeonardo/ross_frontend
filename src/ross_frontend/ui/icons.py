from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap


def studio_icon(name: str, color: str = "#DDEBF6", size: int = 20) -> QIcon:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pen = QPen(QColor(color), max(1.4, size / 13.0), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen); painter.setBrush(Qt.BrushStyle.NoBrush)
    r = QRectF(2.5, 2.5, size - 5.0, size - 5.0); cx, cy = size / 2.0, size / 2.0
    if name == "home":
        path=QPainterPath(QPointF(3.5,9)); path.lineTo(cx,3.2); path.lineTo(size-3.5,9); painter.drawPath(path); painter.drawRect(QRectF(5.5,8.5,size-11,size-11))
    elif name in {"rotor","shaft"}:
        painter.drawLine(QPointF(3,cy),QPointF(size-3,cy)); painter.drawEllipse(QPointF(6,cy),2.2,2.2); painter.drawEllipse(QPointF(size-6,cy),2.2,2.2); painter.drawRect(QRectF(cx-2.3,4,4.6,size-8))
    elif name == "disk":
        painter.drawEllipse(r); painter.drawLine(QPointF(cx,3),QPointF(cx,size-3)); painter.drawEllipse(QPointF(cx,cy),2.2,2.2)
    elif name == "bearing":
        painter.drawEllipse(r); painter.drawEllipse(QRectF(6,6,size-12,size-12)); painter.drawLine(QPointF(3,cy),QPointF(size-3,cy))
    elif name == "seal":
        painter.drawArc(r,35*16,290*16); painter.drawLine(QPointF(5,size-4),QPointF(size-5,size-4)); painter.drawLine(QPointF(cx,4),QPointF(cx,size-7))
    elif name == "support":
        painter.drawLine(QPointF(cx,4),QPointF(cx,11)); painter.drawLine(QPointF(cx,11),QPointF(5,size-5)); painter.drawLine(QPointF(cx,11),QPointF(size-5,size-5)); painter.drawLine(QPointF(4,size-3),QPointF(size-4,size-3))
    elif name == "coupling":
        painter.drawRect(QRectF(3,6,5,size-12)); painter.drawRect(QRectF(size-8,6,5,size-12)); painter.drawLine(QPointF(8,cy),QPointF(size-8,cy))
    elif name == "load":
        painter.drawLine(QPointF(3,cy),QPointF(size-6,cy)); painter.drawLine(QPointF(size-6,cy),QPointF(size-10,cy-4)); painter.drawLine(QPointF(size-6,cy),QPointF(size-10,cy+4))
    elif name in {"wave","transient"}:
        path=QPainterPath(QPointF(2,cy)); path.cubicTo(5,cy,5,3,8,3); path.cubicTo(11,3,10,size-3,13,size-3); path.cubicTo(16,size-3,15,cy,size-2,cy); painter.drawPath(path)
    elif name == "response":
        for i,h in enumerate((7,12,16,10)): x=3+i*4; painter.drawLine(QPointF(x,size-3),QPointF(x,size-h))
    elif name == "shield":
        path=QPainterPath(QPointF(cx,3)); path.lineTo(size-4,6); path.lineTo(size-5,size-8); path.quadTo(cx,size-2,5,size-8); path.lineTo(4,6); path.closeSubpath(); painter.drawPath(path)
    elif name == "warning":
        path=QPainterPath(QPointF(cx,3)); path.lineTo(size-3,size-4); path.lineTo(3,size-4); path.closeSubpath(); painter.drawPath(path); painter.drawLine(QPointF(cx,7),QPointF(cx,12)); painter.drawPoint(QPointF(cx,size-6))
    elif name == "stochastic":
        painter.drawRect(r); [painter.drawPoint(QPointF(x,y)) for x,y in ((7,7),(size-7,7),(cx,cy),(7,size-7),(size-7,size-7))]
    elif name == "results":
        painter.drawRect(QRectF(3,3,size-6,size-6)); path=QPainterPath(QPointF(5,size-6)); path.lineTo(9,11); path.lineTo(12,14); path.lineTo(size-5,6); painter.drawPath(path)
    elif name == "new":
        painter.drawRect(QRectF(5,3,size-10,size-6)); painter.drawLine(QPointF(cx,7),QPointF(cx,size-7)); painter.drawLine(QPointF(7,cy),QPointF(size-7,cy))
    elif name == "open":
        path=QPainterPath(QPointF(3,8)); path.lineTo(8,8); path.lineTo(10,5); path.lineTo(size-3,5); path.lineTo(size-5,size-4); path.lineTo(3,size-4); path.closeSubpath(); painter.drawPath(path)
    elif name == "save":
        painter.drawRect(r); painter.drawRect(QRectF(6,4,size-12,5)); painter.drawRect(QRectF(6,size-9,size-12,6))
    elif name in {"undo","redo"}:
        left=name=="undo"; painter.drawArc(QRectF(5,5,size-9,size-9),30*16 if left else 150*16,250*16); x=5 if left else size-5; painter.drawLine(QPointF(x,6),QPointF(x+(4 if left else -4),3)); painter.drawLine(QPointF(x,6),QPointF(x+(4 if left else -4),9))
    elif name == "zoom":
        painter.drawEllipse(QRectF(3,3,10,10)); painter.drawLine(QPointF(12,12),QPointF(size-3,size-3)); painter.drawLine(QPointF(6,8),QPointF(10,8)); painter.drawLine(QPointF(8,6),QPointF(8,10))
    elif name == "fit":
        for a,b in (((3,8),(3,3)),((3,3),(8,3)),((size-3,8),(size-3,3)),((size-3,3),(size-8,3)),((3,size-8),(3,size-3)),((3,size-3),(8,size-3)),((size-3,size-8),(size-3,size-3)),((size-3,size-3),(size-8,size-3))): painter.drawLine(QPointF(*a),QPointF(*b))
    elif name == "play":
        painter.setBrush(QColor(color)); path=QPainterPath(QPointF(6,4)); path.lineTo(size-4,cy); path.lineTo(6,size-4); path.closeSubpath(); painter.drawPath(path)
    elif name == "check":
        painter.drawEllipse(r); painter.drawLine(QPointF(6,cy),QPointF(9,size-6)); painter.drawLine(QPointF(9,size-6),QPointF(size-5,6))
    elif name == "trash":
        painter.drawRect(QRectF(6,7,size-12,size-9)); painter.drawLine(QPointF(5,6),QPointF(size-5,6)); painter.drawLine(QPointF(8,4),QPointF(size-8,4))
    elif name == "export":
        painter.drawRect(QRectF(4,8,size-8,size-5)); painter.drawLine(QPointF(cx,3),QPointF(cx,12)); painter.drawLine(QPointF(cx,3),QPointF(cx-4,7)); painter.drawLine(QPointF(cx,3),QPointF(cx+4,7))
    elif name == "gear":
        painter.drawEllipse(QRectF(5,5,size-10,size-10)); painter.drawEllipse(QRectF(8,8,size-16,size-16))
        for dx,dy in ((0,-1),(0,1),(-1,0),(1,0)): painter.drawLine(QPointF(cx+dx*6,cy+dy*6),QPointF(cx+dx*8,cy+dy*8))
    elif name == "coefficient":
        path=QPainterPath(QPointF(5,3)); path.lineTo(5,6); path.lineTo(3.5,8); path.lineTo(6.5,10); path.lineTo(3.5,12); path.lineTo(6.5,14); path.lineTo(5,16); path.lineTo(5,size-3); painter.drawPath(path); painter.drawLine(QPointF(size-7,3),QPointF(size-7,8)); painter.drawRect(QRectF(size-10,8,6,5)); painter.drawLine(QPointF(size-7,13),QPointF(size-7,size-3)); painter.drawLine(QPointF(size-12,3),QPointF(size-2,3))
    elif name in {"ball","roller","cylindrical","journal","tilting"}:
        painter.drawEllipse(r); painter.drawEllipse(QRectF(6,6,size-12,size-12))
        if name=="tilting":
            import math
            for a in range(0,360,60): painter.drawLine(QPointF(cx+4*math.cos(math.radians(a)),cy+4*math.sin(math.radians(a))),QPointF(cx+8*math.cos(math.radians(a)),cy+8*math.sin(math.radians(a))))
    else: painter.drawEllipse(r)
    painter.end(); return QIcon(pm)


def app_icon(size: int = 28) -> QIcon:
    pm=QPixmap(size,size); pm.fill(Qt.GlobalColor.transparent); p=QPainter(pm); p.setRenderHint(QPainter.RenderHint.Antialiasing,True); p.setBrush(QColor("#1685F7")); p.setPen(Qt.PenStyle.NoPen); p.drawEllipse(QRectF(1,1,size-2,size-2)); p.setBrush(QColor("#103B5D")); p.drawEllipse(QRectF(size*.28,size*.28,size*.44,size*.44)); p.setBrush(QColor("#BFE1FF")); p.drawEllipse(QRectF(size*.40,size*.40,size*.20,size*.20)); p.end(); return QIcon(pm)
