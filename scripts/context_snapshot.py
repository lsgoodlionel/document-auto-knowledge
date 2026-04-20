from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    print("# Context Snapshot")
    print()
    print("## Git")
    run(["git", "status", "--short"])
    run(["git", "branch", "-vv"])
    run(["git", "log", "--oneline", "--decorate", "--all", "--max-count=12"])
    print()
    print("## Key Files")
    for path in [
        "README.md",
        "docs/PROJECT_STATE.md",
        "docs/V2_PLAN.md",
        "docs/PARALLEL_TASKS.md",
        "docs/ARCHITECTURE.md",
        "backend/server.py",
        "frontend/app.js",
        "frontend/editor.js",
    ]:
        file_path = ROOT / path
        marker = "ok" if file_path.exists() else "missing"
        print(f"- {path}: {marker}")
    print()
    print("## Suggested Verification")
    print("PYTHONPYCACHEPREFIX=/tmp/pycache python3 -m py_compile run.py backend/server.py backend/db.py backend/config.py backend/services/docx_parser.py backend/services/docx_exporter.py backend/services/projects.py")
    print("node --check frontend/app.js")
    print("node --check frontend/editor.js")


def run(args: list[str]) -> None:
    print(f"$ {' '.join(args)}")
    result = subprocess.run(args, cwd=ROOT, text=True, capture_output=True, check=False)
    output = (result.stdout + result.stderr).strip()
    print(output or "(no output)")
    print()


if __name__ == "__main__":
    main()
