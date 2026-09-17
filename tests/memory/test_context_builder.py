"""Context Builder（V4-03 §17–§20、§34–§35）。"""

from __future__ import annotations

from pathlib import Path

import pytest

from novelforge.memory import (
    AuthorPreferenceService,
    ContextBuilder,
    ContextRequest,
)
from novelforge.memory.semantic import SemanticEntry
from support import build_novel, build_two_novels, service_for


def _builder(tmp_path: Path, novel_id: str = "novel_alpha",
             **kwargs) -> ContextBuilder:
    preferences = AuthorPreferenceService(novel_id, project_root=tmp_path,
                                          project_id=novel_id)
    preferences.set("novel", "forbidden_tropes", ["失忆", "穿越"])
    preferences.set("novel", "pacing", "快")
    service = service_for(tmp_path, novel_id)
    return ContextBuilder(service, preferences=preferences, **kwargs)


def _request(**overrides) -> ContextRequest:
    payload = {"novel_id": "novel_alpha", "operation": "scene_plan",
               "task": "下一场戏：主角在车站面对对手",
               "target_kind": "scene", "target_id": "sc_002",
               "characters": ("hero", "rival"), "locations": ("station",),
               "token_budget": 1200}
    payload.update(overrides)
    return ContextRequest(**payload)


# ---------------------------------------------------------------- golden（§34）
def test_golden_context_bundle_contains_expected_blocks(tmp_path: Path) -> None:
    build_novel(tmp_path, "novel_alpha", title="阿尔法计划", fact_text="主角不会使用枪械")
    bundle = _builder(tmp_path).build(_request())

    assert bundle.order == (
        "required.canon", "required.story_state", "required.target",
        "relevant.characters", "recent.episodes", "relevant.setup_payoff",
        "relevant.locations", "relevant.semantic", "preferences")

    canon_text = " ".join(item.text for item in bundle.blocks["required.canon"].items)
    assert "枪械" in canon_text, "相关 Canon 必须包含"

    state_text = " ".join(item.text
                          for item in bundle.blocks["required.story_state"].items)
    assert "当前位置" in state_text
    assert "主角" in state_text, "状态块必须包含出场角色的可读名称"

    episode_text = " ".join(item.text for item in bundle.blocks["recent.episodes"].items)
    assert "act_betray" in episode_text or "rival" in episode_text, \
        "最近的背叛 episode 必须包含"

    setup_text = " ".join(item.text
                          for item in bundle.blocks["relevant.setup_payoff"].items)
    assert "备用电源" in setup_text, "未回收 setup / 承诺必须包含"

    preference_values = [row["value"] for row in bundle.preferences]
    assert ["失忆", "穿越"] in preference_values, "作者明确要求必须进入上下文"


def test_golden_bundle_excludes_unrelated_semantic_items(tmp_path: Path) -> None:
    build_novel(tmp_path, "novel_alpha", title="阿尔法计划", fact_text="主角不会使用枪械")
    service = service_for(tmp_path, "novel_alpha")
    service.add_semantic([
        SemanticEntry(entry_id="unrelated", novel_id="novel_alpha",
                      text="完全无关的天气记录", keywords=("天气", "记录")),
    ])
    builder = ContextBuilder(service)
    bundle = builder.build(_request())
    semantic_text = " ".join(item.text
                             for item in bundle.blocks["relevant.semantic"].items)
    assert "完全无关" not in semantic_text, "无关语义条目不得进入上下文"


def test_golden_bundle_has_no_prompt_string(tmp_path: Path) -> None:
    build_novel(tmp_path, "novel_alpha", title="阿尔法计划", fact_text="主角不会使用枪械")
    bundle = _builder(tmp_path).build(_request())
    assert not isinstance(bundle, str)
    payload = bundle.as_dict()
    assert isinstance(payload["blocks"], dict)
    assert "huge_prompt_string" not in str(payload)
    context = bundle.to_memory_context()
    assert set(context) == {"blocks", "preferences", "budget"}


def test_context_is_deterministic(tmp_path: Path) -> None:
    build_novel(tmp_path, "novel_alpha", title="阿尔法计划", fact_text="主角不会使用枪械")
    builder = _builder(tmp_path)
    first = builder.build(_request())
    second = builder.build(_request())
    assert first.order == second.order
    assert first.digest == second.digest, "同一请求必须得到同一上下文 digest"
    assert [item.memory_id for item in first.items] == \
        [item.memory_id for item in second.items]


def test_selection_reasons_are_explainable(tmp_path: Path) -> None:
    build_novel(tmp_path, "novel_alpha", title="阿尔法计划", fact_text="主角不会使用枪械")
    bundle = _builder(tmp_path).build(_request())
    reasons = {block.selection_reason for block in bundle.blocks.values()}
    assert {"required_canon", "current_state", "recent_episode",
            "author_preference"} <= reasons
    for row in bundle.provenance:
        assert row["source_id"] and row["source_type"]
        assert row["selection_reason"] and row["block_id"]


def test_provenance_records_revision(tmp_path: Path) -> None:
    build_novel(tmp_path, "novel_alpha", title="阿尔法计划", fact_text="主角不会使用枪械")
    bundle = _builder(tmp_path).build(_request())
    assert bundle.memory_schema_version >= 1
    assert any(row["revision"] is not None for row in bundle.provenance)


def test_duplicate_items_are_deduplicated(tmp_path: Path) -> None:
    """同一 memory_id 出现在多个 block 时只保留优先级最高的一个。"""

    build_novel(tmp_path, "novel_alpha", title="阿尔法计划", fact_text="主角不会使用枪械")
    service = service_for(tmp_path, "novel_alpha")
    from novelforge.memory.retrieval import semantic_entries_from_items

    items = service.index.items("novel_alpha", source_types=("canon_entity",))
    service.add_semantic(semantic_entries_from_items("novel_alpha", items))
    bundle = ContextBuilder(service).build(_request())
    ids = [item.memory_id for item in bundle.items]
    assert len(ids) == len(set(ids)), "同一 memory_id 不得在多个 block 重复出现"


def test_budget_flag_is_reported(tmp_path: Path) -> None:
    build_novel(tmp_path, "novel_alpha", title="阿尔法计划", fact_text="主角不会使用枪械")
    bundle = _builder(tmp_path).build(_request(token_budget=40))
    assert bundle.budget["limit"] == 40
    assert bundle.budget["used"] <= 40 or bundle.budget["overflow"] > 0


def test_context_rejects_other_novel(tmp_path: Path) -> None:
    from novelforge.memory import MemoryError

    build_two_novels(tmp_path)
    service = service_for(tmp_path, "novel_alpha")
    builder = ContextBuilder(service)
    with pytest.raises(MemoryError):
        builder.build(_request(novel_id="novel_beta"))
