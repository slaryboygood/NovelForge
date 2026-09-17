"""V2-I 创作者 UI 浏览器验收用的隔离测试服务。

只挂载构建后的前端与临时数据根目录，不碰作者正在使用的数据：

    .venv\\Scripts\\python.exe scripts/creator_ui_test_server.py --port 8012 --root <临时目录>
"""

from __future__ import annotations

import sys
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def main() -> int:
    import uvicorn
    from fastapi import FastAPI
    from fastapi.responses import FileResponse, JSONResponse
    from fastapi.staticfiles import StaticFiles

    from novelforge.api.story_builder_routes import install_story_builder_api
    from novelforge.story_builder import load_story_catalog

    port = int(sys.argv[sys.argv.index("--port") + 1]) if "--port" in sys.argv else 8012
    data_root = Path(sys.argv[sys.argv.index("--root") + 1]) if "--root" in sys.argv else ROOT / "workspace" / "creator_ui_test_root"
    data_root.mkdir(parents=True, exist_ok=True)
    # 隔离数据根目录也要能看到内容包与题材模板配置，否则无法验证面板内容。
    for relative in ("novel/config/story_engine", "novel/config/story_builder"):
        source, target = ROOT / relative, data_root / relative
        if source.is_dir() and not target.exists():
            shutil.copytree(source, target)

    app = FastAPI(title="NovelForge 创作者 UI 验收", version="2.0.0")
    install_story_builder_api(app, data_root, catalog=load_story_catalog(ROOT))
    ui_dist = ROOT / "ui" / "dist"

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "product": "creator-ui-test", "root": str(data_root)}

    @app.get("/", include_in_schema=False)
    def index():
        path = ui_dist / "index.html"
        if path.is_file():
            return FileResponse(path)
        return JSONResponse(status_code=503, content={"detail": "请先构建前端：npm run build --prefix ui"})

    if (ui_dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=ui_dist / "assets"), name="assets")

    print(f"[creator-ui-test] root={data_root} -> http://127.0.0.1:{port}", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
