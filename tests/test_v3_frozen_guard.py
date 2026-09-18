"""V3-P6 Frozen Guard：V2 语义变更必须有证据、有边界、有回归。

V3-P1 把 `route_lab.list_branches` 的 no-content-pack 行为从
`CONTENT_PACK_REQUIRED` 放宽为合法空结果，原因是浏览器把预期空状态记为 Console Error。

本文件固定这次放宽的确切边界，避免它被误解成「route_lab 不再要求内容包」：

* 只读列表（list_branches）：没有内容包 == 这本书还没开始推演 → 空结果；
* 会改动事实的接口（fork / compare / merge / freeze）：仍然要求内容包，语义未放宽；
* 生成侧（runtime/start）：仍然要求内容包并通过自检。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from novelforge.api.story_builder_routes import install_story_builder_api
from novelforge.story_builder import load_story_catalog
from novelforge.story_engine.route_lab import (
    BranchLabError,
    compare_branches,
    fork_branch,
    freeze_branch,
    list_branches,
    merge_preview,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRESH = "novel_frozen_guard_fresh"


def client_for(tmp_path: Path) -> TestClient:
    """最小 fixture：只装配作品 API（不再依赖别的测试模块的 helper）。"""

    app = FastAPI()
    install_story_builder_api(app, tmp_path,
                              catalog=load_story_catalog(PROJECT_ROOT))
    return TestClient(app)


def new_novel(client: TestClient, novel_id: str) -> None:
    created = client.post("/api/story-builder/novels",
                          json={"novel_id": novel_id, "title": novel_id})
    assert created.status_code in (201, 409), created.text


def _fresh_novel(tmp_path: Path) -> TestClient:
    client = client_for(tmp_path)
    new_novel(client, FRESH)
    return client


def test_list_branches_is_empty_result_without_content_pack(tmp_path: Path) -> None:
    """V3 只读放宽：没有内容包不是错误，是一个合法的空路线列表。"""

    _fresh_novel(tmp_path)
    listing = list_branches(tmp_path, FRESH)

    assert listing["branches"] == []
    assert listing["official_branch"] == ""
    assert listing["frozen_revision"] == 0


@pytest.mark.parametrize("operation", [
    lambda root: fork_branch(root, FRESH, source_branch="main", label="试演"),
    lambda root: compare_branches(root, FRESH, base_branch="main", target_branch="other"),
    lambda root: merge_preview(root, FRESH, target_branch="main", source_branches=["other"]),
    lambda root: freeze_branch(root, FRESH, branch_id="main", label="正式"),
])
def test_mutating_route_lab_operations_still_require_content_pack(
        tmp_path: Path, operation) -> None:
    """会改动事实的接口没有放宽：仍然要求内容包。"""

    _fresh_novel(tmp_path)
    with pytest.raises(BranchLabError) as excinfo:
        operation(tmp_path)
    assert excinfo.value.code == "CONTENT_PACK_REQUIRED"


def test_generation_still_gated_by_content_pack(tmp_path: Path) -> None:
    """开始推演仍然由「内容包 + 设定自检」把关。"""

    client = _fresh_novel(tmp_path)
    started = client.post(f"/api/story-builder/runtime/start?novel_id={FRESH}", json={})
    assert started.status_code == 422
    assert started.json()["detail"]["code"] == "CONTENT_PACK_REQUIRED"
