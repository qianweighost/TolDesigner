# -*- coding: utf-8 -*-
"""界面各页面：尺寸链计算、公差仿真、公差分配、标准公差库、使用说明。"""

from __future__ import annotations

import datetime
import html
import math

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (QAbstractItemView, QButtonGroup, QCheckBox,
                               QComboBox, QFileDialog, QFrame, QGridLayout,
                               QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                               QMessageBox, QPushButton, QScrollArea,
                               QSizePolicy, QSplitter, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from core.tol_core import (ALLOC_METHODS, DEFAULT_DIST, DISTRIBUTIONS,
                           DIST_KEYS, HOLE_DEV, IT_A, IT_GRADES, IT_MAX_SIZE,
                           SHAFT_DEV, STD_TEMP, DesignError, allocate,
                           analyze, auto_signs, default_links, dev_for_zone,
                           dist_label, example_links, it_grade_for, it_table,
                           it_value, monte_carlo, new_link, parse_zone,
                           ppm_to_sigma_level, sigma_level_table,
                           tolerance_factor)

from .diagram import BandDiagram, ChainDiagram, ContribBar, HistogramDiagram
from .theme import (ACCENT, BAD, BORDER, CARD, DEC, INC, OK, TEXT, TEXT_DIM,
                    TEXT_MID, WARN)


# =====================================================================
# 全局共享的尺寸链状态（各页读写同一份数据，切页时同步）
# =====================================================================

class ChainState:
    """一处编辑、多处复用的尺寸链数据。"""

    def __init__(self):
        self.links: list[dict] = default_links()
        self.target = {"nominal": "", "es": 0.25, "ei": -0.25}
        self.use_thermal = False
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
        return analyze(self.links, self.target_or_none(), self.use_thermal)

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
                warnings: list[str], notes: list[str]) -> str:
    L = ["=" * 68, f"        {title}", "=" * 68]
    L.append(f"生成时间：{datetime.datetime.now():%Y-%m-%d %H:%M:%S}")
    for k, v in meta:
        L.append(f"{k}：{v}")
    for sec_title, rows in sections:
        L.append("")
        L.append(f"【{sec_title}】")
        for k, v in rows:
            L.append(f"  {k}：{v}")
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
                warnings: list[str], notes: list[str]) -> str:
    esc = html.escape

    def tbl(rows):
        return "<table>" + "".join(
            f"<tr><td class='k'>{esc(k)}</td><td class='v'>{esc(v)}</td></tr>"
            for k, v in rows) + "</table>"

    metas = "".join(f"<tr><td class='k'>{esc(k)}</td><td class='v'>{esc(v)}</td></tr>"
                    for k, v in meta)
    body = "".join(f"<h2>{i}. {esc(t)}</h2>{tbl(rows)}"
                   for i, (t, rows) in enumerate(sections, start=1))
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
 .meta td {{ font-weight:400; }}
 footer {{ margin-top:34px; padding-top:14px; border-top:1px solid #E3E7ED;
           color:#7A8794; font-size:11.5px; white-space:pre-wrap; }}
</style></head><body>
<h1>{esc(title)}</h1>
<p style="color:#7A8794;font-size:12.5px">生成时间：{datetime.datetime.now():%Y-%m-%d %H:%M:%S}</p>
<table class="meta">{metas}</table>
{body}
<h2>校核结论</h2>
<ul>{warn}</ul>
{notes_html}
<footer>{esc(DOC_FOOTER_DEFAULT)}</footer>
</body></html>"""


def save_report(parent, title: str, default_name: str, meta, sections,
                warnings, notes):
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
        content = (report_text(title, meta, sections, warnings, notes)
                   if path.lower().endswith(".txt")
                   else report_html(title, meta, sections, warnings, notes))
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
              "环型", "分布状态", "公差\nmm", "ξ", "贡献率\n(统计法)"]
_LINK_W = [58, 108, 84, 84, 84, 80, 140, 78, 40, 92]


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
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        hh.setStretchLastSection(True)
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
            cell(t, r, 0, str(l.get("no", "")), align="c")
            cell(t, r, 1, str(l.get("name", "")))
            cell(t, r, 2, f"{l['nominal']:g}", align="r")
            cell(t, r, 3, f"{l['es']:g}", align="r")
            cell(t, r, 4, f"{l['ei']:g}", align="r")
            cb = QComboBox()
            cb.addItems(["增环", "减环"])
            cb.setCurrentIndex(0 if int(l.get("sign", 1)) >= 0 else 1)
            cb.currentIndexChanged.connect(
                lambda _i, rr=r: self._set_field(rr, "sign"))
            t.setCellWidget(r, 5, cb)
            db = QComboBox()
            db.addItems([DISTRIBUTIONS[k]["label"] for k in DIST_KEYS])
            di = DIST_KEYS.index(l.get("dist", DEFAULT_DIST)) \
                if l.get("dist") in DIST_KEYS else 0
            db.setCurrentIndex(di)
            db.currentIndexChanged.connect(
                lambda _i, rr=r: self._set_field(rr, "dist"))
            t.setCellWidget(r, 6, db)
            cell(t, r, 7, "—", align="r")
            cell(t, r, 8, "", align="c")
            cell(t, r, 9, "—", align="r")
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
                no = str(STATE.links[i].get("no"))
                lc = lmap.get(no)
                hit = next((c for c in pool if str(c.get("no")) == no), None)
                if hit is not None:
                    pool.remove(hit)
                cell(t, i, 7, "—" if not lc else f"{lc['T']:.4f}", align="r")
                cell(t, i, 8, "—" if not lc else f"{lc['xi']:+d}", align="c",
                     color=None if not lc else (INC if lc["xi"] >= 0 else DEC))
                cell(t, i, 9, "—" if hit is None
                     else f"{hit['share_rss'] * 100:.2f}%", align="r")
        finally:
            t.blockSignals(False)

    def _clear_computed(self):
        t = self.table
        t.blockSignals(True)
        try:
            for i in range(t.rowCount()):
                cell(t, i, 7, "—", align="r")
                cell(t, i, 8, "", align="c")
                cell(t, i, 9, "—", align="r")
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
        w = self.table.cellWidget(r, 5 if kind == "sign" else 6)
        if isinstance(w, QComboBox):
            if kind == "sign":
                STATE.links[r]["sign"] = 1 if w.currentIndex() == 0 else -1
            else:
                STATE.links[r]["dist"] = DIST_KEYS[w.currentIndex()]
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
            nom = self.q_nom.value()
            if nom is None:
                nom = STATE.links[r]["nominal"]
            z = parse_zone(self.q_code.text(), nom)
        except (DesignError, ValueError) as e:
            QMessageBox.warning(self, "代号无效", str(e))
            return
        STATE.links[r]["es"] = z["es"]
        STATE.links[r]["ei"] = z["ei"]
        self._fill()
        self.table.selectRow(r)
        self.recalc()

    def _on_thermal(self):
        STATE.use_thermal = self.in_thermal.is_checked()
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
        self.m_rss.set(f"±{s['es']:.4f}" if s["es"] == -s["ei"] else
                       f"{s['es']:+.3f}/{s['ei']:+.3f}", "ok" if rec == "rss" else "na",
                       f"T = {s['T']:.4f} mm（√ΣTᵢ²）"
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
        self.rows.add("6σ = T（正态假设）", f"{6 * s['sigma']:.6f} mm")
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
            cell(t, r, 3, f"{row['xi']:+d}", align="c",
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
             f"ξ={l['xi']:+d}　{dist_label(l['dist'])}　"
             f"k={l['k']:.2f}　e={l['e']:+.2f}")
            for l in res["links"]]))
        w, s = res["wc"], res["rss"]
        sec.append(("极值法 WC（≤3 个累积尺寸推荐）", [
            ("公差带全宽 T₀", f"{w['T']:.6f} mm"),
            ("上偏差 ES₀", f"{w['es']:+.6f} mm"),
            ("下偏差 EI₀", f"{w['ei']:+.6f} mm"),
            ("极限尺寸范围", f"{w['min']:.6g} ~ {w['max']:.6g} mm"),
        ]))
        sec.append(("统计法 RSS / 概率法（≥4 个累积尺寸推荐）", [
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
             f"T={c['T']:.4f} mm　ξ={c['xi']:+d}　"
             f"极值法 {c['share_wc'] * 100:.2f}%　统计法 {c['share_rss'] * 100:.2f}%")
            for c in res["contrib"]]))
        warns = list(res.get("tips") or [])
        if res.get("target"):
            for key, name in (("wc", "极值法"), ("rss", "统计法")):
                if not res["verdict"][key]["ok"]:
                    warns.append(f"{name}判定超差，详见「与设计要求比对」。")
        notes = [res["recommend_reason"]]
        save_report(self, "尺寸链公差分析报告", "尺寸链公差分析",
                    meta, sec, warns, notes)


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
<p><b>① 封闭环基本尺寸</b>：N₀ = Σ ξᵢ·Aᵢ，ξ 为传递系数（增环 +1 / 减环 −1）。</p>
<p><b>② 极值法 WC</b>：T₀ = Σ Tᵢ，
ES₀ = Σ ξᵢΔᵢ + T₀/2，EI₀ = Σ ξᵢΔᵢ − T₀/2，其中 Δᵢ 为各环中间偏差。</p>
<p><b>③ 统计法 RSS / 概率法</b>：σᵢ = kᵢ·Tᵢ/6，σ₀ = √(Σ ξᵢ²σᵢ²)，T₀ = 6σ₀。</p>
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

<h2>快捷键与其它</h2>
<p><b>F1</b> 直达本页。三个数据页共享同一份尺寸链：在「尺寸链计算」页改环，
「公差仿真」「公差分配」页切过去会自动同步。报告可导出为 HTML 或 TXT。</p>
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
        sa.setWidget(card)
