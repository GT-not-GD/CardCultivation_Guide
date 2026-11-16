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
title 卡牌修仙传图鉴工具 - 重新生成 HTML 攻略
echo ================================================
echo   重新生成 HTML 攻略
echo ================================================
echo  [1] 只重新生成网页（使用 docs\data 里现有的 JSON，保留你的手动修改）
echo  [2] 重新 OCR 所有已抓取的截图，再生成网页（会覆盖手动修改，旧版自动备份到 docs\data_backup）
echo  [3] 生成发布版网页（隐藏校对工具，用于上传 GitHub Pages）
echo.
choice /c 123 /n /m "请输入 1 / 2 / 3 ："
if errorlevel 3 (
    %PY% build_html.py --publish
) else if errorlevel 2 (
    %PY% capture_tujian.py --ocr-only --force-ocr
) else (
    %PY% build_html.py
)
echo.
if exist "docs\index.html" start "" "docs\index.html"
pause
