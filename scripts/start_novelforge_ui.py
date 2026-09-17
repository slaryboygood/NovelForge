from __future__ import annotations

"""Start the NovelForge Authoring Studio (backend API + built UI) on 127.0.0.1.

Usage:
    python scripts/start_novelforge_ui.py [--port 8000]

Secrets are loaded from process variables or the gitignored `.env.local` only;
they are never served to the browser.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
UI_DIR = ROOT / "ui"
UI_DIST = UI_DIR / "dist"
UI_INDEX = UI_DIST / "index.html"
BUNDLED_NPM = ROOT / ".dsh-runtime" / "node-v22" / "npm.cmd"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _npm_command() -> str | None:
    """优先使用项目随附的 Node 运行时，避免依赖用户 PATH。"""
    if BUNDLED_NPM.exists():
        return str(BUNDLED_NPM)
    return shutil.which("npm.cmd") or shutil.which("npm")


def ensure_ui_build(*, rebuild: bool = False) -> None:
    """确保 FastAPI 启动前已经有可服务的前端构建物。"""
    if UI_INDEX.exists() and not rebuild:
        print("[NovelForge] 前端构建产物已存在，跳过构建。")
        return

    npm = _npm_command()
    if npm is None:
        print(
            "[NovelForge] 前端构建失败：找不到 Node/npm 运行环境。\n"
            "请确认 .dsh-runtime/node-v22/npm.cmd 存在，或将 npm 加入 PATH。",
            file=sys.stderr,
        )
        raise RuntimeError("npm not found")

    reason = "已请求重新构建" if rebuild else "未找到 ui/dist/index.html，开始自动构建"
    print(f"[NovelForge] {reason}。")
    try:
        completed = subprocess.run([npm, "run", "build"], cwd=str(UI_DIR), check=False)
    except OSError as exc:
        print(f"[NovelForge] 前端构建失败：无法执行 npm（{exc}）。", file=sys.stderr)
        raise RuntimeError("frontend build could not start") from exc
    if completed.returncode != 0 or not UI_INDEX.exists():
        print(
            "[NovelForge] 前端构建失败，服务器不会启动。\n"
            "请检查 Node 运行环境、ui 依赖和前端编译错误。",
            file=sys.stderr,
        )
        raise RuntimeError("frontend build failed")
    print("[NovelForge] 前端构建完成。")


def main() -> int:
    rebuild = "--rebuild-ui" in sys.argv
    try:
        ensure_ui_build(rebuild=rebuild)
    except RuntimeError:
        return 1

    try:
        import uvicorn
    except ModuleNotFoundError:
        print("NovelForge 启动依赖缺失：请先安装 requirements.txt 中的 Python 依赖。", file=sys.stderr)
        return 2

    host = "127.0.0.1"
    port = int(sys.argv[sys.argv.index("--port") + 1]) if "--port" in sys.argv else 8000
    print(f"NovelForge Authoring Studio -> http://{host}:{port}  (Ctrl+C to stop)")
    uvicorn.run("novelforge.api.app:app", host=host, port=port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
