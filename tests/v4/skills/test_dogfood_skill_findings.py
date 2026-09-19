"""V4.0.1 skill dogfood：把这次实测发现固化成守卫。

来源：`docs/v4/V4_0_1_SKILL_DOGFOOD_REPORT.md`（§7 的 D1–D18）。
这些断言只覆盖两类事实：

1. 产品接口的真实形状（导入 contract / 读 FastAPI route 表），当接口变化时立刻失败；
2. skill 必须保留的"诚实警告"（例如某个能力当前不可用），避免文档又漂回乐观描述。

不修改任何 runtime；不需要网络、不需要模型。
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SKILL_ROOT = ROOT / "skills" / "novelforge-v4.0.1"
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def skill_text(*parts: str) -> str:
    path = SKILL_ROOT.joinpath(*parts)
    assert path.is_file(), f"missing skill file: {path}"
    return path.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def openapi_spec() -> dict:
    from novelforge.api.app import create_app

    app = create_app(Path(tempfile.mkdtemp(prefix="nf_skill_dogfood_")))
    return app.openapi()


# --- 产品接口事实（来自 dogfood 实测） -----------------------------------------


def test_character_arc_payload_requires_character_id():
    """D1：character_arc contract 必填 character_id，skill 必须写明。"""
    from novelforge.blueprint.contracts import CharacterArcPayload

    fields = CharacterArcPayload.model_fields
    assert "character_id" in fields
    assert fields["character_id"].is_required(), (
        "character_id 不再是必填：请同步更新 generate-character-arc skill 与 dogfood report")
    text = skill_text("generation", "generate-character-arc", "SKILL.md")
    assert "character_id" in text


def test_canon_post_routes_take_novel_id_as_query(openapi_spec):
    """D6/D7：validate-outline 与 rebuild 的 novel_id 是 query 参数，不是 body 字段。"""
    for path in ("/api/story-builder/canon/validate-outline",
                 "/api/story-builder/canon/rebuild"):
        operation = openapi_spec["paths"][path]["post"]
        parameters = {(p["name"], p["in"]) for p in operation.get("parameters", [])}
        assert ("novel_id", "query") in parameters, f"{path} 的 novel_id 不再是 query 参数"

    for skill in ("validate-planning-against-canon", "rebuild-canon"):
        text = skill_text("canon", skill, "SKILL.md")
        assert "?novel_id=" in text, f"canon/{skill} 未写明 novel_id 走 query"


def test_memory_query_has_no_text_field():
    """D8：MemoryQuery 没有 text/query 字段；检索维度是 task/entities/locations 等。"""
    from novelforge.memory import MemoryQuery

    fields = set(MemoryQuery.__dataclass_fields__)
    assert "text" not in fields and "query" not in fields
    assert {"task", "entities", "locations"} <= fields

    text = skill_text("memory", "inspect-derived-memory", "SKILL.md")
    assert "没有** `text`" in text or "没有" in text and "text" in text
    assert "task=" in text


# --- skill 必须保留的诚实警告 --------------------------------------------------


def test_structural_unit_and_scene_id_formats_documented():
    """D2/D4：结构单元 id 形如 act_01；场景 id 形如 sc_001_01（两位补零）。"""
    unit = skill_text("generation", "generate-structural-unit", "SKILL.md")
    assert "unit_<unit_type>_<index>" not in unit
    assert "act_01" in unit

    scene = skill_text("generation", "generate-scene-plan", "SKILL.md")
    assert "sc_007_2" not in scene
    assert "sc_007_02" in scene


def test_accept_revision_documents_non_idempotent_repeat():
    """D9：重复 accept 返回 422，而不是 idempotent=true。"""
    text = skill_text("editor", "accept-revision", "SKILL.md")
    assert "EDITOR_OPERATION_REJECTED" in text
    assert "idempotent=true" not in text.replace("**也不是** idempotent=true", "")


def test_quality_report_documents_real_summary_fields():
    """D10：summary 用 issues/open/by_gate/repair_rounds，没有 open_blockers。"""
    text = skill_text("quality", "inspect-quality-report", "SKILL.md")
    assert "open_blockers" not in text or "没有** open_blockers" in text
    assert "by_gate" in text


def test_delivery_validate_documents_unfiltered_blockers():
    """D11：policy 放不开关全部 blocker；历史 issue 按状态过滤的问题已记录。"""
    text = skill_text("delivery", "validate-delivery", "SKILL.md")
    assert "DELIVERY_Q9_BLOCKER" in text
    assert "explicit_revisions" in text
    assert "excluded" in text


def test_agent_skills_document_approval_defect_and_field_names():
    """D12–D15：plan/start/inspect 的真实字段；approve 当前缺陷必须保留警告。"""
    plan = skill_text("agent", "plan-agent-goal", "SKILL.md")
    assert "requires_approval" in plan

    inspect_text = skill_text("agent", "inspect-agent-session", "SKILL.md")
    for key in ("runs", "checkpoint", "pending_approvals", "audit"):
        assert key in inspect_text

    approve = skill_text("agent", "approve-agent-run", "SKILL.md")
    assert "AGENT_STEP_FAILED" in approve
    assert "approval_recorded" in approve


def test_mcp_start_skill_documents_pythonpath_and_stdio_defect():
    """D16：stdio 入口需要 PYTHONPATH=src，且当前会 crash（skill 必须保持警告）。"""
    text = skill_text("mcp", "start-mcp-server", "SKILL.md")
    assert "PYTHONPATH" in text
    assert "resources_changed" in text


def test_studio_skill_does_not_promise_root_flag():
    """D17：start_novelforge_ui.py 没有 --root。"""
    text = skill_text("studio", "open-story-studio", "SKILL.md")
    assert "`--root` | 否 | 项目根" not in text
    assert "studio_ui_test_server.py" in text
