# -*- coding: utf-8 -*-
"""界面各页面：尺寸链计算、公差仿真、公差分配、标准公差库、使用说明。"""

from __future__ import annotations

import base64
import datetime
import html
import math
import os

from PySide6.QtCore import (QBuffer, QCoreApplication, QIODevice, Qt, QTimer,
                            QUrl)
from PySide6.QtGui import QColor, QDesktopServices, QFont
from PySide6.QtWidgets import (QAbstractItemView, QButtonGroup, QCheckBox,
                               QComboBox, QDialog, QFileDialog, QFrame,
                               QGridLayout, QHBoxLayout, QHeaderView, QLabel,
                               QLineEdit, QMessageBox, QPushButton,
                               QScrollArea, QSizePolicy, QSplitter,
                               QTableWidget, QTableWidgetItem, QVBoxLayout,
                               QWidget)

from core.tol_core import (ALLOC_METHODS, DEFAULT_DIST, DEFAULT_SIGMA_GRADE,
                           DISTRIBUTIONS,
                           DIST_KEYS, HOLE_DEV, IT_A, IT_GRADES, IT_MAX_SIZE,
                           SHAFT_DEV, SIGMA_GRADES, SIGMA_GRADE_LABELS,
                           STD_TEMP, DesignError, allocate,
                           analyze, auto_signs, default_links, dev_for_zone,
                           dist_label, example_links, it_grade_for, it_table,
                           it_value, monte_carlo, new_link, parse_zone,
                           ppm_to_sigma_level, sigma_level_table,
                           tolerance_factor)

from .diagram import BandDiagram, ChainDiagram, ContribBar, HistogramDiagram
from .theme import (ACCENT, BAD, BORDER, CARD, DEC, INC, OK, TEXT, TEXT_DIM,
                    TEXT_MID, WARN)
from core import persist


# =====================================================================
# 全局共享的尺寸链状态（各页读写同一份数据，切页时同步）
# =====================================================================

class ChainState:
    """一处编辑、多处复用的尺寸链数据。"""

    def __init__(self):
        self.links: list[dict] = default_links()
        self.target = {"nominal": "", "es": 0.25, "ei": -0.25}
        self.use_thermal = False
        # σ 等级缺省值（每环可在 link["sigma_grade"] 单独覆盖）。
        # 默认 3 = T 为 6σ 带宽，与 GB/T 5847 / 华为胶片的正态口径一致。
        self.n_sigma = DEFAULT_SIGMA_GRADE
        self.project = {"name": "L20 浇灌机 传动装配", "code": "TA-2026-001",
                        "author": "", "note": ""}

    # ---- 封闭环要求 ----
    def target_or_none(self):
        es = float(self.target.get("es") or 0.0)
        ei = float(self.target.get("ei") or 0.0)
        if es == 0.0 and ei == 0.0:
            return None
        n = str(self.target.get("nominal") or "").strip()
        return {"nominal": (n or None), "es": es, "ei": ei}

    def result(self):
        return analyze(self.links, self.target_or_none(), self.use_thermal,
                       n_sigma=self.n_sigma)

    def active(self):
        return [l for l in self.links if l.get("enabled", True)]


STATE = ChainState()


# =====================================================================
# 报告输出工具（各页共用，与家族成员同款）
# =====================================================================

DOC_FOOTER_DEFAULT = """标准依据
  GB/T 1800.1-2020  极限与配合 公差、偏差和配合的基础
  GB/T 1800.2-2020  标准公差带代号和孔、轴的极限偏差表
  GB/T 5847-2004    尺寸链 计算方法
  GB/T 5371          极限与配合 过盈配合的计算和选用
  机械设计手册（第六版）第 1 卷 公差与配合、尺寸链
  ISO 286-1 / ISO 286-2  公差带与基本偏差国际系列

免责声明
  本报告由程序按上述标准的通用工程取值自动生成，用于公差方案比选与初步设计。
  基本偏差按标准公式计算并取整到 1 μm，与标准表值可能存在 ±1~2 μm 的取整差异；
  「等公差等级法」分配结果会就近归入标准 IT 等级，实际累积公差与目标值存在差额。
  正式投产前请以最新版标准原文、实际加工能力（Cp/Cpk 实测）以及样机验证结果复核。"""


def report_text(title: str, meta: list[tuple[str, str]],
                sections: list[tuple[str, list[tuple[str, str]]]],
                warnings: list[str], notes: list[str],
                images: list[tuple[str, bytes]] | None = None) -> str:
    L = ["=" * 68, f"        {title}", "=" * 68]
    L.append(f"生成时间：{datetime.datetime.now():%Y-%m-%d %H:%M:%S}")
    for k, v in meta:
        L.append(f"{k}：{v}")
    for sec_title, rows in sections:
        L.append("")
        L.append(f"【{sec_title}】")
        for k, v in rows:
            L.append(f"  {k}：{v}")
    for cap, _png in (images or []):
        L.append("")
        L.append(f"【图】{cap}（文本版省略图形，请查看 HTML 版报告）")
    L.append("")
    L.append("【校核结论】")
    if warnings:
        for w in warnings:
            L.append(f"  ⚠ {w}")
    else:
        L.append("  ✓ 各项校核均在推荐范围内。")
    for nt in notes:
        L.append(f"  · {nt}")
    L.append("")
    L.append("-" * 68)
    L.append(DOC_FOOTER_DEFAULT)
    return "\n".join(L)


def report_html(title: str, meta: list[tuple[str, str]],
                sections: list[tuple[str, list[tuple[str, str]]]],
                warnings: list[str], notes: list[str],
                images: list[tuple[str, bytes]] | None = None) -> str:
    esc = html.escape

    def tbl(rows):
        return "<table>" + "".join(
            f"<tr><td class='k'>{esc(k)}</td><td class='v'>{esc(v)}</td></tr>"
            for k, v in rows) + "</table>"

    metas = "".join(f"<tr><td class='k'>{esc(k)}</td><td class='v'>{esc(v)}</td></tr>"
                    for k, v in meta)
    body = "".join(f"<h2>{i}. {esc(t)}</h2>{tbl(rows)}"
                   for i, (t, rows) in enumerate(sections, start=1))
    # 图表以 base64 PNG 内嵌，单文件即可离线查看、转发不失真
    figs = ""
    if images:
        parts = []
        for i, (cap, png) in enumerate(images, start=1):
            b64 = base64.b64encode(png).decode("ascii")
            parts.append(f"<h2>{len(sections) + i}. {esc(cap)}</h2>"
                         f"<img src='data:image/png;base64,{b64}' alt='{esc(cap)}'>")
        figs = "".join(parts)
    warn = "".join(f"<li class='w'>{esc(w)}</li>" for w in warnings) \
        or "<li class='o'>各项校核均在推荐范围内。</li>"
    notes_html = f"<ul>{''.join(f'<li>{esc(n)}</li>' for n in notes)}</ul>" if notes else ""
    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>{esc(title)}</title>
<style>
 body {{ font-family:"Microsoft YaHei","Segoe UI",sans-serif; color:#1F2933;
        max-width:920px; margin:36px auto; padding:0 22px; line-height:1.7; }}
 h1 {{ font-size:22px; border-bottom:2px solid #2F6FED; padding-bottom:10px; }}
 h2 {{ font-size:15px; color:#2F6FED; margin-top:26px;
       border-left:3px solid #2F6FED; padding-left:9px; }}
 table {{ width:100%; border-collapse:collapse; margin:8px 0; font-size:13.5px; }}
 td {{ border:1px solid #E3E7ED; padding:7px 11px; }}
 td.k {{ background:#F7F9FC; width:46%; color:#4A5A6A; }}
 td.v {{ font-weight:600; text-align:right; font-variant-numeric:tabular-nums; }}
 ul {{ padding-left:20px; }}
 li.w {{ color:#8A5A12; background:#FFF9F0; margin:5px 0; padding:6px 10px;
         border-radius:5px; list-style:none; }}
 li.o {{ color:#0B7A3C; background:#F1FBF5; padding:6px 10px; border-radius:5px;
         list-style:none; }}
 img {{ max-width:100%; height:auto; border:1px solid #E3E7ED; border-radius:6px;
        margin:4px 0 10px; }}
 .meta td {{ font-weight:400; }}
 footer {{ margin-top:34px; padding-top:14px; border-top:1px solid #E3E7ED;
           color:#7A8794; font-size:11.5px; white-space:pre-wrap; }}
</style></head><body>
<h1>{esc(title)}</h1>
<p style="color:#7A8794;font-size:12.5px">生成时间：{datetime.datetime.now():%Y-%m-%d %H:%M:%S}</p>
<table class="meta">{metas}</table>
{body}
{figs}
<h2>校核结论</h2>
<ul>{warn}</ul>
{notes_html}
<footer>{esc(DOC_FOOTER_DEFAULT)}</footer>
</body></html>"""


def grab_widget_png(w) -> bytes:
    """把控件当前画面渲染成 PNG 字节。grab() 前先冲一遍布局事件，
    否则刚改完数据还没重绘时会截到旧图。"""
    for _ in range(6):
        QCoreApplication.processEvents()
    pix = w.grab()
    buf = QBuffer()
    buf.open(QIODevice.WriteOnly)
    pix.save(buf, "PNG")
    return bytes(buf.data())


def save_report(parent, title: str, default_name: str, meta, sections,
                warnings, notes, images: list[tuple[str, bytes]] | None = None):
    if not sections:
        QMessageBox.warning(parent, "无可导出内容", "请先完成一次有效计算。")
        return
    path, _ = QFileDialog.getSaveFileName(
        parent, "导出公差分析报告",
        f"{default_name}_{datetime.datetime.now():%Y%m%d_%H%M}.html",
        "网页报告 (*.html);;文本文件 (*.txt)")
    if not path:
        return
    try:
        if path.lower().endswith(".txt"):
            content = report_text(title, meta, sections, warnings, notes, images)
        else:
            content = report_html(title, meta, sections, warnings, notes, images)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
    except OSError as e:
        QMessageBox.critical(parent, "写入失败", str(e))
        return
    QMessageBox.information(parent, "导出完成", f"报告已保存到：\n{path}")


# =====================================================================
# 基础控件（与家族成员同款 + 两个本工具新增）
# =====================================================================

class Card(QFrame):
    """带标题的白色卡片容器。"""

    def __init__(self, title: str = "", hint: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 12, 14, 14)
        outer.setSpacing(8)
        if title:
            head = QHBoxLayout()
            head.setSpacing(8)
            lab = QLabel(title)
            lab.setObjectName("CardTitle")
            head.addWidget(lab)
            head.addStretch(1)
            if hint:
                h = QLabel(hint)
                h.setObjectName("CardHint")
                head.addWidget(h)
            outer.addLayout(head)
        self.body = QVBoxLayout()
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(8)
        outer.addLayout(self.body)

    def add(self, w):
        self.body.addWidget(w)
        return w

    def add_layout(self, l):
        self.body.addLayout(l)
        return l


class MetricCard(QFrame):
    """大数字指标卡。"""

    def __init__(self, name: str, unit: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("Metric")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 9, 12, 9)
        lay.setSpacing(1)
        top = QHBoxLayout()
        top.setSpacing(4)
        self.name = QLabel(name)
        self.name.setObjectName("MetricName")
        self.unit = QLabel(unit)
        self.unit.setObjectName("MetricUnit")
        top.addWidget(self.name)
        top.addStretch(1)
        top.addWidget(self.unit)
        self.value = QLabel("—")
        self.value.setObjectName("MetricValue")
        self.value.setStyleSheet(f"color:{TEXT};")
        self.note = QLabel("")
        self.note.setObjectName("MetricNote")
        lay.addLayout(top)
        lay.addWidget(self.value)
        lay.addWidget(self.note)

    def set(self, value: str, state: str = "ok", note: str = ""):
        color = {"ok": OK, "warn": WARN, "bad": BAD, "na": TEXT_DIM}[state]
        self.value.setText(value)
        self.value.setStyleSheet(f"color:{color};")
        self.note.setText(note)


class NumberInput(QWidget):
    """一行数值输入：标签 + 输入框 + 单位。"""

    def __init__(self, label: str, unit: str = "", placeholder: str = "",
                 label_w: int = 104, tip: str = "", parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        self.label = QLabel(label)
        self.label.setObjectName("FieldLabel")
        self.label.setFixedWidth(label_w)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText(placeholder)
        self.edit.setMinimumWidth(70)
        if tip:
            self.edit.setToolTip(tip)
            self.label.setToolTip(tip)
        self.unit = QLabel(unit)
        self.unit.setObjectName("FieldUnit")
        self.unit.setMinimumWidth(30)
        lay.addWidget(self.label)
        lay.addWidget(self.edit, 1)
        lay.addWidget(self.unit)

    def set_label(self, text: str):
        self.label.setText(text)

    def value(self):
        s = self.edit.text().strip().replace("，", "").replace(",", "")
        if not s:
            return None
        try:
            return float(s)
        except ValueError:
            raise ValueError(f"「{self.label.text()}」不是有效数值：{s}")

    def value_or(self, default: float = 0.0) -> float:
        v = self.value()
        return default if v is None else v

    def set_value(self, v):
        if v is None or v == "":
            self.edit.setText("")
            return
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            f = float(v)
            # 大整数用 %g 会变成科学计数法（20260918 → 2.02609e+07），
            # 仿真种子这类整数值必须按整数写法显示
            if f.is_integer() and abs(f) < 1e15:
                self.edit.setText(f"{int(f)}")
            else:
                self.edit.setText(f"{f:g}")
            return
        self.edit.setText(str(v))

    def set_tip(self, tip: str):
        self.edit.setToolTip(tip)
        self.label.setToolTip(tip)

    def on_change(self, fn):
        self.edit.textChanged.connect(fn)


class TextInput(QWidget):
    """一行文本输入（本工具新增）。"""

    def __init__(self, label: str, placeholder: str = "", label_w: int = 104,
                 parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        self.label = QLabel(label)
        self.label.setObjectName("FieldLabel")
        self.label.setFixedWidth(label_w)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText(placeholder)
        lay.addWidget(self.label)
        lay.addWidget(self.edit, 1)

    def text(self) -> str:
        return self.edit.text().strip()

    def set_text(self, s: str):
        self.edit.setText(s or "")

    def on_change(self, fn):
        self.edit.textChanged.connect(fn)


class CheckInput(QWidget):
    """一行勾选项（本工具新增）。"""

    def __init__(self, label: str, text: str = "", label_w: int = 104,
                 tip: str = "", parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        self.label = QLabel(label)
        self.label.setObjectName("FieldLabel")
        self.label.setFixedWidth(label_w)
        self.check = QCheckBox(text)
        if tip:
            self.check.setToolTip(tip)
        lay.addWidget(self.label)
        lay.addWidget(self.check, 1)

    def is_checked(self) -> bool:
        return self.check.isChecked()

    def set_checked(self, v: bool):
        self.check.setChecked(bool(v))

    def on_change(self, fn):
        self.check.toggled.connect(fn)


class ComboInput(QWidget):
    def __init__(self, label: str, items, label_w: int = 104, parent=None,
                 editable: bool = False, unit: str = ""):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        self.label = QLabel(label)
        self.label.setObjectName("FieldLabel")
        self.label.setFixedWidth(label_w)
        self.combo = QComboBox()
        self.combo.addItems(items)
        if editable:
            self.combo.setEditable(True)
            self.combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
            self.combo.lineEdit().setPlaceholderText("选择或直接输入数值")
        self.unit = QLabel(unit)
        self.unit.setObjectName("FieldUnit")
        self.unit.setMinimumWidth(30)
        lay.addWidget(self.label)
        lay.addWidget(self.combo, 1)
        if unit:
            lay.addWidget(self.unit)

    def on_change(self, fn):
        self.combo.currentIndexChanged.connect(fn)

    def on_text_change(self, fn):
        self.combo.currentTextChanged.connect(fn)

    def current(self):
        return self.combo.currentText()

    def set_current(self, text: str):
        i = self.combo.findText(text)
        if i >= 0:
            self.combo.setCurrentIndex(i)

    def set_tip(self, tip: str):
        self.combo.setToolTip(tip)
        self.label.setToolTip(tip)


class RowList(QWidget):
    """键值对列表。"""

    def __init__(self, parent=None, key_w: int = 104):
        super().__init__(parent)
        self.key_w = key_w
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(10)
        self.grid.setVerticalSpacing(5)
        self.grid.setColumnStretch(0, 0)
        self.grid.setColumnStretch(1, 1)
        self.grid.setColumnMinimumWidth(0, key_w)
        self._row = 0

    def clear(self):
        while self.grid.count():
            item = self.grid.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._row = 0

    def add(self, key: str, value: str, bold=False, color=None):
        k = QLabel(key)
        k.setObjectName("RowKey")
        v = QLabel(value)
        v.setObjectName("RowVal")
        v.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        v.setWordWrap(True)
        v.setMinimumWidth(40)
        v.setFont(QFont("Consolas", 9))
        v.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        if color:
            v.setStyleSheet(f"color:{color};font-size:12px;font-weight:600;")
        elif bold:
            v.setStyleSheet(f"color:{TEXT};font-size:12.5px;font-weight:700;")
        self.grid.addWidget(k, self._row, 0)
        self.grid.addWidget(v, self._row, 1)
        self._row += 1

    def add_sep(self):
        f = QFrame()
        f.setObjectName("Divider")
        self.grid.addWidget(f, self._row, 0, 1, 2)
        self._row += 1

    def rows(self) -> list[tuple[str, str]]:
        out = []
        for i in range(self.grid.rowCount()):
            a = self.grid.itemAtPosition(i, 0)
            b = self.grid.itemAtPosition(i, 1)
            if not (a and b):
                continue
            aw, bw = a.widget(), b.widget()
            if isinstance(aw, QLabel) and isinstance(bw, QLabel):
                out.append((aw.text(), bw.text()))
        return out


class VerifyBox(QWidget):
    """校核结论区：自动排列 通过 / 警告 条目。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(0, 0, 0, 0)
        self.lay.setSpacing(6)

    def clear(self):
        while self.lay.count():
            it = self.lay.takeAt(0)
            w = it.widget()
            if w:
                w.deleteLater()

    def show_items(self, warnings: list[str], notes: list[str],
                   ok_text: str = "各项校核均在设计要求范围内。"):
        self.clear()
        if warnings:
            for w in warnings:
                self._add(w, "warn")
        else:
            self._add(ok_text, "ok")
        for n in notes:
            self._add(n, "warn")

    def _add(self, text: str, kind: str = "warn"):
        f = QFrame()
        f.setObjectName("OkItem" if kind == "ok" else "WarnItem")
        lay = QHBoxLayout(f)
        lay.setContentsMargins(10, 7, 10, 7)
        ico = QLabel("✓" if kind == "ok" else "!")
        ico.setFixedWidth(16)
        ico.setStyleSheet(
            f"color:{OK if kind == 'ok' else WARN};font-weight:700;font-size:13px;")
        t = QLabel(text)
        t.setObjectName("OkText" if kind == "ok" else "WarnText")
        t.setWordWrap(True)
        lay.addWidget(ico, 0, Qt.AlignmentFlag.AlignTop)
        lay.addWidget(t, 1)
        self.lay.addWidget(f)


def fit_table(t: QTableWidget, cap: int = 460, pad: int = 4):
    """把表格高度收到刚好装下所有行，避免末行被截、还冒出内部滚动条。

    表头高与行高都从控件实测，不写死数字 —— QSS 定了单元格内边距，
    实测本主题下：行高 30 px，两行表头 57 px、单行表头 40 px。
    注意表头要用 sizeHint 而不是 height()：show 之前 height() 只有 40，
    按它算会矮 17 px，正好把最后一行挤掉。
    """
    n = max(1, t.rowCount())
    hdr = t.horizontalHeader().sizeHint().height()
    rows = sum(t.rowHeight(r) for r in range(n))
    t.setFixedHeight(min(cap, hdr + rows + pad))


def make_table(cols: list[str], widths: list[int] | None = None) -> QTableWidget:
    """统一风格的只读外观表格。"""
    t = QTableWidget(0, len(cols))
    t.setHorizontalHeaderLabels(cols)
    t.verticalHeader().setVisible(False)
    t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    t.setAlternatingRowColors(False)
    t.setShowGrid(True)
    hh = t.horizontalHeader()
    hh.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
    if widths:
        for i, wd in enumerate(widths):
            t.setColumnWidth(i, wd)
    else:
        hh.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    return t


def cell(t: QTableWidget, r: int, c: int, text: str, color=None, bold=False,
         align="l"):
    it = QTableWidgetItem(text)
    if align == "r":
        it.setTextAlignment(Qt.AlignmentFlag.AlignRight
                            | Qt.AlignmentFlag.AlignVCenter)
    elif align == "c":
        it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
    if color:
        it.setForeground(QColor(color))
    if bold:
        f = it.font()
        f.setBold(True)
        it.setFont(f)
    t.setItem(r, c, it)
    return it


# =====================================================================
# 页 1 · 尺寸链计算（正算 / 公差分析）
# =====================================================================

_FORMAT_TIP = ("公差带代号，如 H7 / f6 / js6（可带直径，如 φ50H7）。\n"
               "本工具已内置：轴 d e f g h js k，孔 D E F G H JS K。\n"
               "其余代号（a b c、j m n p~zc）国标取值含分段修正量，"
               "请直接填上/下偏差。")

_LINK_COLS = ["编号", "名称", "基本尺寸\nmm", "上偏差\nmm", "下偏差\nmm",
              "环型", "分布状态", "σ 等级", "公差\nmm", "传递系数\nξ",
              "贡献率\n(统计法)"]
_LINK_W = [58, 108, 84, 84, 84, 80, 156, 92, 100, 132, 110]
# 列索引（表格增删列时只改这里，避免散落的魔数）
_C_NO, _C_NAME, _C_NOM, _C_ES, _C_EI = 0, 1, 2, 3, 4
_C_SIGN, _C_DIST, _C_GRADE, _C_TOL, _C_XI, _C_SHARE = 5, 6, 7, 8, 9, 10

# 各列表头的悬浮说明（悬停即弹出，不用查帮助页）
_LINK_TIPS = {
    "编号": "组成环编号（A1、A2…），报告与贡献率排序按此显示",
    "名称": "零件或尺寸的名称，如「活塞」「壁厚」",
    "基本尺寸\nmm": "该环的名义尺寸。换算公差带代号（如 H7）时按此值查表",
    "上偏差\nmm": "上极限偏差 ES = 最大极限尺寸 − 基本尺寸，可填 +0.05 或 0.05",
    "下偏差\nmm": "下极限偏差 EI = 最小极限尺寸 − 基本尺寸，负值带负号",
    "环型": "增环：该环变大 → 封闭环变大；减环反之。\n拿不准可先填封闭环目标值再点「自动判增减环」",
    "分布状态": "该环尺寸的实际分布（只影响统计法与蒙特卡洛仿真，极值法不使用）。\n批量机加工通常按「正态分布」",
    "σ 等级": "本环公差带对应「±几个 σ」，逐环可选（默认 ±3σ）。\n"
           "· ±3σ：Tᵢ 就是 6σ 带宽，GB/T 5847 与华为胶片的标准正态口径\n"
           "· ±4σ / ±5σ / ±6σ：该环的工艺数据比标准口径更保守（同一公差带\n"
           "  按更宽的 σ 解读），在统计法合成里占的带宽更大\n"
           "统计法评估带宽 ᵢ = nᵢ·σᵢ，合成 T_rss = √(Σ(ξᵢ·nᵢ·σᵢ)²)。\n"
           "极值法 WC 不使用本列；σ₀ 与 Cp / Ppk 始终按 6σ 标准定义，也不受本列影响",
    "公差\nmm": "公差带全宽 T = 上偏差 − 下偏差（只读，改偏差后自动更新）",
    "传递系数\nξ": "传递系数 ξ：该环变化 1 mm 时封闭环变化多少。\n"
         "· 自动：按增/减环取 ±1（平行尺寸链，绝大多数场景）\n"
         "· 显式选 0.866 / 0.707 等：斜面、锥面、投影方向的环按几何关系取，\n"
         "  例如与封闭环方向成 30° 的滑块位移取 cos30° = +0.866。\n"
         "选中后环型随 ξ 符号联动；切回增/减环会恢复自动 ±1",
    "贡献率\n(统计法)": "该环方差占封闭环总方差的比例（σ₀² 中它占多少）。\n"
                     "占比最大的就是主导环，想收紧总公差先收紧它",
}

# 传递系数 ξ 的可选项：第 0 项「自动」= 按增/减环取 ±1；
# 其余为显式系数（斜面、投影等非平行环：cos30°=0.866、cos45°=0.707、
# tan30°=1/√3≈0.577、cos60°=0.5，含正负）。文字必须与 f"{v:+g}" 严格一致。
_XI_ITEMS = ["自动", "+1", "-1", "+0.866", "-0.866", "+0.707", "-0.707",
             "+0.577", "-0.577", "+0.5", "-0.5"]


def _grade_index(v) -> int:
    """把 σ 等级值映射成 SIGMA_GRADES 的下标（非标准值取最近一档）。"""
    try:
        v = float(v)
    except (TypeError, ValueError):
        return 0
    return min(range(len(SIGMA_GRADES)), key=lambda i: abs(SIGMA_GRADES[i] - v))


def grade_summary(res) -> str:
    """把各环 σ 等级汇总成一行文字（报告 / 导出共用）。"""
    links = res.get("links") or []
    if not links:
        return "—"
    cnt: dict[float, int] = {}
    for l in links:
        g = float(l.get("sigma_grade", DEFAULT_SIGMA_GRADE))
        cnt[g] = cnt.get(g, 0) + 1
    if len(cnt) == 1:
        g = next(iter(cnt))
        tail = "（标准正态口径，单环 T = 6σ）" if abs(g - 3.0) < 1e-9 else ""
        return f"全环统一 ±{g:g}σ{tail}"
    neff = float((res.get("rss") or {}).get("n_eff", 0.0) or 0.0)
    detail = "、".join(f"±{g:g}σ×{cnt[g]}" for g in sorted(cnt))
    return f"逐环设定：{detail}　→ 等效 ±{neff:.4f}σ₀"


class TolPage(QWidget):
    """尺寸链计算：组成环表格 + 封闭环要求 + 极值/统计双算法结果 + 示意图。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(240)
        self._timer.timeout.connect(self.recalc)
        self._res = None
        self._build()

    # ---------------- 构建 ----------------
    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        outer.addWidget(sa)
        body = QWidget()
        sa.setWidget(body)
        lay = QVBoxLayout(body)
        lay.setContentsMargins(12, 10, 12, 14)
        lay.setSpacing(10)

        # ---- 顶部：工程信息 + 封闭环要求 ----
        top = QHBoxLayout()
        top.setSpacing(10)
        proj = Card("工程信息")
        self.in_name = TextInput("项目名称", "例：L20 浇灌机 传动装配")
        self.in_name.set_text(STATE.project["name"])
        self.in_code = TextInput("图号 / 编号", "例：TA-2026-001")
        self.in_code.set_text(STATE.project["code"])
        self.in_author = TextInput("设计 / 校核", "姓名")
        for w in (self.in_name, self.in_code, self.in_author):
            proj.add(w)
        self.in_thermal = CheckInput(
            "热膨胀", "按工作温度修正（20 ℃ 基准）",
            tip="勾选后每个组成环按 基本尺寸×(1+α·ΔT) 修正，"
                "其中 α 为该环线膨胀系数（×10⁻⁶/K）、ΔT = 工作温度 − 20 ℃。")
        proj.add(self.in_thermal)
        top.addWidget(proj, 3)

        tgt = Card("封闭环要求", hint="留空目标值 = 按算出的名义值取偏差带")
        self.in_tnom = NumberInput("封闭环目标值", "mm", "留空 = 用计算值",
                                   tip="留空时按「相对封闭环计算名义值的偏差带」比对，"
                                       "即最常用的「累积公差须落在 ±x 内」。\n"
                                       "填写后则按绝对尺寸比对。")
        self.in_tes = NumberInput("上偏差", "mm", "如 0.25")
        self.in_tei = NumberInput("下偏差", "mm", "如 -0.25")
        self.in_tes.set_value(STATE.target["es"])
        self.in_tei.set_value(STATE.target["ei"])
        for w in (self.in_tnom, self.in_tes, self.in_tei):
            tgt.add(w)
        lab = QLabel("口径：目标值留空 → 按 N₀ ± 偏差带比对；填写 → 按绝对尺寸比对。")
        lab.setObjectName("FieldHint")
        lab.setWordWrap(True)
        tgt.add(lab)
        top.addWidget(tgt, 3)
        lay.addLayout(top)

        # ---- 组成环表格 ----
        tcard = Card("组成环（尺寸环）")
        bar = QHBoxLayout()
        bar.setSpacing(6)
        for text, fn, tip in (
                ("+ 添加环", self._add_link, "在表尾新增一个组成环"),
                ("− 删除选中", self._del_link, "删除当前选中的组成环"),
                ("↑", lambda: self._move(-1), "上移"),
                ("↓", lambda: self._move(1), "下移"),
                ("自动判增减环", self._auto_signs,
                 "按封闭环基本尺寸反解各环的传递系数（子集和求解）"),
                ("载入示例", self._load_example, "载入一个教科书级算例"),
                ("标准选取…", self._pick_std,
                 "弹窗选取标准公差：常用配合 / 按加工方式选 IT / "
                 "标准件 / PCB / 连接器，填入选中环的上、下偏差"),
        ):
            b = QPushButton(text)
            b.setObjectName("Mini")
            b.setToolTip(tip)
            b.clicked.connect(fn)
            bar.addWidget(b)
        bar.addStretch(1)

        bar.addWidget(QLabel("按代号填偏差："))
        self.q_nom = QLineEdit()
        self.q_nom.setPlaceholderText("基本尺寸")
        self.q_nom.setFixedWidth(84)
        self.q_code = QLineEdit()
        self.q_code.setPlaceholderText("如 H7")
        self.q_code.setFixedWidth(78)
        self.q_code.setToolTip(_FORMAT_TIP)
        b_apply = QPushButton("填入选中环")
        b_apply.setObjectName("Mini")
        b_apply.setToolTip("把公差带代号换算成的上/下偏差填入当前选中行")
        b_apply.clicked.connect(self._apply_zone)
        bar.addWidget(self.q_nom)
        bar.addWidget(self.q_code)
        bar.addWidget(b_apply)
        tcard.add_layout(bar)

        self.table = QTableWidget(0, len(_LINK_COLS))
        self.table.setHorizontalHeaderLabels(_LINK_COLS)
        for i, c in enumerate(_LINK_COLS):
            it = self.table.horizontalHeaderItem(i)
            if it is not None and c in _LINK_TIPS:
                it.setToolTip(_LINK_TIPS[c])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        hh = self.table.horizontalHeader()
        # 列宽策略：数字列定宽（Fixed），「名称」列吃掉全部余量（Stretch）。
        # 之前是 stretchLastSection，窗口一宽贡献率列就独吞几百像素空白，
        # 前面数字列反而显得挤——余量给名称列才合理。
        hh.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hh.setStretchLastSection(False)
        hh.setMinimumSectionSize(56)
        for i, wd in enumerate(_LINK_W):
            self.table.setColumnWidth(i, wd)
        # 不设 setMinimumHeight：行数可增减，高度交给 fit_table 按实际行数收放，
        # 否则 5 行时（表头 57 + 5×30 = 211 px > 200）末行被截、冒出内部滚动条。
        self.table.cellChanged.connect(self._on_cell)
        tcard.add(self.table)
        lay.addWidget(tcard)

        # ---- 示意图两联 ----
        dia = QHBoxLayout()
        dia.setSpacing(10)
        c1 = Card("尺寸链简图")
        self.d_chain = ChainDiagram()
        c1.add(self.d_chain)
        c2 = Card("公差带图")
        self.d_band = BandDiagram()
        c2.add(self.d_band)
        dia.addWidget(c1, 1)
        dia.addWidget(c2, 1)
        lay.addLayout(dia)

        # ---- 结果 ----
        rcard = Card("封闭环计算结果", hint="T 为公差带全宽；± 为半带")
        mrow = QHBoxLayout()
        mrow.setSpacing(8)
        self.m_nom = MetricCard("封闭环 N₀", "mm")
        self.m_wc = MetricCard("极值法 WC", "mm")
        self.m_rss = MetricCard("统计法 RSS", "mm")
        self.m_ppk = MetricCard("Ppk", "")
        for m in (self.m_nom, self.m_wc, self.m_rss, self.m_ppk):
            mrow.addWidget(m, 1)
        rcard.add_layout(mrow)
        srow = QHBoxLayout()
        srow.setSpacing(6)
        sl = QLabel("统一 σ 等级")
        sl.setToolTip("一键把所有组成环的 σ 等级设为同一档；表格「σ 等级」列还能逐环单独改。\n"
                      "默认 ±3σ = 该环公差带就是 6σ 带宽，GB/T 5847 与华为胶片的标准正态口径。\n"
                      "统计法评估带宽ᵢ = nᵢ·σᵢ，合成 T_rss = √(Σ(ξᵢ·nᵢ·σᵢ)²)；\n"
                      "σ₀ 与 Cp / Ppk 始终按 6σ 定义，不随本档位变化。")
        self.cb_nsigma = QComboBox()
        self.cb_nsigma.addItems(["±3σ（默认，标准正态口径）", "±4σ",
                                 "±5σ", "±6σ（华为表格口径）",
                                 "±8σ（更保守）"])
        self.cb_nsigma.setCurrentIndex(0)
        self.cb_nsigma.setToolTip(sl.toolTip())
        self.cb_nsigma.currentIndexChanged.connect(self._on_nsigma)
        srow.addWidget(sl)
        srow.addWidget(self.cb_nsigma)
        srow.addStretch(1)
        rcard.add_layout(srow)

        self.rows = RowList(key_w=150)
        rcard.add(self.rows)
        self.verify = VerifyBox()
        rcard.add(self.verify)
        lay.addWidget(rcard)

        # ---- 贡献率 ----
        ccard = Card("各环贡献率排序", hint="统计法按方差占比，极值法按公差占比")
        self.d_contrib = ContribBar()
        ccard.add(self.d_contrib)
        self.t_contrib = make_table(
            ["环", "名称", "公差带 T\nmm", "传递系数 ξ", "贡献率\n极值法 WC",
             "贡献率\n统计法 RSS"], [64, 150, 100, 96, 118, 118])
        self.t_contrib.setMinimumHeight(150)
        ccard.add(self.t_contrib)
        lay.addWidget(ccard)

        # ---- 操作 ----
        foot = QHBoxLayout()
        b_exp = QPushButton("导出公差分析报告")
        b_exp.setObjectName("Primary")
        b_exp.clicked.connect(self._export)
        foot.addStretch(1)
        foot.addWidget(b_exp)
        lay.addLayout(foot)

        # ---- 事件 ----
        for w in (self.in_tes, self.in_tei, self.in_tnom):
            w.on_change(self._kick)
        self.in_thermal.on_change(self._on_thermal)
        for w in (self.in_name, self.in_code, self.in_author):
            w.on_change(self._kick)

        self._fill()
        self.recalc()

    # ---------------- 表格读写 ----------------
    def _fill(self):
        t = self.table
        t.blockSignals(True)
        t.setRowCount(0)
        for l in STATE.links:
            r = t.rowCount()
            t.insertRow(r)
            cell(t, r, _C_NO, str(l.get("no", "")), align="c")
            cell(t, r, _C_NAME, str(l.get("name", "")))
            cell(t, r, _C_NOM, f"{l['nominal']:g}", align="r")
            cell(t, r, _C_ES, f"{l['es']:g}", align="r")
            cell(t, r, _C_EI, f"{l['ei']:g}", align="r")
            cb = QComboBox()
            cb.addItems(["增环", "减环"])
            cb.setCurrentIndex(0 if int(l.get("sign", 1)) >= 0 else 1)
            cb.currentIndexChanged.connect(
                lambda _i, rr=r: self._set_field(rr, "sign"))
            t.setCellWidget(r, _C_SIGN, cb)
            db = QComboBox()
            db.addItems([DISTRIBUTIONS[k]["label"] for k in DIST_KEYS])
            di = DIST_KEYS.index(l.get("dist", DEFAULT_DIST)) \
                if l.get("dist") in DIST_KEYS else 0
            db.setCurrentIndex(di)
            db.currentIndexChanged.connect(
                lambda _i, rr=r: self._set_field(rr, "dist"))
            t.setCellWidget(r, _C_DIST, db)
            # σ 等级：逐环可选，默认 ±3σ（= T 为 6σ 带宽的标准正态口径）
            nb = QComboBox()
            nb.addItems(list(SIGMA_GRADE_LABELS))
            nb.setCurrentIndex(_grade_index(l.get("sigma_grade")))
            nb.setToolTip(_LINK_TIPS["σ 等级"])
            nb.currentIndexChanged.connect(
                lambda _i, rr=r: self._set_field(rr, "grade"))
            t.setCellWidget(r, _C_GRADE, nb)
            cell(t, r, _C_TOL, "—", align="r")
            xb = QComboBox()
            xb.addItems(_XI_ITEMS)
            if l.get("xi") is not None:
                _xi = xb.findText(f"{float(l['xi']):+g}")
                xb.setCurrentIndex(_xi if _xi > 0 else 1)
            xb.setToolTip("传递系数 ξ：自动 = 按增/减环取 ±1；"
                          "斜面、投影等非平行环可显式选系数（cos30°=0.866 等）")
            xb.currentIndexChanged.connect(
                lambda _i, rr=r: self._set_field(rr, "xi"))
            t.setCellWidget(r, _C_XI, xb)
            cell(t, r, _C_SHARE, "—", align="r")
        t.blockSignals(False)
        # 行数变了（增/删/移动/整表重建）都要重算高度，保证所有行直接可见、不出内部滚动条
        fit_table(t, cap=720)

    def _fill_computed(self, res):
        """把算出来的「公差 / 传递系数 ξ / 贡献率」回填到表格的只读列。

        这三列由计算结果决定、不允许手改，所以回填时必须屏蔽 cellChanged ——
        否则 cellChanged → _on_cell → _kick → recalc → 再回填，会自激成死循环。
        按「编号」而非行号匹配：组成环可能被停用，行号不一定对得上。
        """
        t = self.table
        t.blockSignals(True)
        try:
            lmap = {str(l.get("no")): l for l in res.get("links") or []}
            pool = list(res.get("contrib") or [])
            for i in range(t.rowCount()):
                if i >= len(STATE.links):
                    break
                lk = STATE.links[i]
                no = str(lk.get("no"))
                lc = lmap.get(no)
                hit = next((c for c in pool if str(c.get("no")) == no), None)
                if hit is not None:
                    pool.remove(hit)
                cell(t, i, _C_TOL, "—" if not lc else f"{lc['T']:.4f}", align="r")
                # ξ 列：第 0 项「自动」动态显示实际生效的传递系数
                xb = t.cellWidget(i, _C_XI)
                if isinstance(xb, QComboBox):
                    xb.blockSignals(True)
                    if lk.get("xi") is None:
                        xb.setItemText(0, "自动" if lc is None
                                       else f"自动（{lc['xi']:+g}）")
                        xb.setCurrentIndex(0)
                    else:
                        xb.setItemText(0, "自动")
                        _xi = xb.findText(f"{float(lk['xi']):+g}")
                        xb.setCurrentIndex(_xi if _xi > 0 else 1)
                    xb.blockSignals(False)
                cell(t, i, _C_SHARE, "—" if hit is None
                     else f"{hit['share_rss'] * 100:.2f}%", align="r")
        finally:
            t.blockSignals(False)

    def _clear_computed(self):
        t = self.table
        t.blockSignals(True)
        try:
            for i in range(t.rowCount()):
                cell(t, i, _C_TOL, "—", align="r")
                cell(t, i, _C_XI, "", align="c")
                cell(t, i, _C_SHARE, "—", align="r")
        finally:
            t.blockSignals(False)

    def _on_cell(self, r: int, c: int):
        if r >= len(STATE.links):
            return
        it = self.table.item(r, c)
        if it is None:
            return
        l = STATE.links[r]
        txt = it.text().strip()
        try:
            if c == 0:
                l["no"] = txt
            elif c == 1:
                l["name"] = txt
            elif c in (2, 3, 4):
                v = float(txt.replace("，", "").replace(",", "") or 0)
                l[{2: "nominal", 3: "es", 4: "ei"}[c]] = v
        except ValueError:
            it.setForeground(QColor(BAD))
            self._kick()
            return
        it.setForeground(QColor(TEXT))
        self._kick()

    def _set_field(self, r: int, kind: str):
        if r >= len(STATE.links):
            return
        l = STATE.links[r]
        col = {"sign": _C_SIGN, "dist": _C_DIST, "grade": _C_GRADE,
               "xi": _C_XI}[kind]
        w = self.table.cellWidget(r, col)
        if isinstance(w, QComboBox):
            if kind == "sign":
                l["sign"] = 1 if w.currentIndex() == 0 else -1
                l["xi"] = None                     # 切增/减环 = 回到自动 ±1
            elif kind == "dist":
                l["dist"] = DIST_KEYS[w.currentIndex()]
            elif kind == "grade":
                l["sigma_grade"] = SIGMA_GRADES[w.currentIndex()]
            else:                                   # xi
                txt = w.currentText()
                if txt == "自动":
                    l["xi"] = None
                else:
                    l["xi"] = float(txt)
                    l["sign"] = 1 if l["xi"] >= 0 else -1
                    # 环型跟着符号走（屏蔽信号，避免又把 xi 清回自动）
                    sb = self.table.cellWidget(r, _C_SIGN)
                    if isinstance(sb, QComboBox):
                        sb.blockSignals(True)
                        sb.setCurrentIndex(0 if l["sign"] > 0 else 1)
                        sb.blockSignals(False)
        self._kick()

    def _add_link(self):
        n = len(STATE.links) + 1
        STATE.links.append(new_link(no=f"A{n}", name=f"环{n}", nominal=10.0,
                                    es=0.05, ei=-0.05, sign=1))
        self._fill()
        # 新增后立刻选中：一是能接着改这一行，二是「− 删除选中」马上可用
        self.table.selectRow(len(STATE.links) - 1)
        self.recalc()

    def _del_link(self):
        r = self.table.currentRow()
        if r < 0 or r >= len(STATE.links):
            return
        STATE.links.pop(r)
        self._fill()
        self.recalc()

    def _move(self, d: int):
        r = self.table.currentRow()
        j = r + d
        if r < 0 or not (0 <= j < len(STATE.links)):
            return
        L = STATE.links
        L[r], L[j] = L[j], L[r]
        self._fill()
        self.table.selectRow(j)
        self.recalc()

    def _auto_signs(self):
        tn = self.in_tnom.value()
        if tn is None:
            # 没给目标值就用「各环基本尺寸」的某一组合试探：直接提示用户
            QMessageBox.information(
                self, "需要封闭环基本尺寸",
                "自动判定增减环需要知道封闭环的基本尺寸。\n"
                "请在「封闭环要求 → 封闭环目标值」里填入该值后重试。")
            return
        signs, msg = auto_signs(STATE.links, tn)
        if signs is None:
            QMessageBox.warning(self, "反解失败", msg)
            return
        for l, s in zip(STATE.links, signs):
            l["sign"] = s
            l["xi"] = None      # 反解的是 ±1 组合，显式 ξ 一律清空回自动
        self._fill()
        self.recalc()
        QMessageBox.information(self, "自动判定完成", msg)

    def _load_example(self):
        from PySide6.QtWidgets import QInputDialog
        names = [t for _k, t in __import__("core.tol_core", fromlist=["x"]).EXAMPLE_NAMES]
        keys = [k for k, _t in __import__("core.tol_core", fromlist=["x"]).EXAMPLE_NAMES]
        i, okd = QInputDialog.getItem(self, "载入示例", "选择算例：", names, 0, False)
        if not okd:
            return
        STATE.links = example_links(keys[names.index(i)])
        self._fill()
        self.recalc()

    def _apply_zone(self):
        r = self.table.currentRow()
        if r < 0:
            QMessageBox.information(self, "未选中行", "请先在表格里点选一个组成环。")
            return
        try:
            txt = self.q_nom.text().strip().replace("，", "").replace(",", "")
            nom = float(txt) if txt else None
            if nom is None:
                nom = STATE.links[r]["nominal"]
            z = parse_zone(self.q_code.text(), nom)
        except (DesignError, ValueError) as e:
            QMessageBox.warning(self, "无法换算", str(e))
            return
        STATE.links[r]["es"] = z["es"]
        STATE.links[r]["ei"] = z["ei"]
        self._fill()
        self.table.selectRow(r)
        self.recalc()

    def _pick_std(self):
        r = self.table.currentRow()
        if r < 0 or r >= len(STATE.links):
            QMessageBox.information(self, "未选中行",
                                    "请先在表格里点选一个组成环，再打开标准选取。")
            return
        StdDevDialog(self, r).exec()

    def _on_thermal(self):
        STATE.use_thermal = self.in_thermal.is_checked()
        self.recalc()

    def _on_nsigma(self, idx: int):
        """统一 σ 等级：把所有组成环一次性设为同一档（表格里仍可逐环覆盖）。"""
        STATE.n_sigma = SIGMA_GRADES[max(0, min(idx, len(SIGMA_GRADES) - 1))]
        for l in STATE.links:
            l["sigma_grade"] = STATE.n_sigma
        self._fill()
        self.recalc()

    def _kick(self):
        self._timer.start()

    def sync_from_state(self):
        """从共享 STATE 重新灌表并重算。

        「公差分配」页把分配结果写回 STATE.links 之后，切回本页必须重新读入，
        否则表格里还显示旧公差。
        """
        self._fill()
        self.recalc()

    def load_from_state(self):
        """把 STATE 里的工程信息 / 封闭环要求 / 热膨胀 / σ 等级灌回控件，再重算。

        启动时恢复上次编辑必须走这条路径：recalc() 会反过来用控件值覆盖 STATE，
        所以必须先写控件、再 recalc，否则刚读回来的数据会被空控件冲掉。
        """
        self.in_name.set_text(STATE.project.get("name", ""))
        self.in_code.set_text(STATE.project.get("code", ""))
        self.in_author.set_text(STATE.project.get("author", ""))
        self.in_thermal.set_checked(bool(STATE.use_thermal))
        tgt = STATE.target or {}
        self.in_tnom.set_value(tgt.get("nominal", ""))
        self.in_tes.set_value(tgt.get("es", 0.0))
        self.in_tei.set_value(tgt.get("ei", 0.0))
        # 统一 σ 等级下拉是「一次性按钮」语义，恢复时要屏蔽它的信号，
        # 否则会把各环保留的逐环档位统统改成同一档
        self.cb_nsigma.blockSignals(True)
        self.cb_nsigma.setCurrentIndex(_grade_index(STATE.n_sigma))
        self.cb_nsigma.blockSignals(False)
        self._fill()
        self.recalc()

    # ---------------- 计算与呈现 ----------------
    def recalc(self):
        STATE.target = {"nominal": self.in_tnom.value() or "",
                        "es": self.in_tes.value_or(0.0),
                        "ei": self.in_tei.value_or(0.0)}
        STATE.use_thermal = self.in_thermal.is_checked()
        STATE.project = {"name": self.in_name.text(), "code": self.in_code.text(),
                         "author": self.in_author.text(), "note": ""}
        try:
            res = STATE.result()
        except (DesignError, ValueError) as e:
            self._show_error(str(e))
            return
        self._res = res
        self._render(res)

    def _show_error(self, msg: str):
        self.m_nom.set("—", "bad", msg)
        for m in (self.m_wc, self.m_rss, self.m_ppk):
            m.set("—", "na")
        self.rows.clear()
        self.verify.show_items([msg], [])
        self.d_chain.set_result(None)
        self.d_band.set_result(None)
        self.d_contrib.set_rows([])
        self.t_contrib.setRowCount(0)
        self._clear_computed()

    def _render(self, res):
        w, s = res["wc"], res["rss"]
        n = res["n"]
        rec = res["recommend"]

        self.m_nom.set(f"{res['nominal']:.4g}", "ok",
                       f"{n} 个组成环 · {res['recommend_reason']}")
        self.m_wc.set(f"±{w['es']:.4f}" if w["es"] == -w["ei"] else
                      f"{w['es']:+.3f}/{w['ei']:+.3f}", "ok" if rec == "wc" else "na",
                      f"T = {w['T']:.4f} mm（ΣTᵢ）"
                      + ("　← 建议口径" if rec == "wc" else ""))
        ns = s.get("n_sigma", DEFAULT_SIGMA_GRADE)
        neff = s.get("n_eff", ns)
        uniform = s.get("uniform_grade", True)
        gradetag = f"±{ns:g}σ" if uniform else f"≈±{neff:.2f}σ"
        self.m_rss.name.setText(f"统计法 RSS {gradetag}")
        self.m_rss.set(f"±{s['es']:.4f}" if s["es"] == -s["ei"] else
                       f"{s['es']:+.3f}/{s['ei']:+.3f}", "ok" if rec == "rss" else "na",
                       f"T = {s['T']:.4f} mm = {neff:.4g}·σ₀"
                       + ("" if uniform else "（逐环 σ 等级不同，取等效值）")
                       + ("　← 建议口径" if rec == "rss" else ""))

        tgt = res.get("target")
        if tgt:
            cap = res["verdict"]["rss"]
            if cap.get("ppk") is not None:
                pk = cap["ppk"]
                state = "ok" if pk >= 1.33 else ("warn" if pk >= 1.0 else "bad")
                self.m_ppk.set(f"{pk:.2f}", state,
                               f"合格率 {cap['pass_rate'] * 100:.3f}%　"
                               f"σ 水平 {cap['sigma_level']:.2f}")
            else:
                self.m_ppk.set("—", "na", "缺少统计法结果")
        else:
            self.m_ppk.set("—", "na", "未填封闭环要求")

        # ---- 明细 ----
        self.rows.clear()
        self.rows.add("封闭环名义值 N₀", f"{res['nominal']:.6g} mm", bold=True)
        if res["use_thermal"]:
            self.rows.add("热膨胀修正", f"已启用（20 ℃ 基准）")
        self.rows.add_sep()
        self.rows.add("【极值法 WC】", "", bold=True)
        self.rows.add("公差带全宽 T", f"{w['T']:.6f} mm")
        self.rows.add("上偏差 ES₀", f"{w['es']:+.6f} mm")
        self.rows.add("下偏差 EI₀", f"{w['ei']:+.6f} mm")
        self.rows.add("极限尺寸范围", f"{w['min']:.6g} ~ {w['max']:.6g} mm")
        self.rows.add_sep()
        self.rows.add("【统计法 RSS / 概率法】", "", bold=True)
        self.rows.add("公差带全宽 T", f"{s['T']:.6f} mm")
        self.rows.add("上偏差 ES₀", f"{s['es']:+.6f} mm")
        self.rows.add("下偏差 EI₀", f"{s['ei']:+.6f} mm")
        self.rows.add("标准差 σ₀", f"{s['sigma']:.6f} mm")
        self.rows.add("±3σ 范围", f"{s['dmid'] - 3 * s['sigma']:+.6f} ~ "
                                f"{s['dmid'] + 3 * s['sigma']:+.6f} mm")
        if uniform:
            self.rows.add("σ 等级（全环统一）",
                          f"±{ns:g}σ　→ 评估带宽 = {ns:g}·σ₀ = {s['T']:.6f} mm")
        else:
            cnt = {}
            for r_ in res.get("links") or []:
                cnt[r_["sigma_grade"]] = cnt.get(r_["sigma_grade"], 0) + 1
            detail = "、".join(f"±{g:g}σ×{cnt[g]}" for g in sorted(cnt))
            self.rows.add("σ 等级（逐环不同）", detail)
            self.rows.add("等效评估带宽", f"±{neff:.4f}σ₀ = {s['T']:.6f} mm"
                                       f"（按 √(Σ(ξᵢ·nᵢ·σᵢ)²) 合成）")
        if tgt:
            self.rows.add_sep()
            self.rows.add("【与设计要求比对】", "", bold=True)
            if tgt["nominal_auto"]:
                self.rows.add("目标值口径", f"留空 → 取 N₀ = {tgt['nominal']:.6g} mm")
            self.rows.add("要求范围", f"{tgt['low']:.6g} ~ {tgt['high']:.6g} mm"
                                    f"（{tgt['ei']:+.4f} ~ {tgt['es']:+.4f}）")
            for key, name in (("wc", "极值法 WC"), ("rss", "统计法 RSS")):
                cap = res["verdict"][key]
                if cap["ok"]:
                    txt = "合格"
                    col = OK
                else:
                    over = max(cap["over_high"], cap["over_low"])
                    side = "上限" if cap["over_high"] >= cap["over_low"] else "下限"
                    txt = f"超差 {over:.6f}（{side}）"
                    col = BAD
                self.rows.add(f"{name} 判定", txt, bold=True, color=col)
            cap = res["verdict"]["rss"]
            if cap.get("cp") is not None:
                self.rows.add("Cp", f"{cap['cp']:.3f}")
                self.rows.add("Ppk", f"{cap['ppk']:.3f}")
                self.rows.add("σ 水平（含1.5σ漂移）", f"{cap['sigma_level']:.2f}")
                self.rows.add("预期不良率", f"{cap['ppm']:.1f} PPM")

        # ---- 判定区 ----
        warns = list(res.get("tips") or [])
        if tgt:
            for key, name in (("wc", "极值法"), ("rss", "统计法")):
                cap = res["verdict"][key]
                if not cap["ok"]:
                    s = res[key]
                    side = "上限" if cap["over_high"] >= cap["over_low"] else "下限"
                    warns.append(
                        f"{name}判定超差：要求 {tgt['low']:.4f} ~ {tgt['high']:.4f} mm，"
                        f"实际 {s['min']:.4f} ~ {s['max']:.4f} mm，"
                        f"{side}超出 {max(cap['over_high'], cap['over_low']):.4f} mm。"
                        f"建议优先收紧「{res['contrib'][0].get('no') or res['contrib'][0].get('name')}」"
                        f"这一主导环（统计法贡献 "
                        f"{res['contrib'][0]['share_rss'] * 100:.1f}%）。")
        notes = []
        if not tgt:
            notes.append("尚未填写封闭环要求，只给出两种算法的公差带，不做合格判定。")
        notes.append(res["recommend_reason"])
        self.verify.show_items(warns, notes)

        # ---- 图表 ----
        self.d_chain.set_result(res)
        self.d_band.set_result(res)
        self.d_contrib.set_rows(res["contrib"])

        t = self.t_contrib
        t.setRowCount(0)
        for r, row in enumerate(res["contrib"]):
            t.insertRow(r)
            cell(t, r, 0, str(row.get("no") or "—"), align="c",
                 color=INC if row["xi"] >= 0 else DEC, bold=True)
            cell(t, r, 1, str(row.get("name") or ""))
            cell(t, r, 2, f"{row['T']:.4f}", align="r")
            cell(t, r, 3, f"{row['xi']:+g}", align="c",
                 color=INC if row["xi"] >= 0 else DEC)
            cell(t, r, 4, f"{row['share_wc'] * 100:.2f}%", align="r")
            cell(t, r, 5, f"{row['share_rss'] * 100:.2f}%", align="r",
                 color=ACCENT if r == 0 else None, bold=(r == 0))
        fit_table(t, 320)

        # ---- 把计算结果回填到组成环表的只读列（公差 / ξ / 贡献率）----
        self._fill_computed(res)

    # ---------------- 报告 ----------------
    def _export(self):
        res = self._res
        if res is None:
            QMessageBox.warning(self, "尚无结果", "请先完成一次有效计算。")
            return
        meta = [("项目名称", STATE.project["name"] or "—"),
                ("图号 / 编号", STATE.project["code"] or "—"),
                ("设计 / 校核", STATE.project["author"] or "—"),
                ("计算方法", "极值法 WC + 统计法 RSS（华为内部《公差分析》口径）"),
                ("σ 等级", grade_summary(res)),
                ("热膨胀修正", "启用" if res["use_thermal"] else "未启用")]
        sec = []
        sec.append(("封闭环要求", [
            ("封闭环名义值 N₀", f"{res['nominal']:.6g} mm"),
            ("目标值口径", "留空 → 取计算名义值" if res.get("target", {}).get("nominal_auto")
             else ("按绝对尺寸" if res.get("target") else "未填写")),
        ] + ([("要求范围", f"{res['target']['low']:.6g} ~ {res['target']['high']:.6g} mm"),
              ("要求偏差带", f"{res['target']['ei']:+.6f} ~ {res['target']['es']:+.6f} mm")]
             if res.get("target") else [])))
        sec.append(("组成环明细", [
            (f"{l.get('no', '—')} {l.get('name', '')}".strip(),
             f"A = {l['nominal']:g} mm　{l['es']:+.4f}/{l['ei']:+.4f}　"
             f"ξ={l['xi']:+g}　{dist_label(l['dist'])}　"
             f"k={l['k']:.2f}　e={l['e']:+.2f}　"
             f"σ等级 ±{float(l.get('sigma_grade', DEFAULT_SIGMA_GRADE)):g}")
            for l in res["links"]]))
        w, s = res["wc"], res["rss"]
        sec.append(("极值法 WC（≤3 个累积尺寸推荐）", [
            ("公差带全宽 T₀", f"{w['T']:.6f} mm"),
            ("上偏差 ES₀", f"{w['es']:+.6f} mm"),
            ("下偏差 EI₀", f"{w['ei']:+.6f} mm"),
            ("极限尺寸范围", f"{w['min']:.6g} ~ {w['max']:.6g} mm"),
        ]))
        sec.append(("统计法 RSS / 概率法（≥4 个累积尺寸推荐）", [
            ("σ 等级", grade_summary(res)),
            ("等效评估带宽", f"±{s.get('n_eff', s.get('n_sigma', DEFAULT_SIGMA_GRADE)):.4f}σ₀"
                          f"　（T_rss = √(Σ(ξᵢ·nᵢ·σᵢ)²)）"),
            ("公差带全宽 T₀", f"{s['T']:.6f} mm"),
            ("上偏差 ES₀", f"{s['es']:+.6f} mm"),
            ("下偏差 EI₀", f"{s['ei']:+.6f} mm"),
            ("标准差 σ₀", f"{s['sigma']:.6f} mm"),
            ("±3σ 范围", f"{s['dmid'] - 3 * s['sigma']:+.6f} ~ "
                       f"{s['dmid'] + 3 * s['sigma']:+.6f} mm"),
        ]))
        if res.get("target"):
            cap = res["verdict"]["rss"]
            rowsc = [("极值法判定", "合格" if res["verdict"]["wc"]["ok"] else "超差"),
                     ("统计法判定", "合格" if cap["ok"] else "超差")]
            if cap.get("cp") is not None:
                rowsc += [("Cp", f"{cap['cp']:.3f}"), ("Ppk", f"{cap['ppk']:.3f}"),
                          ("σ 水平（含1.5σ漂移）", f"{cap['sigma_level']:.2f}"),
                          ("预期合格率", f"{cap['pass_rate'] * 100:.4f}%"),
                          ("预期不良率", f"{cap['ppm']:.2f} PPM")]
            sec.append(("合格判定与制程能力", rowsc))
        sec.append(("各环贡献率（降序）", [
            (f"{c.get('no', '—')} {c.get('name', '')}".strip(),
             f"T={c['T']:.4f} mm　ξ={c['xi']:+g}　"
             f"极值法 {c['share_wc'] * 100:.2f}%　统计法 {c['share_rss'] * 100:.2f}%")
            for c in res["contrib"]]))
        warns = list(res.get("tips") or [])
        if res.get("target"):
            for key, name in (("wc", "极值法"), ("rss", "统计法")):
                if not res["verdict"][key]["ok"]:
                    warns.append(f"{name}判定超差，详见「与设计要求比对」。")
        notes = [res["recommend_reason"]]
        images = []
        for cap, wdg in (("尺寸链简图", self.d_chain),
                         ("公差带图", self.d_band),
                         ("各环贡献率图", self.d_contrib)):
            try:
                png = grab_widget_png(wdg)
                if png:
                    images.append((cap, png))
            except Exception:
                pass  # 图渲染失败不阻塞报告导出
        save_report(self, "尺寸链公差分析报告", "尺寸链公差分析",
                    meta, sec, warns, notes, images)


# =====================================================================
# 标准公差选取弹窗（填上 / 下偏差）
# =====================================================================

def _std_entries() -> list[dict]:
    """弹窗数据集。条目三选一：
    zones=[(按钮文字, 代号, 基本尺寸覆盖|None), ...] —— 按 GB/T 1800.2 换算；
    sym=±值 —— 直接对称填入；it="ITn" —— 按 ±ITn/2 对称填入。
    期望值全部来自外部权威源或行业通用口径，不使用本程序自算值当依据。
    """
    E: list[dict] = []
    A = E.append
    # ---- 常用配合（GB/T 1800.1 / 1800.2，内置代号可直接换算）----
    for nm, hz, sz, tip in (
            ("间隙 · 滑动（轻负荷转动）", "H7", "g6", "滑动轴承、轻载导轨"),
            ("间隙 · 一般转动", "H7", "f7", "泵类、常规转动配合"),
            ("间隙 · 松转（大间隙）", "H8", "d9", "低温、多尘、宽间隙场合"),
            ("过渡 · 对中可拆", "H7", "js6", "对中性好，手装/轻敲可拆"),
            ("过渡 · 定位轻压", "H7", "k6", "定位销、轴承内圈常用"),
            ("过渡 · 基轴制定位", "K7", "h6", "基轴制：销/冷拉轴定位孔"),
    ):
        A({"cat": "常用配合", "name": nm, "src": "GB/T 1800.1 / 1800.2",
           "desc": f"{tip}；公差带 {hz}/{sz}",
           "zones": [(f"孔侧 {hz}", hz, None), (f"轴侧 {sz}", sz, None)]})
    # ---- 按加工方式选 IT（经济加工精度，±IT/2 对称填入）----
    for nm, rng, g in (
            ("外圆 · 精车", "IT7~9", "IT8"), ("外圆 · 半精车", "IT9~11", "IT10"),
            ("外圆 · 粗车", "IT11~13", "IT12"), ("外圆 · 精磨", "IT6~7", "IT6"),
            ("外圆 · 粗磨", "IT8~9", "IT9"), ("外圆 · 研磨/超精", "IT5~6", "IT5"),
            ("孔 · 钻孔", "IT11~13", "IT12"), ("孔 · 扩孔", "IT10~13", "IT11"),
            ("孔 · 铰孔", "IT7~9", "IT8"), ("孔 · 精镗", "IT7~9", "IT8"),
            ("孔 · 拉孔", "IT7~9", "IT8"), ("孔 · 磨孔", "IT7~9", "IT8"),
            ("孔 · 珩磨/研磨", "IT5~6", "IT6"),
            ("平面 · 精铣/精刨", "IT7~8", "IT8"), ("平面 · 普通铣/刨", "IT9~11", "IT10"),
            ("钣金 · 普通冲裁", "IT11~13", "IT12"), ("钣金 · 精冲", "IT8~9", "IT9"),
            ("毛坯 · 铸/锻/切割（参考）", "IT14~16", "IT15"),
    ):
        A({"cat": "加工方式 → IT", "name": nm,
           "desc": f"经济精度 {rng}，按对称 ±{g}/2 填入（按本环基本尺寸计算）",
           "src": "经济加工精度（机械设计手册常用口径）", "it": g})
    # ---- 标准件 ----
    A({"cat": "标准件", "name": "滚动轴承 内圈 · 轴（内圈旋转负荷）",
       "desc": "轴公差带 k6（GB/T 275 最常用），填入轴侧",
       "src": "GB/T 275 滚动轴承配合（常用口径）",
       "zones": [("轴 k6", "k6", None)]})
    A({"cat": "标准件", "name": "滚动轴承 外圈 · 座孔（外圈固定）",
       "desc": "座孔 H7（外圈轴向固定端）", "src": "GB/T 275（常用口径）",
       "zones": [("孔 H7", "H7", None)]})
    A({"cat": "标准件", "name": "滚动轴承 外圈 · 座孔（轴向游动端）",
       "desc": "座孔 JS7（允许外圈轴向游动）", "src": "GB/T 275（常用口径）",
       "zones": [("孔 JS7", "JS7", None)]})
    A({"cat": "标准件", "name": "平键 · 毂槽宽（正常联结）",
       "desc": "GB/T 1095 正常联结：毂槽 JS9（轴槽 N9 不在本工具内置代号，请手填）",
       "src": "GB/T 1095 平键联结",
       "zones": [("槽宽 JS9", "JS9", None)]})
    A({"cat": "标准件", "name": "平键 · 槽宽（松联结）",
       "desc": "GB/T 1095 松联结：轴槽/毂槽 H9（导向平键），毂槽亦可用 D10",
       "src": "GB/T 1095 平键联结",
       "zones": [("槽宽 H9", "H9", None), ("毂槽 D10", "D10", None)]})
    A({"cat": "标准件", "name": "圆柱销 · 销孔（铰制装配）",
       "desc": "销孔一般铰孔后 H7 装配", "src": "GB/T 119.1 / 装配惯例",
       "zones": [("孔 H7", "H7", None)]})
    A({"cat": "标准件", "name": "圆柱销 · 销径（GB/T 119.1）",
       "desc": "销径公差带 h8（另有 m6 磨削销，m 不在本工具内置代号）",
       "src": "GB/T 119.1 圆柱销",
       "zones": [("销径 h8", "h8", None)]})
    # ---- 螺栓通孔（GB/T 5277-1985）----
    for spec, fine, mid, coarse in (
            ("M3", 3.2, 3.4, 3.6), ("M4", 4.3, 4.5, 4.8), ("M5", 5.3, 5.5, 5.8),
            ("M6", 6.4, 6.6, 7.0), ("M8", 8.4, 9.0, 10.0),
            ("M10", 10.5, 11.0, 12.0), ("M12", 13.0, 13.5, 14.5),
            ("M16", 17.0, 17.5, 18.5), ("M20", 21.0, 22.0, 24.0)):
        A({"cat": "螺栓通孔 GB/T 5277", "set_nominal": True,
           "name": f"{spec} 通孔（精装 ⌀{fine} / 中装 ⌀{mid} / 粗装 ⌀{coarse}）",
           "desc": "填入同时把基本尺寸改为所选通孔直径",
           "src": "GB/T 5277-1985（精 H12 / 中 H13 / 粗 H14）",
           "zones": [(f"精装 ⌀{fine} H12", "H12", fine),
                     (f"中装 ⌀{mid} H13", "H13", mid),
                     (f"粗装 ⌀{coarse} H14", "H14", coarse)]})
    # ---- PCB（行业常规制程能力值，各厂略有差异）----
    A({"cat": "PCB", "name": "金属化孔 PTH ⌀≤0.8", "sym": 0.08,
       "desc": "镀覆通孔成品孔径 ±0.08（插装/导通孔常规能力）",
       "src": "IPC 体系 · 板厂常规制程能力"})
    A({"cat": "PCB", "name": "金属化孔 PTH ⌀0.8~6.3", "sym": 0.15,
       "desc": "镀覆通孔成品孔径 ±0.15", "src": "IPC 体系 · 常规制程能力"})
    A({"cat": "PCB", "name": "非金属化孔 NPTH ⌀≤6.3", "sym": 0.05,
       "desc": "非镀覆通孔 ±0.05（定位/安装孔）", "src": "IPC 体系 · 常规制程能力"})
    A({"cat": "PCB", "name": "压接孔（压接连接器 / 铆装件）", "sym": 0.05,
       "desc": "压接孔孔径公差收紧到 ±0.05，保证压接保持力",
       "src": "IPC 体系 · 行业常用口径"})
    A({"cat": "PCB", "name": "钻孔孔位（位置度，参考）", "sym": 0.075,
       "desc": "孔位公差 ±0.075（数控钻常规）；用作跨板装配尺寸环时参考",
       "src": "IPC 体系 · 行业常用口径"})
    # ---- 连接器（内置代号组合表达）----
    A({"cat": "连接器", "name": "接触件（插针/插孔）直径 · 精密", "it": "IT6",
       "desc": "精密/高频连接器接触件常用 IT5~IT6，按对称 ±IT6/2 填入",
       "src": "行业常用口径（精密连接器接触件等级）"})
    A({"cat": "连接器", "name": "接触件（插针/插孔）直径 · 普通", "it": "IT7",
       "desc": "一般工业连接器接触件常用 IT7~IT8，按对称 ±IT7/2 填入",
       "src": "行业常用口径（工业连接器接触件等级）"})
    A({"cat": "连接器", "name": "基座引脚孔（压接插针）", "zones": [("孔 H7", "H7", None)],
       "desc": "插针压入基座引脚孔，孔按基孔制 H7", "src": "GB/T 1800.1（基孔制）"})
    A({"cat": "连接器", "name": "插头/插座外壳 · 插拔导向（间隙）",
       "zones": [("孔 H7", "H7", None), ("轴 f6", "f6", None)],
       "desc": "导向外径 f6 对孔 H7，保证插拔顺畅且晃动量受控",
       "src": "GB/T 1800.1 / 1800.2"})
    A({"cat": "连接器", "name": "PCB 定位销 · 定位孔（基轴制）",
       "zones": [("孔 J7", "J7", None), ("轴 h6", "h6", None)],
       "desc": "定位销 h6（冷拉/车削），PCB/基座定位孔 J7，过渡对中",
       "src": "GB/T 1800.1 / 1800.2"})
    return E

_STD_CATS = list(dict.fromkeys(e["cat"] for e in _std_entries()))


class StdDevDialog(QDialog):
    """按分类选取标准公差/常用值，一键填入选中组成环的上、下偏差。"""

    def __init__(self, page: "TolPage", row: int):
        super().__init__(page)
        self.page = page
        self.row = row
        self.setWindowTitle("标准公差选取 → 填入选中环")
        self.resize(780, 540)
        lay = QVBoxLayout(self)
        lay.setSpacing(8)

        l = STATE.links[row]
        head = QHBoxLayout()
        lab = QLabel(f"目标环：{l.get('no', '')} {l.get('name', '')}".strip())
        lab.setObjectName("FieldHint")
        head.addWidget(lab)
        head.addStretch(1)
        self.in_nom = NumberInput("基本尺寸", "mm", "按此尺寸换算代号/IT")
        self.in_nom.set_value(l.get("nominal", 0.0))
        head.addWidget(self.in_nom)
        lay.addLayout(head)

        catrow = QHBoxLayout()
        catrow.addWidget(QLabel("分类："))
        self.cb_cat = QComboBox()
        self.cb_cat.addItems(_STD_CATS)
        catrow.addWidget(self.cb_cat, 1)
        lay.addLayout(catrow)

        self.t = QTableWidget(0, 3)
        self.t.setHorizontalHeaderLabels(["名称", "说明 / 数值", "依据"])
        self.t.verticalHeader().setVisible(False)
        self.t.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows)
        self.t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        hh = self.t.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        hh.setStretchLastSection(True)
        for i, wd in enumerate([230, 330, 180]):
            self.t.setColumnWidth(i, wd)
        self.t.cellClicked.connect(lambda _r, _c: self._refresh_btns())
        lay.addWidget(self.t, 1)

        self.lab_prev = QLabel("选中条目后点下方按钮填入。")
        self.lab_prev.setObjectName("FieldHint")
        self.lab_prev.setWordWrap(True)
        lay.addWidget(self.lab_prev)

        self.btnrow = QHBoxLayout()
        lay.addLayout(self.btnrow)

        foot = QHBoxLayout()
        self.lab_status = QLabel("")
        self.lab_status.setObjectName("FieldHint")
        foot.addWidget(self.lab_status)
        foot.addStretch(1)
        b_close = QPushButton("关闭")
        b_close.clicked.connect(self.accept)
        foot.addWidget(b_close)
        lay.addLayout(foot)

        self.cb_cat.currentIndexChanged.connect(lambda _i: self._fill_table())
        self._fill_table()

    # ---------------- 内部 ----------------
    def _entries(self) -> list[dict]:
        cat = self.cb_cat.currentText()
        return [e for e in _std_entries() if e["cat"] == cat]

    def _fill_table(self):
        t = self.t
        t.setRowCount(0)
        for e in self._entries():
            r = t.rowCount()
            t.insertRow(r)
            for c, txt in enumerate((e["name"], e["desc"], e["src"])):
                it = QTableWidgetItem(txt)
                it.setToolTip(e["desc"])
                t.setItem(r, c, it)
        fit_table(t, cap=300)

    def _nom(self) -> float:
        v = self.in_nom.value()
        return 0.0 if v is None else float(v)

    def _calc(self, e: dict, idx: int) -> tuple[float, float, str]:
        """第 idx 个填入动作 → (上偏差, 下偏差, 展示文字)。抛 DesignError。"""
        nom = self._nom()
        if "zones" in e:
            txt, code, nomv = e["zones"][idx]
            n = nom if nomv is None else float(nomv)
            z = parse_zone(code, n)
            return z["es"], z["ei"], f"⌀{n:g} {code} → +{z['es']:.4f} / {z['ei']:.4f}"
        if "sym" in e:
            s = float(e["sym"])
            return s, -s, f"±{s:g}"
        T = it_value(nom, e["it"])
        return T / 2.0, -T / 2.0, f"⌀{nom:g} {e['it']} → ±{T / 2.0:.4f}"

    def _refresh_btns(self):
        r = self.t.currentRow()
        while self.btnrow.count():
            w = self.btnrow.takeAt(0)
            if w.widget() is not None:
                w.widget().deleteLater()
        if r < 0 or r >= len(self._entries()):
            self.lab_prev.setText("选中条目后点下方按钮填入。")
            return
        e = self._entries()[r]
        acts = ([{"txt": z[0], "idx": i} for i, z in enumerate(e.get("zones", []))]
                or ([{"txt": f"填入 ±{e['sym']:g}", "idx": 0}] if "sym" in e
                    else [{"txt": f"填入 ±{e['it']}/2", "idx": 0}]))
        prevs = []
        for a in acts:
            b = QPushButton(a["txt"])
            b.setObjectName("Mini")
            try:
                es, ei, txt = self._calc(e, a["idx"])
                b.setToolTip(txt)
                prevs.append(f"{a['txt']}：{txt}")
                b.clicked.connect(lambda _=False, ee=e, ii=a["idx"],
                                  p=(es, ei): self._apply(ee, ii, p))
            except (DesignError, ValueError) as ex:
                b.setEnabled(False)
                b.setToolTip(str(ex))
                prevs.append(f"{a['txt']}：无法换算（{ex}）")
            self.btnrow.addWidget(b)
        self.btnrow.addStretch(1)
        self.lab_prev.setText("；".join(prevs))

    def _apply(self, e: dict, idx: int, band: tuple[float, float]):
        r = self.row
        if not (0 <= r < len(STATE.links)):
            return
        l = STATE.links[r]
        l["es"], l["ei"] = float(band[0]), float(band[1])
        if e.get("set_nominal") and "zones" in e:
            nomv = e["zones"][idx][2]
            if nomv is not None:
                l["nominal"] = float(nomv)
        self.page._fill()
        self.page.table.selectRow(r)
        self.page.recalc()
        self.in_nom.set_value(l["nominal"])
        self.lab_status.setText(
            f"已填入 {l.get('no', '')}：上 {l['es']:+.4f} / 下 {l['ei']:+.4f}"
            f"（基本尺寸 {l['nominal']:g}）")


# =====================================================================
# 页 2 · 公差仿真（蒙特卡洛）
# =====================================================================

class SimPage(QWidget):
    """公差仿真：用蒙特卡洛给出封闭环实际分布、合格率与制程能力。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._mc = None
        self._build()

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        outer.addWidget(sa)
        body = QWidget()
        sa.setWidget(body)
        lay = QVBoxLayout(body)
        lay.setContentsMargins(12, 10, 12, 14)
        lay.setSpacing(10)

        pcard = Card("仿真参数", hint="分布形状按各环「分布状态」抽样")
        row = QHBoxLayout()
        row.setSpacing(12)
        self.in_n = NumberInput("仿真次数", "次", "100000", label_w=88,
                                tip="建议 ≥ 100000 次；上限 2000000。\n"
                                    "次数越多，合格率与 Ppk 的重复性越好。")
        self.in_n.set_value(100000)
        self.in_seed = NumberInput("随机种子", "", "20260918", label_w=88,
                                   tip="固定种子可复现同一组抽样结果。")
        self.in_seed.set_value(20260918)
        row.addWidget(self.in_n, 1)
        row.addWidget(self.in_seed, 1)
        b = QPushButton("开始仿真")
        b.setObjectName("Primary")
        b.clicked.connect(self.run)
        row.addWidget(b)
        row.addStretch(1)
        pcard.add_layout(row)
        self.lab_state = QLabel("")
        self.lab_state.setObjectName("FieldHint")
        self.lab_state.setWordWrap(True)
        pcard.add(self.lab_state)
        lay.addWidget(pcard)

        mcard = Card("仿真结果")
        mrow = QHBoxLayout()
        mrow.setSpacing(8)
        self.m_pass = MetricCard("合格率", "%")
        self.m_ppm = MetricCard("不良率", "PPM")
        self.m_cp = MetricCard("Cp", "")
        self.m_ppk = MetricCard("Ppk", "")
        self.m_sig = MetricCard("σ 水平", "含1.5σ漂移")
        for m in (self.m_pass, self.m_ppm, self.m_cp, self.m_ppk, self.m_sig):
            mrow.addWidget(m, 1)
        mcard.add_layout(mrow)
        self.d_hist = HistogramDiagram()
        self.d_hist.setMinimumHeight(280)
        mcard.add(self.d_hist)
        lay.addWidget(mcard)

        scard = Card("各环灵敏度（方差占比）")
        self.t_sens = make_table(
            ["环", "名称", "σᵢ\nmm", "方差占比", "对封闭环 σ 的贡献"],
            [64, 150, 100, 100, 220])
        self.t_sens.setMinimumHeight(150)
        scard.add(self.t_sens)
        lay.addWidget(scard)

        lay.addStretch(1)

    def refresh(self):
        """从共享状态同步（切页时调用）。"""
        n = len(STATE.active())
        self.lab_state.setText(
            f"当前尺寸链：{n} 个组成环，封闭环名义值 "
            f"{STATE.result()['nominal']:.6g} mm。"
            if n else "当前尺寸链没有启用的组成环。")
        self.run()

    def run(self):
        try:
            n = int(self.in_n.value_or(100000))
            seed = int(self.in_seed.value_or(20260918)) if self.in_seed.value() is not None else None
            mc = monte_carlo(STATE.links, n=n, seed=seed,
                             target=STATE.target_or_none(),
                             use_thermal=STATE.use_thermal)
        except (DesignError, ValueError) as e:
            QMessageBox.warning(self, "无法仿真", str(e))
            return
        self._mc = mc
        self._render(mc)

    def _render(self, mc):
        rate = mc.get("pass_rate")
        if rate is None:
            self.m_pass.set("—", "na", "未填封闭环要求")
            self.m_ppm.set("—", "na")
            self.m_cp.set("—", "na")
            self.m_ppk.set("—", "na")
            self.m_sig.set("—", "na")
        else:
            st = "ok" if rate >= 0.9999 else ("warn" if rate >= 0.99 else "bad")
            self.m_pass.set(f"{rate * 100:.4f}", st,
                            f"{mc['pass_count']:,} / {mc['n']:,} 次")
            ppm = mc["ppm"]
            self.m_ppm.set(f"{ppm:.2f}", "ok" if ppm < 1 else
                           ("warn" if ppm < 1000 else "bad"), "百万分之")
            if mc.get("cp") is not None:
                pk = mc["ppk"]
                self.m_cp.set(f"{mc['cp']:.3f}", "ok" if mc["cp"] >= 1.33 else "warn")
                self.m_ppk.set(f"{pk:.3f}",
                               "ok" if pk >= 1.33 else ("warn" if pk >= 1.0 else "bad"),
                               "一般要求 ≥ 1.33")
                sl = mc["sigma_level"]
                self.m_sig.set(f"{sl:.2f}σ",
                               "ok" if sl >= 4.5 else ("warn" if sl >= 3 else "bad"),
                               f"Z = {mc['z']:.2f}")
        self.d_hist.set_result(mc)

        t = self.t_sens
        t.setRowCount(0)
        for r, s in enumerate(mc["sens"]):
            t.insertRow(r)
            cell(t, r, 0, str(s.get("no") or "—"), align="c",
                 color=ACCENT if r == 0 else None, bold=(r == 0))
            cell(t, r, 1, str(s.get("name") or ""))
            cell(t, r, 2, f"{s['sigma']:.6f}", align="r")
            cell(t, r, 3, f"{s['share'] * 100:.2f}%", align="r",
                 color=ACCENT if r == 0 else None, bold=(r == 0))
            bar = "█" * max(1, int(round(s["share"] * 40)))
            cell(t, r, 4, bar, color=ACCENT if r == 0 else TEXT_DIM)
        fit_table(t, 460)


# =====================================================================
# 页 3 · 公差分配（反算）
# =====================================================================

class AllocPage(QWidget):
    """公差分配：给定封闭环公差，按三种规则反算各组成环公差。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._res = None
        self._build()

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        outer.addWidget(sa)
        body = QWidget()
        sa.setWidget(body)
        lay = QVBoxLayout(body)
        lay.setContentsMargins(12, 10, 12, 14)
        lay.setSpacing(10)

        icard = Card("分配条件")
        row = QHBoxLayout()
        row.setSpacing(12)
        self.in_tol = NumberInput("封闭环公差 T₀", "mm", "如 0.25", label_w=104)
        self.in_tol.set_value(0.25)
        self.in_method = ComboInput("分配方法", list(ALLOC_METHODS.values()),
                                    label_w=104)
        self.in_rule = ComboInput("分配口径", ["统计法 RSS（推荐）", "极值法 WC"],
                                  label_w=104)
        self.in_keep = CheckInput("中间偏差", "保留各环原有中间偏差", label_w=104,
                                  tip="勾选：只改公差带宽度，公差带位置不动。\n"
                                      "取消：各环按对称公差 ±T/2 重新定位。")
        self.in_keep.set_checked(True)
        row.addWidget(self.in_tol, 2)
        row.addWidget(self.in_method, 3)
        row.addWidget(self.in_rule, 3)
        row.addWidget(self.in_keep, 3)
        row.addStretch(1)
        icard.add_layout(row)
        b = QPushButton("执行分配")
        b.setObjectName("Primary")
        b.clicked.connect(self.run)
        row2 = QHBoxLayout()
        row2.addWidget(b)
        b2 = QPushButton("把结果应用到「尺寸链计算」页")
        b2.setObjectName("Mini")
        b2.clicked.connect(self._apply)
        row2.addWidget(b2)
        row2.addStretch(1)
        icard.add_layout(row2)
        self.lab_info = QLabel("")
        self.lab_info.setObjectName("FieldHint")
        self.lab_info.setWordWrap(True)
        icard.add(self.lab_info)
        lay.addWidget(icard)

        mcard = Card("分配结果")
        mrow = QHBoxLayout()
        mrow.setSpacing(8)
        self.m_req = MetricCard("目标公差 T₀", "mm")
        self.m_wc = MetricCard("复算 极值法", "mm")
        self.m_rss = MetricCard("复算 统计法", "mm")
        self.m_dev = MetricCard("与目标差", "mm")
        for m in (self.m_req, self.m_wc, self.m_rss, self.m_dev):
            mrow.addWidget(m, 1)
        mcard.add_layout(mrow)
        self.t_res = make_table(
            ["环", "名称", "原公差\nmm", "推荐公差\nmm", "推荐偏差\nmm",
             "标准等级", "分配依据"],
            [58, 110, 84, 92, 156, 78, 300])
        self.t_res.setMinimumHeight(180)
        mcard.add(self.t_res)
        lay.addWidget(mcard)
        lay.addStretch(1)

    def refresh(self):
        n = len(STATE.active())
        self.lab_info.setText(
            f"当前尺寸链共 {n} 个启用的组成环；"
            f"按当前规则分配后会自动用两种算法复算，"
            f"并与目标 T₀ 比较。"
            if n else "当前尺寸链没有启用的组成环。")
        # 首次切进来就先算一遍：满屏「—」会让人以为程序是坏的。
        # 这里刻意走静默分支，参数不全时直接跳过，不弹框打断切页动作。
        if self._res is None and n:
            try:
                res = self._compute()
            except (DesignError, ValueError):
                return
            self._res = res
            self._render(res)

    def _compute(self):
        tol = self.in_tol.value()
        if tol is None:
            raise DesignError("请填写封闭环公差 T₀")
        keys = list(ALLOC_METHODS)
        method = keys[list(ALLOC_METHODS.values()).index(self.in_method.current())]
        rule = "rss" if self.in_rule.current().startswith("统计法") else "wc"
        return allocate(STATE.links, tol, method=method, rule=rule,
                        keep_dmid=self.in_keep.is_checked(),
                        use_thermal=STATE.use_thermal)

    def run(self):
        try:
            res = self._compute()
        except (DesignError, ValueError) as e:
            QMessageBox.warning(self, "无法分配", str(e))
            return
        self._res = res
        self._render(res)

    def _render(self, res):
        self.m_req.set(f"{res['T_required']:.4f}", "ok", f"口径：{res['rule'].upper()}")
        self.m_wc.set(f"{res['T_wc']:.4f}", "ok")
        self.m_rss.set(f"{res['T_rss']:.4f}", "ok")
        d = res["deviation"]
        if d is None:
            self.m_dev.set("—", "na")
        else:
            self.m_dev.set(f"{d:+.4f}",
                           "ok" if abs(d) <= res["T_required"] * 0.05 else "warn",
                           f"{d / res['T_required'] * 100:+.1f}%")
        self.lab_info.setText(res.get("tip") or "分配后复算与目标一致。")

        t = self.t_res
        t.setRowCount(0)
        for r, row in enumerate(res["rows"]):
            l = row["link"]
            t.insertRow(r)
            cell(t, r, 0, str(l.get("no") or "—"), align="c",
                 color=INC if int(l.get("sign", 1)) >= 0 else DEC, bold=True)
            cell(t, r, 1, str(l.get("name") or ""))
            cell(t, r, 2, f"{l['es'] - l['ei']:.4f}", align="r")
            cell(t, r, 3, f"{row['T']:.4f}", align="r", color=ACCENT, bold=True)
            cell(t, r, 4, f"{row['es']:+.4f} / {row['ei']:+.4f}", align="r")
            cell(t, r, 5, row.get("grade") or "—", align="c")
            cell(t, r, 6, row.get("basis", ""))
        fit_table(t, 340)

    def _apply(self):
        if not self._res:
            QMessageBox.information(self, "尚无结果", "请先执行一次分配。")
            return
        STATE.links = self._res["new_links"]
        QMessageBox.information(
            self, "已应用",
            "各组成环的公差已更新。切到「尺寸链计算」页可看到新的结果。")
        # 通知主窗口刷新其它页
        w = self.window()
        if hasattr(w, "refresh_pages"):
            w.refresh_pages()


# =====================================================================
# 页 4 · 标准公差库
# =====================================================================

class StdPage(QWidget):
    """标准公差库：GB/T 1800.1 的 IT 等级表、公差带代号解析、σ 水平对照。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build()

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        outer.addWidget(sa)
        body = QWidget()
        sa.setWidget(body)
        lay = QVBoxLayout(body)
        lay.setContentsMargins(12, 10, 12, 14)
        lay.setSpacing(10)

        q = Card("查询", hint="基本尺寸 + 公差带代号 → 上/下偏差")
        row = QHBoxLayout()
        row.setSpacing(12)
        self.q_nom = NumberInput("基本尺寸", "mm", "如 50", label_w=88)
        self.q_nom.set_value(50)
        self.q_code = ComboInput(
            "公差带代号",
            ["H7", "h6", "js6", "JS7", "f6", "F7", "g6", "G7", "e8", "E8",
             "d9", "D9", "k6", "K7"], label_w=104, editable=True)
        row.addWidget(self.q_nom, 2)
        row.addWidget(self.q_code, 2)
        b = QPushButton("查询")
        b.setObjectName("Primary")
        b.clicked.connect(self.query)
        row.addWidget(b)
        row.addStretch(1)
        q.add_layout(row)
        self.lab_q = QLabel("")
        self.lab_q.setObjectName("FieldHint")
        self.lab_q.setWordWrap(True)
        q.add(self.lab_q)
        lay.addWidget(q)

        tcard = Card("IT 标准公差等级表", hint="单位 μm，按 GB/T 1800.1-2020")
        self.t_it = make_table(["尺寸段 mm"] + list(IT_GRADES),
                               [104] + [56] * len(IT_GRADES))
        self.t_it.setMinimumHeight(300)
        tcard.add(self.t_it)
        lay.addWidget(tcard)

        scard = Card("σ 水平 / PPM 对照", hint="含 1.5σ 长期漂移，与华为内部胶片同口径")
        self.t_sig = make_table(["σ 水平", "PPM", "评价"], [110, 150, 300])
        self.t_sig.setMinimumHeight(200)
        scard.add(self.t_sig)
        lay.addWidget(scard)

        hcard = Card("内置的基本偏差代号")
        txt = QLabel(
            f"轴（小写）：{' '.join(SHAFT_DEV)}\n"
            f"孔（大写）：{' '.join(HOLE_DEV)}\n\n"
            "未内置：a b c（大间隙）、j m n p r s t u v x y z za zb zc"
            "（手册取值含分段修正量 Δ，本工具不提供以免给出近似值）。\n"
            "这些代号请在组成环表里直接填写上/下偏差。")
        txt.setWordWrap(True)
        txt.setObjectName("NoteText")
        hcard.add(txt)
        lay.addWidget(hcard)

        self._fill_it()
        self._fill_sigma()
        self.query()

    def _fill_it(self):
        t = self.t_it
        t.setRowCount(0)
        for r, (lo, hi) in enumerate(
                [(0, 3), (3, 6), (6, 10), (10, 18), (18, 30), (30, 50), (50, 80),
                 (80, 120), (120, 180), (180, 250), (250, 315), (315, 400),
                 (400, 500)]):
            t.insertRow(r)
            cell(t, r, 0, f"{lo:g} ~ {hi:g}", align="c", bold=True)
            probe = hi if lo == 0 else (lo + hi) / 2.0
            for c, g in enumerate(IT_GRADES, start=1):
                try:
                    v = it_value(probe, g) * 1000.0
                    s = f"{v:g}"
                except DesignError:
                    s = "—"
                cell(t, r, c, s, align="r",
                     color=ACCENT if g in ("IT6", "IT7") else None)
        # 13 个尺寸段一次全显示，省得参考表里再套一层内部滚动条
        fit_table(t, 520)

    def _fill_sigma(self):
        t = self.t_sig
        t.setRowCount(0)
        for r, (lv, ppm, judge) in enumerate(sigma_level_table(1, 6)):
            t.insertRow(r)
            cell(t, r, 0, lv, align="c", bold=True,
                 color=OK if lv in ("5σ", "6σ") else None)
            cell(t, r, 1, f"{ppm:,.1f}", align="r")
            cell(t, r, 2, judge)
        fit_table(t, 400)

    def query(self):
        try:
            nom = self.q_nom.value()
            if nom is None:
                raise DesignError("请填写基本尺寸")
            code = self.q_code.current().strip()
            if not code:
                raise DesignError("请填写公差带代号")
            z = parse_zone(code, nom)
        except (DesignError, ValueError) as e:
            self.lab_q.setText(f"⚠ {e}")
            return
        seg = f"{it_value(nom, z['grade']) * 1000:.0f} μm"
        self.lab_q.setText(
            f"φ{nom:g} {z['text']}：上偏差 {z['es'] * 1000:+.1f} μm"
            f"（{z['es']:+.4f} mm），下偏差 {z['ei'] * 1000:+.1f} μm"
            f"（{z['ei']:+.4f} mm），公差 T = {z['T'] * 1000:.0f} μm"
            f"（{z['T']:.4f} mm）；标准公差因子 i = "
            f"{tolerance_factor(nom):.3f} μm，等级值 {seg}。")


# =====================================================================
# 页 5 · 使用说明
# =====================================================================

HELP_HTML = """
<h2>这个工具是干什么的</h2>
<p>按<b>尺寸链（公差累积）</b>做两件事：<b>正算</b>——已知各组成环公差，求封闭环的公差带、
合格率与制程能力；<b>反算</b>——已知封闭环要求，把公差分配到各组成环。</p>
<p>算法口径对齐<b>华为研发内部《公差分析》方法</b>：以极值法（WC）与统计法（RSS）
两种方法并重，并用 Cp / Ppk、σ 水平、PPM 评价批量生产的合格率。</p>

<h2>为什么「≥4 个累积尺寸」要改用统计法</h2>
<p>极值法假设<b>所有环同时取到各自的极限</b>，这在批量生产中概率极低。
华为内部胶片给了一个很有说服力的例子：</p>
<table>
<tr><td class="k">5 个 ±0.05 的环，极值法 WC</td><td class="v">±0.25</td></tr>
<tr><td class="k">5 个 ±0.05 的环，统计法 RSS</td><td class="v">±0.11</td></tr>
<tr><td class="k">出现「全部取到极限」的概率</td><td class="v">约 0.001 PPM</td></tr>
<tr><td class="k">若要求累积 ±0.25，统计法下每环可放宽到</td><td class="v">±0.1</td></tr>
</table>
<p>所以内部口径是：<b>≤3 个累积尺寸用极值法，≥4 个用统计法</b>。
本工具会自动按组成环个数给出建议口径（结果卡上的「← 建议口径」）。</p>
<p>但要注意：<b>极值法并非没用</b>。安全件、单件小批、装配后不可返修的场合，
仍然应当用极值法保证 100% 互换。</p>

<h2>计算方法</h2>
<p><b>① 封闭环基本尺寸</b>：N₀ = Σ ξᵢ·Aᵢ，ξ 为传递系数（增环 +1 / 减环 −1；
斜面、投影等非平行环可在 ξ 下拉里显式指定 ±0.866 / ±0.707 / ±0.577 / ±0.5）。</p>
<p><b>② 极值法 WC</b>：T₀ = Σ Tᵢ，
ES₀ = Σ ξᵢΔᵢ + T₀/2，EI₀ = Σ ξᵢΔᵢ − T₀/2，其中 Δᵢ 为各环中间偏差。</p>
<p><b>③ 统计法 RSS / 概率法</b>：σᵢ = kᵢ·Tᵢ/6，σ₀ = √(Σ ξᵢ²σᵢ²)。
每环的 <b>σ 等级 nᵢ</b>（表格「σ 等级」列，默认全环 ±3σ）决定该环的评估带宽 nᵢ·σᵢ，
合成公差带 T₀ = <b>√(Σ (ξᵢ·nᵢ·σᵢ)²)</b>——只有全环档位相同时，它才等于通常写的 n·σ₀。
默认 ±3σ 意味着 Tᵢ = 6σᵢ，是 GB/T 5847 与华为胶片的标准正态口径，日常不用去动它；
某环改成 ±4σ / ±5σ / ±6σ 表示该环的公差按更保守的工艺数据解读，在合成里占的带宽更大。
σ₀ 与各环档位无关，Cp / Ppk 的定义始终是 6σ 口径。</p>
<p><b>④ 中间偏差</b>：Δ₀ = Σ ξᵢ·(Δᵢ + eᵢ·Tᵢ/2)，其中 eᵢ 为相对不对称系数。</p>
<p><b>⑤ 制程能力</b>：Cp = (USL−LSL)/(6σ₀)，
Ppk = min(USL−μ₀, μ₀−LSL)/(3σ₀)，σ 水平 = 3·Ppk + 1.5。</p>
<p class="dim">其中 ξ 为传递系数、T 为公差、Δ 为中间偏差、k 为相对分布系数、e 为相对不对称系数。
k 的定义是 σ = k·T/6，因此正态分布 k = 1（即 T = 6σ）。</p>

<h2>「σ 水平 + 1.5」是怎么回事</h2>
<p>长期生产中制程中心会缓慢漂移，业界惯例是留 <b>1.5σ</b> 的漂移量，
所以「6σ 水平」对应的不良率才是众所周知的 <b>3.4 PPM</b>，而不是正态分布理论上的 0.002 PPM。
本工具的 σ 水平与华为胶片里的 PPM 对照表完全一致（2σ=308537、3σ=66807、4σ=6210、5σ=233、6σ=3.4）。</p>

<h2>三步上手</h2>
<ol>
<li><b>尺寸链计算</b>页：填各组成环的基本尺寸与上下偏差，指定增环 / 减环；
在「封闭环要求」里填上允许的偏差带（例如上偏差 0.25、下偏差 −0.25）。
<b>目标值留空</b>表示按算出的封闭环名义值取偏差带——这是最常用的提法。</li>
<li><b>不用手查表</b>：点工具条上的<b>「标准选取…」</b>，弹窗里按分类直接选——
常用配合（H7/g6 等）、按加工方式选 IT（车/铣/磨/钻/冲…）、标准件（轴承/键/销/
GB/T 5277 螺栓通孔）、PCB 孔、连接器接触件——选中后一键把上、下偏差填入选中环。</li>
<li><b>非平行环</b>：斜面、投影方向的环把「ξ」下拉从「自动」改成显式系数
（cos30°=0.866、cos45°=0.707、tan30°≈0.577、cos60°=0.5，含正负）。</li>
<li><b>σ 等级</b>：默认全环 ±3σ（T = 6σ 的标准正态口径），一般不用改。
只有当某个零件是按更保守的 ±4σ / ±5σ / ±6σ 数据提交时，
才在对应行的「σ 等级」列单独上调——它会在统计法合成里占更大带宽。
想整体切档就用结果卡的「统一 σ 等级」，一键把全环设成同一档。</li>
<li>看结果卡的<b>极值法 / 统计法</b>两个数，以及 Ppk 与合格率是否达标。
「各环贡献率排序」里排第一的就是<b>主导环</b>，优化先动它。</li>
<li><b>公差分配</b>页：填封闭环公差 T₀，选分配方法，得到各环推荐公差与 IT 等级，
可一键应用到尺寸链页复算。</li>
</ol>

<h2>几个容易踩的坑</h2>
<table>
<tr><td class="k">目标值不要填 0</td><td class="v">会按绝对尺寸比对而判超差</td></tr>
<tr><td class="k">公差带 T 与 ± 值</td><td class="v">T 是全宽，± 是半带，T = 2×±</td></tr>
<tr><td class="k">等公差等级法</td><td class="v">就近归入标准 IT 等级，累积值与目标必有差额</td></tr>
<tr><td class="k">自动判增减环</td><td class="v">需要先填封闭环目标值，否则无从反解</td></tr>
<tr><td class="k">分布状态</td><td class="v">极值法不受影响，只影响概率法与仿真</td></tr>
<tr><td class="k">标准选取</td><td class="v">弹窗里的配合 / IT / 通孔值按选中环的基本尺寸换算；
PCB 与连接器一栏是行业常规能力值，各家厂会有差异，重要场合以你的供应商实测为准</td></tr>
<tr><td class="k">显式 ξ 与增减环</td><td class="v">切增环/减环会把 ξ 清回自动 ±1；
「自动判增减环」也会清空全部显式 ξ</td></tr>
<tr><td class="k">σ 等级</td><td class="v">逐环可选，默认全环 ±3σ（= T 为 6σ 的标准正态口径）。
结果卡的「统一 σ 等级」是一键把全环设成同一档，设完仍可逐行微调；
改它只影响统计法合成带宽与超差判定，极值法、σ₀、Cp/Ppk 都不变</td></tr>
<tr><td class="k">导出报告</td><td class="v">HTML 版内嵌尺寸链简图、公差带图、贡献率图三张图，
单文件即可转发查看；TXT 版为纯文字（图形省略）。鼠标悬停表头可看各列说明</td></tr>
<tr><td class="k">热膨胀</td><td class="v">勾选后按 20 ℃ 基准修正，各环 α 需自行填对</td></tr>
</table>

<h2>本工具没有做的部分</h2>
<ul>
<li><b>形位公差环</b>：可以用「基本尺寸填 0、上偏差填公差值、下偏差填 0、分布选均匀」
的方式手工加进尺寸链，但没有做专门的形位公差建模块。</li>
<li><b>多闭环联合优化</b>：一次只算一条封闭环。多条链请分别建、分别算。</li>
<li><b>基本偏差全谱</b>：只内置了轴 d e f g h js k 与孔 D E F G H JS K。
其余代号（a b c、j m n p~zc）国标取值含分段修正量，请直接填上下偏差。</li>
<li><b>三维尺寸链</b>：只做线性链（传递系数 ±1）。角度链需自行折算成线性环后输入。</li>
</ul>

<h2>上次编辑会被记住</h2>
<p>组成环、封闭环要求、工程信息、热膨胀开关、σ 等级、仿真参数、分配参数
以及当前页签，都会<b>在关窗、切页时立刻存盘</b>，另外每 60 秒兜底存一次；
下次打开自动恢复，不用每次从头填。</p>
<p>历史记录存在本机的一个状态文件里（本页底部显示完整路径）。想换台电脑带走配置，
把它拷过去即可；删掉它、或点本页的<b>「恢复出厂默认」</b>，就回到出厂的示例数据。</p>

<h2>快捷键与其它</h2>
<p><b>F1</b> 直达本页。三个数据页共享同一份尺寸链：在「尺寸链计算」页改环，
「公差仿真」「公差分配」页切过去会自动同步。报告可导出为 HTML（内嵌计算简图、
公差带图与贡献率图）或 TXT 纯文本。</p>
<p class="dim">计算结果用于方案比选与初步设计，正式投产前请以最新版标准原文、
实际加工能力（实测 Cp/Cpk）与样机验证结果复核。</p>
"""


class HelpPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        outer.addWidget(sa)
        card = Card("使用说明")
        lab = QLabel(HELP_HTML)
        lab.setWordWrap(True)
        lab.setTextFormat(Qt.TextFormat.RichText)
        lab.setStyleSheet(
            "QLabel{background:#FFFFFF;}"
            "h2{font-size:14px;}"
            "table{border-collapse:collapse;}"
            "ol,ul{margin-left:-18px;}")
        card.add(lab)

        # ---- 历史记录（上次编辑的自动恢复）管理 ----
        row = QHBoxLayout()
        row.setSpacing(8)
        self.lab_path = QLabel()
        self.lab_path.setObjectName("FieldHint")
        self.lab_path.setWordWrap(True)
        self.lab_path.setText(f"历史记录文件：{persist.state_path()}")
        row.addWidget(self.lab_path, 1)
        b_dir = QPushButton("打开所在目录")
        b_dir.setObjectName("Mini")
        b_dir.setToolTip("在资源管理器里定位状态文件（可直接删除，等同于恢复默认）")
        b_dir.clicked.connect(self._open_dir)
        b_reset = QPushButton("恢复出厂默认")
        b_reset.setObjectName("Mini")
        b_reset.setToolTip("清除历史记录，并把尺寸链恢复为出厂示例数据")
        b_reset.clicked.connect(self._reset)
        row.addWidget(b_dir)
        row.addWidget(b_reset)
        card.add_layout(row)
        sa.setWidget(card)

    def _open_dir(self):
        d = os.path.dirname(persist.state_path())
        try:
            os.makedirs(d, exist_ok=True)
        except OSError:
            pass
        QDesktopServices.openUrl(QUrl.fromLocalFile(d))

    def _reset(self):
        r = QMessageBox.question(
            self, "恢复出厂默认",
            "将清除上次编辑的历史记录，并把尺寸链恢复为出厂示例数据。\n"
            "当前编辑内容不会另存，确定继续吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if r != QMessageBox.StandardButton.Yes:
            return
        w = self.window()
        if hasattr(w, "reset_to_default"):
            w.reset_to_default()
        QMessageBox.information(self, "已恢复", "已清除历史记录并恢复默认数据。")
