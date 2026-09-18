"""V3 验收修复（Repair branch）回归 —— post-release cleanup 后的 **current** 版本。

历史：本文件原本在 Product V3 Command Center（`story_builder/v3_projection.py` +
`/api/story-builder/v3/*` + writer / outline / runtime 端点）上把 NF-001…NF-012 的
验收缺陷变成断言。

V4 post-release cleanup 把 V2/V3 Story Builder 后端整体退休（`v3_projection` /
`ui_flow` / `writer_integration` / `outline_forge` / runtime 端点随之删除），
因此本文件按 `V4_POST_RELEASE_CLEANUP` 任务书 §17 的许可做了**输入构造方式迁移**
（"replace legacy helper used to construct test input"），断言改由 current 产品层
（JourneyService / BlueprintRepository / QualityStore / DeliveryService / Story Studio
 REST）承载。**不变式没有放宽**：每条断言仍然检查同一个缺陷不会再出现。

编号对照（current owner）：

```text
NF-002  写入路径 == 读取路径（一份 canonical store）      BlueprintRepository + Studio REST
NF-003  作者可见文本不出现字段标签占位                    Story Studio 蓝图投影
NF-004  作者可见产物不泄漏引擎 id                         交付物 + Studio 投影
NF-005  阶段 / 进度 / 下一步只有一套公式                   JourneyService（REST / MCP / 服务层同源）
NF-008  投影推荐的下一步必须真的可执行                     journey next_action → /studio/generate
NF-011  删除作品＝整体归档，不留孤儿文件                   ProjectService.archive_novel
NF-012  有问题时报真实 blocker，而不是"还差 0 步"           DeliveryValidator.preflight
```

已经随能力一起退休的项（NF-001 引导流 onboarding、writer 草稿路径、
outline 章节导出）不再作为 current 断言：它们的产品面已经不存在。
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))


def _load(module_name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


_support = _load("studio_support_for_acceptance_repair",
                 ROOT / "tests" / "studio" / "studio_support.py")

clean_studio = _support.clean_studio
empty_studio = _support.empty_studio
build_novel = _support.build_novel
delivery_stack = _support.delivery_stack
premise_payload = _support.premise_payload
studio_app = _support.studio_app
NOVEL_ID = _support.NOVEL_ID

#: 引擎内部 id / 命名（NF-004：不得出现在作者可见文本里）
INTERNAL_ID_PATTERN = re.compile(
    r"\b(act_[a-z0-9_]+|ev_[a-z0-9_]+|faction_\d+|npc_\d+|location_\d+|character_\d+"
    r"|route_\d+|planned_[a-z0-9_]+|suggested_[a-z0-9_]+|start_place|work_place"
    r"|hidden_place|core_record|protagonist|favors)\b")
#: 只用于 markdown 叙述文本（结构化引用字段在 JSON 侧单独豁免）
ENGINE_TOKEN_PATTERN = re.compile(
    r"\b(act_[a-z0-9_]+|ev_[a-z0-9_]+|planned_[a-z0-9_]+|suggested_[a-z0-9_]+"
    r"|protagonist|favors|npc_\d+|character_\d+|route_\d+|start_place|work_place"
    r"|hidden_place)\b")
#: 字段标签占位（NF-003：标题不许是字段名）
FIELD_LABEL_BLACKLIST = ("阶段目标", "长期方向", "（规划）", "（设定草稿）")

#: artifact identity / 引用字段：它们承载 id 是结构需要，不是"泄漏到作者文本"
IDENTITY_KEYS = {
    "item_id", "package_id", "parent_package_id", "child_ids", "source_ids",
    "route_source", "canon_fact_ids", "canon_event_ids", "novel_id", "branch_id",
    "blueprint_id", "chapter_uuid", "participants", "node_id", "parent_id",
    "character_id", "setup_id", "payoff_id", "source", "target", "transition_id",
    "information_reveal", "snapshot_id", "manifest_id", "project_id",
    "selected_revisions", "input_digest", "revisions", "excluded", "ordering",
}

#: JourneyService 的 action_id → Story Studio 生成任务（NF-008）
ACTION_TO_TASK = {
    "define_premise": "premise", "shape_world": "world",
    "cast_characters": "character", "sketch_arc": "story_arc",
    "define_units": "structural_unit", "write_scenes": "scene",
}
STUDIO_VIEWS = {"overview", "creation", "world", "characters", "story", "scenes",
                "quality", "agent", "delivery", "plugins", "settings"}


def content_strings(node: Any, skip_identity: bool = False) -> list[str]:
    """收集作者可见文本；identity / 引用字段里的 id 不算泄漏（与原 V3 断言同规则）。"""

    if isinstance(node, list):
        return [text for value in node for text in content_strings(value, skip_identity)]
    if isinstance(node, dict):
        return [text for key, value in node.items()
                for text in content_strings(value, skip_identity or key in IDENTITY_KEYS)]
    if isinstance(node, str):
        return [] if skip_identity else [node]
    return []


def _overview(client: Any, novel_id: str) -> dict[str, Any]:
    response = client.get("/api/story-builder/studio/overview",
                          params={"novel_id": novel_id})
    assert response.status_code == 200, response.text
    return response.json()


def _deliver(client: Any, novel_id: str, formats: list[str]) -> dict[str, Any]:
    response = client.post("/api/story-builder/delivery",
                           json={"novel_id": novel_id, "formats": formats,
                                 "selection_mode": "accepted"})
    assert response.status_code == 200, response.text
    return response.json()


def _artifact(client: Any, novel_id: str, snapshot_id: str, path: str) -> str:
    response = client.get(
        f"/api/story-builder/delivery/{snapshot_id}/artifacts/{path}",
        params={"novel_id": novel_id})
    assert response.status_code == 200, response.text
    return response.text


# ------------------------------------------------------- NF-005 单一公式
def test_journey_projection_is_the_single_stage_and_next_action_formula(
        tmp_path: Path) -> None:
    """空 / 部分 / 完整三种状态下，REST 与服务层必须给出同一份阶段与下一步。"""

    from novelforge.application.services import JourneyService

    states: list[tuple[str, Path, Any]] = []

    fresh_root = tmp_path / "fresh"
    fresh = empty_studio(fresh_root)
    states.append(("fresh", fresh_root, fresh))

    partial_root = tmp_path / "partial"
    partial = empty_studio(partial_root, script=[premise_payload()])
    generated = partial["client"].post(
        "/api/story-builder/studio/generate",
        json={"novel_id": partial["novel_id"], "task": "premise"})
    assert generated.status_code == 200, generated.text
    states.append(("partial", partial_root, partial))

    rich_root = tmp_path / "rich"
    rich = clean_studio(rich_root)
    states.append(("rich", rich_root, rich))

    for label, root, stack in states:
        novel_id = stack["novel_id"]
        projection = JourneyService(root, novel_id).projection()
        overview = _overview(stack["client"], novel_id)

        assert overview["next_action"] == dict(projection["next_action"]), label
        assert projection["journey"]["current_stage"] == projection["current_stage"]
        assert projection["journey"]["current_stage"] in {
            row["stage_id"] for row in projection["journey"]["stages"]}
        assert projection["journey"]["current_stage_label"], label
        assert projection["progress"]["total"] == 9, label
        # 确定性：同一份状态重复计算完全一致（没有第二套公式掺进来）
        again = JourneyService(root, novel_id).projection()
        assert json.dumps(again["journey"], sort_keys=True, default=str) == \
            json.dumps(projection["journey"], sort_keys=True, default=str), label

    # 唯一公式 = 旧投影模块已经不存在（不会再有第二套 stage 词表）
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("novelforge.story_builder.v3_projection")


def test_mcp_novel_resource_reuses_the_same_journey_projection(tmp_path: Path) -> None:
    """MCP 摘要里的 journey 段必须与 JourneyService 完全一致（接口层不重算）。"""

    from novelforge.application.services import JourneyService
    from novelforge.interfaces.mcp import novel_uri

    support = _load("mcp_support_for_acceptance_repair",
                    ROOT / "tests" / "mcp" / "mcp_support.py")
    stack = support.mcp_stack(tmp_path)
    payload = stack["dispatcher"].read_resource(novel_uri(NOVEL_ID))
    data = json.loads(payload.content if isinstance(payload.content, str)
                      else payload.content.decode("utf-8"))
    projection = JourneyService(tmp_path, NOVEL_ID).projection()

    assert data["journey"]["journey"] == projection["journey"]
    assert data["journey"]["progress"] == projection["progress"]
    assert data["journey"]["next_action"] == projection["next_action"]


# ------------------------------------------------- NF-002 唯一 canonical store
def test_blueprint_write_and_read_share_one_canonical_store(tmp_path: Path) -> None:
    """写入路径 == 读取路径：同一个 BlueprintRepository，REST 立刻看到同一个 revision。"""

    from novelforge.persistence.paths import blueprint_dir

    stack = clean_studio(tmp_path)
    repository = stack["repository"]
    client = stack["client"]

    assert repository.root == blueprint_dir(tmp_path, NOVEL_ID)
    assert repository.project_root == tmp_path
    assert (repository.root / "index.json").is_file()

    node = next(row for row in repository.all_nodes()
                if str(row.status) == "accepted")
    before = repository.current_revision(node.node_id)
    repository.set_status(node.node_id, "superseded", expected_revision=before)

    view = client.get("/api/story-builder/studio/blueprint",
                      params={"novel_id": NOVEL_ID}).json()
    row = next(item for item in view["nodes"] if item["node_id"] == node.node_id)
    assert row["revision"] == before + 1, "REST 必须读到刚写入的新 revision"
    assert row["status"] == "superseded"
    assert repository.current_revision(node.node_id) == before + 1


# --------------------------------------------------- NF-008 可执行的下一步
def test_projection_never_recommends_an_unavailable_action(tmp_path: Path) -> None:
    """投影说「可执行」的方向，点下去必须真的成功（不再出现点主 CTA 就打 422）。"""

    stack = empty_studio(tmp_path, script=[premise_payload()])
    client = stack["client"]
    novel_id = stack["novel_id"]

    action = _overview(client, novel_id)["next_action"]
    assert action["action_id"] in ACTION_TO_TASK, action
    assert action["target_view"] in STUDIO_VIEWS, action
    assert action["action_label"]
    assert action["impact"]

    moved = client.post("/api/story-builder/studio/generate",
                        json={"novel_id": novel_id,
                              "task": ACTION_TO_TASK[action["action_id"]]})
    assert moved.status_code == 200, (
        f"投影推荐的可执行方向必须真的能执行：{action['action_id']} → "
        f"{moved.status_code} {moved.text[:200]}")

    after = _overview(client, novel_id)["next_action"]
    assert after["action_id"] != action["action_id"], "完成后必须推进到下一步"
    assert after["action_id"] in ACTION_TO_TASK or after["action_id"] == "extend_story"
    assert after["target_view"] in STUDIO_VIEWS


# ------------------------------------------------ NF-012 交付 blocker 文案
def test_delivery_preflight_reports_real_blockers_not_zero_steps(
        tmp_path: Path) -> None:
    """有问题时必须报出真实 blocker（而不是"还差 0 步"这种自相矛盾文案）。"""

    from novelforge.application.services import ExportService

    stack = delivery_stack(tmp_path, clean=False)
    selection = ExportService(tmp_path, NOVEL_ID).delivery_selection(formats=("json",))
    payload = stack["delivery"].validate(selection)
    validation = payload["validation"]

    assert validation["ok"] is False
    assert validation["issues"], "未交付的原因必须是具体 blocker，而不是空列表"
    assert validation["blocking_reason"]
    assert "0 步" not in validation["blocking_reason"]
    codes = {row["code"] for row in validation["issues"]}
    assert {"DELIVERY_NO_ACCEPTED_REVISION", "DELIVERY_MISSING_REQUIRED_NODE"} & codes


# -------------------------------------------- NF-003 / NF-004 作者可见文本
def test_delivered_artifacts_do_not_leak_internal_ids(tmp_path: Path) -> None:
    stack = clean_studio(tmp_path)
    client = stack["client"]
    delivered = _deliver(client, NOVEL_ID, ["json", "markdown"])
    assert delivered["ok"] is True, delivered.get("validation")
    snapshot_id = delivered["snapshot_id"]

    structured = json.loads(_artifact(client, NOVEL_ID, snapshot_id,
                                      "exports/blueprint.json"))
    leaks = [(key, text) for key, text in _text_rows(structured)
             if INTERNAL_ID_PATTERN.search(text)]
    assert leaks == [], f"交付 JSON 的作者可见字段泄漏内部 id：{leaks[:3]}"

    markdown = _artifact(client, NOVEL_ID, snapshot_id, "exports/blueprint.md")
    leak = ENGINE_TOKEN_PATTERN.search(markdown)
    assert leak is None, f"交付 Markdown 泄漏引擎 id：{leak and leak.group(0)}"
    assert "来源：来源：" not in markdown
    assert markdown.strip(), "交付物不能是空文件"


def _text_rows(node: Any, key: str = "") -> list[tuple[str, str]]:
    """(key, text) 行；跳过 identity / 引用字段（它们的 id 是结构需要）。"""

    if isinstance(node, list):
        return [row for value in node for row in _text_rows(value, key)]
    if isinstance(node, dict):
        return [row for child_key, value in node.items()
                for row in _text_rows(value, child_key)]
    if isinstance(node, str):
        return [] if key in IDENTITY_KEYS else [(key, node)]
    return []


def test_studio_projection_speaks_author_language(tmp_path: Path) -> None:
    """Story Studio 的蓝图投影只给作者语言：没有字段标签占位、没有引擎 id。"""

    stack = clean_studio(tmp_path)
    view = stack["client"].get("/api/story-builder/studio/blueprint",
                               params={"novel_id": NOVEL_ID}).json()
    assert view["nodes"], "fixture 必须有节点"

    for row in view["nodes"]:
        visible = dict(row.get("visible") or {})
        assert visible, f"{row['node_id']}: 作者可见字段不能是空对象"
        texts = [text for text in content_strings(visible)]
        assert texts, f"{row['node_id']}: 作者可见文本不能为空"
        title = str(visible.get("title") or texts[0])
        assert title.strip(), f"{row['node_id']}: 可见标题不能为空"
        for banned in FIELD_LABEL_BLACKLIST:
            assert banned not in title, f"{row['node_id']}: 占位标题 {title}"
        time_text = str(visible.get("time") or "")
        assert "tick" not in time_text, "时间必须是作者语言，不是引擎 tick"

    leaks = [(key, text) for key, text in _text_rows(json.loads(json.dumps({
        "nodes": [{"node_id": row["node_id"], "payload": row["payload"]}
                  for row in view["nodes"]]})))
             if INTERNAL_ID_PATTERN.search(text)]
    assert leaks == [], f"Studio 投影泄漏内部 id：{leaks[:3]}"


def test_studio_errors_use_stable_codes_and_author_language(tmp_path: Path) -> None:
    """失败文案必须是稳定错误码 + 作者语言（不出现引擎标识 / traceback）。"""

    build_novel(tmp_path, "repair_no_model", title="无模型",
                fact_text="无模型作品：只验证错误码。")
    client = studio_app(tmp_path)          # 未注入 gateway
    response = client.post("/api/story-builder/studio/generate",
                           json={"novel_id": "repair_no_model", "task": "premise"})
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "GENERATION_UNAVAILABLE"
    message = str(detail["message"])
    assert "protagonist" not in message and "favors" not in message
    assert "traceback" not in message.lower()


# ------------------------------------------------------ NF-011 作品管理
def test_novel_rename_and_archive_delete_leave_no_orphans(tmp_path: Path) -> None:
    """删除作品＝整体归档：profile / Blueprint / Quality / Editor / Delivery 一起移动。"""

    stack = clean_studio(tmp_path)
    client = studio_app(tmp_path, gateway=stack["gateway"], memory=stack["memory"],
                        with_legacy=True)
    delivered = _deliver(client, NOVEL_ID, ["json"])
    assert delivered["ok"] is True

    renamed = client.patch(f"/api/story-builder/novels/{NOVEL_ID}",
                           json={"title": "新的作品名"})
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["title"] == "新的作品名"

    unconfirmed = client.delete(f"/api/story-builder/novels/{NOVEL_ID}")
    assert unconfirmed.status_code == 409, "删除必须二次确认"

    removed = client.delete(
        f"/api/story-builder/novels/{NOVEL_ID}?confirm=true&reason=acceptance")
    assert removed.status_code == 200, removed.text
    manifest = removed.json()
    assert manifest["recoverable"] is True and manifest["moved"]
    assert client.get("/api/story-builder/novels").json()["novels"] == []

    leftovers = [path for path in tmp_path.rglob(f"*{NOVEL_ID}*")
                 if "archived_novels" not in path.as_posix()]
    assert leftovers == [], f"删除后不得留下孤儿文件：{leftovers}"


# ------------------------------------------- 历史目录不得参与 current 计算
def test_services_ignore_historic_directories(tmp_path: Path) -> None:
    """只在历史布局里放数据，current 投影必须完全不受影响（没有任何回退读取）。"""

    from novelforge.application.services import JourneyService

    build_novel(tmp_path, "repair_legacy_dir", title="历史目录作品",
                fact_text="只验证历史目录不参与计算。")
    before = JourneyService(tmp_path, "repair_legacy_dir").projection()

    legacy = tmp_path / "novel" / "authoring" / "story_engine" / "writer" \
        / "repair_legacy_dir"
    (legacy / "drafts").mkdir(parents=True, exist_ok=True)
    (legacy / "index.json").write_text(json.dumps(
        {"drafts": [{"draft_id": "draft_legacy"}]}, ensure_ascii=False),
        encoding="utf-8")
    historic_outline = tmp_path / "novel" / "authoring" / "story_builder" / \
        "outlines" / "chapter"
    historic_outline.mkdir(parents=True, exist_ok=True)
    (historic_outline / "ol_legacy_repair_legacy_dir.json").write_text(
        "{}", encoding="utf-8")

    after = JourneyService(tmp_path, "repair_legacy_dir").projection()
    assert json.dumps(after, sort_keys=True, default=str) == \
        json.dumps(before, sort_keys=True, default=str), (
        "历史目录不得改变任何 current 投影（没有历史回退读取）")
