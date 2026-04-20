from __future__ import annotations

import shutil
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DIST_DIR = ROOT / "dist"
APP_NAME = "knowledge-network-local"
PACKAGE_PATHS = ["backend", "frontend", "docs", "scripts", "run.py", "README.md"]
IGNORED_PATTERNS = ("__pycache__", "*.pyc", "*.sqlite3", "*.sqlite3-*", ".DS_Store")


PLATFORMS = {
    "mac": {
        "folder": f"{APP_NAME}-mac",
        "launcher": "start.command",
        "content": """#!/bin/bash
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
bash "$SCRIPT_DIR/scripts/start-mac.command"
""",
        "readme": "双击 start.command 启动服务。脚本会检查 Python 版本和端口占用，并显示访问地址。",
    },
    "windows": {
        "folder": f"{APP_NAME}-windows",
        "launcher": "start.bat",
        "content": """@echo off
call "%~dp0scripts\\start-windows.bat"
""",
        "readme": "双击 start.bat 启动服务。脚本会检查 Python 版本和端口占用，并显示访问地址。",
    },
    "ubuntu": {
        "folder": f"{APP_NAME}-ubuntu",
        "launcher": "start.sh",
        "content": """#!/bin/bash
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
bash "$SCRIPT_DIR/scripts/start-ubuntu.sh"
""",
        "readme": "执行 chmod +x start.sh 后运行 ./start.sh。脚本会检查 Python 版本和端口占用，并显示访问地址。",
    },
}


def main() -> None:
    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR)
    DIST_DIR.mkdir(parents=True)

    for platform, config in PLATFORMS.items():
        package_dir = DIST_DIR / config["folder"]
        package_dir.mkdir(parents=True)
        for item in PACKAGE_PATHS:
            source = ROOT / item
            target = package_dir / item
            if source.is_dir():
                shutil.copytree(source, target, ignore=shutil.ignore_patterns(*IGNORED_PATTERNS))
            else:
                shutil.copy2(source, target)

        (package_dir / "data").mkdir(exist_ok=True)

        launcher_path = package_dir / config["launcher"]
        launcher_path.write_text(config["content"].replace("\r\n", "\n"), encoding="utf-8")
        if launcher_path.suffix in {".sh", ".command"}:
            launcher_path.chmod(0o755)

        install_note = package_dir / "INSTALL.txt"
        install_note.write_text(
            "\n".join(
                [
                    f"{config['folder']}",
                    "",
                    "这是一个本地离线知识网络工具安装包。",
                    config["readme"],
                    "需要系统已安装 Python 3.10 或更高版本。",
                    "默认访问地址：http://127.0.0.1:8000",
                    "如果 8000 端口被占用，请设置 PORT 环境变量后重新启动，例如 PORT=8001 ./start.sh。",
                    "项目数据会保存在安装目录下的 data/ 目录中。",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        archive_path = DIST_DIR / f"{config['folder']}.zip"
        zip_directory(package_dir, archive_path)

    print("Release packages created in:", DIST_DIR)


def zip_directory(source_dir: Path, archive_path: Path) -> None:
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file_path in sorted(source_dir.rglob("*")):
            archive.write(file_path, file_path.relative_to(source_dir.parent))


if __name__ == "__main__":
    main()
