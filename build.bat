@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================================
echo   尺寸链公差分析计算器 —— 打包脚本
echo   需要先安装： pip install PySide6-Essentials pyinstaller
echo ============================================================

rem 先按同一套画法生成 app.ico（exe 文件图标 + 窗口图标保持一致）
python "tools\make_icon.py" "app.ico"

rem 用 spec 打包：排除清单、图标、文件名都在 spec 里维护，
rem 成品文件名自动带版本号（spec 从 app.py 读 APP_VERSION），
rem 产出 dist\尺寸链公差分析计算器-v<版本>.exe
pyinstaller --noconfirm --clean "尺寸链公差分析计算器.spec"

echo.
echo 打包完成，输出目录： dist\
echo.
echo 建议接着跑一次启动存活验证：
echo     python tools\smoke_exe.py
pause
