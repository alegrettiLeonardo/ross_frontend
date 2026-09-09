from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from ..backends.ross.bearing_calculator import BearingOperatingPoint
from .theme import P


class BearingFieldView(QWidget):
    """Compact engineering plot for a ROSS film field at one speed."""

    def __init__(self, title: str, unit: str):
        super().__init__(); self.title=title; self.unit=unit; self.values=None; self.theta=None; self.setMinimumHeight(230)

    def set_field(self, values, theta=None):
        self.values=values; self.theta=theta; self.update()

    @staticmethod
    def _centerline(pad):
        if not isinstance(pad,(list,tuple)) or not pad: return []
        if not isinstance(pad[0],(list,tuple)): return [float(v) for v in pad]
        mid=len(pad[0])//2
        return [float(row[mid] if isinstance(row,(list,tuple)) and row else 0.0) for row in pad]

    def paintEvent(self,event):
        p=QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing,True); p.fillRect(self.rect(),QColor("white")); w,h=self.width(),self.height(); left,top,right,bottom=68,42,w-24,h-46
        font=p.font(); font.setBold(True); font.setPointSize(11); p.setFont(font); p.setPen(QColor(P.text_dark)); p.drawText(14,24,self.title); font.setBold(False); font.setPointSize(9); p.setFont(font)
        if not self.values:
            p.setPen(QColor(P.muted)); p.drawText(self.rect(),Qt.AlignmentFlag.AlignCenter,"Run Calculate Bearing to display native ROSS field results."); p.end(); return
        pads=self.values if isinstance(self.values,(list,tuple)) else [self.values]; curves=[self._centerline(pad) for pad in pads]; curves=[c for c in curves if c]
        if not curves: p.end(); return
        flat=[v for c in curves for v in c]; ymin,ymax=min(flat),max(flat)
        if ymax==ymin: ymax=ymin+1.0
        p.setPen(QPen(QColor("#DCE6EF"),1))
        for i in range(6): x=left+(right-left)*i/5; p.drawLine(QPointF(x,top),QPointF(x,bottom))
        for i in range(5): y=top+(bottom-top)*i/4; p.drawLine(QPointF(left,y),QPointF(right,y)); val=ymax-(ymax-ymin)*i/4; p.setPen(QColor(P.muted)); p.drawText(QRectF(5,y-9,55,18),Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter,f"{val:.3g}"); p.setPen(QPen(QColor("#DCE6EF"),1))
        p.setPen(QPen(QColor("#688096"),1.2)); p.drawLine(QPointF(left,top),QPointF(left,bottom)); p.drawLine(QPointF(left,bottom),QPointF(right,bottom))
        colors=["#137FF1","#E2575A","#16A66B","#E9A23B","#7B61C9","#0FA3B1","#D66A9C","#60768E"]
        for idx,curve in enumerate(curves):
            pen=QPen(QColor(colors[idx%len(colors)]),1.8); p.setPen(pen); path=QPainterPath()
            for j,val in enumerate(curve):
                x=left+(right-left)*(j/max(len(curve)-1,1)); y=bottom-(bottom-top)*(val-ymin)/(ymax-ymin); path.moveTo(x,y) if j==0 else path.lineTo(x,y)
            p.drawPath(path); p.drawText(right-64,top+16+idx*15,f"Pad {idx+1}")
        p.setPen(QColor(P.muted)); p.drawText(QRectF(left,bottom+20,right-left,18),Qt.AlignmentFlag.AlignCenter,"Circumferential film position"); p.save(); p.translate(8,(top+bottom)/2); p.rotate(-90); p.drawText(QRectF(-90,0,180,18),Qt.AlignmentFlag.AlignCenter,f"{self.title} [{self.unit}]"); p.restore(); p.end()


class JournalPositionView(QWidget):
    def __init__(self):
        super().__init__(); self.points:list[BearingOperatingPoint]=[]; self.setMinimumHeight(230)

    def set_points(self, points:list[BearingOperatingPoint]): self.points=points; self.update()

    def paintEvent(self,event):
        p=QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing,True); p.fillRect(self.rect(),QColor("white")); w,h=self.width(),self.height(); cx,cy=w*.48,h*.52; radius=min(w,h)*.34
        p.setPen(QPen(QColor(P.border),2)); p.setBrush(QColor("#F7FAFD")); p.drawEllipse(QPointF(cx,cy),radius,radius); p.setPen(QPen(QColor("#B3C3D1"),1,Qt.PenStyle.DashLine)); p.drawLine(QPointF(cx-radius-12,cy),QPointF(cx+radius+12,cy)); p.drawLine(QPointF(cx,cy-radius-12),QPointF(cx,cy+radius+12)); p.setPen(QColor(P.text_dark)); p.drawText(14,24,"Journal Position"); p.setPen(QColor(P.muted)); p.drawText(QRectF(cx-radius,cy+radius+12,2*radius,18),Qt.AlignmentFlag.AlignCenter,"Normalized by radial clearance")
        colors=["#137FF1","#16A66B","#E2575A","#E9A23B","#7B61C9"]
        for i,pt in enumerate(self.points):
            if pt.journal_x_over_clearance is None or pt.journal_y_over_clearance is None: continue
            x=cx+pt.journal_x_over_clearance*radius; y=cy-pt.journal_y_over_clearance*radius; p.setPen(QPen(QColor(colors[i%len(colors)]),2)); p.setBrush(QColor("white")); p.drawEllipse(QPointF(x,y),5,5); p.drawText(QRectF(x+7,y-10,90,20),Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter,f"{pt.rpm:,.0f} rpm")
        p.end()
