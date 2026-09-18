"""V4-10 Closure Gate §15：Studio generate 契约回归（index / parent / scene）。

冻结两个真实缺陷：

```text
1. studio generate 忽略 sibling index → 第二次 chapter 覆盖 ch_001（revision 叠加）
2. chapter → scene 必须在同一 turn 内成功（不依赖页面刷新 / sleep）
```
"""

from __future__ import annotations

from pathlib import Path

from studio_support import (
    chapter_payload,
    empty_studio,
    scene_payload,
    story_arc_payload,
    unit_payload,
)


def _nodes(client, novel_id: str, node_type: str = "") -> list[dict]:
    params = {"novel_id": novel_id}
    if node_type:
        params["node_type"] = node_type
    response = client.get("/api/story-builder/studio/blueprint", params=params)
    assert response.status_code == 200, response.text
    return response.json()["nodes"]


def _generate(client, novel_id: str, task: str, **extra) -> dict:
    response = client.post("/api/story-builder/studio/generate",
                           json={"novel_id": novel_id, "task": task, **extra})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["ok"] is True, payload
    return payload


def test_sibling_index_creates_distinct_chapters(tmp_path: Path) -> None:
    """§15：index=1 / index=2 → 两个不同的 chapter 节点（不是 ch_001 revision 叠加）。"""

    stack = empty_studio(tmp_path, script=[
        story_arc_payload(), unit_payload(),
        chapter_payload(), chapter_payload(title="第二章：备用电池组"),
    ])
    client, novel_id = stack["client"], stack["novel_id"]

    story = _generate(client, novel_id, "story_arc")
    unit = _generate(client, novel_id, "structural_unit",
                     parent_id=story["node"]["node_id"])
    parent = unit["node"]["node_id"]

    first = _generate(client, novel_id, "chapter", parent_id=parent, index=1)
    second = _generate(client, novel_id, "chapter", parent_id=parent, index=2)

    first_id = first["node"]["node_id"]
    second_id = second["node"]["node_id"]
    assert first_id != second_id, "index=2 覆盖了 index=1 的章节（回归！）"
    assert first_id == "ch_001" and second_id == "ch_002"
    assert first["node"]["revision"] == 1 and second["node"]["revision"] == 1

    chapters = _nodes(client, novel_id, "chapter")
    assert sorted(row["node_id"] for row in chapters) == ["ch_001", "ch_002"]
    assert all(row["parent_id"] == parent for row in chapters)


def test_chapter_then_scene_in_same_turn(tmp_path: Path) -> None:
    """§4：chapter 生成后立即生成 scene（同一 turn、无刷新）必须成功。"""

    stack = empty_studio(tmp_path, script=[
        story_arc_payload(), unit_payload(), chapter_payload(),
        scene_payload("ch_001"), scene_payload("ch_001"),
    ])
    client, novel_id = stack["client"], stack["novel_id"]

    story = _generate(client, novel_id, "story_arc")
    unit = _generate(client, novel_id, "structural_unit",
                     parent_id=story["node"]["node_id"])
    chapter = _generate(client, novel_id, "chapter",
                        parent_id=unit["node"]["node_id"], index=1)
    chapter_id = chapter["node"]["node_id"]

    # 立即（同一进程、无刷新、无等待）用刚返回的 chapter node_id 生成场景；
    # 第二个场景由 Host 补齐 seq（不得覆盖第一个场景节点）
    first_scene = _generate(client, novel_id, "scene", parent_id=chapter_id)
    second_scene = _generate(client, novel_id, "scene", parent_id=chapter_id)

    assert first_scene["node"]["parent_id"] == chapter_id
    assert second_scene["node"]["parent_id"] == chapter_id
    assert first_scene["node"]["node_id"] != second_scene["node"]["node_id"]
    scenes = _nodes(client, novel_id, "scene")
    assert len(scenes) == 2 and {row["parent_id"] for row in scenes} == {chapter_id}
    assert first_scene["node"]["status"] == "proposed"


def test_missing_parent_is_rejected_with_stable_code(tmp_path: Path) -> None:
    """父节点缺失时错误稳定（UI 侧由 resolveParent 提前拦截并给出可读提示）。"""

    stack = empty_studio(tmp_path, script=[chapter_payload()])
    response = stack["client"].post("/api/story-builder/studio/generate",
                                    json={"novel_id": stack["novel_id"],
                                          "task": "chapter", "index": 1})
    assert response.status_code >= 400
    code = response.json()["detail"]["code"]
    assert code and "Traceback" not in response.text
