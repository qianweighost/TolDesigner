# -*- coding: utf-8 -*-
"""自检脚本：数值校验 + 示意图几何自检 + 界面冒烟 + 截图。

三部分：
  一、数值校验 —— 期望值取自两处硬锚点：
        (a) 华为研发内部《公差分析》培训胶片的算例与 σ/PPM 对照表；
        (b) GB/T 1800.1-2020 标准公差表与 GB/T 1800.2 基本偏差表。
     这两处都是「外部权威值」，不是本程序自己算出来又自己验证，
     所以能真正锁住计算口径。

  二、示意图几何自检 —— 控件把像素级几何记进 self._geom，
     断言图形不越出卡片、不压住标注带。不靠扫像素猜边界
     （标注文字的反锯齿灰像素会把包围盒撑大，造成误判）。

  三、界面冒烟 —— 真实字体渲染但不弹窗（WA_DontShowOnScreen），逐页截图。

⚠ 截图**不要**用 QT_QPA_PLATFORM=offscreen：offscreen 平台没有字体数据库，
中文会渲染成豆腐块，会让人误判排版有问题。正确做法是用
WA_DontShowOnScreen 属性 + 默认平台，拿到真实字体渲染的画面。
"""
from __future__ import annotations

import math
import os
import sys
import traceback

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from core.tol_core import (DIST_KEYS, DesignError, HOLE_DEV, IT_GRADES,
                           SHAFT_DEV,  # noqa: E402
                           allocate, analyze, auto_signs, default_links,
                           example_links, it_grade_for, it_segment_mean,
                           it_table, it_value, link_calc, monte_carlo,
                           new_link, parse_zone, ppm_to_sigma_level,
                           sigma_level_table, tolerance_factor)

OUT_DIR = os.path.join(_ROOT, "tools", "out")
LOG: list[str] = []
PASS = 0
FAIL = 0


def log(s: str = ""):
    LOG.append(str(s))


def check(title: str, got, want, tol: float = 1e-9):
    global PASS, FAIL
    if isinstance(want, (int, float)) and isinstance(got, (int, float)):
        ok = abs(got - want) <= tol * max(1.0, abs(want))
    else:
        ok = got == want
    if ok:
        PASS += 1
        log(f"  ✓ {title}: {got}")
    else:
        FAIL += 1
        log(f"  ✗ {title}: got {got!r}, want {want!r}")
    return ok


def check_true(title: str, cond, extra: str = ""):
    global PASS, FAIL
    if cond:
        PASS += 1
        log(f"  ✓ {title} {extra}".rstrip())
    else:
        FAIL += 1
        log(f"  ✗ {title} {extra}".rstrip())
    return bool(cond)


def _raises(fn) -> bool:
    try:
        fn()
        return False
    except Exception:  # noqa: BLE001
        return True


# =====================================================================
# 一、数值校验
# =====================================================================

def test_huawei_example():
    log("【1】华为内部胶片算例：5 × ±0.05 对称环")
    r = analyze(default_links())
    check("累积环数", r["n"], 5)
    # 口径提示：胶片写的是「±0.25」，那是半带；本工具的 T 是全带，故 T = 2×0.25
    check("WC 半带（即 ± 值）", r["wc"]["es"], 0.25, 1e-12)
    check("WC 全带 T = ΣTᵢ", r["wc"]["T"], 0.5, 1e-12)
    check("WC 上下对称", r["wc"]["ei"], -0.25, 1e-12)
    check("RSS 半带 = √(ΣTᵢ²)/2", r["rss"]["es"], math.sqrt(5 * 0.05 ** 2), 1e-12)
    log(f"      └ RSS = ±{r['rss']['es']:.4f}（胶片写 ±0.11）  "
        f"全带 {r['rss']['T']:.4f}")
    check("σ₀ = √Σσᵢ²", r["rss"]["sigma"], math.sqrt(5) * 0.1 / 6, 1e-12)
    check("推荐口径（5 环 → 统计法）", r["recommend"], "rss")

    log("【2】华为内部胶片算例：5 个不等公差环 → ±0.43")
    r2 = analyze(example_links("rss5"))
    want = math.sqrt(0.1 ** 2 + 0.15 ** 2 + 0.2 ** 2 + 0.15 ** 2 + 0.3 ** 2)
    check("RSS 半带", r2["rss"]["es"], want, 1e-12)
    log(f"      └ ±{r2['rss']['es']:.4f}（胶片写 ±0.43）")
    check_true("≈ ±0.43", abs(r2["rss"]["es"] - 0.43) < 0.001)


def test_sigma_table():
    log("")
    log("【3】σ 水平 / PPM 对照表（华为胶片：2σ=308537 … 6σ=3.4）")
    tbl = {lv: ppm for lv, ppm, _ in sigma_level_table(1, 6)}
    check("2σ PPM", round(tbl["2σ"]), 308537, 1)
    check("3σ PPM", round(tbl["3σ"]), 66807, 1)
    check("4σ PPM", round(tbl["4σ"]), 6210, 1)
    check("5σ PPM", round(tbl["5σ"]), 233, 1)
    check("6σ PPM", round(tbl["6σ"], 1), 3.4, 0.05)
    check("PPM → σ 水平 反算", ppm_to_sigma_level(3.4), 6.0, 0.01)
    check("PPM → σ 水平 反算(66807)", ppm_to_sigma_level(66807), 3.0, 0.01)


def test_it_table():
    log("")
    log("【4】GB/T 1800.1-2020 标准公差 IT 值（对照标准表）")
    check("IT7 @30~50", it_value(50, "IT7"), 0.025, 1e-12)
    check("IT6 @30~50", it_value(50, "IT6"), 0.016, 1e-12)
    check("IT9 @30~50", it_value(50, "IT9"), 0.062, 1e-12)
    check("IT11 @30~50", it_value(50, "IT11"), 0.160, 1e-12)
    check("IT5 @30~50", it_value(50, "IT5"), 0.011, 1e-12)
    check("IT4 @30~50", it_value(50, "IT4"), 0.007, 1e-12)
    check("IT7 @18~30", it_value(25, "IT7"), 0.021, 1e-12)
    check("IT8 @80~120", it_value(100, "IT8"), 0.054, 1e-12)
    check("IT7 @6~10", it_value(10, "IT7"), 0.015, 1e-12)
    check("IT1 @≤3", it_value(3, "IT1"), 0.0008, 1e-12)

    log("      · 分段几何平均值 D 与公差因子 i（D ≤ 500 mm）")
    check("D(30,50)", it_segment_mean(50), math.sqrt(30 * 50), 1e-9)
    d = math.sqrt(30 * 50)
    check("i(30,50) = 0.45·∛D + 0.001·D",
          tolerance_factor(50), 0.45 * d ** (1 / 3) + 0.001 * d, 1e-12)
    check_true("IT6 ≈ 10i（标准定义）",
               abs(it_value(50, "IT6") * 1000 - 10 * tolerance_factor(50)) < 1.0,
               f"（IT6 = {it_value(50, 'IT6') * 1000:.0f} μm，"
               f"10i = {10 * tolerance_factor(50):.1f} μm）")

    log("      · 等级推荐（反算用）")
    g, v = it_grade_for(50.0, 0.02)
    check_true("0.02 @ φ50 → IT6/IT7", g in ("IT6", "IT7"),
               f"（得 {g} = {v * 1000:.0f} μm）")
    g2, _v2 = it_grade_for(50.0, 0.03)
    check("0.03 @ φ50 → IT7", g2, "IT7")

    log("      · it_table / IT_GRADES 数据表完整性")
    check("IT 等级数（IT01~IT18）", len(IT_GRADES), 20)
    check_true("IT 表非空", len(it_table(50)) > 0,
               f"（{len(it_table(50))} 行）")


def test_deviations():
    log("")
    log("【5】基本偏差（对照 GB/T 1800.2 标准值，φ50 系列；上偏差/下偏差）")
    cases = [
        ("H7", 0.025, 0.000),
        ("h6", 0.000, -0.016),
        ("f6", -0.025, -0.041),
        ("g6", -0.009, -0.025),
        ("js6", 0.008, -0.008),
        ("D9", 0.142, 0.080),
        ("F8", 0.064, 0.025),
        ("G7", 0.034, 0.009),
        ("d9", -0.080, -0.142),
        ("K7", 0.007, -0.018),
        ("k6", 0.018, 0.002),
    ]
    for code, es_want, ei_want in cases:
        z = parse_zone(code, 50.0)
        check_true(
            f"φ50{code} = {z['es']:+.3f}/{z['ei']:+.3f}",
            abs(z["es"] - es_want) < 5e-5 and abs(z["ei"] - ei_want) < 5e-5,
            f"（标准 {es_want:+.3f}/{ei_want:+.3f}，差 "
            f"{abs(z['es'] - es_want) * 1000:.0f}/{abs(z['ei'] - ei_want) * 1000:.0f} μm）")

    # e 族：GB/T 的 e 基本偏差表值本身是「公式值取整」的结果，允许 2 μm 差
    ze = parse_zone("e8", 50.0)
    log(f"      · φ50e8 = {ze['es']:+.3f}/{ze['ei']:+.3f}"
        f"（手册表值 −0.050/−0.089，差 "
        f"{abs(ze['es'] + 0.050) * 1000:.0f} μm，属取整量级）")
    check_true("e 族差异在取整量级内（≤2 μm）", abs(ze["es"] + 0.050) <= 0.002)

    log("      · 代号解析的边界")
    check("φ50H7 带直径前缀", parse_zone("φ50H7", 50.0)["T"], 0.025, 1e-12)
    check("H7 不带直径也能解析", parse_zone("H7", 50.0)["T"], 0.025, 1e-12)
    check_true("D9 的 D 不被当直径前缀吃掉", parse_zone("D9", 50.0)["es"] > 0)
    check_true("未内置代号（p6）明确报错", _raises(lambda: parse_zone("p6", 50.0)))
    check_true("非法代号（XYZ）报错", _raises(lambda: parse_zone("XYZ", 50.0)))
    check("内置基本偏差代号数（轴）", len(SHAFT_DEV), 7)
    check("内置基本偏差代号数（孔）", len(HOLE_DEV), 7)


def test_auto_signs():
    log("")
    log("【6】自动判定增/减环（按封闭环基本尺寸反解传递系数）")
    ex = example_links("assembly")
    signs, msg = auto_signs(ex, 1.0)
    if check_true("子集和有解", signs is not None, msg) and signs:
        check("反解符号", signs, [1, -1, -1, -1], 0)
        got = analyze([{**l, "sign": s} for l, s in zip(ex, signs)])["nominal"]
        check("反解后封闭环基本尺寸", got, 1.0, 1e-9)
    check_true("无解时明确返回 None",
               auto_signs([new_link(nominal=5.0), new_link(nominal=7.0)], 100.0)[0] is None)


def test_allocate():
    log("")
    log("【7】公差分配（反算）")
    al = allocate(default_links(), 0.25, method="equal", rule="wc")
    check("等公差 WC 每环", al["rows"][0]["T"], 0.05, 1e-12)
    check("复算 WC 总公差", al["T_wc"], 0.25, 1e-12)

    al2 = allocate(default_links(), 0.25, method="equal", rule="rss")
    check("等公差 RSS 每环", al2["rows"][0]["T"], 0.25 / math.sqrt(5), 1e-12)
    log(f"      └ RSS 反推每环 = ±{al2['rows'][0]['T']:.4f}"
        f"（胶片写「若要求 ±0.25，每环可放宽到 ±0.1」）")
    check_true("与胶片 ±0.1 同量级",
               0.08 < al2["rows"][0]["T"] < 0.13,
               f"（{al2['rows'][0]['T']:.4f}）")

    al3 = allocate(default_links(), 0.25, method="grade", rule="wc")
    check_true("等公差等级给出标准等级",
               all(r["grade"] for r in al3["rows"]),
               f"（{al3['rows'][0]['grade']}）")
    log(f"      └ 等公差等级：目标 0.25 → 实际 {al3['T_wc']:.4f}"
        f"（就近归入标准 IT 等级，差额 {al3['deviation']:+.4f}）")
    check_true("等公差等级差额在 ±30% 内", abs(al3["deviation"]) < 0.25 * 0.30)
    check_true("等公差等级给出差额说明", bool(al3.get("tip")))

    al4 = allocate(default_links(), 0.25, method="weight", rule="rss",
                   weights={"A1": 3.0, "A2": 1.0, "A3": 1.0, "A4": 1.0, "A5": 1.0})
    log(f"      └ 按权重 3:1 分配：A1 = {al4['rows'][0]['T']:.4f}，"
        f"A2 = {al4['rows'][1]['T']:.4f}")
    check_true("权重大者公差更大", al4["rows"][0]["T"] > al4["rows"][1]["T"])
    check_true("按权重复算 ≈ T₀（RSS）", abs(al4["T_rss"] - 0.25) < 1e-9,
               f"（{al4['T_rss']:.6f}）")


def test_monte_carlo():
    log("")
    log("【8】蒙特卡洛仿真（与解析 σ 互相印证，两种独立算法）")
    for dist, tag in (("normal", "正态"), ("uniform", "均匀"),
                      ("triangular", "三角")):
        ls = [new_link(no=f"A{i}", nominal=10.0, es=0.05, ei=-0.05, dist=dist)
              for i in range(5)]
        ana = analyze(ls)["rss"]["sigma"]
        mc = monte_carlo(ls, n=60000, seed=42)
        rel = abs(mc["sigma"] - ana) / ana
        check_true(f"{tag}分布：MC σ ≈ 解析 σ", rel < 0.02,
                   f"（MC {mc['sigma']:.5f} / 解析 {ana:.5f}，"
                   f"偏差 {rel * 100:.2f}%）")
    check("分布状态可选数", len(DIST_KEYS), 6)


def test_capability():
    log("")
    log("【9】制程能力（Cp / Ppk / 合格率 / 判定）")
    # 目标值留空 → 按「相对封闭环计算名义值 N₀ 的偏差带」比对（±0.25）
    r3 = analyze(default_links(), target={"es": 0.25, "ei": -0.25})
    check_true("目标值留空时自动取计算名义值", r3["target"]["nominal_auto"])
    check("自动名义值 = N₀", r3["target"]["nominal"], r3["nominal"], 1e-12)
    sig = math.sqrt(5) * 0.1 / 6
    check("Cp", r3["verdict"]["rss"]["cp"], 0.5 / (6 * sig), 1e-9)
    check("Ppk", r3["verdict"]["rss"]["ppk"], 0.25 / (3 * sig), 1e-9)
    check_true("Ppk > 2", r3["verdict"]["rss"]["ppk"] > 2.0,
               f"（Ppk = {r3['verdict']['rss']['ppk']:.3f}，"
               f"σ 水平 = {r3['verdict']['rss']['sigma_level']:.2f}）")
    check_true("RSS 判定合格", r3["verdict"]["rss"]["ok"])
    check_true("WC 判定合格", r3["verdict"]["wc"]["ok"])

    log("      · 口径分支：给了绝对目标值时按绝对尺寸比对")
    r3b = analyze(default_links(), target={"nominal": 60.0, "es": 0.25, "ei": -0.25})
    check("给定目标值时的下限", r3b["target"]["low"], 59.75, 1e-12)
    check_true("给定目标值时同样合格", r3b["verdict"]["rss"]["ok"])
    check_true("目标值误填 0 会判超差（这正是要留空的原因）",
               not analyze(default_links(),
                           target={"nominal": 0.0, "es": 0.25,
                                   "ei": -0.25})["verdict"]["rss"]["ok"])

    log("      · 收紧要求：极值法超差而统计法仍可合格（统计法的价值所在）")
    r4 = analyze(default_links(), target={"es": 0.15, "ei": -0.15})
    check_true("收紧到 ±0.15 后 WC 超差", not r4["verdict"]["wc"]["ok"],
               f"（超 {r4['verdict']['wc']['over_high']:.4f}）")
    check_true("收紧后 RSS 仍合格", r4["verdict"]["rss"]["ok"])
    check_true("给出优化建议", bool(r4.get("tips")),
               f"（{len(r4.get('tips', []))} 条）")

    log("      · 贡献率")
    check("RSS 贡献率合计 = 1", sum(c["share_rss"] for c in r4["contrib"]), 1.0, 1e-9)
    check("WC 贡献率合计 = 1", sum(c["share_wc"] for c in r4["contrib"]), 1.0, 1e-9)
    check("等环时单环统计法贡献率", r4["contrib"][0]["share_rss"], 0.2, 1e-9)
    check_true("贡献率按降序排列",
               all(r4["contrib"][i]["share_rss"] >= r4["contrib"][i + 1]["share_rss"]
                   for i in range(len(r4["contrib"]) - 1)))


def test_thermal():
    log("")
    log("【10】热膨胀修正（20 ℃ 基准，f = 1 + α·ΔT）")
    lh = [new_link(no="A1", nominal=100.0, es=0.05, ei=-0.05,
                   alpha=23.0, temp=60.0)]
    c = analyze(lh, use_thermal=True)
    f = 1 + 23e-6 * 40
    check("工作温度下的基本尺寸", c["nominal"], 100.0 * f, 1e-12)
    check("工作温度下的公差带", c["wc"]["T"], 0.1 * f, 1e-12)
    check("关闭热修正后不变", analyze(lh, use_thermal=False)["nominal"], 100.0, 1e-12)


def test_explicit_xi():
    log("")
    log("【11a】显式传递系数 ξ（斜面 / 投影等非平行环）")
    # 默认：不显式给 ξ 时按 sign 取 ±1
    check("默认 ξ（增环）", link_calc(new_link(nominal=10, es=0.05, ei=-0.05))["xi"], 1)
    check("默认 ξ（减环）",
          link_calc(new_link(nominal=10, es=0.05, ei=-0.05, sign=-1))["xi"], -1)
    # 显式 ξ = 0.5（cos60°）：单环 ±0.05 → WC 半带 = 0.5×0.05 = 0.025，N₀ = 5
    r = analyze([new_link(nominal=10.0, es=0.05, ei=-0.05, xi=0.5)])
    check("ξ=0.5 单环 N₀", r["nominal"], 5.0, 1e-12)
    check("ξ=0.5 单环 WC 半带", r["wc"]["T"] / 2.0, 0.025, 1e-12)
    check("ξ=0.5 单环 RSS 半带", r["rss"]["T"] / 2.0, 0.025, 1e-12)
    # 显式负 ξ：-0.707（投影方向反向）
    r2 = analyze([new_link(nominal=10.0, es=0.05, ei=-0.05, xi=-0.707)])
    check("ξ=-0.707 单环 N₀", r2["nominal"], -7.07, 1e-12)
    check("ξ=-0.707 WC 半带", r2["wc"]["T"] / 2.0, 0.03535, 1e-9)
    # allocate 里 dict(l) 复制环，应保留显式 ξ
    al = allocate([new_link(nominal=10.0, es=0.05, ei=-0.05, xi=0.5)],
                  closing_tol=0.1, method="equal", rule="rss")
    check("分配复算保留显式 ξ",
          link_calc(al["new_links"][0])["xi"], 0.5, 1e-12)


def test_n_sigma():
    log("")
    log("【11b】统计法评估带宽 n·σ 可选（华为表格默认 ±6σ）")
    L = [new_link(no=f"A{i}", nominal=10.0 + i, es=0.05, ei=-0.05)
         for i in range(1, 6)]
    r6 = analyze(L)
    check("默认 n_sigma", r6["n_sigma"], 6.0, 1e-12)
    check("默认 T_rss = 6σ₀", r6["rss"]["T"], 6.0 * r6["rss"]["sigma"], 1e-12)
    r4 = analyze(L, n_sigma=4.0)
    check("n=4 记录", r4["rss"]["n_sigma"], 4.0, 1e-12)
    check("n=4 T_rss = 4σ₀", r4["rss"]["T"], 4.0 * r4["rss"]["sigma"], 1e-12)
    # σ₀ 与 WC 不随 n 变——变的只是评估带宽
    check("σ₀ 不随 n 变", r4["rss"]["sigma"], r6["rss"]["sigma"], 1e-12)
    check("WC 不随 n 变", r4["wc"]["T"], r6["wc"]["T"], 1e-12)
    check("T(n=4) / T(n=6) = 2/3", r4["rss"]["T"] / r6["rss"]["T"], 2.0 / 3.0, 1e-12)
    try:
        analyze(L, n_sigma=1.0)
        check_true("n 越界应报错", False, "（未抛异常）")
    except DesignError:
        check_true("n 越界应报错", True)


# =====================================================================
# 二、示意图几何自检
# =====================================================================

def test_diagram_geometry():
    """示意图必须：(a) 绘制不抛异常；(b) 图形完整落在卡片内。

    paintEvent 里对异常做了兜底（画一行「示意图绘制失败」），
    所以界面冒烟发现不了绘制崩溃 —— 这里直接调 _paint 让异常抛出来。

    几何断言不用「按填充色找像素」：标注文字的反锯齿灰像素会把包围盒撑大，
    误判成越界。改为读控件自己记录的 self._geom（像素级真实几何）。
    """
    log("")
    log("【11】示意图几何自检（不抛异常 + 图形不越出卡片）")
    try:
        from PySide6.QtGui import QImage, QPainter
        from PySide6.QtWidgets import QApplication

        from ui.diagram import (BandDiagram, ChainDiagram, ContribBar,
                                HistogramDiagram)

        if QApplication.instance() is None:
            QApplication(sys.argv)

        def render(wdg, w: int, h: int):
            """把控件压到指定尺寸后直接调 _paint，返回实际生效的 (宽, 高)。

            控件自己声明了最小尺寸（如 ChainDiagram 是 440×300），
            直接 resize 会被 Qt 夹回最小值 —— 那时 self.width() 仍是 440，
            却把画面画进 320 宽的图里，断言就张冠李戴了。
            所以测小窗口前必须先清掉最小尺寸。
            """
            wdg.setMinimumSize(0, 0)
            wdg.resize(w, h)
            aw, ah = wdg.width(), wdg.height()
            img = QImage(aw, ah, QImage.Format.Format_ARGB32)
            img.fill(0xFFFFFFFF)
            p = QPainter(img)
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            try:
                wdg._paint(p)      # 直接调用：异常不被 paintEvent 的兜底吞掉
            finally:
                p.end()
            return aw, ah

        res = analyze(default_links())
        mc = monte_carlo(default_links(), n=40000, seed=7)

        def inside_box(tag, w, h, boxes, kind):
            """boxes: [(x0, y0, x1, y1)]"""
            if not check_true(f"{tag} 记录了几何", len(boxes) > 0,
                              f"（{len(boxes)} 个 {kind}）"):
                return
            bad = []
            for i, (x0, y0, x1, y1) in enumerate(boxes):
                if not (0.0 <= x0 and x1 <= w and 0.0 <= y0 and y1 <= h):
                    bad.append((i, x0, y0, x1, y1))
            check_true(f"{tag} 全部 {kind} 在卡片内", not bad,
                       f"（越界 {len(bad)} 个）" if bad else "")
            for i, x0, y0, x1, y1 in bad[:4]:
                log(f"      └ 越界 #{i} x[{x0:.0f},{x1:.0f}] y[{y0:.0f},{y1:.0f}]"
                    f" 窗口 {w}×{h}")
            # 逐项几何记录，便于人工复核
            for i, (x0, y0, x1, y1) in enumerate(boxes[:6]):
                log(f"      └ {kind}{i + 1} x[{x0:.0f},{x1:.0f}] "
                    f"y[{y0:.0f},{y1:.0f}] in {w}×{h}")

        # 覆盖宽扁 / 窄高 / 极小四种窗口比例
        SIZES = ((700, 300), (560, 260), (900, 340), (320, 200))

        # ---- 尺寸链简图 ----
        for w, h in SIZES:
            d = ChainDiagram()
            d.set_result(res)
            aw, ah = render(d, w, h)
            check_true(f"尺寸链图@{w}x{h} 尺寸生效", (aw, ah) == (w, h),
                       f"（实际 {aw}×{ah}）")
            rows = d._geom.get("rows") or []
            # 尺寸界线与标签都挂在尺寸线上下，留 ±30 px 余量
            box = [(r["xa"], r["y"] - 30, r["xb"], r["y"] + 30) for r in rows]
            inside_box(f"尺寸链图@{w}x{h}", aw, ah, box, "环")

        # ---- 公差带图 ----
        for w, h in SIZES:
            d = BandDiagram()
            d.set_result(res)
            aw, ah = render(d, w, h)
            check_true(f"公差带图@{w}x{h} 尺寸生效", (aw, ah) == (w, h),
                       f"（实际 {aw}×{ah}）")
            rows = d._geom.get("rows") or []
            box = [(r["xa"], r["y"] - 12, r["xb"], r["y"] + 12) for r in rows]
            inside_box(f"公差带图@{w}x{h}", aw, ah, box, "带")

        # ---- 蒙特卡洛直方图 ----
        for w, h in SIZES:
            d = HistogramDiagram()
            d.set_result(mc)
            aw, ah = render(d, w, h)
            check_true(f"直方图@{w}x{h} 尺寸生效", (aw, ah) == (w, h),
                       f"（实际 {aw}×{ah}）")
            bars = d._geom.get("bars") or []
            box = [(b["xa"], b["top"], b["xb"], float(ah)) for b in bars]
            inside_box(f"直方图@{w}x{h}", aw, ah, box, "柱")

        # ---- 规格限与数据同量级时，显示量程应扩到含规格限，分布居中 ----
        # （回归：曾把「数据起点」和「显示量程」用同一个变量，
        #   扩量程后柱子整体左移并被截断，看起来像分布偏了。）
        mc2 = monte_carlo(default_links(), n=40000, seed=7,
                          target={"es": 0.25, "ei": -0.25})
        d = HistogramDiagram()
        d.set_result(mc2)
        render(d, 700, 320)
        bars = d._geom.get("bars") or []
        if check_true("扩量程算例有柱", len(bars) > 0):
            left = bars[0]["xa"] - 22.0
            right = 678.0 - bars[-1]["xb"]
            check_true("扩量程后分布不再占满全宽",
                       left > 40 and right > 40,
                       f"（左 {left:.0f} / 右 {right:.0f}）")
            check_true("扩量程后分布左右基本对称（未被平移截断）",
                       abs(left - right) < 40,
                       f"（左 {left:.0f} / 右 {right:.0f}）")

        # ---- 贡献率条形图 ----
        for w, h in SIZES:
            d = ContribBar()
            d.set_rows(res["contrib"])
            aw, ah = render(d, w, h)
            check_true(f"贡献率图@{w}x{h} 尺寸生效", (aw, ah) == (w, h),
                       f"（实际 {aw}×{ah}）")
            rows = d._geom.get("rows") or []
            box = [(r["top_x"], r["y"] - 10,
                    r["top_x"] + r["top_w"], r["y"] + 10) for r in rows]
            inside_box(f"贡献率图@{w}x{h}", aw, ah, box, "条")

        # ---- 极端工况：空数据不能崩 ----
        for cls, setter in ((ChainDiagram, "set_result"),
                            (BandDiagram, "set_result"),
                            (HistogramDiagram, "set_result")):
            d = cls()
            getattr(d, setter)(None)
            render(d, 600, 260)
        d = ContribBar()
        d.set_rows([])
        render(d, 600, 260)
        check_true("空数据不崩", True, "（4 个控件全部通过）")
    except Exception as exc:  # noqa: BLE001
        global FAIL
        FAIL += 1
        log(f"  ✗ 示意图几何自检失败：{exc}")
        log(traceback.format_exc())


# =====================================================================
# 三、界面冒烟
# =====================================================================

def test_ui():
    log("")
    log("【12】界面冒烟 + 截图")
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication, QMessageBox

        from app import APP_NAME, APP_VERSION, MainWindow
        from ui import theme

        # 冒烟阶段不允许弹模态框（会把无人值守的测试进程挂住），改为记录
        popups: list[tuple[str, str]] = []

        def _rec(kind):
            def f(_parent, title="", text="", *a, **k):
                popups.append((kind, f"{title} | {text}"))
                return QMessageBox.StandardButton.Ok
            return staticmethod(f)

        QMessageBox.warning = _rec("warning")
        QMessageBox.information = _rec("information")
        QMessageBox.critical = _rec("critical")

        app = QApplication.instance() or QApplication(sys.argv)
        app.setStyleSheet(theme.stylesheet())
        win = MainWindow()
        # 真实字体渲染但不真弹窗：offscreen 平台没有字体库会出豆腐块
        win.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        win.resize(1440, 920)
        win.show()
        for _ in range(8):
            app.processEvents()

        os.makedirs(OUT_DIR, exist_ok=True)
        names = ["tol", "sim", "alloc", "std", "help"]
        pages = [win.tabs.widget(i) for i in range(win.tabs.count())]
        check("页签数量", len(pages), 5)
        check_true("窗口标题含程序名", APP_NAME in win.windowTitle(),
                   f"（{win.windowTitle()}）")
        check_true("版本号非空", bool(APP_VERSION))

        for i, pg in enumerate(pages):
            win.tabs.setCurrentIndex(i)
            for _ in range(4):
                app.processEvents()
            if hasattr(pg, "recalc"):
                pg.recalc()
            win.layout().activate()
            for _ in range(8):
                app.processEvents()
            shot = os.path.join(OUT_DIR, f"shot_{i}_{names[i]}.png")
            check_true(f"截图 {names[i]}", win.grab().save(shot))

        # ---- 尺寸链页：表格与结果 ----
        tol = pages[0]
        check("组成环默认行数", tol.table.rowCount(), 5)
        check_true("已算出结果", tol._res is not None)
        tol._add_link()
        check("新增一环后 6 行", tol.table.rowCount(), 6)
        tol._del_link()
        check("删除后回到 5 行", tol.table.rowCount(), 5)

        # ---- 组成环表的只读计算列必须被回填（否则要空着三列很浪费）----
        check_true("公差列已回填", tol.table.item(0, 7).text() not in ("", "—"),
                   f"（{tol.table.item(0, 7).text()}）")
        check("ξ 列已回填（自动档显示实际系数）",
              tol.table.cellWidget(0, 8).currentText(), "自动（+1）")
        check_true("贡献率列已回填",
                   tol.table.item(0, 9).text().endswith("%"),
                   f"（{tol.table.item(0, 9).text()}）")
        # 回填必须屏蔽 cellChanged，否则 recalc 会自激成死循环；
        # 能跑到这里就说明没锁死，再确认一次结果仍在
        check_true("回填后结果依然有效（未自激死循环）", tol._res is not None)

        # ---- ξ 下拉：显式系数（斜面/投影环）与自动档互相切换 ----
        from PySide6.QtWidgets import QComboBox  # noqa: E402
        from ui.pages import STATE  # noqa: E402
        win.tabs.setCurrentIndex(0)
        for _ in range(6):
            app.processEvents()
        xb = tol.table.cellWidget(0, 8)
        check_true("ξ 列是下拉框", isinstance(xb, QComboBox))
        check("ξ 选项数", xb.count(), 11)
        xb.setCurrentIndex(xb.findText("+0.707"))
        for _ in range(6):
            app.processEvents()
        tol.recalc()        # _kick 走 240ms 防抖定时器，测试里直接触发
        check("显式 ξ 已写入状态", STATE.links[0]["xi"], 0.707, 1e-12)
        # 默认 5 环 N₀=60，A1 基本尺寸 10 → ξ 变 0.707 后 N₀ = 60 − 10 + 7.07
        check("显式 ξ 改变封闭环 N₀", round(tol._res["nominal"], 4), 57.07, 1e-9)
        check_true("环型随 ξ 符号联动",
                   tol.table.cellWidget(0, 5).currentIndex() == 0)
        sb = tol.table.cellWidget(0, 5)
        sb.setCurrentIndex(1)                       # 切「减环」→ 回到自动 −1
        for _ in range(6):
            app.processEvents()
        tol.recalc()
        check("切环型清空显式 ξ", STATE.links[0]["xi"], None)
        check("减环后 ξ 自动取 −1", round(tol._res["nominal"], 4), 40.0, 1e-9)
        sb.setCurrentIndex(0)                       # 切回增环，恢复默认 60
        for _ in range(6):
            app.processEvents()
        tol.recalc()
        check("恢复增环后 N₀", round(tol._res["nominal"], 4), 60.0, 1e-9)

        # ---- 标准公差选取弹窗：填上 / 下偏差 ----
        from ui.pages import _STD_CATS, StdDevDialog  # noqa: E402
        check("弹窗分类数", len(_STD_CATS), 6)
        dlg = StdDevDialog(tol, 0)
        # 常用配合：H7 @ ⌀10 → +0.015 / 0（kernel 已对照标准表验证过）
        dlg.cb_cat.setCurrentIndex(_STD_CATS.index("常用配合"))
        dlg.t.selectRow(0)
        dlg._refresh_btns()
        dlg.in_nom.set_value(10.0)
        e0 = dlg._entries()[0]
        es, ei, _tx = dlg._calc(e0, 0)
        check("H7@10 上偏差", round(es, 4), 0.015)
        check("H7@10 下偏差", round(ei, 4), 0.0)
        dlg._apply(e0, 0, (es, ei))
        check("配合条目已填入选中环",
              (round(STATE.links[0]["es"], 4), round(STATE.links[0]["ei"], 4)),
              (0.015, 0.0))
        # PCB：PTH ⌀≤0.8 → ±0.08
        dlg.cb_cat.setCurrentIndex(_STD_CATS.index("PCB"))
        pcb = dlg._entries()
        i1 = next(i for i, e in enumerate(pcb) if e["name"].startswith("金属化孔 PTH ⌀≤0.8"))
        dlg.t.selectRow(i1)
        dlg._refresh_btns()
        es, ei, _tx = dlg._calc(pcb[i1], 0)
        check("PCB PTH ±0.08", (round(es, 3), round(ei, 3)), (0.08, -0.08))
        dlg._apply(pcb[i1], 0, (es, ei))
        check("PCB 条目已填入选中环",
              (round(STATE.links[0]["es"], 3), round(STATE.links[0]["ei"], 3)),
              (0.08, -0.08))
        # 螺栓通孔 GB/T 5277：M6 精装配 ⌀6.4 H12 → +0.150 / 0，且更新基本尺寸
        dlg.cb_cat.setCurrentIndex(_STD_CATS.index("螺栓通孔 GB/T 5277"))
        e2 = dlg._entries()[3]                      # 第 4 条 = M6
        check_true("5277 条目是 M6", e2["name"].startswith("M6"), e2["name"][:6])
        es, ei, _tx = dlg._calc(e2, 0)
        check("M6 精装 H12@⌀6.4", (round(es, 4), round(ei, 4)), (0.15, 0.0))
        dlg._apply(e2, 0, (es, ei))
        check("通孔条目同步基本尺寸", STATE.links[0]["nominal"], 6.4, 1e-12)
        # 连接器 + 加工方式两类至少能算出数值（不抛异常）
        dlg.cb_cat.setCurrentIndex(_STD_CATS.index("连接器"))
        dlg.t.selectRow(0)
        dlg._refresh_btns()
        es, ei, _tx = dlg._calc(dlg._entries()[0], 0)
        check_true("连接器条目可换算", es > 0 and ei < 0,
                   f"（+{es:.4f} / {ei:.4f}）")
        dlg.cb_cat.setCurrentIndex(_STD_CATS.index("加工方式 → IT"))
        dlg.in_nom.set_value(30.0)
        es, ei, _tx = dlg._calc(dlg._entries()[0], 0)   # 精车 IT8 @30 → ±0.0165
        check("精车 IT8@30 半带", round(es, 4), 0.0165)
        dlg.close()

        # ---- 组成环表本体：所有行直接可见、无内部滚动条（水平/垂直都不要）----
        from PySide6.QtGui import QFontMetrics  # noqa: E402
        from PySide6.QtWidgets import QHeaderView  # noqa: E402
        from ui.pages import _LINK_COLS  # noqa: E402
        win.tabs.setCurrentIndex(0)
        for _ in range(8):
            app.processEvents()
        lt = tol.table
        need_h = (lt.horizontalHeader().sizeHint().height()
                  + sum(lt.rowHeight(r) for r in range(lt.rowCount())))
        check_true("组成环表高度装下所有行", lt.height() >= need_h,
                   f"（高 {lt.height()} / 需 {need_h}，{lt.rowCount()} 行）")
        check_true("组成环表无垂直滚动条", lt.verticalScrollBar().maximum() == 0,
                   f"（滚动上限 {lt.verticalScrollBar().maximum()}）")
        check_true("组成环表无水平滚动条",
                   lt.horizontalScrollBar().maximum() == 0,
                   f"（合计列宽 "
                   f"{sum(lt.columnWidth(i) for i in range(lt.columnCount()))}"
                   f" / 视口 {lt.viewport().width()}）")
        # 每列宽度必须容纳「表头文字 / 单元格内容 / 下拉框」三者的最大值，
        # 否则出现省略号或下拉框箭头被裁（实测：环型 62→需 76、分布状态 96→需 102）
        hfm = QFontMetrics(lt.horizontalHeader().font())
        vfm = QFontMetrics(lt.font())
        bad = []
        for i, label in enumerate(_LINK_COLS):
            need = max((hfm.horizontalAdvance(x) for x in label.split("\n")),
                       default=0) + 26
            for r in range(lt.rowCount()):
                w = lt.cellWidget(r, i)
                if w is not None:
                    need = max(need, w.sizeHint().width() + 8)
                it = lt.item(r, i)
                if it is not None:
                    need = max(need, vfm.horizontalAdvance(it.text()) + 20)
            if lt.columnWidth(i) + 1 < need:
                bad.append(f"{label.splitlines()[0]} 需{need}/给{lt.columnWidth(i)}")
        check_true("组成环表各列宽度足够（文字与下拉框不被裁）", not bad,
                   "；".join(bad))

        # ---- 表头悬浮说明：用户不知道 ξ 是什么，靠 tooltip 现场教学 ----
        tips_bad = [c for i, c in enumerate(_LINK_COLS)
                    if not lt.horizontalHeaderItem(i).toolTip()]
        check_true("全部表头都有悬浮说明", not tips_bad,
                   f"（缺：{tips_bad}）")
        check("ξ 表头写全称", lt.horizontalHeaderItem(8).text(), "传递系数\nξ")
        check_true("名称列吃掉余量（贡献率列不再独吞空白）",
                   lt.horizontalHeader().sectionResizeMode(1)
                   == QHeaderView.ResizeMode.Stretch)
        check("贡献率列定宽不再拉伸", lt.columnWidth(9), 110)
        check_true("统计法评估带宽下拉存在",
                   tol.cb_nsigma.currentText().startswith("±6σ"),
                   f"（{tol.cb_nsigma.currentText()}）")
        tol.cb_nsigma.setCurrentIndex(2)          # 切 ±4σ
        for _ in range(6):
            app.processEvents()
        check("切 ±4σ 后 n_sigma 生效", tol._res["rss"]["n_sigma"], 4.0, 1e-12)
        check("RSS 卡片标题跟随口径", tol.m_rss.name.text(), "统计法 RSS ±4σ")
        r6 = tol._res["rss"]["sigma"]
        check("±4σ 半带 = 2σ₀", tol._res["rss"]["T"] / 2.0, 2.0 * r6, 1e-9)
        tol.cb_nsigma.setCurrentIndex(0)          # 恢复默认 ±6σ
        for _ in range(6):
            app.processEvents()

        # ---- 公差仿真页 ----
        sim = pages[1]
        check("随机种子按整数显示", sim.in_seed.edit.text(), "20260918")
        sim.run()
        check_true("仿真产出结果", sim._mc is not None,
                   f"（n = {sim._mc['n']:,}）" if sim._mc else "")
        if sim._mc:
            check_true("仿真合格率在 0~1", 0.0 <= sim._mc["pass_rate"] <= 1.0,
                       f"（{sim._mc['pass_rate'] * 100:.3f}%）")

        # ---- 公差分配页 ----
        alloc = pages[2]
        alloc.run()
        check_true("分配产出结果", alloc._res is not None)
        if alloc._res:
            check("分配结果行数 = 组成环数", len(alloc._res["rows"]), 5)

        # ---- 标准公差库页 ----
        std = pages[3]
        std.query()
        check_true("标准库查询给出文字结论",
                   len(std.lab_q.text()) > 20, f"（{std.lab_q.text()[:40]}…）")

        # ---- 表格高度必须装得下所有行：否则末行被截掉、还会冒出内部滚动条 ----
        for idx, name, attr in ((0, "贡献率表", "t_contrib"),
                                (1, "灵敏度表", "t_sens"),
                                (2, "分配结果表", "t_res"),
                                (3, "IT 标准表", "t_it"),
                                (3, "σ 对照表", "t_sig")):
            win.tabs.setCurrentIndex(idx)
            for _ in range(6):
                app.processEvents()
            tb = getattr(pages[idx], attr)
            if not check_true(f"{name}有数据", tb.rowCount() > 0,
                              f"（{tb.rowCount()} 行）"):
                continue
            need = tb.horizontalHeader().height() + sum(
                tb.rowHeight(r) for r in range(tb.rowCount()))
            check_true(f"{name}无内部滚动条",
                       tb.verticalScrollBar().maximum() == 0,
                       f"（高 {tb.height()} / 需 {need}，"
                       f"滚动上限 {tb.verticalScrollBar().maximum()}）")

        # ---- 报告生成 ----
        from ui.pages import grab_widget_png, report_html, report_text
        h = report_html("测试", [("a", "b")], [("一", [("k", "v")])], [], [])
        t = report_text("测试", [("a", "b")], [("一", [("k", "v")])], [], [])
        check_true("HTML 报告非空", len(h) > 800, f"（{len(h)} 字符）")
        check_true("TXT 报告非空", len(t) > 300, f"（{len(t)} 字符）")

        # ---- 报告必须带图：尺寸链 / 公差带 / 贡献率三张，base64 内嵌 ----
        png = grab_widget_png(tol.d_chain)
        check_true("尺寸链图可渲染成 PNG", len(png) > 2000, f"（{len(png):,} B）")
        h2 = report_html("测试", [], [("一", [("k", "v")])], [], [],
                         images=[("尺寸链简图", png), ("公差带图", png),
                                 ("各环贡献率图", png)])
        n_img = h2.count("data:image/png;base64,")
        check("HTML 报告内嵌三张图", n_img, 3)
        check_true("图表带标题", all(k in h2 for k in
                                     ("尺寸链简图", "公差带图", "各环贡献率图")))
        t2 = report_text("测试", [], [], [], [],
                         images=[("尺寸链简图", png)])
        check_true("TXT 版标注图形省略", "【图】尺寸链简图" in t2
                   and "HTML 版" in t2)

        # ---- 报告导出链路（不落盘，只走生成分支）----
        check_true("报告含标准依据", "GB/T 1800.1-2020" in t)
        check_true("报告含免责声明", "免责声明" in t)

        win.close()
        check_true("冒烟期间没有意外弹窗", not popups,
                   f"（{popups}）" if popups else "")
    except Exception as exc:  # noqa: BLE001
        global FAIL
        FAIL += 1
        log(f"  ✗ 界面冒烟失败：{exc}")
        log(traceback.format_exc())


# =====================================================================

def main():
    only_num = "--no-ui" in sys.argv
    log("=" * 70)
    log("尺寸链公差分析计算器 —— 自检")
    log("=" * 70)
    for fn in (test_huawei_example, test_sigma_table, test_it_table,
               test_deviations, test_auto_signs, test_allocate,
               test_monte_carlo, test_capability, test_thermal,
               test_explicit_xi, test_n_sigma):
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            global FAIL
            FAIL += 1
            log(f"  ✗ {fn.__name__} 抛异常：{exc}")
            log(traceback.format_exc())
    if not only_num:
        test_diagram_geometry()
        test_ui()

    log("")
    log("=" * 70)
    log(f"结果：通过 {PASS} 项，失败 {FAIL} 项")
    log("=" * 70)

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "selftest.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(LOG))
    print("\n".join(LOG))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
