"""NovelForge REST 应用装配（V4-10：可注入 composition）。

```python
app = create_app(project_root)                       # 默认（无插件平台 / 无模型）
app = create_app(root, gateway=..., plugin_host=...) # 宿主注入（脚本 / 测试）
app  = <module level default>                        # uvicorn novelforge.api.app:app
```

边界（`V4_MODULE_BOUNDARIES.md` §3.2 / §3.16）：

* 本模块属于 interface 层，只依赖 `application.services` 与各 V4 路由模块；
* 插件平台由宿主（`scripts/*` 或测试）在 composition 处构建后**注入**——
  `api` 不 import `novelforge.plugins`（MCP 与 REST 是平级 adapter）。
"""

from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .canon_routes import install_canon_api
from .agent_routes import install_agent_api
from .delivery_routes import install_delivery_api
from .editor_routes import install_editor_api
from .story_builder_routes import install_story_builder_api
from .studio_routes import install_studio_api

ROOT = Path(__file__).resolve().parents[3]
UI_DIST = ROOT / "ui" / "dist"


def create_app(project_root: Path | str = ROOT, *,
               gateway: Any = None, memory: Any = None,
               plugin_host: Any = None,
               exporter_registry: Any = None,
               evaluator_registry: Any = None,
               with_legacy: bool = True,
               ui_dist: Path | str | None = None) -> FastAPI:
    """构造 REST 应用（唯一装配入口）。

    `plugin_host` 由宿主注入（任何暴露 `service` / `exporter_registry` /
    `evaluator_registry` 的对象），用于让交付格式与插件页反映真实 registry。
    """

    root = Path(project_root)
    # UI 构建物属于产品（仓库），不属于作者数据根
    resolved_dist = Path(ui_dist or UI_DIST)
    app = FastAPI(title="NovelForge 故事构筑", version="4.0.0")

    if plugin_host is not None:
        exporter_registry = exporter_registry or getattr(plugin_host,
                                                         "exporter_registry", None)
        evaluator_registry = evaluator_registry or getattr(plugin_host,
                                                           "evaluator_registry", None)
    plugin_service = getattr(plugin_host, "service", None) if plugin_host is not None \
        else None

    if with_legacy:
        # legacy catalog 来自仓库配置（数据根可以没有 novel/config，V4-01 起
        # 产品配置属于仓库而不是作品数据）
        from novelforge.story_builder import load_story_catalog

        install_story_builder_api(app, root, catalog=load_story_catalog(ROOT))
    install_canon_api(app, root)
    install_editor_api(app, root, gateway=gateway, memory=memory)
    install_delivery_api(app, root, exporter_registry=exporter_registry)
    install_studio_api(app, root, gateway=gateway, memory=memory,
                       exporter_registry=exporter_registry,
                       evaluator_registry=evaluator_registry,
                       plugin_service=plugin_service)
    install_agent_api(app, root, gateway=gateway, memory=memory)

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {"status": "ok", "product": "story-builder",
                "plugins": plugin_service is not None,
                "ai": gateway is not None}

    @app.get("/", include_in_schema=False)
    def index():
        path = resolved_dist / "index.html"
        if path.is_file():
            return FileResponse(path)
        return JSONResponse(status_code=503,
                            content={"detail": "请先构建前端：npm run build --prefix ui"})

    if (resolved_dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=resolved_dist / "assets"),
                  name="assets")
    return app


#: ASGI 默认入口（`uvicorn novelforge.api.app:app`）：无模型 / 无插件平台的最小装配
app = create_app(ROOT)


__all__ = ["ROOT", "UI_DIST", "app", "create_app"]
