"""V2-I 方向审核：UI 只展示 Story Engine，不出现第二套状态与题材判断。"""

from __future__ import annotations

import re
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from novelforge.api.story_builder_routes import install_story_builder_api
from novelforge.story_builder import load_story_catalog

PROJECT_ROOT = Path(__file__).resolve().parents[1]
UI_SRC = PROJECT_ROOT / "ui" / "src"
ENGINE_SRC = PROJECT_ROOT / "src" / "novelforge" / "story_engine"
PANELS = {
    "WorldPanel.tsx": "creatorWorld",
    "CharacterPanel.tsx": "creatorCharacters",
    "PlotPanel.tsx": "creatorPlot",
    "ProgressionPanel.tsx": "creatorProgression",
    "MemoryPanel.tsx": "creatorMemory",
    "DirectorPanel.tsx": "creatorDirector",
    "LinkagePanel.tsx": "creatorLinkage",
}
CREATOR_ENDPOINTS = ("/api/story-builder/creator/world", "/api/story-builder/creator/characters",
                     "/api/story-builder/creator/plot", "/api/story-builder/creator/progression",
                     "/api/story-builder/creator/memory", "/api/story-builder/creator/director",
                     "/api/story-builder/creator/linkage")


def read(name: str) -> str:
    return (UI_SRC / name).read_text(encoding="utf-8")


def test_every_panel_is_driven_by_the_creator_api() -> None:
    for panel, method in PANELS.items():
        text = read(panel)
        assert f"api.{method}(" in text, f"{panel} 必须通过 API 读取数据"
        assert "fetch(" not in text, f"{panel} 不允许自行拼接口"
        assert "interface StoryState" not in text and "class StoryState" not in text, \
            f"{panel} 不允许出现第二套状态模型"
        # 面板只保存 API 返回值：不能有可以被前端改写的状态副本。
        for name in re.findall(r"const \[(\w+), set\w+\] = useState", text):
            assert name in ("data", "error", "loading", "selected", "actor", "stage", "note",
                            "previewing", "saving", "weightKey", "weightValue", "characters",
                            "characterId"), f"{panel} 出现可疑可写状态：{name}"
        assert "setData(" in text, f"{panel} 必须只把 API 结果放进展示数据"


def test_ui_has_no_genre_or_novel_name_branching() -> None:
    forbidden = ("if genre", "genre ===", "genre === ", "world_type", "小说名",
                 "if (novelId === \"", "novelId ===")
    for panel in PANELS:
        text = read(panel)
        for pattern in forbidden:
            assert pattern not in text, f"{panel} 出现题材分支：{pattern}"
    # 面板不得根据题材挑选不同组件或字段。
    story = read("StoryBuilderPage.tsx")
    assert "genre" not in story.replace("genre: string", ""), "StoryBuilderPage 不得按题材分支"


def test_backend_view_modules_stay_read_only_and_generic() -> None:
    for path in sorted(ENGINE_SRC.glob("*_view.py")):
        text = path.read_text(encoding="utf-8")
        for pattern in ("if genre ==", "if world_type ==", "if novel_id ==", "apply_effects(",
                        "StoryStateRepository", "StoryState("):
            assert pattern not in text, f"{path.name} 违反约束：{pattern}"


def test_creator_endpoints_exist_and_are_read_only(tmp_path: Path) -> None:
    app = FastAPI()
    install_story_builder_api(app, tmp_path, catalog=load_story_catalog(PROJECT_ROOT))
    client = TestClient(app)
    routes = {route.path for route in app.routes if hasattr(route, "path")}
    for endpoint in CREATOR_ENDPOINTS:
        assert endpoint in routes, f"缺少创作者接口：{endpoint}"
    # 只有导演权重是显式写入口，且写入的是配置而不是状态。
    writes = [route.path for route in app.routes
              if hasattr(route, "methods") and route.path.startswith("/api/story-builder/creator")
              and route.methods - {"GET", "HEAD", "OPTIONS"}]
    assert writes == ["/api/story-builder/creator/director/weights"]
    health = client.get("/api/health")
    assert health.status_code in (200, 404)
    # 只读接口不落盘：预览状态下不产生任何 StoryState 文件。
    response = client.get("/api/story-builder/creator/world?novel_id=novel_audit")
    assert response.status_code == 200
    assert response.json()["meta"]["preview"] is True
    assert not (tmp_path / "novel" / "authoring" / "story_engine" / "state").exists()


def test_story_builder_v1_page_still_present() -> None:
    story = read("StoryBuilderPage.tsx")
    for marker in ("story-builder-layout", "builder-steps", "builder-choice-area",
                   "builder-outline-flow", "AdventurePanel", "DesignTreePanel",
                   "OutlineItemEditor"):
        assert marker in story, f"V1 Story Builder 入口被破坏：{marker}"
    # 七个面板都挂载在同一个页签容器里，而不是各自重写页面。
    for panel in PANELS:
        assert f"<{panel.replace('.tsx', '')} novelId={{projectId}}" in story, \
            f"{panel} 必须挂在现有 StoryBuilderPage 上"
