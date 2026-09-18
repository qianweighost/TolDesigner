# -*- coding: utf-8 -*-
"""尺寸链 / 公差分析示意图组件（QPainter 实时绘制）。

  ChainDiagram      —— 尺寸链简图（环宽按基本尺寸成比例；↑增环 / ↓减环）
  BandDiagram       —— 公差带图（各组成环公差带 + 封闭环结果带 + 设计要求线）
  HistogramDiagram  —— 蒙特卡洛仿真分布直方图（含规格上下限与 ±3σ）
  ContribBar        —— 贡献率条形图（极值法 / 统计法并列）

坐标策略
  这几个图都是「示意性」的，横轴是尺寸或偏差、纵轴是「行」，
  所以直接用像素坐标手算映射，不用 DriveDesigner 里的毫米坐标系。
  控件把像素级几何记进 self._geom，供 selftest 断言（不靠扫像素猜边界）。
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QBrush, QColor, QFont, QFontMetricsF, QLinearGradient,
                           QPainter, QPen, QPolygonF)
from PySide6.QtWidgets import QSizePolicy, QWidget

from .theme import (ACCENT, BAD, BAND, BAND_RSS, BAND_SOFT, BAND_WC, BORDER,
                    CHAIN_AXIS, DEC, DIM, HIST, HIST_TOP, INC, LIMIT, OK,
                    TEXT, TEXT_DIM, TEXT_MID, THREE_SIGMA, WARN, ZERO_LINE)


# =====================================================================
# 基础工具
# =====================================================================

def _pen(color, width: float = 1.2, cosmetic: bool = True,
         style=Qt.PenStyle.SolidLine) -> QPen:
    pen = QPen(QColor(color), width, style)
    pen.setCosmetic(cosmetic)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


def _text(p: QPainter, x: float, y: float, s: str, color=TEXT, size=8.4,
          bold=False, anchor="mm", box=False, bg="#FFFFFFF2"):
    """在像素坐标 (x, y) 处写字。anchor: 横 l/m/r + 纵 t/m/b。"""
    f = QFont()
    f.setPointSizeF(size)
    f.setBold(bold)
    p.setFont(f)
    fm = QFontMetricsF(f)
    lines = s.split("\n")
    w = max(fm.horizontalAdvance(ln) for ln in lines) + (10 if box else 2)
    h = fm.height() * len(lines) + (7 if box else 1)
    rx = x if anchor[0] == "l" else (x - w if anchor[0] == "r" else x - w / 2.0)
    ry = y if anchor[1] == "t" else (y - h if anchor[1] == "b" else y - h / 2.0)
    rect = QRectF(rx, ry, w, h)
    if box:
        p.setBrush(QBrush(QColor(bg)))
        p.setPen(_pen(BORDER, 1))
        p.drawRoundedRect(rect, 5, 5)
    p.setPen(_pen(color, 1))
    p.drawText(rect, Qt.AlignmentFlag.AlignCenter, s)


def _arrow(p: QPainter, tip: QPointF, ang: float, size: float = 5.0,
           color: str = DIM):
    a1, a2 = ang + math.radians(152), ang - math.radians(152)
    p1 = QPointF(tip.x() + size * math.cos(a1), tip.y() + size * math.sin(a1))
    p2 = QPointF(tip.x() + size * math.cos(a2), tip.y() + size * math.sin(a2))
    p.setBrush(QBrush(QColor(color)))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawPolygon(QPolygonF([tip, p1, p2]))


def _double_arrow(p: QPainter, xa: float, xb: float, y: float,
                  color: str = DIM, size: float = 5.0, lw: float = 1.1):
    p.setPen(_pen(color, lw))
    p.drawLine(QPointF(xa + size, y), QPointF(xb - size, y))
    _arrow(p, QPointF(xa, y), math.pi, size, color)
    _arrow(p, QPointF(xb, y), 0.0, size, color)


def _base_card(p: QPainter, w: int, h: int, hint: str = "",
               hint_left: str = ""):
    """先画底板：白底 + 圆角边框 + 底部注释。必须最先调用。"""
    p.fillRect(QRectF(0, 0, w, h), QColor("#FFFFFF"))
    p.setPen(_pen(BORDER, 1))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), 8, 8)
    if hint:
        _text(p, w / 2, h - 6, hint, TEXT_DIM, 8.0, False, "mb")
    if hint_left:
        _text(p, 10, h - 6, hint_left, TEXT_DIM, 8.0, False, "mb")


def _ellipsis(fm: QFontMetricsF, s: str, width: float) -> str:
    if fm.horizontalAdvance(s) <= width:
        return s
    out = s
    while out and fm.horizontalAdvance(out + "…") > width:
        out = out[:-1]
    return out + "…"


def _fmt(v: float, nd: int = 3) -> str:
    return f"{v:.{nd}f}"


def _pm(v: float, nd: int = 3) -> str:
    """带正负号的偏差显示。"""
    return f"{v:+.{nd}f}"


# =====================================================================
# 1. 尺寸链简图
# =====================================================================

class ChainDiagram(QWidget):
    """尺寸链简图：各环沿轴线排开，增环画在轴上方（向右箭头），
       减环画在轴下方（向左箭头），封闭环在底部用双向箭头标出。"""

    CAPTION = "尺寸链简图"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._res = None
        self._geom = {}
        self.setMinimumSize(440, 300)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_result(self, res):
        self._res = res
        self.update()

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        try:
            self._paint(p)
        except Exception as exc:  # noqa: BLE001
            p.setPen(_pen(BAD, 1))
            p.setFont(QFont("Microsoft YaHei UI", 9))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                       f"示意图绘制失败：{exc}")
        finally:
            p.end()

    def _paint(self, p: QPainter):
        w, h = self.width(), self.height()
        res = self._res
        links = (res or {}).get("links") or []
        _base_card(p, w, h, hint="宽度按基本尺寸成比例",
                   hint_left="↑ 增环（ξ=+1）   ↓ 减环（ξ=−1）")

        if not links:
            _text(p, w / 2, h / 2, "尚无组成环", TEXT_DIM, 10, False, "mm")
            self._geom = {"segs": [], "rows": []}
            return

        n = len(links)
        pad_l, pad_r = 30.0, 30.0
        avail = max(60.0, w - pad_l - pad_r)

        # 纵向按高度比例分配：增环在上、减环在下、封闭环在最下，四行互不打架
        y_inc_lab2 = h * 0.135      # 增环标签（错开行）
        y_inc_lab1 = h * 0.205
        y_inc_arr = h * 0.265       # 增环尺寸线
        base_y = h * 0.345          # 轴线
        y_dec_arr = h * 0.425       # 减环尺寸线
        y_dec_lab1 = h * 0.485
        y_dec_lab2 = h * 0.555
        y_close = h * 0.720         # 封闭环尺寸线
        y_close_lab = y_close - 4.0

        # ---- 环宽：按 |基本尺寸| 成比例，最小 44 px，再归一化 ----
        mags = [max(abs(l["nominal"]), 1e-9) for l in links]
        tot = sum(mags) or 1.0
        widths = [max(44.0, avail * m / tot) for m in mags]
        k = avail / sum(widths)
        widths = [x * k for x in widths]

        # ---- 轴线 ----
        p.setPen(_pen(CHAIN_AXIS, 1.4))
        p.drawLine(QPointF(pad_l, base_y), QPointF(pad_l + avail, base_y))

        segs, rows = [], []
        x = pad_l
        stagger = {True: 0, False: 0}
        for l, bw in zip(links, widths):
            xa, xb = x, x + bw
            x += bw
            inc = int(l.get("xi", 1)) >= 0
            col = INC if inc else DEC

            # 尺寸界线：增环朝上、减环朝下，从轴线穿出到标签之外
            if inc:
                ya, yb = base_y + 4.0, y_inc_lab2 - 20.0
            else:
                ya, yb = base_y - 4.0, y_dec_lab2 + 20.0
            p.setPen(_pen(BORDER, 0.9, style=Qt.PenStyle.DashLine))
            p.drawLine(QPointF(xa, ya), QPointF(xa, yb))
            p.drawLine(QPointF(xb, ya), QPointF(xb, yb))

            # 尺寸箭头：增环指向右，减环指向左
            ay = y_inc_arr if inc else y_dec_arr
            p.setPen(_pen(col, 1.5))
            p.drawLine(QPointF(xa + 3, ay), QPointF(xb - 3, ay))
            if inc:
                _arrow(p, QPointF(xb, ay), 0.0, 5.4, col)
            else:
                _arrow(p, QPointF(xa, ay), math.pi, 5.4, col)

            # 标签：同侧相邻环交错半格，降低重叠概率
            ly = ((y_inc_lab1, y_inc_lab2) if inc else (y_dec_lab1, y_dec_lab2))[
                stagger[inc] % 2]
            stagger[inc] += 1
            anchor = "mb" if inc else "mt"
            no = l.get("no") or "—"
            _text(p, (xa + xb) / 2, ly,
                  f"{no}  {l['nominal']:g}\n{_pm(l['es'], 3)} ~ {_pm(l['ei'], 3)}",
                  col, 7.6, False, anchor, True)

            segs.append((xa, xb, col, inc))
            rows.append({"y": ay, "xa": xa, "xb": xb, "inc": inc, "no": no})

        # ---- 封闭环 ----
        cxa, cxb = pad_l, pad_l + avail
        es0, ei0 = res["wc"]["es"], res["wc"]["ei"]
        p.setPen(_pen(OK, 0.8, style=Qt.PenStyle.DashLine))
        for xx in (cxa, cxb):
            p.drawLine(QPointF(xx, base_y + 5), QPointF(xx, y_close - 5))
        p.setPen(_pen(OK, 1.6))
        _double_arrow(p, cxa, cxb, y_close, OK, 5.6, 1.6)
        _text(p, (cxa + cxb) / 2, y_close_lab,
              f"封闭环 N₀ = {res['nominal']:.4g}    "
              f"极值 {_pm(es0)} ~ {_pm(ei0)}    统计 ±{res['rss']['es']:.4f}",
              OK, 8.2, True, "mb", True)

        self._geom = {"segs": segs, "rows": rows, "n": n,
                      "base_y": base_y, "closing_y": y_close}


# =====================================================================
# 2. 公差带图
# =====================================================================

class BandDiagram(QWidget):
    """公差带图：每个组成环一条公差带，底部给出封闭环的极值法 / 统计法结果带
       与设计要求的规格上下限。横轴是偏差（mm）。"""

    CAPTION = "公差带图"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._res = None
        self._geom = {}
        self.LABEL_W = 104.0
        self.setMinimumSize(460, 220)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_result(self, res):
        self._res = res
        n = len((res or {}).get("links") or [])
        # 行数 = 组成环 + 极值法 / 统计法 /（设计要求），按行高自适应最小高度
        self.setMinimumHeight(int(58 + 20 * max(4, n + 3)))
        self.update()

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        try:
            self._paint(p)
        except Exception as exc:  # noqa: BLE001
            p.setPen(_pen(BAD, 1))
            p.setFont(QFont("Microsoft YaHei UI", 9))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                       f"示意图绘制失败：{exc}")
        finally:
            p.end()

    def _paint(self, p: QPainter):
        w, h = self.width(), self.height()
        res = self._res
        links = (res or {}).get("links") or []
        _base_card(p, w, h, hint="横轴为偏差（mm），虚线为公称零线")

        if not links:
            _text(p, w / 2, h / 2, "尚无组成环", TEXT_DIM, 10, False, "mm")
            self._geom = {"rows": []}
            return

        # ---- 收集所有带的两端 ----
        bands = [(l["ei"], l["es"], l["no"] or "—", int(l["xi"]) >= 0) for l in links]
        bands.append((res["wc"]["ei"], res["wc"]["es"], "极值法 WC", None))
        bands.append((res["rss"]["ei"], res["rss"]["es"], "统计法 RSS", None))
        tgt = res.get("target")
        if tgt:
            bands.append((tgt["ei"], tgt["es"], "设计要求", None))

        lo = min(b[0] for b in bands)
        hi = max(b[1] for b in bands)
        if tgt:
            lo = min(lo, tgt["ei"])
            hi = max(hi, tgt["es"])
        span = (hi - lo) or 1e-9
        lo -= span * 0.10
        hi += span * 0.10

        x0 = self.LABEL_W
        x1 = w - 58.0
        if x1 - x0 < 80:
            x0 = 60.0
            x1 = max(120.0, w - 30.0)

        def X(v):
            return x0 + (v - lo) / (hi - lo) * (x1 - x0)

        top = 16.0
        bottom = h - 26.0
        nrow = len(bands)
        row_h = max(11.0, min(22.0, (bottom - top) / max(1, nrow)))
        bar_h = min(11.0, row_h * 0.62)

        # ---- 零线 ----
        if lo <= 0.0 <= hi:
            p.setPen(_pen(ZERO_LINE, 1.0, style=Qt.PenStyle.DashLine))
            p.drawLine(QPointF(X(0.0), top - 6), QPointF(X(0.0), bottom + 4))

        # ---- 规格上下限 ----
        if tgt:
            p.setPen(_pen(LIMIT, 1.1, style=Qt.PenStyle.DashLine))
            for v in (tgt["ei"], tgt["es"]):
                p.drawLine(QPointF(X(v), top - 6), QPointF(X(v), bottom + 4))
            # 标签右对齐到上限线左侧：左对齐会从卡片右缘溢出被裁掉
            _text(p, X(tgt["es"]) - 3, top - 8,
                  f"规格 {_pm(tgt['ei'])}~{_pm(tgt['es'])}",
                  LIMIT, 7.6, True, "rt")

        rows = []
        fm = QFontMetricsF(QFont("Microsoft YaHei UI", 8))
        for i, (a, b, name, inc) in enumerate(bands):
            cy = top + row_h * (i + 0.5)
            is_res = name.startswith(("极值法", "统计法"))
            is_req = name == "设计要求"
            if is_req:
                col, fill = LIMIT, "#FBE9E9"
            elif name == "极值法 WC":
                col, fill = BAND_WC, "#FDF1E1"
            elif name == "统计法 RSS":
                col, fill = BAND_RSS, "#E8F0FE"
            elif inc is None:
                col, fill = BAND, BAND_SOFT
            else:
                col, fill = (INC if inc else DEC), ("#FDF1E1" if inc else "#E8F0FE")

            # 标签
            lab = name + ("  增" if inc is True else ("  减" if inc is False else ""))
            _text(p, 10, cy, _ellipsis(fm, lab, self.LABEL_W - 16),
                  TEXT_MID if not is_res else col, 8.0,
                  bold=is_res or is_req, anchor="lm")

            xa, xb = X(a), X(b)
            if xb - xa < 3.0:
                xb = xa + 3.0
            r = QRectF(xa, cy - bar_h / 2, xb - xa, bar_h)
            p.setBrush(QBrush(QColor(fill)))
            p.setPen(_pen(col, 1.2 if (is_res or is_req) else 1.0))
            p.drawRect(r)
            # 中间偏差刻度
            if xb - xa > 14:
                p.setPen(_pen(col, 1.0))
                p.drawLine(QPointF((xa + xb) / 2, cy - bar_h / 2),
                           QPointF((xa + xb) / 2, cy + bar_h / 2))

            rows.append({"y": cy, "xa": xa, "xb": xb, "kind": name,
                         "inc": inc, "ei": a, "es": b})

            # 数值：带宽够就写在带内右侧，否则写在带右侧外面
            txt = f"{_pm(a, 4)} ~ {_pm(b, 4)}"
            tw = fm.horizontalAdvance(txt) + 8
            if xb - xa > tw + 16:
                _text(p, xb - 5, cy, txt, TEXT_MID, 7.4, False, "rm")
            elif w - xb > tw + 14:
                _text(p, xb + 6, cy, txt, TEXT_MID, 7.4, False, "lm")

        self._geom = {"rows": rows, "lo": lo, "hi": hi, "x0": x0, "x1": x1}


# =====================================================================
# 3. 蒙特卡洛直方图
# =====================================================================

class HistogramDiagram(QWidget):
    """蒙特卡洛仿真结果直方图：柱高为频数，超差区柱变色，
       并标出均值、±3σ 与规格上下限。"""

    CAPTION = "仿真分布直方图"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._mc = None
        self._geom = {}
        self.setMinimumSize(420, 200)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_result(self, mc):
        self._mc = mc
        self.update()

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        try:
            self._paint(p)
        except Exception as exc:  # noqa: BLE001
            p.setPen(_pen(BAD, 1))
            p.setFont(QFont("Microsoft YaHei UI", 9))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                       f"示意图绘制失败：{exc}")
        finally:
            p.end()

    def _paint(self, p: QPainter):
        w, h = self.width(), self.height()
        mc = self._mc
        _base_card(p, w, h, hint="横轴＝封闭环相对公称值的偏差（mm）")
        if not mc:
            _text(p, w / 2, h / 2, "尚无仿真结果", TEXT_DIM, 10, False, "mm")
            self._geom = {"bars": []}
            return

        hist = mc["hist"]
        counts = hist["counts"]
        top, bottom = 20.0, h - 26.0
        x0, x1 = 22.0, w - 22.0
        if not counts:
            self._geom = {"bars": []}
            return

        # d0 是直方图柱子的起点，柱位置必须用它算；
        # lo_v / hi_v 只是显示量程，扩量程时不能动 d0，否则柱子会整体平移并被截断。
        d0 = hist["x0"]
        dx = hist["dx"]
        lo_v = d0
        hi_v = d0 + dx * len(counts)

        # 规格上下限若与数据量程同量级，就把显示量程扩到含规格限
        # （标准 QC 直方图画法：分布居中，两侧标出 LSL / USL）。
        # 差得太远就不扩 —— 否则分布会被压成一条细线，形状反而看不清。
        llim = mc.get("limit_low")
        hlim = mc.get("limit_high")
        span_v = (hi_v - lo_v) or 1e-12
        if llim is not None and hlim is not None:
            if (hi_v - llim) <= 4 * span_v and (hlim - lo_v) <= 4 * span_v:
                lo_v, hi_v = min(lo_v, llim), max(hi_v, hlim)

        cmax = max(counts) or 1

        def X(v):
            return x0 + (v - lo_v) / max(1e-12, hi_v - lo_v) * (x1 - x0)

        def Y(c):
            return bottom - (bottom - top) * (c / cmax)

        bars = []
        for i, c in enumerate(counts):
            xa, xb = X(d0 + i * dx), X(d0 + (i + 1) * dx)
            yt = Y(c)
            v_mid = d0 + (i + 0.5) * dx
            out = (llim is not None and v_mid < llim) or \
                  (hlim is not None and v_mid > hlim)
            col = HIST_TOP if out else HIST
            if xb - xa < 1.0:
                xb = xa + 1.0
            p.setBrush(QBrush(QColor(col)))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRect(QRectF(xa, yt, xb - xa, bottom - yt))
            bars.append({"xa": xa, "xb": xb, "top": yt, "out": out})

        # 基线
        p.setPen(_pen(BORDER, 1.0))
        p.drawLine(QPointF(x0, bottom), QPointF(x1, bottom))

        # 规格上下限（只画落在显示量程内的，否则线会跑出卡片）
        for v, lab in ((llim, "LSL"), (hlim, "USL")):
            if v is None or not (x0 - 0.5 <= X(v) <= x1 + 0.5):
                continue
            xx = X(v)
            p.setPen(_pen(LIMIT, 1.6))
            p.drawLine(QPointF(xx, top - 8), QPointF(xx, bottom))
            # 左半区左对齐、右半区右对齐，标签才不会越过卡片边缘
            anchor = "rt" if xx > w / 2 else "lt"
            _text(p, xx + (-3 if anchor == "rt" else 3), 8, lab, LIMIT, 7.6,
                  True, anchor)

        # 均值与 ±3σ
        mean, sd = mc["mean"], mc["sigma"]
        if sd > 0:
            p.setPen(_pen(THREE_SIGMA, 1.0, style=Qt.PenStyle.DashLine))
            for v in (mean - 3 * sd, mean + 3 * sd):
                p.drawLine(QPointF(X(v), top + 6), QPointF(X(v), bottom))
        p.setPen(_pen(ACCENT, 1.6))
        p.drawLine(QPointF(X(mean), top - 8), QPointF(X(mean), bottom))

        # 顶部信息
        rate = mc.get("pass_rate")
        info = (f"n = {mc['n']:,}   均值 {mean:+.4f}   σ = {sd:.4f}   "
                f"±3σ = {mean - 3 * sd:+.4f} ~ {mean + 3 * sd:+.4f}")
        if rate is not None:
            info += f"   合格率 {rate * 100:.3f}%"
        _text(p, w / 2, 12, info, TEXT_MID, 8.0, False, "mt")

        # 图例：用真实色块，否则「■」全是一个颜色，看不出哪个代表超差
        lx = x0 + 2.0
        p.setPen(Qt.PenStyle.NoPen)
        for col, txt in ((HIST, "合格区"), (HIST_TOP, "超差区")):
            p.setBrush(QBrush(QColor(col)))
            p.drawRect(QRectF(lx, h - 17.0, 7, 7))
            _text(p, lx + 10, h - 19, txt, TEXT_DIM, 7.6, False, "lt")
            lx += 10 + 8 + 46
        self._geom = {"bars": bars, "x0": x0, "x1": x1}


# =====================================================================
# 4. 贡献率条形图
# =====================================================================

class ContribBar(QWidget):
    """贡献率条形图：每个环两行（极值法 / 统计法），按统计法贡献率降序。"""

    CAPTION = "公差贡献率"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows = None
        self._geom = {}
        self.LABEL_W = 118.0
        self.RIGHT_W = 132.0
        self.ROW_H = 30.0
        self.setMinimumSize(430, 130)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_rows(self, rows):
        self._rows = rows
        self.setMinimumHeight(int(40 + self.ROW_H * max(1, len(rows or []))))
        self.update()

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        try:
            self._paint(p)
        except Exception as exc:  # noqa: BLE001
            p.setPen(_pen(BAD, 1))
            p.setFont(QFont("Microsoft YaHei UI", 9))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                       f"示意图绘制失败：{exc}")
        finally:
            p.end()

    def _paint(self, p: QPainter):
        w, h = self.width(), self.height()
        rows = self._rows or []
        _base_card(p, w, h, hint="上：极值法 ΣTᵢ 占比    下：统计法 ΣTᵢ² 占比")
        if not rows:
            _text(p, w / 2, h / 2, "尚无贡献率数据", TEXT_DIM, 10, False, "mm")
            self._geom = {"rows": []}
            return

        x0 = self.LABEL_W
        x1 = max(x0 + 40.0, w - self.RIGHT_W)
        top = 18.0
        fm = QFontMetricsF(QFont("Microsoft YaHei UI", 8))
        mx = max(max(r["share_wc"] for r in rows),
                 max(r["share_rss"] for r in rows), 1e-9)

        geom = []
        y = top
        for r in rows:
            cy = y + self.ROW_H / 2.0
            name = r.get("no") or r.get("name") or "—"
            nm2 = r.get("name")
            lab = name if (not nm2 or nm2 == name) else f"{name} {nm2}"
            _text(p, 10, cy, _ellipsis(fm, lab, self.LABEL_W - 18), TEXT_MID,
                  8.0, anchor="lm")

            top_share, bot_share = r["share_wc"], r["share_rss"]
            for share, col, dy, tag in ((top_share, BAND_WC, -6.0, "WC"),
                                        (bot_share, BAND_RSS, 6.0, "RSS")):
                bw = (share / mx) * (x1 - x0)
                bw = max(1.6, bw)
                rr = QRectF(x0, cy + dy - 4.0, bw, 8.0)
                p.setBrush(QBrush(QColor(col)))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawRect(rr)
                _text(p, x1 + 6, cy + dy, f"{tag} {share * 100:5.1f}%",
                      TEXT_MID, 7.4, False, "lm")
            geom.append({"y": cy, "label_h": self.LABEL_W,
                         "top_x": x0, "top_w": (top_share / mx) * (x1 - x0)})
            y += self.ROW_H

        # 主导环标注
        if rows:
            top1 = rows[0]
            _text(p, 10, h - 6,
                  f"主导环：{top1.get('no') or top1.get('name')}"
                  f"（统计法贡献 {top1['share_rss'] * 100:.1f}%）",
                  WARN, 8.0, True, "lb")
        self._geom = {"rows": geom, "x0": x0, "x1": x1}
