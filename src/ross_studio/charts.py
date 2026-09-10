from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from .models import BearingModel, ProjectModel
from .theme import COLORS

class RotorSketch(QWidget):
    def __init__(self, project: ProjectModel, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.project=project
        self.setMinimumHeight(270)

    def paintEvent(self, event) -> None:  # noqa: N802
        p=QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        w,h=self.width(),self.height(); left,right=62,w-44; cy=h*0.55
        p.setPen(QPen(QColor("#7892aa"),1,Qt.PenStyle.DashLine)); p.drawLine(QPointF(left-24,cy),QPointF(right+24,cy))
        total=sum(s.length_mm for s in self.project.segments); scale=(right-left)/total
        x=left
        fills=[("#f8fbfd","#cad5df"),("#f5f8fa","#c4d1dc")]
        pen=QPen(QColor("#4e6276"),1.4); p.setPen(pen)
        centers=[]
        for i,seg in enumerate(self.project.segments):
            sw=seg.length_mm*scale; od=max(seg.od_left_mm,seg.od_right_mm); sh=52+(od-50)*1.0
            grad=QColor(fills[i%2][0]); p.setBrush(grad); p.drawRect(QRectF(x,cy-sh/2,sw,sh)); centers.append(x+sw/2)
            p.setPen(QColor("#173b63")); p.drawText(QRectF(x,cy-18,sw,36),Qt.AlignmentFlag.AlignCenter,str(seg.section)); p.setPen(pen); x+=sw
        p.setBrush(QColor("#d8e1e8")); p.drawRect(QRectF(left-20,cy-15,20,30)); p.drawRect(QRectF(right,cy-15,20,30))
        for px,label in ((left+0.34*(right-left),"Disk 1"),(left+0.62*(right-left),"Disk 2")):
            p.setBrush(QColor("#7fb5e4")); p.setPen(QPen(QColor("#184f7d"),1.6)); p.drawRect(QRectF(px-18,cy-73,36,146));
            p.drawLine(QPointF(px,cy-92),QPointF(px,cy-73)); p.drawText(QRectF(px-48,cy-122,96,24),Qt.AlignmentFlag.AlignCenter,label)
        for px,label in ((left+20,"Bearing 1\n(Journal)"),(right-20,"Bearing 2\n(Journal)")):
            p.setBrush(QColor("#4b96d3")); p.setPen(QPen(QColor("#174c7d"),1.8)); p.drawRect(QRectF(px-18,cy-46,36,92)); p.setBrush(Qt.BrushStyle.NoBrush); p.drawEllipse(QRectF(px-8,cy-8,16,16)); p.drawLine(QPointF(px-11,cy-14),QPointF(px+11,cy+14)); p.drawLine(QPointF(px+11,cy-14),QPointF(px-11,cy+14))
            p.drawLine(QPointF(px,cy-68),QPointF(px,cy-46)); p.drawText(QRectF(px-68,cy-118,136,44),Qt.AlignmentFlag.AlignCenter,label)
            p.setBrush(QColor("#d5dadd")); p.drawRect(QRectF(px-7,cy+47,14,31)); p.setPen(QPen(QColor("#56687a"),1.4)); p.drawLine(QPointF(px-28,cy+80),QPointF(px+28,cy+80));
            for k in range(-24,25,8): p.drawLine(QPointF(px+k,cy+80),QPointF(px+k-8,cy+88))
        axx=30; axy=h-48; p.setPen(QPen(QColor("#173b63"),1.7)); p.drawLine(QPointF(axx,axy),QPointF(axx+42,axy)); p.drawLine(QPointF(axx,axy),QPointF(axx,axy-42)); p.drawText(axx+44,axy+5,"Z"); p.drawText(axx+6,axy-43,"Y")
        p.drawText(QRectF(right-180,h-42,175,24),Qt.AlignmentFlag.AlignRight,f"Total length: {self.project.total_length_mm:,.0f} mm")
        p.end()


class BearingCoefficientChart(QWidget):
    """Plot the complete solved table with independent stiffness/damping scales."""
    def __init__(self, bearing: BearingModel, parent=None):
        super().__init__(parent)
        self.bearing = bearing
        self.kind = "k"
        self.setMinimumSize(330, 220)

    def set_coefficient_kind(self, index):
        self.kind = "c" if index else "k"
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        plot = QRectF(80, 30, self.width()-155, self.height()-85)
        rows = self.bearing.coefficients
        names = [self.kind + suffix for suffix in ("xx", "xy", "yx", "yy")]
        if not rows:
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No solved coefficients")
            return
        xmin, xmax = min(r.rpm for r in rows), max(r.rpm for r in rows)
        if xmin == xmax:
            xmin, xmax = xmin-1, xmax+1
        values = [getattr(r, name) for r in rows for name in names]
        ymin, ymax = min(values), max(values)
        pad = max((ymax-ymin)*0.05, max(abs(ymin), abs(ymax))*0.01, 1e-12)
        ymin, ymax = ymin-pad, ymax+pad
        def xy(x, y):
            return QPointF(plot.left()+(x-xmin)/(xmax-xmin)*plot.width(), plot.bottom()-(y-ymin)/(ymax-ymin)*plot.height())
        for i in range(5):
            frac = i/4
            y = plot.bottom()-frac*plot.height()
            x = plot.left()+frac*plot.width()
            p.setPen(QColor(COLORS.grid))
            p.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            p.setPen(QColor(COLORS.text))
            p.drawText(QRectF(1,y-9,74,18), Qt.AlignmentFlag.AlignRight, f"{ymin+frac*(ymax-ymin):.2e}")
            p.drawText(QRectF(x-32,plot.bottom()+4,64,18), Qt.AlignmentFlag.AlignCenter, f"{xmin+frac*(xmax-xmin):g}")
        for i, (name, color) in enumerate(zip(names, ("#1487e8", "#109b56", "#f3a000", "#ff3b30"))):
            p.setPen(QPen(QColor(color), 2))
            path = QPainterPath()
            for j, row in enumerate(rows):
                pt = xy(row.rpm, getattr(row, name))
                if j == 0:
                    path.moveTo(pt)
                else:
                    path.lineTo(pt)
                p.drawEllipse(pt, 2, 2)
            p.drawPath(path)
            p.drawText(QRectF(plot.right()+8, plot.top()+i*22, 60, 20), Qt.AlignmentFlag.AlignLeft, name.capitalize())
        unit = "N/m" if self.kind == "k" else "N·s/m"
        p.setPen(QColor(COLORS.text))
        p.drawText(QRectF(0,0,self.width(),24), Qt.AlignmentFlag.AlignCenter, f"Solved {self.kind.upper()} ({unit})")
        p.drawText(QRectF(0,self.height()-24,self.width(),20), Qt.AlignmentFlag.AlignCenter, "Speed (rpm)")
        p.end()


class CampbellChart(QWidget):
    def __init__(self,parent:QWidget|None=None) -> None:
        super().__init__(parent); self.setMinimumSize(560,390)

    def paintEvent(self,event) -> None:  # noqa: N802
        p=QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing,True)
        w,h=self.width(),self.height(); lm,rm,tm,bm=62,20,48,54; plot=QRectF(lm,tm,w-lm-rm,h-tm-bm)
        p.setPen(QPen(QColor(COLORS.grid),1))
        for i in range(7):
            y=plot.top()+plot.height()*i/6; p.drawLine(QPointF(plot.left(),y),QPointF(plot.right(),y)); val=600-i*100; p.setPen(QColor(COLORS.text_muted)); p.drawText(QRectF(3,y-9,52,18),Qt.AlignmentFlag.AlignRight,str(val)); p.setPen(QPen(QColor(COLORS.grid),1))
        for i in range(6):
            x=plot.left()+plot.width()*i/5; p.drawLine(QPointF(x,plot.top()),QPointF(x,plot.bottom())); p.setPen(QColor(COLORS.text_muted)); p.drawText(QRectF(x-32,plot.bottom()+7,64,18),Qt.AlignmentFlag.AlignCenter,f"{i*2000:,}"); p.setPen(QPen(QColor(COLORS.grid),1))
        p.setPen(QPen(QColor("#536f8f"),1.3)); p.drawLine(QPointF(plot.left(),plot.bottom()),QPointF(plot.right(),plot.bottom())); p.drawLine(QPointF(plot.left(),plot.top()),QPointF(plot.left(),plot.bottom()))
        def pt(rpm,hz): return QPointF(plot.left()+rpm/10000*plot.width(),plot.bottom()-hz/600*plot.height())
        fw=[[(0,130),(2000,145),(4000,180),(6000,235),(8000,285),(10000,335)],[(0,200),(2000,210),(4000,260),(6000,330),(8000,390),(10000,450)],[(0,330),(2000,340),(4000,380),(6000,430),(8000,500),(10000,580)]]
        bw=[[(0,580),(2000,540),(4000,470),(6000,420),(8000,375),(10000,360)],[(0,515),(2000,465),(4000,410),(6000,365),(8000,335),(10000,320)],[(0,330),(2000,320),(4000,260),(6000,210),(8000,195),(10000,190)]]
        for series,color,dash in [(fw,"#167ce1",False),(bw,"#ff3b30",True)]:
            for pts in series:
                pen=QPen(QColor(color),1.8); pen.setStyle(Qt.PenStyle.DashLine if dash else Qt.PenStyle.SolidLine); p.setPen(pen); path=QPainterPath();
                for i,(rpm,hz) in enumerate(pts): path.moveTo(pt(rpm,hz)) if i==0 else path.lineTo(pt(rpm,hz))
                p.drawPath(path)
        pen=QPen(QColor("#263f57"),1.7); pen.setStyle(Qt.PenStyle.DashLine); p.setPen(pen); p.drawLine(pt(0,0),pt(10000,520))
        for rpm,hz,label in [(2840,153.6,"2,840 rpm\n(1st Critical)"),(6520,332.8,"6,520 rpm\n(2nd Critical)")]:
            x=pt(rpm,hz).x(); pen=QPen(QColor("#70879b"),1); pen.setStyle(Qt.PenStyle.DashLine); p.setPen(pen); p.drawLine(QPointF(x,plot.top()),QPointF(x,plot.bottom())); p.setBrush(QColor("white")); p.setPen(QPen(QColor("#ff3b30"),2)); p.drawEllipse(pt(rpm,hz),8,8); p.setPen(QColor(COLORS.text_dark)); p.drawText(QRectF(x+8,plot.bottom()-40,120,38),Qt.AlignmentFlag.AlignLeft,label)
        y=18; x=80
        for name,color,dash in [("Forward Whirl (FW)","#167ce1",False),("Backward Whirl (BW)","#ff3b30",True),("Synchronous (1X)","#263f57",True)]:
            pen=QPen(QColor(color),1.8); pen.setStyle(Qt.PenStyle.DashLine if dash else Qt.PenStyle.SolidLine); p.setPen(pen); p.drawLine(QPointF(x,y),QPointF(x+26,y)); p.setPen(QColor(COLORS.text)); p.drawText(QRectF(x+33,y-9,132,18),Qt.AlignmentFlag.AlignLeft,name); x+=165
        p.setPen(QColor("#ff3b30")); p.setBrush(QColor("white")); p.drawEllipse(QPointF(x+8,y),7,7); p.setPen(QColor(COLORS.text)); p.drawText(QRectF(x+21,y-9,100,18),Qt.AlignmentFlag.AlignLeft,"Critical Speeds")
        p.drawText(QRectF(plot.left(),h-28,plot.width(),20),Qt.AlignmentFlag.AlignCenter,"Rotational Speed (rpm)")
        p.save(); p.translate(18,plot.center().y()); p.rotate(-90); p.drawText(QRectF(-plot.height()/2,-10,plot.height(),20),Qt.AlignmentFlag.AlignCenter,"Frequency (Hz)"); p.restore(); p.end()
