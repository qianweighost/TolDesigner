# -*- coding: utf-8 -*-
"""尺寸链 / 公差分析计算内核（纯标准库，零第三方依赖）。

口径对齐华为研发内部《公差分析》方法
=====================================================================
极值法 WC   T_tot = Σ Tᵢ                        —— 适用 ≤3 个累积尺寸
统计法 RSS  T_tot = √(Σ Tᵢ²)                    —— 适用 ≥4 个累积尺寸
概率法      T_tot = √(Σ (kᵢ·Tᵢ)²)               —— RSS 的一般化，计入分布特征
中间偏差    Δ₀ = Σ ξᵢ·(Δᵢ + eᵢ·Tᵢ/2)
评价指标    Cp / Ppk、σ 水平（含 1.5σ 漂移）、PPM、合格率

符号
  ξ  传递系数     增环 +1，减环 −1
  T  公差         上偏差 − 下偏差
  Δ  中间偏差     (上偏差 + 下偏差) / 2
  k  相对分布系数 定义为 σᵢ = kᵢ·Tᵢ/6  ⇒ 正态分布 k=1（即 T=6σ）
  e  相对不对称系数 分布中心相对公差带中心的偏移率，e = 2Δμ/T

封闭环基本尺寸
  N₀ = Σ ξᵢ·Aᵢ      （Aᵢ 为组成环基本尺寸）

为什么「≥4 个累积尺寸改用统计法」
  极值法假设所有环同时取到各自的极限，概率极低：5 个 ±0.05 的环叠加，
  极值法给 ±0.25，而实际出现该极限的概率约 1e-3 PPM，过于保守；
  RSS 给 ±0.11，同样要求下每个环可放宽到 ±0.1，显著降低加工成本。
"""

from __future__ import annotations

import math
import random
import re
from statistics import NormalDist

# =====================================================================
# 分布特征
# =====================================================================

# k 取《机械设计手册》/ GB/T 5847 附录的常用值（与 σ = k·T/6 的定义口径一致）
# e 为分布中心相对公差带中心的偏移率
DISTRIBUTIONS = {
    "normal":     {"label": "正态分布",       "k": 1.00, "e":  0.00, "exact": True,
                   "note": "大量独立因素综合，绝大多数加工尺寸"},
    "triangular": {"label": "三角分布",       "k": 1.22, "e":  0.00, "exact": True,
                   "note": "两个相近正态叠加，如孔距、两工序复合尺寸"},
    "uniform":    {"label": "均匀分布",       "k": 1.73, "e":  0.00, "exact": True,
                   "note": "等概率取值，如单件小批、形位公差带内随机"},
    "rayleigh":   {"label": "瑞利分布",       "k": 2.25, "e": -0.28, "exact": False,
                   "note": "偏心、径向跳动类误差"},
    "skew_pos":   {"label": "偏态分布(偏正)", "k": 1.17, "e":  0.26, "exact": False,
                   "note": "试切法加工外圆等单侧偏向"},
    "skew_neg":   {"label": "偏态分布(偏负)", "k": 1.17, "e": -0.26, "exact": False,
                   "note": "单侧偏向的另一侧"},
}
DIST_KEYS = list(DISTRIBUTIONS)
DEFAULT_DIST = "normal"


def dist_label(key: str) -> str:
    return DISTRIBUTIONS.get(key, DISTRIBUTIONS[DEFAULT_DIST])["label"]


def dist_params(key: str) -> tuple[float, float]:
    d = DISTRIBUTIONS.get(key, DISTRIBUTIONS[DEFAULT_DIST])
    return float(d["k"]), float(d["e"])


def dist_is_exact(key: str) -> bool:
    """该分布是否可按真实形状抽样（否则蒙特卡洛按等效正态处理）。"""
    return bool(DISTRIBUTIONS.get(key, {}).get("exact", False))


# =====================================================================
# 标准公差（GB/T 1800.1-2020）
# =====================================================================

IT_GRADES = ("IT01", "IT0", "IT1", "IT2", "IT3", "IT4", "IT5", "IT6", "IT7",
             "IT8", "IT9", "IT10", "IT11", "IT12", "IT13", "IT14", "IT15",
             "IT16", "IT17", "IT18")

# 标准公差因子系数 a（IT5~IT18，T = a·i）
IT_A = {"IT5": 7, "IT6": 10, "IT7": 16, "IT8": 25, "IT9": 40, "IT10": 64,
        "IT11": 100, "IT12": 160, "IT13": 250, "IT14": 400, "IT15": 640,
        "IT16": 1000, "IT17": 1600, "IT18": 2500}

# 尺寸分段（mm，上限含），与 GB/T 1800.1 表一致
IT_RANGES = ((0.0, 3.0), (3.0, 6.0), (6.0, 10.0), (10.0, 18.0), (18.0, 30.0),
             (30.0, 50.0), (50.0, 80.0), (80.0, 120.0), (120.0, 180.0),
             (180.0, 250.0), (250.0, 315.0), (315.0, 400.0), (400.0, 500.0))

# 标准公差数值（μm），行对应 IT_RANGES，列对应 IT_GRADES
_IT_UM = {
    (0.0, 3.0):     (0.3, 0.5, 0.8, 1.2, 2, 3, 4, 6, 10, 14, 25, 40, 60, 100, 140, 250, 400, 600, 1000, 1400),
    (3.0, 6.0):     (0.4, 0.6, 1, 1.5, 2.5, 4, 5, 8, 12, 18, 30, 48, 75, 120, 180, 300, 480, 750, 1200, 1800),
    (6.0, 10.0):    (0.4, 0.6, 1, 1.5, 2.5, 4, 6, 9, 15, 22, 36, 58, 90, 150, 220, 360, 580, 900, 1500, 2200),
    (10.0, 18.0):   (0.5, 0.8, 1.2, 2, 3, 5, 8, 11, 18, 27, 43, 70, 110, 180, 270, 430, 700, 1100, 1800, 2700),
    (18.0, 30.0):   (0.6, 1, 1.5, 2.5, 4, 6, 9, 13, 21, 33, 52, 84, 130, 210, 330, 520, 840, 1300, 2100, 3300),
    (30.0, 50.0):   (0.6, 1, 1.5, 2.5, 4, 7, 11, 16, 25, 39, 62, 100, 160, 250, 390, 620, 1000, 1600, 2500, 3900),
    (50.0, 80.0):   (0.8, 1.2, 2, 3, 5, 8, 13, 19, 30, 46, 74, 120, 190, 300, 460, 740, 1200, 1900, 3000, 4600),
    (80.0, 120.0):  (1, 1.5, 2.5, 4, 6, 10, 15, 22, 35, 54, 87, 140, 220, 350, 540, 870, 1400, 2200, 3500, 5400),
    (120.0, 180.0): (1.2, 2, 3.5, 5, 8, 12, 18, 25, 40, 63, 100, 160, 250, 400, 630, 1000, 1600, 2500, 4000, 6300),
    (180.0, 250.0): (2, 3, 4.5, 7, 10, 14, 20, 29, 46, 72, 115, 185, 290, 460, 720, 1150, 1850, 2900, 4600, 7200),
    (250.0, 315.0): (2.5, 4, 6, 8, 12, 16, 23, 32, 52, 81, 130, 210, 320, 520, 810, 1300, 2100, 3200, 5200, 8100),
    (315.0, 400.0): (3, 5, 7, 9, 13, 18, 25, 36, 57, 89, 140, 230, 360, 570, 890, 1400, 2300, 3600, 5700, 8900),
    (400.0, 500.0): (4, 6, 8, 10, 15, 20, 27, 40, 63, 97, 155, 250, 400, 630, 970, 1550, 2500, 4000, 6300, 9700),
}

# >500 mm 用 I = 0.004·D + 2.1（μm），仅 IT6~IT18 有定义
_IT_RANGES_BIG = ((500.0, 630.0), (630.0, 800.0), (800.0, 1000.0),
                  (1000.0, 1250.0), (1250.0, 1600.0), (1600.0, 2000.0),
                  (2000.0, 2500.0), (2500.0, 3150.0))

IT_MAX_SIZE = 3150.0


class DesignError(ValueError):
    """输入不合法（供界面统一捕获并提示）。"""


def it_segment(nominal: float) -> tuple[float, float]:
    """返回基本尺寸所在的尺寸分段 (下限, 上限)。"""
    d = abs(float(nominal))
    for lo, hi in IT_RANGES:
        if d <= hi:
            return lo, hi
    for lo, hi in _IT_RANGES_BIG:
        if d <= hi:
            return lo, hi
    raise DesignError(f"基本尺寸 {nominal:g} mm 超出标准公差表范围（≤ {IT_MAX_SIZE:g} mm）")


def it_segment_mean(nominal: float) -> float:
    """尺寸分段的几何平均值 D = √(D₁·D₂)。"""
    lo, hi = it_segment(nominal)
    if lo <= 0.0:
        return hi            # 首段 0~3 按标准取 3
    return math.sqrt(lo * hi)


def tolerance_factor(nominal: float) -> float:
    """标准公差因子 i（μm）：
       D ≤ 500 mm → i = 0.45·∛D + 0.001·D
       D > 500 mm → I = 0.004·D + 2.1
    """
    D = it_segment_mean(nominal)
    if abs(nominal) > 500.0:
        return 0.004 * D + 2.1
    return 0.45 * D ** (1.0 / 3.0) + 0.001 * D


def it_value(nominal: float, grade: str) -> float:
    """标准公差值，单位 mm。"""
    if grade not in IT_GRADES:
        raise DesignError(f"未知公差等级：{grade}")
    d = abs(float(nominal))
    if d <= 500.0:
        lo, hi = it_segment(d)
        return _IT_UM[(lo, hi)][IT_GRADES.index(grade)] / 1000.0
    # > 500 mm：国标仅 IT6~IT18，按公式 T = a·I 计算
    if grade not in IT_A:
        raise DesignError(f"基本尺寸 > 500 mm 时 {grade} 无标准值（国标仅 IT6~IT18）")
    return IT_A[grade] * tolerance_factor(d) / 1000.0


def it_grade_for(nominal: float, tol_mm: float) -> tuple[str, float]:
    """给定基本尺寸与公差（mm），返回最接近且不小于该公差的标准等级。"""
    if tol_mm <= 0:
        raise DesignError("公差必须为正")
    best = None
    for g in IT_GRADES:
        try:
            v = it_value(nominal, g)
        except DesignError:
            continue
        if v >= tol_mm:
            best = (g, v)
            break
    if best is None:
        g = "IT18"
        return g, it_value(nominal, g)
    # 与前一档比，取更接近的
    idx = IT_GRADES.index(best[0])
    if idx > 0:
        g0 = IT_GRADES[idx - 1]
        try:
            v0 = it_value(nominal, g0)
            if abs(v0 - tol_mm) < abs(best[1] - tol_mm):
                return g0, v0
        except DesignError:
            pass
    return best


def it_table(nominal: float) -> list[tuple[str, float, float]]:
    """某基本尺寸下的完整等级表 → [(等级, 公差 mm, a 系数或 None)]。"""
    out = []
    for g in IT_GRADES:
        try:
            v = it_value(nominal, g)
        except DesignError:
            continue
        out.append((g, v, IT_A.get(g)))
    return out


# =====================================================================
# 基本偏差（GB/T 1800.1）
# =====================================================================
#
# 覆盖范围与取舍：
#   已内置 —— 轴 d e f g h js k     孔 D E F G H JS K
#   未内置 —— a b c（大间隙，公式值需按表取整，与标准表可能差数 μm）
#             j m n p r s t u v x y z za zb zc（手册取值含分段修正量 Δ）
#   未内置的代号请直接输入上/下偏差；这样不会把近似值当权威值用。
#
# 孔的规则：基本偏差 EI/ES = −(同名轴的基本偏差)，且对 K 在 ≤IT8 时加 Δ = ITn − IT(n−1)。

SHAFT_DEV = ("d", "e", "f", "g", "h", "js", "k")
HOLE_DEV = tuple(c.upper() if c != "js" else "JS" for c in SHAFT_DEV)


def _round_um(x: float) -> int:
    """把公式值取整到整数 μm（GB/T 1800.1 表值即按 μm 取整）。

    实测口径：φ50 时 f → −24.63→−25、d → −79.95→−80、e → −49.26→−50、
    g → −8.67→−9，均为四舍五入到 1 μm。
    """
    return int(math.floor(abs(x) + 0.5)) * (1 if x >= 0 else -1)


def shaft_fundamental_dev(letter: str, nominal: float) -> int | None:
    """轴基本偏差（μm，带符号）。返回 None 表示本工具未内置该代号。"""
    if letter not in SHAFT_DEV:
        return None
    D = it_segment_mean(nominal)
    if letter == "d":
        return _round_um(-16.0 * D ** 0.44)
    if letter == "e":
        return _round_um(-11.0 * D ** 0.41)
    if letter == "f":
        return _round_um(-5.5 * D ** 0.41)
    if letter == "g":
        return _round_um(-2.5 * D ** 0.34)
    if letter == "h":
        return 0
    if letter == "js":
        return 0                      # 对称，由调用方按 ±IT/2 处理
    if letter == "k":
        return None                   # 与等级有关，见 dev_for_zone()
    return None


def _it_steps(nominal: float, grade: str) -> int:
    """Δ = ITn − IT(n−1)（μm），用于孔 K 的修正。"""
    i = IT_GRADES.index(grade)
    if i == 0:
        return 0
    a = it_value(nominal, IT_GRADES[i - 1]) * 1000.0
    b = it_value(nominal, grade) * 1000.0
    return int(round(b - a))


def dev_for_zone(letter: str, grade: str, nominal: float) -> tuple[float, float]:
    """返回 (上偏差, 下偏差)，单位 mm。"""
    if grade not in IT_GRADES:
        raise DesignError(f"未知公差等级：{grade}")
    T = it_value(nominal, grade)
    up = letter.upper()

    # ---- 对称 -->
    if letter in ("js", "JS"):
        return T / 2.0, -T / 2.0

    # ---- 轴 ----
    if letter.islower():
        if letter == "k":
            # k 的基本偏差 ei 仅 IT4~IT7 有定义，其余等级 ei = 0
            if grade in ("IT4", "IT5", "IT6", "IT7"):
                ei = _round_um(0.6 * it_segment_mean(nominal) ** (1.0 / 3.0)) / 1000.0
            else:
                ei = 0.0
            return ei + T, ei
        fd = shaft_fundamental_dev(letter, nominal)
        if fd is None:
            raise DesignError(f"本工具未内置轴的基本偏差代号「{letter}」")
        es = fd / 1000.0
        return es, es - T

    # ---- 孔 ----
    if up == "K":
        # ES = −ei(k) + Δ，等级 ≤ IT8 时 Δ = ITn − IT(n−1)，否则 Δ = 0
        if grade in ("IT4", "IT5", "IT6", "IT7"):
            ei_k = _round_um(0.6 * it_segment_mean(nominal) ** (1.0 / 3.0))
        else:
            ei_k = 0
        delta = _it_steps(nominal, grade) if grade in (
            "IT01", "IT0", "IT1", "IT2", "IT3", "IT4", "IT5", "IT6", "IT7", "IT8") else 0
        ES = (-ei_k + delta) / 1000.0
        return ES, ES - T

    low = up.lower()
    fd = shaft_fundamental_dev(low, nominal) if low in SHAFT_DEV else None
    if fd is None:
        raise DesignError(f"本工具未内置孔的基本偏差代号「{up}」")
    # 孔的基本偏差为下偏差 EI = −(同名轴的上偏差 / 基本偏差)
    EI = -fd / 1000.0
    if low == "h":
        EI = 0.0
    return EI + T, EI


def parse_zone(code: str, nominal: float) -> dict:
    """解析公差带代号，如 ``H7`` / ``f6`` / ``js6``（可带直径前缀 ``φ50H7``）。

    返回 {"letter", "grade", "es", "ei", "T", "text"}

    ⚠ 不要用「剥前缀」的写法解析：``D9`` 的 ``D`` 与直径前缀 ``D`` 同形，
      会把它误吃掉。这里用一次性正则把 (直径数字)(偏差字母)(等级数字) 拆开。
    """
    if not code:
        raise DesignError("公差带代号为空")
    s = str(code).strip().replace(" ", "")
    m = re.match(r"^(?:[φΦØø]|%%[cC])?(\d+(?:\.\d+)?)?([A-Za-z]{1,2})(\d{1,2})$", s)
    if not m:
        raise DesignError(f"「{code}」不是有效的公差带代号（示例：H7、f6、φ50js6）")
    _size, letter, num = m.group(1), m.group(2), m.group(3)
    grade = "IT" + num
    if grade not in IT_GRADES:
        raise DesignError(f"「{code}」中的等级 {num} 不是标准等级（IT01~IT18）")
    if len(letter) == 2 and letter.upper() != "JS":
        raise DesignError(f"「{code}」中的基本偏差代号 {letter} 无法识别")
    es, ei = dev_for_zone(letter, grade, nominal)
    return {"letter": letter, "grade": grade, "es": es, "ei": ei,
            "T": es - ei, "text": f"{letter}{num}"}


def zone_examples() -> list[str]:
    return ["H7", "h6", "js6", "JS7", "f6", "F7", "g6", "G7", "e8", "E8",
            "d9", "D9", "k6", "K7"]


# =====================================================================
# 尺寸环
# =====================================================================

STD_TEMP = 20.0        # 标准温度 ℃（GB/T 1800.1）


def new_link(no: str = "", name: str = "", nominal: float = 0.0,
             es: float = 0.0, ei: float = 0.0, sign: int = 1,
             dist: str = DEFAULT_DIST, enabled: bool = True,
             alpha: float = 0.0, temp: float = STD_TEMP,
             k: float | None = None, e: float | None = None,
             xi: float | None = None,
             note: str = "") -> dict:
    k0, e0 = dist_params(dist)
    return {"no": no, "name": name, "nominal": float(nominal),
            "es": float(es), "ei": float(ei), "sign": int(sign),
            # xi：显式传递系数（斜面/投影等非平行环）。None = 按 sign 自动取 ±1
            "xi": None if xi is None else float(xi),
            "dist": dist, "enabled": bool(enabled),
            "alpha": float(alpha), "temp": float(temp),
            "k": k0 if k is None else float(k),
            "e": e0 if e is None else float(e),
            "note": note}


def default_links() -> list[dict]:
    """一组示例环：5 个 ±0.05 的对称环（华为胶片里的经典例子）。"""
    return [new_link(no=f"A{i + 1}", name=f"零件{i + 1}", nominal=10.0 + i,
                     es=0.05, ei=-0.05, sign=1, dist="normal")
            for i in range(5)]


def _thermal(link: dict, use_thermal: bool) -> tuple[float, float, float]:
    """热膨胀修正 → (基本尺寸, 上偏差, 下偏差)。"""
    if not use_thermal:
        return link["nominal"], link["es"], link["ei"]
    a = float(link.get("alpha") or 0.0) * 1e-6
    dt = float(link.get("temp") or STD_TEMP) - STD_TEMP
    f = 1.0 + a * dt
    return link["nominal"] * f, link["es"] * f, link["ei"] * f


def link_calc(link: dict, use_thermal: bool = False) -> dict:
    """单个组成环的派生量。"""
    nom, es, ei = _thermal(link, use_thermal)
    if es < ei:
        es, ei = ei, es
    T = es - ei
    dmid = (es + ei) / 2.0
    # 传递系数：优先用显式 ξ（斜面/投影等非平行环，可为 ±0.707 等）；
    # 未指定时按增/减环取 ±1
    xv = link.get("xi")
    xi = float(xv) if xv is not None else \
        (1 if int(link["sign"]) >= 0 else -1)
    k = float(link.get("k", 1.0))
    e = float(link.get("e", 0.0))
    if k <= 0:
        raise DesignError(f"环 {link.get('no', '')} 的相对分布系数 k 必须为正")
    return {"nominal": nom, "es": es, "ei": ei, "T": T, "dmid": dmid,
            "xi": xi, "k": k, "e": e,
            "dist": link.get("dist", DEFAULT_DIST),
            "sigma": k * T / 6.0,
            "shift": xi * e * T / 2.0}


# =====================================================================
# 传递系数：按封闭环基本尺寸反解「增环 / 减环」
# =====================================================================

def auto_signs(links: list[dict], closing_nominal: float,
               max_links: int = 18) -> tuple[list[int] | None, str]:
    """已知各组成环基本尺寸与封闭环基本尺寸，反解增/减环组合。

    原理：N₀ = ΣξᵢAᵢ，ξᵢ∈{+1,−1}
          ⇔ Σ_{增} 2Aᵢ = N₀ + ΣAᵢ   —— 一个子集和问题
    返回 (符号列表, 说明)。无解时符号为 None。
    """
    vals = [abs(float(l["nominal"])) for l in links]
    n = len(vals)
    if n == 0:
        return [], "没有组成环"
    if n > max_links:
        return None, f"组成环过多（{n} > {max_links}），请手工指定增减环"

    total = sum(vals)
    # 需要 Σ_{增} Aᵢ = (N₀ + ΣAᵢ) / 2，所以 DP 的目标是**除以 2 之后**的值
    target_sum = (float(closing_nominal) + total) / 2.0
    scale = 1_000_000
    w = [int(round(v * scale)) for v in vals]
    tt = int(round(target_sum * scale))
    if tt < 0 or tt > sum(w):
        return None, "封闭环基本尺寸超出各环可组合的范围，无解"

    # 字典 DP：sum -> (所用环下标, 前驱 sum)
    prev: dict[int, tuple[int, int]] = {0: (-1, -1)}
    for idx, wi in enumerate(w):
        items = list(prev.items())
        for s, _meta in items:
            ns = s + wi
            if ns <= tt and ns not in prev:
                prev[ns] = (idx, s)
        if len(prev) > 3_000_000:
            return None, "组合空间过大，请手工指定增减环"
    if tt not in prev:
        return None, "按该封闭环基本尺寸反解不出增减环组合，请核对尺寸或手工指定"

    chosen, cur = set(), tt
    while cur > 0:
        idx, ps = prev[cur]
        if idx < 0:
            break
        chosen.add(idx)
        cur = ps
    signs = [1 if i in chosen else -1 for i in range(n)]
    k_inc = len(chosen)
    msg = (f"已反解出 {k_inc} 个增环 / {n - k_inc} 个减环"
           f"（增环基本尺寸之和 = {target_sum:.4g} mm）")
    return signs, msg


# =====================================================================
# 正算：公差分析
# =====================================================================

def _summarize(T0: float, d0: float, N0: float, sigma0: float | None) -> dict:
    es0 = d0 + T0 / 2.0
    ei0 = d0 - T0 / 2.0
    out = {"T": T0, "dmid": d0, "es": es0, "ei": ei0,
           "max": N0 + es0, "min": N0 + ei0, "nominal": N0}
    if sigma0 is not None:
        out["sigma"] = sigma0
    return out


def _capability(mu: float, sigma: float, low: float, high: float) -> dict:
    """制程能力（与华为胶片的 Ppk / PPM / σ 水平同口径）。"""
    nd = NormalDist()
    if high < low:
        raise DesignError("封闭环要求的最大值不能小于最小值")
    span = high - low
    p_ok = nd.cdf((high - mu) / sigma) - nd.cdf((low - mu) / sigma) if sigma > 0 else 1.0
    p_ok = min(max(p_ok, 0.0), 1.0)
    ppm = (1.0 - p_ok) * 1e6
    cp = span / (6.0 * sigma) if sigma > 0 else float("inf")
    cpk = (min(high - mu, mu - low) / (3.0 * sigma)) if sigma > 0 else float("inf")
    # σ 水平（含 1.5σ 长期漂移，与「6σ = 3.4 PPM」的表同口径）
    z = 3.0 * cpk if sigma > 0 else float("inf")
    return {"cp": cp, "cpk": cpk, "ppk": cpk, "z": z,
            "sigma_level": z + 1.5 if math.isfinite(z) else z,
            "pass_rate": p_ok, "ppm": ppm,
            "limit_low": low, "limit_high": high, "mu": mu, "sigma": sigma}


def analyze(links: list[dict], target: dict | None = None,
            use_thermal: bool = False, n_sigma: float = 6.0) -> dict:
    """尺寸链正算（公差分析）。

    links  : 组成环列表（只有 enabled=True 的参与计算）
    target : 封闭环要求 {"nominal":, "es":, "ei":}；也可给 None
    n_sigma: 统计法评估带宽的 σ 倍数（华为表格口径为 6σ，即 99.73%）。
             σ₀ 的定义不变（单环公差带 = 6σ，与华为表一致），
             改变的只是合成公差带取 n·σ₀：选小值（如 ±4σ）公差带更紧、
             废品率上升；选大值更保守。
    返回    : 含 wc / rss 两套结果、贡献率、判定、建议的字典
    """
    n_sigma = float(n_sigma)
    if not (2.0 <= n_sigma <= 10.0):
        raise DesignError("统计法评估带宽 n 必须在 2 ~ 10 个 σ 之间")
    act = [l for l in links if l.get("enabled", True)]
    if not act:
        raise DesignError("至少需要一个参与计算的组成环")

    rows, N0 = [], 0.0
    sum_T = 0.0
    sum_var = 0.0
    d0_wc = 0.0
    sum_shift = 0.0
    for l in act:
        c = link_calc(l, use_thermal)
        N0 += c["xi"] * c["nominal"]
        sum_T += abs(c["xi"]) * c["T"]
        sum_var += (c["xi"] * c["k"] * c["T"]) ** 2
        d0_wc += c["xi"] * c["dmid"]
        sum_shift += c["shift"]
        rows.append({**l, **c})

    sigma0 = math.sqrt(sum_var) / 6.0
    T_rss = n_sigma * sigma0
    d0_rss = d0_wc + sum_shift

    wc = _summarize(sum_T, d0_wc, N0, None)
    rss = _summarize(T_rss, d0_rss, N0, sigma0)
    rss["n_sigma"] = n_sigma

    # ---- 贡献率 ----
    tot_T = sum_T or 1.0
    tot_v = sum_var or 1.0
    for r in rows:
        r["term_wc"] = abs(r["xi"]) * r["T"]
        r["term_rss"] = (r["xi"] * r["k"] * r["T"]) ** 2
        r["share_wc"] = r["term_wc"] / tot_T
        r["share_rss"] = r["term_rss"] / tot_v
    contrib = sorted(rows, key=lambda r: -r["share_rss"])

    n = len(act)
    rec = "wc" if n <= 3 else "rss"

    res = {
        "links": rows,
        "n": n,
        "nominal": N0,
        "wc": wc,
        "rss": rss,
        "recommend": rec,
        "recommend_reason": (
            f"共 {n} 个累积尺寸（≤3），按华为口径建议用极值法 WC 校核"
            if n <= 3 else
            f"共 {n} 个累积尺寸（≥4），按华为口径建议用统计法 RSS 校核"),
        "contrib": contrib,
        "use_thermal": use_thermal,
        "n_sigma": n_sigma,
    }

    # ---- 与封闭环要求比对 ----
    #
    # 目标值的口径（重要）：
    #   给了「目标值」      → 按绝对尺寸比对：low = 目标值 + ei，high = 目标值 + es
    #   留空 / 未给 / None  → 按「相对封闭环计算名义值 N₀ 的偏差带」比对：
    #                         low = N₀ + ei，high = N₀ + es
    # 后者才符合「累积公差必须落在 ±0.25 内」这种最常见的提法，
    # 也避免出现「目标值填 0 而实际名义值是 60」造成的伪超差。
    if target:
        raw_n = target.get("nominal", None)
        try:
            tn = None if raw_n in (None, "", "auto") else float(raw_n)
        except (TypeError, ValueError):
            tn = None
        if tn is None:
            tn = N0
            nominal_auto = True
        else:
            nominal_auto = False
        tes = float(target.get("es", 0.0))
        tei = float(target.get("ei", 0.0))
        if tes < tei:
            tes, tei = tei, tes
        low, high = tn + tei, tn + tes
        v = {}
        for key, s in (("wc", wc), ("rss", rss)):
            mu = N0 + s["dmid"]
            sig = s.get("sigma")
            if sig and sig > 0:
                cap = _capability(mu, sig, low, high)
            else:
                # 极值法没有 σ：以「极限边界是否越界」判定，合格率取 0/1
                inside = (s["min"] >= low and s["max"] <= high)
                cap = {"cp": None, "cpk": None, "ppk": None, "z": None,
                       "sigma_level": None, "pass_rate": 1.0 if inside else 0.0,
                       "ppm": 0.0 if inside else 1e6,
                       "limit_low": low, "limit_high": high, "mu": mu, "sigma": None}
            cap["ok"] = (s["min"] >= low and s["max"] <= high)
            cap["over_high"] = max(0.0, s["max"] - high)
            cap["over_low"] = max(0.0, low - s["min"])
            cap["margin_high"] = high - s["max"]
            cap["margin_low"] = s["min"] - low
            v[key] = cap
        res["target"] = {"nominal": tn, "es": tes, "ei": tei,
                         "low": low, "high": high, "T": tes - tei,
                         "nominal_auto": nominal_auto}
        res["verdict"] = v

        # 优化建议：找出贡献率最大的环
        tips = []
        for key in ("wc", "rss"):
            cap = v[key]
            if cap["ok"]:
                continue
            top = contrib[0]
            tips.append(
                f"{'极值法' if key == 'wc' else '统计法'}判定{'上限' if cap['over_high'] > cap['over_low'] else '下限'}超差 "
                f"{max(cap['over_high'], cap['over_low']):.4g} mm；"
                f"贡献率最大的是「{top.get('no') or top.get('name')}」"
                f"（{top['share_rss'] * 100:.1f}%），优先收紧该环公差")
        if not tips:
            v_rss = v["rss"]
            if v_rss.get("ppk") is not None:
                if v_rss["ppk"] < 1.0:
                    tips.append(f"RSS 判定虽未越界，但 Ppk = {v_rss['ppk']:.2f} < 1.0，"
                                f"批量生产不良率高（{v_rss['ppm']:.0f} PPM），建议收紧公差")
                elif v_rss["ppk"] < 1.33:
                    tips.append(f"RSS 判定通过，Ppk = {v_rss['ppk']:.2f} 偏低（一般要求 ≥1.33），"
                                f"建议关注「{contrib[0].get('no') or contrib[0].get('name')}」这一主导环")
        res["tips"] = tips

    return res


# =====================================================================
# 反算：公差分配
# =====================================================================

ALLOC_METHODS = {
    "equal": "等公差（各环公差相同）",
    "grade": "等公差等级（各环同级 IT）",
    "weight": "按权重比例分配",
}


def allocate(links: list[dict], closing_tol: float,
             method: str = "equal", rule: str = "rss",
             weights: dict | None = None,
             keep_dmid: bool = True,
             use_thermal: bool = False) -> dict:
    """公差分配（反算）：把封闭环公差 T₀ 分给各组成环。

    rule : "wc" 按极值法 ΣTᵢ = T₀ 分配
           "rss" 按统计法 √(ΣTᵢ²) = T₀ 分配
    """
    act = [l for l in links if l.get("enabled", True)]
    if not act:
        raise DesignError("至少需要一个参与计算的组成环")
    if closing_tol <= 0:
        raise DesignError("封闭环公差必须为正")
    m = len(act)
    weights = weights or {}
    out = []

    if method == "equal":
        t_each = closing_tol / m if rule == "wc" else closing_tol / math.sqrt(m)
        for l in act:
            out.append({"link": l, "T": t_each, "grade": None,
                        "basis": f"T₀ / {'m' if rule == 'wc' else '√m'} = {t_each:.4g} mm"})

    elif method == "grade":
        # 求公共公差等级系数 a：Σ a·iᵢ = T₀ 或 √(Σ(a·iᵢ)²) = T₀
        fac = []
        for l in act:
            nom = _thermal(l, use_thermal)[0]
            fac.append(tolerance_factor(nom) / 1000.0)      # mm
        denom = sum(fac) if rule == "wc" else math.sqrt(sum(f * f for f in fac))
        a = closing_tol / denom
        for l, f in zip(act, fac):
            nom = _thermal(l, use_thermal)[0]
            t_raw = a * f
            g, t_std = it_grade_for(nom, t_raw)
            out.append({"link": l, "T": t_std, "grade": g,
                        "raw_T": t_raw,
                        "basis": f"所需 a = T₀ / {'Σiᵢ' if rule == 'wc' else '√(Σiᵢ²)'}"
                                 f" = {a:.1f}；本环 i = {f * 1000:.3f} μm，"
                                 f"取最接近标准等级 {g} = {t_std * 1000:.0f} μm"})

    elif method == "weight":
        ws = [max(0.0, float(weights.get(l.get("no", ""), 1.0))) for l in act]
        if sum(ws) <= 0:
            raise DesignError("权重之和必须为正")
        if rule == "wc":
            s = sum(ws)
        else:
            s = math.sqrt(sum(w * w for w in ws))
        for l, w in zip(act, ws):
            t = closing_tol * w / s
            out.append({"link": l, "T": t, "grade": None,
                        "basis": f"T₀ × {w:g} / {s:.4g} = {t:.4g} mm"})
    else:
        raise DesignError(f"未知分配方法：{method}")

    # 组装成新的环（默认保留原中间偏差，即对称分布时上下偏差各 ±T/2）
    new_links = []
    for row in out:
        l = row["link"]
        nom, es, ei = _thermal(l, use_thermal)
        dmid = (es + ei) / 2.0 if keep_dmid else 0.0
        nl = dict(l)
        nl["es"] = dmid + row["T"] / 2.0
        nl["ei"] = dmid - row["T"] / 2.0
        new_links.append(nl)
        row["es"] = nl["es"]
        row["ei"] = nl["ei"]

    # 用分配后的公差复算
    chk_wc = analyze(new_links, use_thermal=use_thermal) if new_links else None
    t_wc = chk_wc["wc"]["T"] if chk_wc else None
    t_rss = chk_wc["rss"]["T"] if chk_wc else None
    achieved = t_wc if rule == "wc" else t_rss
    dev = (achieved - closing_tol) if achieved is not None else None
    tip = None
    if dev is not None:
        if rule == "grade":
            tip = (f"等公差等级法会把各环公差就近归到标准 IT 等级，"
                   f"实际累积 {achieved:.4f} mm 与目标 {closing_tol:.4f} mm "
                   f"相差 {dev:+.4f} mm（{dev / closing_tol * 100:+.1f}%）。"
                   f"{'偏大，可按标准等级表选更紧一档后复算。' if dev > 0 else '偏小，有余量。'}")
        elif abs(dev) > closing_tol * 0.02:
            tip = (f"复算累积 {achieved:.4f} mm 与目标 {closing_tol:.4f} mm "
                   f"相差 {dev:+.4f} mm，请复核分配规则。")
    return {
        "method": method, "rule": rule, "rows": out,
        "new_links": new_links,
        "T_required": closing_tol,
        "T_wc": t_wc,
        "T_rss": t_rss,
        "T_achieved": achieved,
        "deviation": dev,
        "tip": tip,
        "achieved": chk_wc,
    }


# =====================================================================
# 蒙特卡洛仿真
# =====================================================================

def _sample(link_c: dict, dist: str, rng: random.Random) -> float:
    """按分布抽一个偏差量（相对基本尺寸的偏移）。"""
    mu = link_c["dmid"]
    T = link_c["T"]
    if T <= 0:
        return 0.0
    k, e = link_c["k"], link_c["e"]
    if dist == "uniform":
        half = T / 2.0
        return rng.uniform(mu - half, mu + half)
    if dist == "triangular":
        half = T / 2.0
        return rng.triangular(mu - half, mu + half, mu)
    # 正态，以及无法按形状抽样的分布（瑞利 / 偏态）按等效正态处理
    sigma = k * T / 6.0
    return rng.gauss(mu + e * T / 2.0, sigma)


def monte_carlo(links: list[dict], n: int = 100000, seed: int | None = 20260918,
                target: dict | None = None, bins: int = 61,
                use_thermal: bool = False) -> dict:
    """蒙特卡洛仿真：给出封闭环的实际分布、合格率与制程能力。"""
    act = [l for l in links if l.get("enabled", True)]
    if not act:
        raise DesignError("至少需要一个参与计算的组成环")
    n = int(n)
    if n < 1000:
        raise DesignError("仿真次数建议不少于 1000 次")
    n = min(n, 2_000_000)

    rng = random.Random(seed)
    cs = [link_calc(l, use_thermal) for l in act]
    N0 = sum(c["xi"] * c["nominal"] for c in cs)

    samples = []
    for _ in range(n):
        s = 0.0
        for c in cs:
            s += c["xi"] * _sample(c, c["dist"], rng)
        samples.append(s)

    samples.sort()
    mean = sum(samples) / n
    var = sum((v - mean) ** 2 for v in samples) / (n - 1 if n > 1 else 1)
    sigma = math.sqrt(var)

    def pct(q):
        i = min(n - 1, max(0, int(round(q * (n - 1)))))
        return samples[i]

    lo, hi = samples[0], samples[-1]
    width = (hi - lo) or 1e-9
    step = width / bins
    counts = [0] * bins
    for v in samples:
        idx = int((v - lo) / step)
        counts[min(bins - 1, max(0, idx))] += 1

    res = {"n": n, "seed": seed, "mean": mean, "sigma": sigma,
           "nominal": N0, "min": lo, "max": hi,
           "p_low": pct(0.00135), "p_high": pct(0.99865),
           "p50": pct(0.5), "range6": pct(0.99865) - pct(0.00135),
           "hist": {"x0": lo, "dx": step, "counts": counts},
           "mu_shift": mean - N0}

    if target:
        raw_n = target.get("nominal", None)
        try:
            tn = None if raw_n in (None, "", "auto") else float(raw_n)
        except (TypeError, ValueError):
            tn = None
        tn = N0 if tn is None else tn
        low, high = tn + float(target.get("ei", 0.0)), tn + float(target.get("es", 0.0))
        k = sum(1 for v in samples if low <= N0 + v <= high)
        res["pass_count"] = k
        res["pass_rate"] = k / n
        res["ppm"] = (1 - k / n) * 1e6
        res["limit_low"] = low - N0
        res["limit_high"] = high - N0
        if sigma > 0:
            cap = _capability(N0 + mean, sigma, low, high)
            res.update({kk: cap[kk] for kk in ("cp", "cpk", "ppk", "z",
                                               "sigma_level")})
    # 各环敏感度（标准差占比）
    tot = sum((c["xi"] * c["sigma"]) ** 2 for c in cs) or 1.0
    res["sens"] = sorted(
        [{"no": l.get("no", ""), "name": l.get("name", ""),
          "sigma": abs(c["xi"]) * c["sigma"],
          "share": ((c["xi"] * c["sigma"]) ** 2) / tot}
         for l, c in zip(act, cs)],
        key=lambda r: -r["share"])
    return res


# =====================================================================
# σ 水平 / PPM 对照（华为胶片同口径：含 1.5σ 长期漂移）
# =====================================================================

def sigma_level_table(min_level: int = 1, max_level: int = 6) -> list[tuple[str, float, str]]:
    nd = NormalDist()
    rows = []
    for lv in range(min_level, max_level + 1):
        ppm = nd.cdf(-(lv - 1.5)) * 1e6
        if ppm >= 10000:
            txt = f"{ppm:,.0f} PPM"
        elif ppm >= 1:
            txt = f"{ppm:,.0f} PPM"
        else:
            txt = f"{ppm:.1f} PPM"
        judge = {2: "不能接收", 3: "业界平均水平", 4: "较好", 5: "世界级", 6: "卓越"}
        rows.append((f"{lv}σ", ppm, judge.get(lv, "")))
    return rows


def ppm_to_sigma_level(ppm: float) -> float:
    """由 PPM 反推 σ 水平（含 1.5σ 漂移）。"""
    if ppm <= 0:
        return float("inf")
    if ppm >= 1e6:
        return -math.inf
    return -NormalDist().inv_cdf(ppm / 1e6) + 1.5


# =====================================================================
# 参考算例（用于自检与「载入示例」按钮）
# =====================================================================

def example_links(name: str) -> list[dict]:
    """几个教科书级尺寸链算例。"""
    if name == "huawei5":
        # 华为胶片：5 个 ±0.05 对称环
        return [new_link(no=f"A{i + 1}", name=f"零件{i + 1}", nominal=10.0,
                         es=0.05, ei=-0.05, sign=1) for i in range(5)]
    if name == "rss5":
        # 华为胶片：5 个不同尺寸的累积
        data = [("Dim1", 3.3, 0.10), ("Dim2", 4.5, 0.15), ("Dim3", 10.0, 0.20),
                ("Dim4", 5.8, 0.15), ("Dim5", 20.5, 0.30)]
        return [new_link(no=d[0], name=d[0], nominal=d[1], es=d[2], ei=-d[2])
                for d in data]
    if name == "assembly":
        # 典型装配间隙链：孔 + 轴 + 两个定位环
        return [
            new_link(no="A1", name="座孔深度", nominal=30.0, es=0.052, ei=0.0),
            new_link(no="A2", name="轴肩厚度", nominal=8.0, es=0.0, ei=-0.036, sign=-1),
            new_link(no="A3", name="垫片厚", nominal=2.0, es=0.05, ei=-0.05, sign=-1),
            new_link(no="A4", name="端盖凸台", nominal=19.0, es=0.03, ei=-0.03, sign=-1),
        ]
    raise DesignError(f"未知示例：{name}")


EXAMPLE_NAMES = [
    ("huawei5", "华为胶片例：5 × ±0.05 对称环"),
    ("rss5", "华为胶片例：5 个不等公差环"),
    ("assembly", "装配间隙链：孔 + 轴 + 垫片 + 端盖"),
]
