from __future__ import annotations

from typing import Iterable

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from ..domain import RotorProject
from .theme import P


class RotorSketch(QWidget):
    def __init__(self, project: RotorProject):
        super().__init__(); self.project=project; self.setMinimumHeight(265); self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_project(self, project: RotorProject): self.project=project; self.update()

    def paintEvent(self, event):
        p=QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.fillRect(self.rect(), QColor("white")); w,h=self.width(),self.height(); x0,x1=78,w-72; y=h*0.50; length=max(self.project.shaft_length_mm,1.0)
        p.setPen(QPen(QColor("#8CA4B8"),1,Qt.PenStyle.DashLine)); p.drawLine(QPointF(x0-38,y),QPointF(x1+38,y))
        max_od=max((max(s.outer_diameter_left_mm,s.odr_mm) for s in self.project.shaft), default=60)
        pos=0.0
        for i,s in enumerate(self.project.shaft,1):
            xa=x0+(pos/length)*(x1-x0); xb=x0+((pos+s.length_mm)/length)*(x1-x0)
            ha=18+28*s.outer_diameter_left_mm/max_od; hb=18+28*s.odr_mm/max_od
            path=QPainterPath(QPointF(xa,y-ha/2)); path.lineTo(xb,y-hb/2); path.lineTo(xb,y+hb/2); path.lineTo(xa,y+ha/2); path.closeSubpath()
            grad=QLinearGradient(0,y-max(ha,hb)/2,0,y+max(ha,hb)/2); grad.setColorAt(0,QColor("#EAF0F4")); grad.setColorAt(.52,QColor("#AEBCC6")); grad.setColorAt(1,QColor("#EFF3F6"))
            p.setBrush(grad); p.setPen(QPen(QColor("#5D6871"),1.2)); p.drawPath(path)
            p.setPen(QColor("#1B2934")); p.drawText(QRectF(xa,y-11,xb-xa,22),Qt.AlignmentFlag.AlignCenter,str(i)); pos += s.length_mm
        p.setBrush(QColor("#C6D0D7")); p.setPen(QPen(QColor("#56636C"),1.2)); p.drawRect(QRectF(x0-18,y-10,18,20)); p.drawRect(QRectF(x1,y-10,18,20))
        def mapx(mm): return x0+(mm/length)*(x1-x0)
        for disk in self.project.disks:
            x=mapx(disk.position_mm); grad=QLinearGradient(x-15,0,x+15,0); grad.setColorAt(0,QColor("#2B6EA4")); grad.setColorAt(.5,QColor("#8EBCE1")); grad.setColorAt(1,QColor("#2B6EA4")); p.setBrush(grad); p.setPen(QPen(QColor("#174C77"),1.3)); p.drawRoundedRect(QRectF(x-17,y-61,34,122),2,2)
            p.setPen(QColor(P.text_dark)); p.drawText(QRectF(x-55,y-100,110,22),Qt.AlignmentFlag.AlignCenter,disk.tag or "Disk"); p.drawLine(QPointF(x,y-78),QPointF(x,y-61))
        for idx,b in enumerate(self.project.bearings,1):
            x=mapx(b.position_mm); p.setBrush(QColor("#3981B8")); p.setPen(QPen(QColor("#1F5E8D"),1.3)); p.drawRect(QRectF(x-15,y-39,30,78)); p.drawEllipse(QRectF(x-7,y-7,14,14)); p.drawLine(QPointF(x-9,y-12),QPointF(x+9,y+12)); p.drawLine(QPointF(x+9,y-12),QPointF(x-9,y+12))
            p.setPen(QColor("#65717A")); p.drawRect(QRectF(x-5,y+39,10,21)); p.drawLine(QPointF(x-20,y+64),QPointF(x+20,y+64))
            for hx in range(-18,19,7): p.drawLine(QPointF(x+hx,y+64),QPointF(x+hx-5,y+70))
            p.setPen(QColor(P.text_dark)); p.drawText(QRectF(x-65,y-92,130,38),Qt.AlignmentFlag.AlignHCenter|Qt.AlignmentFlag.AlignTop,f"Bearing {idx}\n(Journal)")
        p.setPen(QPen(QColor(P.text),1.4)); ax=24; ay=h-30; p.drawLine(QPointF(ax,ay),QPointF(ax,ay-36)); p.drawLine(QPointF(ax,ay),QPointF(ax+40,ay)); p.drawText(ax+6,ay-33,"Y"); p.drawText(ax+35,ay+16,"Z")
        p.drawText(QRectF(w-220,h-35,195,22),Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter,f"Total length: {length:,.0f} mm"); p.end()


class SimpleLineChart(QWidget):
    def __init__(self, title: str = "", parent=None):
        super().__init__(parent); self.title=title; self.setMinimumHeight(205); self.series=[]; self.xmax=10000; self.ymin=-5e7; self.ymax=5e7

    def set_series(self, series: Iterable[tuple[str, list[tuple[float,float]], str, bool]]): self.series=list(series); self.update()

    def paintEvent(self,event):
        p=QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing,True); p.fillRect(self.rect(),QColor("white")); left,top,right,bottom=58,36,self.width()-18,self.height()-40
        p.setPen(QColor(P.text_dark)); p.drawText(10,20,self.title); p.setPen(QPen(QColor("#DFE8F1"),1))
        for i in range(6):
            x=left+(right-left)*i/5; p.drawLine(QPointF(x,top),QPointF(x,bottom)); p.setPen(QColor(P.muted)); p.drawText(QRectF(x-28,bottom+5,56,18),Qt.AlignmentFlag.AlignCenter,f"{self.xmax*i/5:,.0f}"); p.setPen(QPen(QColor("#DFE8F1"),1))
        for i in range(5): y=top+(bottom-top)*i/4; p.drawLine(QPointF(left,y),QPointF(right,y))
        p.setPen(QPen(QColor("#698198"),1.2)); p.drawLine(QPointF(left,top),QPointF(left,bottom)); p.drawLine(QPointF(left,bottom),QPointF(right,bottom)); colors={"blue":"#0D7CF2","red":"#F04444","green":"#1A9F66","orange":"#F59A23","black":"#273444"}
        for name,pts,color,dashed in self.series:
            pen=QPen(QColor(colors.get(color,color)),2); pen.setStyle(Qt.PenStyle.DashLine if dashed else Qt.PenStyle.SolidLine); p.setPen(pen); path=QPainterPath()
            for j,(xv,yv) in enumerate(pts):
                x=left+(right-left)*(xv/self.xmax if self.xmax else 0); y=bottom-(bottom-top)*((yv-self.ymin)/(self.ymax-self.ymin) if self.ymax!=self.ymin else 0.5); path.moveTo(x,y) if j==0 else path.lineTo(x,y)
            p.drawPath(path)
        p.end()


class CampbellChart(QWidget):
    def __init__(self):
        super().__init__(); self.setMinimumHeight(390); self.speed=[0,2000,4000,6000,8000,10000]; self.freqs=None; self.critical=[2840,6520]

    def set_data(self, speed: list[float], freqs: list[list[float]] | None, critical: list[float]): self.speed=speed or self.speed; self.freqs=freqs; self.critical=critical or self.critical; self.update()

    def paintEvent(self,event):
        p=QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing,True); p.fillRect(self.rect(),QColor("white")); w,h=self.width(),self.height(); left,top,right,bottom=65,70,w-28,h-54; xmax=max(self.speed or [10000]); ymax=600.0
        p.setPen(QColor(P.text_dark)); font=p.font(); font.setBold(True); font.setPointSize(12); p.setFont(font); p.drawText(12,24,"Campbell Diagram"); font.setBold(False); font.setPointSize(9); p.setFont(font)
        legend=[("Forward Whirl (FW)","#1677EE",False),("Backward Whirl (BW)","#F04444",True),("Synchronous (1X)","#2A2F35",True),("Critical Speeds","#F04444",False)]; xleg=54
        for label,col,dash in legend:
            if label=="Critical Speeds": p.setBrush(Qt.BrushStyle.NoBrush); p.setPen(QPen(QColor(col),2)); p.drawEllipse(QPointF(xleg+8,47),6,6)
            else: pen=QPen(QColor(col),2); pen.setStyle(Qt.PenStyle.DashLine if dash else Qt.PenStyle.SolidLine); p.setPen(pen); p.drawLine(QPointF(xleg,47),QPointF(xleg+25,47))
            p.setPen(QColor(P.text)); p.drawText(xleg+31,51,label); xleg += 155 if label!="Synchronous (1X)" else 145
        p.setPen(QPen(QColor("#DCE6EF"),1))
        for i in range(6): x=left+(right-left)*i/5; p.drawLine(QPointF(x,top),QPointF(x,bottom)); p.setPen(QColor(P.muted)); p.drawText(QRectF(x-30,bottom+7,60,18),Qt.AlignmentFlag.AlignCenter,f"{xmax*i/5:,.0f}"); p.setPen(QPen(QColor("#DCE6EF"),1))
        for i in range(7): y=bottom-(bottom-top)*i/6; p.drawLine(QPointF(left,y),QPointF(right,y)); p.setPen(QColor(P.muted)); p.drawText(QRectF(15,y-9,42,18),Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter,f"{100*i}"); p.setPen(QPen(QColor("#DCE6EF"),1))
        p.setPen(QPen(QColor("#667E94"),1.2)); p.drawLine(QPointF(left,top),QPointF(left,bottom)); p.drawLine(QPointF(left,bottom),QPointF(right,bottom)); p.setPen(QColor(P.text)); p.drawText(QRectF(left,bottom+29,right-left,20),Qt.AlignmentFlag.AlignCenter,"Rotational Speed (rpm)")
        p.save(); p.translate(10,(top+bottom)/2); p.rotate(-90); p.drawText(QRectF(-80,-4,160,18),Qt.AlignmentFlag.AlignCenter,"Frequency (Hz)"); p.restore()
        def sx(v): return left+(right-left)*v/xmax
        def sy(v): return bottom-(bottom-top)*v/ymax
        if self.freqs and len(self.freqs)>1:
            for m in range(min(len(self.freqs[0]),6)):
                pen=QPen(QColor("#1677EE" if m%2 else "#F04444"),2); pen.setStyle(Qt.PenStyle.SolidLine if m%2 else Qt.PenStyle.DashLine); p.setPen(pen); path=QPainterPath()
                for j,s in enumerate(self.speed):
                    if j>=len(self.freqs): break
                    v=float(self.freqs[j][m]); path.moveTo(sx(s),sy(v)) if j==0 else path.lineTo(sx(s),sy(v))
                p.drawPath(path)
        else:
            curves=[("#1677EE",False,[330,342,372,425,490,565]),("#1677EE",False,[198,210,255,318,385,448]),("#1677EE",False,[128,145,180,228,276,325]),("#F04444",True,[575,540,475,435,455,495]),("#F04444",True,[515,465,405,370,360,355]),("#F04444",True,[330,300,260,225,210,205]),("#F04444",True,[198,175,140,112,100,96])]
            for col,dash,vals in curves:
                pen=QPen(QColor(col),2); pen.setStyle(Qt.PenStyle.DashLine if dash else Qt.PenStyle.SolidLine); p.setPen(pen); path=QPainterPath()
                for j,v in enumerate(vals): path.moveTo(sx(self.speed[j]),sy(v)) if j==0 else path.lineTo(sx(self.speed[j]),sy(v))
                p.drawPath(path)
        p.setPen(QPen(QColor("#26313A"),2,Qt.PenStyle.DashLine)); p.drawLine(QPointF(sx(0),sy(0)),QPointF(sx(xmax),sy(xmax/60)))
        for idx,rpm in enumerate(self.critical[:2]):
            hz=rpm/60; x,y=sx(rpm),sy(hz); p.setPen(QPen(QColor("#F04444"),2)); p.setBrush(QColor("white")); p.drawEllipse(QPointF(x,y),7,7); p.setPen(QPen(QColor("#8398AA"),1,Qt.PenStyle.DashLine)); p.drawLine(QPointF(x,top),QPointF(x,bottom)); p.setPen(QColor(P.text_dark)); p.drawText(QRectF(x-55,bottom-46,110,40),Qt.AlignmentFlag.AlignCenter,f"{rpm:,.0f} rpm\n({idx+1}{'st' if idx==0 else 'nd'} Critical)")
        p.end()
