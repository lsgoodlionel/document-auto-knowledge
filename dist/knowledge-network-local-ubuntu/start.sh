#!/bin/bash
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
xdg-open "$SCRIPT_DIR/web/index.html" >/dev/null 2>&1 &
