from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .story_builder_routes import install_story_builder_api
from .canon_routes import install_canon_api

ROOT = Path(__file__).resolve().parents[3]
UI_DIST = ROOT / "ui" / "dist"
app = FastAPI(title="NovelForge 故事构筑", version="2.0.0")
install_story_builder_api(app, ROOT)
install_canon_api(app, ROOT)


@app.get("/api/health")
def health():
    return {"status": "ok", "product": "story-builder"}


@app.get("/", include_in_schema=False)
def index():
    path = UI_DIST / "index.html"
    if path.is_file():
        return FileResponse(path)
    return JSONResponse(status_code=503, content={"detail": "请先构建前端：npm run build --prefix ui"})


if (UI_DIST / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=UI_DIST / "assets"), name="assets")
