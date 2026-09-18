"""V3-P6 Frozen Guard —— post-release cleanup 后的 **current** 版本。

历史：V3-P1 把 `route_lab.list_branches` 的 no-content-pack 行为从
`CONTENT_PACK_REQUIRED` 放宽为合法空结果（浏览器把预期空状态记为 Console Error）。
本文件固定那次放宽的确切边界，避免它被误解成「route_lab 不再要求内容包」：

```text
只读列表：还没有开始 → 合法的空结果
会改动事实的接口：仍然要求前置条件
```

post-release cleanup 把 route_lab / 内容包 / V2 运行时端点整体退休
（`docs/v4/V4_POST_RELEASE_CLEANUP`），因此按 AGENTS.md §20 把这条**永久不变式**
改挂在 current V4 owner 上（历史 timepoint 的部分随能力退休）：

```text
空态只读投影        JourneyService / Studio overview：没有数据 → 空结果，不报错
受门前置条件        Studio 生成：没有模型能力 → 422 GENERATION_UNAVAILABLE
                    Delivery 预检：没有 accepted revision → 明确 blocker
```

断言强度不降低：三条都要求"要么给真实结果，要么给带稳定错误码的真实拒绝"。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))


def _load(module_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


_support = _load("studio_support_for_frozen_guard",
                 ROOT / "tests" / "studio" / "studio_support.py")
FRESH = "novel_frozen_guard_fresh"


def test_empty_read_only_projection_is_an_empty_result_not_an_error(
        tmp_path: Path) -> None:
    """空态只读：没有数据不是错误，是一个合法的空投影（V3 只读放宽的永久不变式）。"""

    from novelforge.application.services import JourneyService

    _support.build_novel(tmp_path, FRESH, title="冻结守卫作品",
                         fact_text="只验证空态边界。")
    projection = JourneyService(tmp_path, FRESH).projection()

    assert projection["journey"]["current_stage"] == "premise"
    assert projection["facts"]["blueprint_nodes"] == 0
    assert projection["facts"]["delivery_snapshots"] == 0
    assert projection["progress"]["done"] <= 1, "空态不得凭空产生进度"
    assert projection["next_action"]["action_id"], "空态也要给出可执行的下一步"


def test_generation_is_gated_by_a_real_precondition(tmp_path: Path) -> None:
    """会改动事实的接口没有放宽：没有模型能力必须给稳定错误码，而不是静默降级。"""

    _support.build_novel(tmp_path, FRESH, title="冻结守卫作品",
                         fact_text="只验证生成前置条件。")
    client = _support.studio_app(tmp_path)      # 未注入 gateway
    response = client.post("/api/story-builder/studio/generate",
                           json={"novel_id": FRESH, "task": "premise"})
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "GENERATION_UNAVAILABLE"


@pytest.mark.parametrize("endpoint", [
    "/api/story-builder/runtime/start",
    "/api/story-builder/runtime/state",
    "/api/story-builder/outline/forge",
    "/api/story-builder/writer/drafts",
    "/api/story-builder/v3/novels",
    "/api/story-builder/guided-flow",
    "/api/story-builder/creator/world",
])
def test_retired_legacy_endpoints_are_gone(endpoint: str) -> None:
    """V2/V3 backend 的端点必须真的不存在（不能再有"隐藏的 legacy 通道"）。"""

    from fastapi.testclient import TestClient

    from novelforge.api.app import create_app

    client = TestClient(create_app())
    assert client.get(endpoint).status_code == 404
    assert client.post(endpoint, json={}).status_code == 404
