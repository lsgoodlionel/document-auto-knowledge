@echo off
setlocal
cd /d "%~dp0\.."

if "%PORT%"=="" set "PORT=8000"
if "%PYTHON_BIN%"=="" set "PYTHON_BIN=python"

where %PYTHON_BIN% >nul 2>nul
if errorlevel 1 (
  where py >nul 2>nul
  if errorlevel 1 (
    echo 未找到 Python。请先安装 Python 3.10 或更高版本。
    pause
    exit /b 1
  )
  set "PYTHON_BIN=py -3"
)

%PYTHON_BIN% -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)"
if errorlevel 1 (
  echo 当前 Python 版本过低。请使用 Python 3.10 或更高版本运行。
  %PYTHON_BIN% --version
  pause
  exit /b 1
)

%PYTHON_BIN% -c "import socket, sys; port=int(sys.argv[1]); sock=socket.socket(socket.AF_INET, socket.SOCK_STREAM); sock.bind(('127.0.0.1', port)); sock.close()" %PORT% >nul 2>nul
if errorlevel 1 (
  echo 端口 %PORT% 已被占用。请先关闭占用程序，或用其他端口启动：
  echo set PORT=8001
  echo scripts\start-windows.bat
  pause
  exit /b 1
)

echo 正在启动 Document Knowledge Network...
echo 访问地址：http://127.0.0.1:%PORT%
echo 按 Ctrl+C 可停止服务。
%PYTHON_BIN% run.py
pause
