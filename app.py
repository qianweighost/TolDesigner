# -*- coding: utf-8 -*-
"""尺寸链公差分析计算器 —— 程序入口。

运行：  python app.py
打包：  pyinstaller --noconsole --onefile --name 尺寸链公差分析计算器 app.py
"""

from __future__ import annotations

import os
import sys

# 保证从任意工作目录启动都能导入 core / ui 包
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from PySide6.QtCore import QSize, Qt, QUrl  # noqa: E402
from PySide6.QtGui import QDesktopServices, QFont, QIcon, QPixmap  # noqa: E402
from PySide6.QtWidgets import (QApplication, QHBoxLayout, QLabel, QMainWindow,  # noqa: E402
                               QPushButton, QTabWidget, QVBoxLayout, QWidget)

from ui import icons, theme  # noqa: E402
from ui.pages import (AllocPage, HelpPage, SimPage, StdPage,  # noqa: E402
                      TolPage)

APP_NAME = "尺寸链公差分析计算器"
APP_VERSION = "1.3"
APP_SUB = ("尺寸链正算（极值法 / 统计法） · 公差分配反算 · "
           "蒙特卡洛仿真 · 标准公差库")

GITHUB_URL = "https://github.com/qianweighost/TolDesigner"
GITHUB_TEXT = "TolDesigner"
SITE_URL = "https://www.qianwei.asia"
SITE_TEXT = "qianwei.asia"

# 「设计计算器」家族统一标识：OringDesigner 系密封圈，DriveDesigner 系传动，
# 本程序系公差与尺寸链
FAMILY_TEXT = "设计计算器家族"


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
    def __init__(self):
        super().__init__()
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

        self.tabs.addTab(TolPage(), "尺寸链计算")
        self.tabs.addTab(SimPage(), "公差仿真")
        self.tabs.addTab(AllocPage(), "公差分配")
        self.tabs.addTab(StdPage(), "标准公差库")
        self.tabs.addTab(HelpPage(), "使用说明")

        # 各页共用同一份尺寸链数据（ui.pages.STATE），切页时把改动同步过去，
        # 否则在「公差分配」页应用了新公差，回到「尺寸链计算」页还是旧表。
        self.tabs.currentChanged.connect(self._sync_page)

    def _sync_page(self, i: int):
        w = self.tabs.widget(i)
        if isinstance(w, TolPage):
            w.sync_from_state()
        elif hasattr(w, "refresh"):
            try:
                w.refresh()
            except Exception:  # noqa: BLE001
                pass

    def refresh_pages(self):
        """供子页调用：STATE 被改动后，让所有页重新读取共享数据。"""
        self._sync_page(self.tabs.currentIndex())

    def keyPressEvent(self, ev):
        if ev.key() == Qt.Key.Key_F1:
            self.tabs.setCurrentIndex(self.tabs.count() - 1)
        super().keyPressEvent(ev)


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
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
