# -*- coding: utf-8 -*-
"""exe 启动存活验证。

打包成 --windowed 单文件后，程序没有控制台、也没有返回值可看，
唯一能自动化验证的就是「起来之后不崩、能一直活着」。

分别在两种平台插件下各启动一次：
  · 默认平台      —— 和用户双击运行完全一致（会短暂闪现窗口）
  · offscreen     —— 无头环境，验证不依赖真实显示器也能起来

用法：
    python tools/smoke_exe.py [exe路径] [每档观察秒数]
"""
from __future__ import annotations

import os
import subprocess
import sys
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_EXE = os.path.join(_ROOT, "dist", "尺寸链公差分析计算器.exe")


def run_once(exe: str, tag: str, extra_env: dict, wait: float) -> bool:
    env = os.environ.copy()
    env.update(extra_env)
    # 单文件 exe 首次启动要解压到临时目录，给足时间
    p = subprocess.Popen([exe], env=env, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT)
    time.sleep(wait)
    alive = p.poll() is None
    if alive:
        print(f"  ✓ [{tag}] 启动后存活 {wait:.0f}s（pid={p.pid}）")
        p.terminate()
        try:
            p.wait(timeout=15)
        except subprocess.TimeoutExpired:
            p.kill()
            p.wait(timeout=10)
    else:
        print(f"  ✗ [{tag}] 提前退出，returncode={p.returncode}")
        try:
            out = p.stdout.read().decode("utf-8", "replace")
        except Exception:  # noqa: BLE001
            out = ""
        if out.strip():
            print("     ---- 输出 ----")
            for line in out.strip().splitlines()[:40]:
                print("     " + line)
    return alive


def main() -> int:
    exe = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_EXE
    wait = float(sys.argv[2]) if len(sys.argv) > 2 else 12.0
    if not os.path.isfile(exe):
        print(f"找不到 exe：{exe}")
        return 2
    size_mb = os.path.getsize(exe) / 1024 / 1024
    print("=" * 64)
    print(f"exe 启动存活验证：{os.path.basename(exe)}  ({size_mb:.1f} MB)")
    print("=" * 64)

    ok = True
    ok &= run_once(exe, "offscreen", {"QT_QPA_PLATFORM": "offscreen"}, wait)
    ok &= run_once(exe, "默认平台", {}, wait)

    print("=" * 64)
    print("结果：" + ("全部存活 ✓" if ok else "存在异常 ✗"))
    print("=" * 64)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
