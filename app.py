# -*- coding: utf-8 -*-
"""尺寸链公差分析计算器 —— 程序入口。

运行：  python app.py
打包：  pyinstaller --noconsole --onefile --name 尺寸链公差分析计算器 app.py
"""

from __future__ import annotations

import json
import os
import sys

# 保证从任意工作目录启动都能导入 core / ui 包
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from PySide6.QtCore import QSize, Qt, QTimer, QUrl  # noqa: E402
from PySide6.QtGui import QDesktopServices, QFont, QIcon, QPixmap  # noqa: E402
from PySide6.QtWidgets import (QApplication, QHBoxLayout, QLabel, QMainWindow,  # noqa: E402
                               QPushButton, QTabWidget, QVBoxLayout, QWidget)

from core import persist  # noqa: E402
from ui import icons, theme  # noqa: E402
from ui.pages import (AllocPage, HelpPage, SimPage, StdPage,  # noqa: E402
                      TolPage)

APP_NAME = "尺寸链公差分析计算器"
APP_VERSION = "1.4"
APP_SUB = ("尺寸链正算（极值法 / 统计法） · 公差分配反算 · "
           "蒙特卡洛仿真 · 标准公差库")

GITHUB_URL = "https://github.com/qianweighost/TolDesigner"
GITHUB_TEXT = "TolDesigner"
SITE_URL = "https://www.qianwei.asia"
SITE_TEXT = "qianwei.asia"

# 「设计计算器」家族统一标识：OringDesigner 系密封圈，DriveDesigner 系传动，
# 本程序系公差与尺寸链
FAMILY_TEXT = "设计计算器家族"

# 自动存盘周期：定时器只负责「兜底」，真正保证不丢数据的是关窗与切页时的存盘
AUTOSAVE_MS = 60000


class IconLink(QPushButton):
    """页眉上的图标链接：点击用系统默认浏览器打开。"""

    def __init__(self, url: str, idle: QPixmap, hover: QPixmap, px: int,
                 text: str = "", tip: str = "", parent=None):
        super().__init__(text, parent)
        self.url = url
        self.setObjectName("LinkBtn")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setIcon(QIcon(idle))
        self.setIconSize(QSize(px, px))
        self._idle, self._hover = QIcon(idle), QIcon(hover)
        if tip:
            self.setToolTip(tip)
        self.clicked.connect(self._open)

    def _open(self):
        QDesktopServices.openUrl(QUrl(self.url))

    def enterEvent(self, ev):
        self.setIcon(self._hover)
        super().enterEvent(ev)

    def leaveEvent(self, ev):
        self.setIcon(self._idle)
        super().leaveEvent(ev)


class Header(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Header")
        self.setFixedHeight(62)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(20, 10, 20, 10)
        lay.setSpacing(12)

        logo = QLabel("⇔")
        logo.setStyleSheet(f"color:{theme.ACCENT};font-size:26px;")
        lay.addWidget(logo)

        col = QVBoxLayout()
        col.setSpacing(1)
        t = QLabel(APP_NAME)
        t.setObjectName("Title")
        s = QLabel(APP_SUB)
        s.setObjectName("Subtitle")
        col.addWidget(t)
        col.addWidget(s)
        lay.addLayout(col)
        lay.addStretch(1)

        fam = QLabel(FAMILY_TEXT)
        fam.setObjectName("Subtitle")
        fam.setStyleSheet(f"color:{theme.TEXT_DIM};font-size:11px;")
        lay.addWidget(fam)

        ver = QLabel(f"v{APP_VERSION}")
        ver.setObjectName("Badge")
        lay.addWidget(ver)

        sep = QLabel()
        sep.setObjectName("HeaderSep")
        sep.setFixedWidth(1)
        sep.setFixedHeight(20)
        lay.addWidget(sep)

        px = 18
        gh = IconLink(GITHUB_URL,
                      icons.github_pixmap(px, theme.TEXT_MID),
                      icons.github_pixmap(px, theme.ACCENT),
                      px, "", f"项目源码：github.com/qianweighost/TolDesigner")
        gh.setFixedSize(30, 28)
        lay.addWidget(gh)

        site = IconLink(SITE_URL,
                        icons.globe_pixmap(px, theme.TEXT_MID),
                        icons.globe_pixmap(px, theme.ACCENT),
                        px, SITE_TEXT, f"个人网站：{SITE_TEXT}")
        site.setFixedHeight(28)
        lay.addWidget(site)


class MainWindow(QMainWindow):
    def __init__(self, restore: bool | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{APP_NAME}  v{APP_VERSION}")
        self.setWindowIcon(icons.app_icon())
        self.resize(1440, 920)
        self.setMinimumSize(1180, 740)

        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)
        lay = QVBoxLayout(root)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(Header())

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        wrap = QWidget()
        wl = QVBoxLayout(wrap)
        wl.setContentsMargins(4, 4, 4, 4)
        wl.addWidget(self.tabs)
        lay.addWidget(wrap, 1)

        self.p_tol = TolPage()
        self.p_sim = SimPage()
        self.p_alloc = AllocPage()
        self.p_std = StdPage()
        self.p_help = HelpPage()
        self.tabs.addTab(self.p_tol, "尺寸链计算")
        self.tabs.addTab(self.p_sim, "公差仿真")
        self.tabs.addTab(self.p_alloc, "公差分配")
        self.tabs.addTab(self.p_std, "标准公差库")
        self.tabs.addTab(self.p_help, "使用说明")

        # 各页共用同一份尺寸链数据（ui.pages.STATE），切页时把改动同步过去，
        # 否则在「公差分配」页应用了新公差，回到「尺寸链计算」页还是旧表。
        self.tabs.currentChanged.connect(self._sync_page)

        # ---- 上次编辑的自动恢复 / 自动存盘 ----
        self._restored = False
        self._last_saved = ""
        if restore is None:
            restore = not persist.restore_disabled()
        if restore:
            self.restore_last()
        self._autosave = QTimer(self)
        self._autosave.setInterval(AUTOSAVE_MS)
        self._autosave.timeout.connect(self.save_last)
        if not persist.autosave_disabled():
            self._autosave.start()

    # ---------------- 上次编辑的存取 ----------------
    def snapshot(self) -> dict:
        """把当前界面状态收成一份可序列化的 dict。"""
        from ui.pages import STATE
        # 输入框 → STATE 的同步平时靠 240 ms 防抖，关窗/存盘前要强制刷一次，
        # 否则刚敲进去还没到点的那次修改会丢
        try:
            self.p_tol.recalc()
        except Exception:  # noqa: BLE001
            pass
        return {
            "links": STATE.links,
            "target": STATE.target,
            "use_thermal": STATE.use_thermal,
            "n_sigma": STATE.n_sigma,
            "project": STATE.project,
            "sim": {"n": self.p_sim.in_n.value_or(100000),
                    "seed": self.p_sim.in_seed.value_or(20260918)},
            "alloc": {"tol": self.p_alloc.in_tol.value_or(0.25),
                      "method": self.p_alloc.in_method.current(),
                      "rule": self.p_alloc.in_rule.current(),
                      "keep": self.p_alloc.in_keep.is_checked()},
            "tab": self.tabs.currentIndex(),
            "version": APP_VERSION,
        }

    def save_last(self, force: bool = False) -> bool:
        """存盘；内容与上次相同就跳过（定时器每 60 s 叫一次，不必反复写盘）。"""
        if persist.autosave_disabled() and not force:
            return False
        try:
            data = persist.normalize(self.snapshot())
            blob = json.dumps(data, ensure_ascii=False, sort_keys=True)
            if not force and blob == self._last_saved:
                return False
            persist.save(data)
            self._last_saved = blob
            return True
        except Exception:  # noqa: BLE001 —— 存盘失败不该影响使用
            return False

    def restore_last(self) -> bool:
        """读回上次编辑；没有记录或文件损坏就保持默认示例。"""
        data = persist.load()
        if not data:
            return False
        from ui.pages import STATE
        if data.get("links"):
            STATE.links = [dict(l) for l in data["links"]]
        STATE.target = dict(data.get("target") or STATE.target)
        STATE.use_thermal = bool(data.get("use_thermal", False))
        STATE.n_sigma = data.get("n_sigma", STATE.n_sigma)
        proj = data.get("project") or {}
        for k in ("name", "code", "author", "note"):
            if proj.get(k):
                STATE.project[k] = proj[k]
        sim = data.get("sim") or {}
        self.p_sim.in_n.set_value(sim.get("n", 100000))
        self.p_sim.in_seed.set_value(sim.get("seed", 20260918))
        alloc = data.get("alloc") or {}
        self.p_alloc.in_tol.set_value(alloc.get("tol", 0.25))
        if alloc.get("method"):
            self.p_alloc.in_method.set_current(alloc["method"])
        if alloc.get("rule"):
            self.p_alloc.in_rule.set_current(alloc["rule"])
        self.p_alloc.in_keep.set_checked(bool(alloc.get("keep", True)))

        self.p_tol.load_from_state()
        tab = int(data.get("tab") or 0)
        if 0 <= tab < self.tabs.count():
            self.tabs.setCurrentIndex(tab)
        self._restored = True
        self._last_saved = json.dumps(data, ensure_ascii=False, sort_keys=True)
        return True

    def reset_to_default(self):
        """清掉历史记录并恢复出厂默认（示例数据）。"""
        persist.clear()
        self._last_saved = ""
        from ui.pages import STATE, ChainState
        fresh = ChainState()
        STATE.links = fresh.links
        STATE.target = dict(fresh.target)
        STATE.use_thermal = fresh.use_thermal
        STATE.n_sigma = fresh.n_sigma
        STATE.project = dict(fresh.project)
        self.p_tol.load_from_state()
        self.refresh_pages()

    def _sync_page(self, i: int):
        w = self.tabs.widget(i)
        if isinstance(w, TolPage):
            w.sync_from_state()
        elif hasattr(w, "refresh"):
            try:
                w.refresh()
            except Exception:  # noqa: BLE001
                pass
        # 换页是个天然的存档点（用户顺手切页后关窗口的概率很高）
        self.save_last()

    def refresh_pages(self):
        """供子页调用：STATE 被改动后，让所有页重新读取共享数据。"""
        self._sync_page(self.tabs.currentIndex())

    def keyPressEvent(self, ev):
        if ev.key() == Qt.Key.Key_F1:
            self.tabs.setCurrentIndex(self.tabs.count() - 1)
        super().keyPressEvent(ev)

    def closeEvent(self, ev):
        self.save_last()
        super().closeEvent(ev)


APP_USER_MODEL_ID = "qianwei.TolDesigner.1.0"


def _set_windows_app_id():
    """Windows 任务栏图标的必要前提。

    不设置 AppUserModelID 时，Windows 会把窗口归到宿主进程（python.exe 或
    PyInstaller 解压出的临时 exe）名下，任务栏只显示一个通用空白文档图标。
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            APP_USER_MODEL_ID)
    except Exception:  # noqa: BLE001
        pass


def main() -> int:
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    _set_windows_app_id()
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName("qianwei")
    app.setWindowIcon(icons.app_icon())

    f = QFont("Microsoft YaHei UI", 9)
    app.setFont(f)
    app.setStyleSheet(theme.stylesheet())

    win = MainWindow()
    win.show()
    # 托盘退出/被系统关掉等路径不一定走到 closeEvent，这里再兜一道
    app.aboutToQuit.connect(win.save_last)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
