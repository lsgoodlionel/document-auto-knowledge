#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$SCRIPT_DIR"

PORT="${PORT:-8000}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "未找到 $PYTHON_BIN。请先安装 Python 3.10 或更高版本。"
  read -r -p "按回车键退出..."
  exit 1
fi

if ! "$PYTHON_BIN" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)"; then
  echo "当前 Python 版本过低。请使用 Python 3.10 或更高版本运行。"
  "$PYTHON_BIN" --version || true
  read -r -p "按回车键退出..."
  exit 1
fi

set +e
"$PYTHON_BIN" - "$PORT" <<'PY'
import socket
import sys

try:
    port = int(sys.argv[1])
except ValueError:
    raise SystemExit(2)

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
    try:
        sock.bind(("127.0.0.1", port))
    except OSError:
        raise SystemExit(1)
PY
PORT_STATUS=$?
set -e

if [ "$PORT_STATUS" -eq 1 ]; then
  echo "端口 $PORT 已被占用。请先关闭占用程序，或用其他端口启动："
  echo "PORT=8001 $0"
  read -r -p "按回车键退出..."
  exit 1
elif [ "$PORT_STATUS" -ne 0 ]; then
  echo "端口号无效：$PORT"
  read -r -p "按回车键退出..."
  exit 1
fi

echo "正在启动 Document Knowledge Network..."
echo "访问地址：http://127.0.0.1:$PORT"
echo "按 Ctrl+C 可停止服务。"
PORT="$PORT" "$PYTHON_BIN" run.py
