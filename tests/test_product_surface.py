"""产品表面守卫：只暴露 current V4 API，legacy Story Builder 端点必须真的消失。

post-release cleanup 把 V2/V3 Story Builder 后端整体退休后，这个文件从
"只有 story-builder 前缀" 升级为两条更强的断言：

```text
1. 对外可见的 /api 路径 = current V4 router 集合（白名单，只减不增）；
2. 已退休的 legacy 端点返回 404（不存在"隐藏的兼容通道"）。
```
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from novelforge.api.app import app

#: current V4 REST 表面（endpoint 路径模板）
CURRENT_API_PREFIXES = (
    "/api/health",
    "/api/story-builder/novels",
    "/api/story-builder/canon",
    "/api/story-builder/editor",
    "/api/story-builder/delivery",
    "/api/story-builder/studio",
    "/api/story-builder/agent",
)

#: 已退休的 legacy 端点（V2 creator / V3 command center / writer / outline /
#: runtime / adventure / inspector / settings 引导流 / v3 投影）
RETIRED_ENDPOINTS = (
    "/api/story-builder/catalogs",
    "/api/story-builder/steps/reader_experience",
    "/api/story-builder/sessions",
    "/api/story-builder/blueprints/bp_1",
    "/api/story-builder/outline/plan",
    "/api/story-builder/outline/export",
    "/api/story-builder/runtime/state",
    "/api/story-builder/writer/context",
    "/api/story-builder/creator/world",
    "/api/story-builder/guided-flow",
    "/api/story-builder/settings/seed",
    "/api/story-builder/inspector/overview",
    "/api/story-builder/repair/diagnosis",
    "/api/story-builder/v3/novels",
    "/api/story-builder/export/package",
    "/api/story-builder/export/writer-bundle",
    "/api/chapters",
    "/api/project",
    "/api/production",
    "/api/skills",
    "/api/promotion",
)


def test_only_current_v4_api_is_exposed() -> None:
    paths = [route.path for route in app.routes if route.path.startswith("/api/")]
    assert paths, "必须暴露 current API"
    offenders = [path for path in paths
                 if not any(path == prefix or path.startswith(prefix + "/")
                            or path.startswith(prefix)
                            for prefix in CURRENT_API_PREFIXES)]
    assert offenders == [], f"出现未登记的 API 路径：{offenders}"
    assert not any("handoffs" in path for path in paths)


def test_retired_legacy_endpoints_are_gone() -> None:
    client = TestClient(app)
    for path in RETIRED_ENDPOINTS:
        assert client.get(path).status_code == 404, f"{path} 仍然存在（应为 404）"
        assert client.post(path, json={}).status_code == 404, f"{path} 仍然存在"
