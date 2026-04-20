from __future__ import annotations

import shutil
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent
WEB_DIR = ROOT / "web"
DIST_DIR = ROOT / "dist"
APP_NAME = "knowledge-network-local"


PLATFORMS = {
    "mac": {
        "folder": f"{APP_NAME}-mac",
        "launcher": "start.command",
        "content": """#!/bin/bash
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
open "$SCRIPT_DIR/web/index.html"
""",
        "readme": "双击 start.command 即可启动。",
    },
    "windows": {
        "folder": f"{APP_NAME}-windows",
        "launcher": "start.bat",
        "content": """@echo off
set SCRIPT_DIR=%~dp0
start "" "%SCRIPT_DIR%web\\index.html"
""",
        "readme": "双击 start.bat 即可启动。",
    },
    "ubuntu": {
        "folder": f"{APP_NAME}-ubuntu",
        "launcher": "start.sh",
        "content": """#!/bin/bash
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
xdg-open "$SCRIPT_DIR/web/index.html" >/dev/null 2>&1 &
""",
        "readme": "执行 chmod +x start.sh 后，双击或运行 ./start.sh 即可启动。",
    },
}


def main() -> None:
    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR)
    DIST_DIR.mkdir(parents=True)

    for platform, config in PLATFORMS.items():
        package_dir = DIST_DIR / config["folder"]
        package_dir.mkdir(parents=True)
        shutil.copytree(WEB_DIR, package_dir / "web")
        shutil.copy2(ROOT / "README.md", package_dir / "README.md")

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
                    "无需联网，无需安装 Python/Node。",
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
