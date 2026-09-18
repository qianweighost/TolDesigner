# -*- coding: utf-8 -*-
"""界面主题：浅色工程风样式表 + 配色常量。

与家族成员「O 形密封圈设计计算器」「齿轮同步带传动设计计算器」共用同一套
配色与控件样式，保证三款软件放在一起是同一副面孔。

⚠ 本文件的 stylesheet() 是从家族成员**逐字节复制**的，不要手改；
  需要新样式请往两边同步。本文件只额外追加了公差分析专用配色常量。
"""

# ---- 配色 ----
BG = "#F4F6F9"
CARD = "#FFFFFF"
BORDER = "#E3E7ED"
BORDER_STRONG = "#D6DCE5"
TEXT = "#1F2933"
TEXT_DIM = "#7A8794"
TEXT_MID = "#4A5A6A"
ACCENT = "#2F6FED"
ACCENT_DARK = "#2456C4"
OK = "#12A150"
WARN = "#E8901A"
BAD = "#E04B4B"
RUBBER = "#3A4550"
METAL = "#B9C3CE"
DIM = "#8E6BC8"
# ---- 传动专用配色 ----
BELT = "#3A4550"      # 同步带本体（深灰）
BELT_TOOTH = "#5A6674"  # 带齿
PULLEY = "#B9C3CE"    # 带轮 / 齿轮
GEAR = "#9AA8B8"      # 齿轮轮辐
HUB = "#7C8B9C"       # 轮毂
MESH = "#E8901A"      # 啮合区高亮

# ---- 尺寸链 / 公差分析专用配色 ----
INC = "#E8901A"          # 增环（传递系数 +1）
DEC = "#2F6FED"          # 减环（传递系数 -1）
CHAIN_AXIS = "#3A4550"   # 尺寸链轴线
BAND = "#5B8DEF"         # 公差带主色
BAND_SOFT = "#C6D8F8"    # 公差带浅色（填充）
BAND_WC = "#E8901A"      # 极值法结果带
BAND_RSS = "#5B8DEF"     # 统计法结果带
HIST = "#7FA8F0"         # 直方图柱
HIST_TOP = "#3F6FD1"     # 直方图超差区柱
LIMIT = "#E04B4B"        # 规格上下限
THREE_SIGMA = "#8E6BC8"  # ±3σ 线
ZERO_LINE = "#8A96A3"    # 零线

FONT_STACK = '"Microsoft YaHei UI","Microsoft YaHei","PingFang SC","Segoe UI",sans-serif'


def stylesheet() -> str:
    return f"""
* {{ font-family: {FONT_STACK}; }}
QWidget {{ color: {TEXT}; font-size: 13px; }}
QMainWindow, QWidget#Root {{ background: {BG}; }}

/* ---------- 顶部标题栏 ---------- */
QWidget#Header {{ background: {CARD}; border-bottom: 1px solid {BORDER}; }}
QLabel#Title {{ font-size: 19px; font-weight: 600; color: #16212E; }}
QLabel#Subtitle {{ font-size: 12px; color: {TEXT_DIM}; }}
QLabel#Badge {{
    background: #EAF1FE; color: {ACCENT}; border-radius: 10px;
    padding: 3px 10px; font-size: 11px; font-weight: 600;
}}

/* ---------- 页眉链接 ---------- */
QLabel#HeaderSep {{ background: {BORDER_STRONG}; }}
QPushButton#LinkBtn {{
    background: transparent; border: 1px solid transparent; border-radius: 6px;
    padding: 2px 8px; color: {TEXT_MID}; font-size: 12px;
}}
QPushButton#LinkBtn:hover {{ background: #EAF1FE; color: {ACCENT}; border-color: #D6E2FB; }}
QPushButton#LinkBtn:pressed {{ background: #DCE8FD; }}

/* ---------- 卡片 ---------- */
QFrame#Card {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 10px; }}
QLabel#CardTitle {{ font-size: 13px; font-weight: 600; color: #2B3A4A; }}
QLabel#CardHint {{ font-size: 11px; color: {TEXT_DIM}; }}
QFrame#Divider {{ background: {BORDER}; max-height: 1px; min-height: 1px; border: none; }}

/* ---------- 输入控件 ---------- */
QLabel#FieldLabel {{ color: {TEXT_MID}; font-size: 12px; }}
QLabel#FieldUnit {{ color: {TEXT_DIM}; font-size: 11px; }}
QLabel#FieldHint {{ color: {TEXT_DIM}; font-size: 11px; }}

QLineEdit, QComboBox, QDoubleSpinBox, QSpinBox {{
    background: {CARD}; border: 1px solid {BORDER_STRONG}; border-radius: 6px;
    padding: 5px 8px; min-height: 21px; selection-background-color: {ACCENT};
    selection-color: #FFFFFF;
}}
QLineEdit:hover, QComboBox:hover {{ border: 1px solid #BFC8D4; }}
QLineEdit:focus, QComboBox:focus {{ border: 1px solid {ACCENT}; }}
QLineEdit[invalid="true"] {{ border: 1px solid {BAD}; background: #FFF7F7; }}
QLineEdit:disabled, QComboBox:disabled {{ background: #F1F3F6; color: #9AA5B1; }}

QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox::down-arrow {{ image: none; border-left: 4px solid transparent;
    border-right: 4px solid transparent; border-top: 5px solid #8A96A3;
    margin-right: 8px; }}
QComboBox QAbstractItemView {{
    border: 1px solid {BORDER_STRONG}; background: {CARD}; outline: none;
    selection-background-color: #EAF1FE; selection-color: #16212E;
    padding: 4px;
}}

/* ---------- 按钮 ---------- */
QPushButton {{
    background: {CARD}; border: 1px solid {BORDER_STRONG}; border-radius: 6px;
    padding: 6px 14px; color: {TEXT_MID};
}}
QPushButton:hover {{ background: #F2F5F9; border-color: #BFC8D4; }}
QPushButton:pressed {{ background: #E8EDF4; }}
QPushButton#Primary {{
    background: {ACCENT}; border: 1px solid {ACCENT}; color: #FFFFFF; font-weight: 600;
}}
QPushButton#Primary:hover {{ background: {ACCENT_DARK}; border-color: {ACCENT_DARK}; }}
QPushButton#Ghost {{ background: transparent; border: 1px solid transparent; color: {ACCENT}; }}
QPushButton#Ghost:hover {{ background: #EAF1FE; }}

QPushButton#Seg {{
    background: {CARD}; border: 1px solid {BORDER_STRONG}; border-radius: 6px;
    padding: 7px 10px; color: {TEXT_MID};
}}
QPushButton#Seg:checked {{
    background: #EAF1FE; border: 1px solid {ACCENT}; color: {ACCENT}; font-weight: 600;
}}
QPushButton#Seg:hover {{ border-color: #A9BEDE; }}

QPushButton#Mini {{
    background: {CARD}; border: 1px solid {BORDER_STRONG}; border-radius: 6px;
    padding: 4px 9px; color: {TEXT_MID}; font-size: 12px;
}}
QPushButton#Mini:hover {{ background: #F2F5F9; border-color: #BFC8D4; color: {ACCENT}; }}

/* ---------- 页签 ---------- */
QTabWidget::pane {{ border: none; background: transparent; top: 6px; }}
QTabBar {{ background: transparent; }}
QTabBar::tab {{
    background: transparent; padding: 9px 20px; margin-right: 2px;
    border-bottom: 2px solid transparent; color: #66727F; font-size: 13px;
}}
QTabBar::tab:hover {{ color: {ACCENT}; }}
QTabBar::tab:selected {{ color: {ACCENT}; border-bottom: 2px solid {ACCENT}; font-weight: 600; }}

/* ---------- 滚动条 ---------- */
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #C9D1DB; border-radius: 5px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: #AFB9C6; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: #C9D1DB; border-radius: 5px; min-width: 30px; }}

/* ---------- 表格 ---------- */
QTableWidget, QTableView {{
    background: {CARD}; border: 1px solid {BORDER}; border-radius: 8px;
    gridline-color: #EEF1F5; outline: none; selection-background-color: #EAF1FE;
    selection-color: #16212E;
}}
QTableWidget::item {{ padding: 5px 7px; border: none; }}
QHeaderView::section {{
    background: #F7F9FC; color: {TEXT_MID}; border: none;
    border-bottom: 1px solid {BORDER}; border-right: 1px solid #EEF1F5;
    padding: 7px 7px; font-weight: 600; font-size: 12px;
}}
QTableCornerButton::section {{ background: #F7F9FC; border: none; }}

/* ---------- 结果卡片 ---------- */
QFrame#Metric {{
    background: {CARD}; border: 1px solid {BORDER}; border-radius: 9px;
}}
QLabel#MetricName {{ font-size: 11px; color: {TEXT_DIM}; }}
QLabel#MetricValue {{ font-size: 21px; font-weight: 700; }}
QLabel#MetricUnit {{ font-size: 11px; color: {TEXT_DIM}; }}
QLabel#MetricNote {{ font-size: 10px; color: #9AA5B1; }}

QLabel#RowKey {{ color: {TEXT_MID}; font-size: 12px; }}
QLabel#RowVal {{ color: #16212E; font-size: 12px; font-weight: 600; }}

/* ---------- 提示 ---------- */
QFrame#WarnItem {{ background: #FFF9F0; border: 1px solid #F6E0BE; border-radius: 6px; }}
QFrame#OkItem {{ background: #F1FBF5; border: 1px solid #C9EBD8; border-radius: 6px; }}
QLabel#WarnText {{ color: #8A5A12; font-size: 12px; }}
QLabel#OkText {{ color: #0B7A3C; font-size: 12px; }}
QLabel#NoteText {{ color: {TEXT_MID}; font-size: 12px; }}

QToolTip {{
    background: #2B3A4A; color: #FFFFFF; border: none;
    padding: 5px 8px; border-radius: 4px; font-size: 12px;
}}
"""
