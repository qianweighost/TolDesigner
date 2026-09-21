# -*- coding: utf-8 -*-
"""界面状态持久化 —— 把上次编辑的尺寸链自动存盘，下次启动自动恢复。

为什么单独一个模块：序列化/反序列化要不依赖 Qt，自检才能在无 GUI 的情况下
验「存盘 → 读回 → 逐字节一致」这条链；也能被以后的命令行/批处理复用。

存放位置（可用环境变量覆盖，便于自检与多机共享）：

    Windows   %APPDATA%\\TolDesigner\\last_state.json
    其它      ~/.config/TolDesigner/last_state.json
    覆盖      TOLDESIGNER_STATE_FILE=完整文件路径

写盘用「临时文件 + os.replace」的原子替换：中途断电/被杀进程也只会丢掉这一次
修改，不会留下半截 JSON 把下次启动弄崩。读取端对任何异常都返回 None（当作没有
历史记录），坏文件永远不会挡住程序启动。
"""
from __future__ import annotations

import datetime
import json
import os
import tempfile

from .tol_core import (DEFAULT_DIST, DEFAULT_SIGMA_GRADE, DIST_KEYS,
                       SIGMA_GRADE_MAX, SIGMA_GRADE_MIN, check_sigma_grade,
                       new_link)

SCHEMA = 1
APP_TAG = "TolDesigner"
ENV_PATH = "TOLDESIGNER_STATE_FILE"
ENV_NO_RESTORE = "TOLDESIGNER_NO_RESTORE"      # =1 时启动不恢复（自检用）
ENV_NO_AUTOSAVE = "TOLDESIGNER_NO_AUTOSAVE"    # =1 时不自动写盘（自检用）


# =====================================================================
# 路径与环境开关
# =====================================================================

def state_path() -> str:
    """状态文件路径（不保证存在）。"""
    env = os.environ.get(ENV_PATH, "").strip()
    if env:
        return env
    if os.name == "nt":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, APP_TAG, "last_state.json")


def restore_disabled() -> bool:
    return os.environ.get(ENV_NO_RESTORE, "").strip() == "1"


def autosave_disabled() -> bool:
    return os.environ.get(ENV_NO_AUTOSAVE, "").strip() == "1"


# =====================================================================
# 数值清洗：磁盘上的东西是不可信的，全部走一遍校验
# =====================================================================

def _num(v, default=0.0):
    """把 ""/None/"1,5"/"abc" 一律变成 float（失败取默认）。"""
    if v is None or isinstance(v, bool):
        return default
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace("，", "").replace(",", "")
    if not s:
        return default
    try:
        return float(s)
    except ValueError:
        return default


def _opt_num(v):
    """可空数值：空字符串/None → None（表示「自动」）。"""
    if v is None:
        return None
    if isinstance(v, str) and not v.strip():
        return None
    return _num(v)


def clean_link(raw: dict) -> dict | None:
    """把一个原始 dict 规范化成合法的组成环；坏到没法用则返回 None。"""
    if not isinstance(raw, dict):
        return None
    dist = str(raw.get("dist") or DEFAULT_DIST)
    if dist not in DIST_KEYS:
        dist = DEFAULT_DIST
    try:
        grade = check_sigma_grade(raw.get("sigma_grade", DEFAULT_SIGMA_GRADE))
    except Exception:  # noqa: BLE001 —— 越界/非法一律回落默认档
        grade = DEFAULT_SIGMA_GRADE
    xi = _opt_num(raw.get("xi"))
    k = _opt_num(raw.get("k"))
    e = _opt_num(raw.get("e"))
    lk = new_link(
        no=str(raw.get("no") or ""),
        name=str(raw.get("name") or ""),
        nominal=_num(raw.get("nominal")),
        es=_num(raw.get("es")),
        ei=_num(raw.get("ei")),
        sign=-1 if _num(raw.get("sign"), 1) < 0 else 1,
        dist=dist,
        enabled=bool(raw.get("enabled", True)),
        alpha=_num(raw.get("alpha")),
        temp=_num(raw.get("temp"), 20.0),
        k=k, e=e, xi=xi, sigma_grade=grade,
        note=str(raw.get("note") or ""),
    )
    return lk


def clean_links(raw) -> list[dict]:
    out = []
    if isinstance(raw, list):
        for item in raw:
            lk = clean_link(item)
            if lk is not None:
                out.append(lk)
    return out


def clean_target(raw) -> dict:
    """封闭环要求 {"nominal": ""|float, "es": float, "ei": float}。"""
    if not isinstance(raw, dict):
        return {"nominal": "", "es": 0.25, "ei": -0.25}
    nom = raw.get("nominal")
    nom_out = "" if nom in (None, "", "auto") else _num(nom)
    return {"nominal": nom_out,
            "es": _num(raw.get("es"), 0.25),
            "ei": _num(raw.get("ei"), -0.25)}


def clean_project(raw) -> dict:
    if not isinstance(raw, dict):
        raw = {}
    return {k: str(raw.get(k) or "") for k in ("name", "code", "author", "note")}


def clean_sim(raw) -> dict:
    if not isinstance(raw, dict):
        raw = {}
    return {"n": int(_num(raw.get("n"), 100000) or 100000),
            "seed": int(_num(raw.get("seed"), 20260918) or 20260918)}


def clean_alloc(raw) -> dict:
    if not isinstance(raw, dict):
        raw = {}
    return {"tol": _num(raw.get("tol"), 0.25),
            "method": str(raw.get("method") or ""),
            "rule": str(raw.get("rule") or ""),
            "keep": bool(raw.get("keep", True))}


def normalize(payload: dict) -> dict:
    """整份状态规范化（存盘与恢复共用同一套口径）。"""
    p = payload if isinstance(payload, dict) else {}
    try:
        n_sigma = check_sigma_grade(p.get("n_sigma", DEFAULT_SIGMA_GRADE))
    except Exception:  # noqa: BLE001
        n_sigma = DEFAULT_SIGMA_GRADE
    try:
        tab = int(_num(p.get("tab"), 0))
    except Exception:  # noqa: BLE001
        tab = 0
    return {
        "links": clean_links(p.get("links")),
        "target": clean_target(p.get("target")),
        "use_thermal": bool(p.get("use_thermal", False)),
        "n_sigma": n_sigma,
        "project": clean_project(p.get("project")),
        "sim": clean_sim(p.get("sim")),
        "alloc": clean_alloc(p.get("alloc")),
        "tab": max(0, tab),
        "version": str(p.get("version") or ""),
    }


# =====================================================================
# 存 / 读
# =====================================================================

def save(payload: dict, path: str | None = None) -> str:
    """原子写盘，返回写入路径。任何失败都抛出（调用方自行决定要不要提示）。"""
    p = path or state_path()
    d = os.path.dirname(p)
    if d:
        os.makedirs(d, exist_ok=True)
    doc = {"schema": SCHEMA, "app": APP_TAG,
           "saved_at": datetime.datetime.now().isoformat(timespec="seconds"),
           "state": normalize(payload)}
    fd, tmp = tempfile.mkstemp(dir=d or ".", prefix=".last_state-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=1)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, p)          # 原子替换，不会有半截文件
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
    return p


def load(path: str | None = None) -> dict | None:
    """读回状态；文件不存在 / JSON 坏了 / 结构不对 一律返回 None。"""
    p = path or state_path()
    try:
        with open(p, encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(doc, dict):
        return None
    state = doc.get("state")
    if not isinstance(state, dict):
        return None
    return normalize(state)


def clear(path: str | None = None) -> bool:
    """删除状态文件（「恢复出厂设置」用）；文件本来不存在也算成功。"""
    p = path or state_path()
    try:
        os.remove(p)
        return True
    except FileNotFoundError:
        return True
    except OSError:
        return False


def describe(payload: dict) -> str:
    """一行摘要，给界面上的提示文字用。"""
    p = normalize(payload)
    n = len(p["links"])
    n_on = sum(1 for l in p["links"] if l.get("enabled", True))
    return (f"{n} 个组成环（启用 {n_on}）· 统一 σ 等级 ±{p['n_sigma']:g}σ"
            f" · 项目「{p['project']['name'] or '未命名'}」")


__all__ = ["SCHEMA", "ENV_PATH", "ENV_NO_RESTORE", "ENV_NO_AUTOSAVE",
           "state_path", "restore_disabled", "autosave_disabled",
           "clean_link", "clean_links", "normalize", "save", "load", "clear",
           "describe",
           # 供外部构造默认值时用到的兜底常量
           "SIGMA_GRADE_MIN", "SIGMA_GRADE_MAX"]
