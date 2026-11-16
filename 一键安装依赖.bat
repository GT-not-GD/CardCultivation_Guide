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
title 卡牌修仙传图鉴工具 - 一键安装依赖
echo ================================================
echo   卡牌修仙传 图鉴抓取工具 - 一键安装依赖
echo ================================================
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)"
if errorlevel 1 (
    echo [错误] Python 版本过低，需要 3.9 或更高版本。
    pause
    exit /b 1
)
echo.
echo [1/3] 升级 pip ……
%PY% -m pip install --upgrade pip
if errorlevel 1 %PY% -m pip install --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple
echo.
echo [2/3] 安装依赖：mss / numpy / Pillow / rapidocr / onnxruntime ……
%PY% -m pip install -r requirements.txt
if errorlevel 1 (
    echo 官方源安装失败，改用清华镜像重试 ……
    %PY% -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
)
if errorlevel 1 (
    echo.
    echo [错误] 依赖安装失败，请检查网络后重试。
    pause
    exit /b 1
)
echo.
echo [3/3] 预下载离线 OCR 模型（约 20MB，只需下载一次）……
%PY% -c "import capture_tujian as c; e = c.OcrEngine(); print('OCR 模型就绪：', e.kind)"
echo.
echo ================================================
echo   安装完成！接下来双击 “开始抓取.bat” 即可。
echo ================================================
pause
