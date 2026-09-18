@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================================
echo   尺寸链公差分析计算器 —— 打包脚本
echo   需要先安装： pip install PySide6-Essentials pyinstaller
echo ============================================================

rem 先按同一套画法生成 app.ico（exe 文件图标 + 窗口图标保持一致）
python "tools\make_icon.py" "app.ico"

rem 注意：不要排除 PySide6.QtSvg —— 页眉的 GitHub / 地球图标由它渲染
set EXCLUDES=--exclude-module PySide6.QtQml --exclude-module PySide6.QtQuick ^
--exclude-module PySide6.QtQuickWidgets --exclude-module PySide6.QtQuickControls2 ^
--exclude-module PySide6.QtNetwork --exclude-module PySide6.QtSql ^
--exclude-module PySide6.QtTest --exclude-module PySide6.QtDBus ^
--exclude-module PySide6.QtDesigner --exclude-module PySide6.QtHelp ^
--exclude-module PySide6.QtUiTools --exclude-module PySide6.QtOpenGL ^
--exclude-module PySide6.QtOpenGLWidgets --exclude-module PySide6.QtPdf ^
--exclude-module PySide6.QtPdfWidgets --exclude-module PySide6.QtSpatialAudio ^
--exclude-module PySide6.QtSerialPort --exclude-module PySide6.QtStateMachine ^
--exclude-module PySide6.QtXml --exclude-module PySide6.QtConcurrent ^
--exclude-module PySide6.QtPrintSupport --exclude-module PySide6.QtSvgWidgets ^
--exclude-module PySide6.QtWebSockets ^
--exclude-module tkinter --exclude-module unittest --exclude-module pydoc

pyinstaller --noconfirm --clean --windowed --onefile ^
  --name "尺寸链公差分析计算器" ^
  --icon "app.ico" ^
  %EXCLUDES% ^
  app.py

echo.
echo 打包完成，输出目录： dist\
echo.
echo 建议接着跑一次启动存活验证：
echo     python tools\smoke_exe.py
pause
