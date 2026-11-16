@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set "PY="
python -c "import sys" >nul 2>nul && set "PY=python"
if not defined PY (
    py -3 -c "import sys" >nul 2>nul && set "PY=py -3"
)
if not defined PY (
    echo.
    echo [错误] 未检测到 Python。
    echo 请先到 https://www.python.org/downloads/ 安装 Python 3.10 或更高版本，
    echo 安装时务必勾选 “Add python.exe to PATH”，然后重新运行本文件。
    echo.
    pause
    exit /b 1
)
title 卡牌修仙传图鉴工具 - 自动抓取
echo ================================================
echo   卡牌修仙传 图鉴自动抓取
echo ================================================
echo  使用前：游戏设为 1920x1080 全屏，进入【图鉴】并选好要抓取的分类
echo  热键：F9 暂停/继续   F10 停止并保存   鼠标甩到屏幕左上角 = 紧急停止
echo.
echo  [1] 开始 / 继续抓取当前分类（推荐，支持断点续抓；未获得的卡牌也会收录并标记）
echo  [2] 从头重新抓取当前分类（丢弃旧进度）
echo  [3] 高精度 OCR 模式抓取（识别更准，但更慢）
echo  [4] 补全未获得卡牌（只检查上次标记为“未获得”的卡，获得了就自动补抓）
echo.
choice /c 1234 /n /m "请输入 1 / 2 / 3 / 4 ："
set "ARGS="
if errorlevel 4 (
    set "ARGS=--update-locked"
) else if errorlevel 3 (
    set "ARGS=--high-accuracy"
) else if errorlevel 2 (
    set "ARGS=--fresh"
)
echo.
echo 选好后请在 5 秒倒计时内切换回游戏画面……
%PY% capture_tujian.py %ARGS% %*
echo.
if errorlevel 1 (
    echo 如果脚本点击游戏没有反应，请右键本文件 → 以管理员身份运行。
)
pause
