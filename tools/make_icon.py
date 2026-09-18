# -*- coding: utf-8 -*-
"""生成程序图标 app.ico（多尺寸 ICO，内嵌 PNG）。

图标画法与程序运行时用的窗口图标完全一致（共用 ui.icons.app_icon_image），
所以任务栏图标、标题栏图标与 exe 文件图标天然统一。

用法：
    python tools/make_icon.py            # 输出到项目根目录 app.ico
    python tools/make_icon.py out.ico
"""
import os
import struct
import sys

# 只用 QPainter 往 QImage 上画，不涉及字体，offscreen 平台足够
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from PySide6.QtCore import QBuffer  # noqa: E402
from PySide6.QtGui import QGuiApplication, QImage  # noqa: E402

from ui.icons import app_icon_image  # noqa: E402

SIZES = [256, 128, 64, 48, 32, 24, 16]


def png_bytes(img: QImage) -> bytes:
    # 注意：不要写成 QBuffer(QByteArray())，临时对象被回收会导致进程崩溃
    buf = QBuffer()
    buf.open(QBuffer.OpenModeFlag.WriteOnly)
    if not img.save(buf, "PNG"):
        raise RuntimeError("PNG 编码失败")
    data = bytes(buf.data())
    buf.close()
    return data


def build(out_path: str) -> None:
    _app = QGuiApplication.instance() or QGuiApplication(sys.argv)  # noqa: F841
    entries = [(s, png_bytes(app_icon_image(s))) for s in SIZES]

    header = struct.pack("<HHH", 0, 1, len(entries))
    offset = len(header) + 16 * len(entries)
    dirs, blobs = b"", b""
    for s, data in entries:
        w = 0 if s >= 256 else s
        dirs += struct.pack("<BBBBHHII", w, w, 0, 0, 1, 32, len(data), offset)
        blobs += data
        offset += len(data)
    with open(out_path, "wb") as f:
        f.write(header + dirs + blobs)
    print("icon ->", out_path, "sizes:", SIZES)


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(_ROOT, "app.ico")
    build(out)
