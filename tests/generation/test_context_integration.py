"""Context Builder 集成（V4-04 §15–§16、§44–§46）。"""

from __future__ import annotations

import json
from pathlib import Path

from novelforge.persistence.paths import canon_db_path
from gen_support import blueprint_service, build_novel, premise_payload


def test_generation_uses_context_builder_and_records_digest(tmp_path: Path) -> None:
    build_novel(tmp_path, "novel_alpha", title="阿尔法计划", fact_text="主角不会使用枪械")
    service, provider = blueprint_service(tmp_path, "novel_alpha", [premise_payload()])
    result = service.generate_task("premise")
    node = service.read(result.node["node_id"])
    assert node["context_digest"] == result.context_digest
    assert node["provenance"]["context_blocks"][0] == "required.canon"
    assert node["source_ids"], "上下文来源必须记录在节点上"


def test_prompt_receives_canon_and_preferences(tmp_path: Path) -> None:
    build_novel(tmp_path, "novel_alpha", title="阿尔法计划", fact_text="主角不会使用枪械")
    service, provider = blueprint_service(tmp_path, "novel_alpha", [premise_payload()])
    service.generation.context_builder.preferences.set(
        "novel", "forbidden_tropes", ["失忆"])
    service.generate_task("premise")
    prompt = provider.requests[0].user
    assert "枪械" in prompt, "Canon 必须进入模型上下文"
    assert "失忆" in prompt, "作者偏好必须进入模型上下文"


def test_generation_does_not_modify_canon_or_story_state(tmp_path: Path) -> None:
    build_novel(tmp_path, "novel_alpha", title="阿尔法计划", fact_text="主角不会使用枪械")
    db = canon_db_path(tmp_path, "novel_alpha")
    before = (db.stat().st_size, db.stat().st_mtime_ns)
    service, _provider = blueprint_service(tmp_path, "novel_alpha", [premise_payload()])
    service.generate_task("premise")
    after = (db.stat().st_size, db.stat().st_mtime_ns)
    assert before == after, "生成不得写入 Canon（proposal only，§29）"


def test_context_selection_is_deterministic_for_same_request(tmp_path: Path) -> None:
    build_novel(tmp_path, "novel_alpha", title="阿尔法计划", fact_text="主角不会使用枪械")
    service, _provider = blueprint_service(tmp_path, "novel_alpha",
                                           [premise_payload(), premise_payload()])
    first = service.generate_task("premise")
    second = service.regenerate(task="premise", node_id="premise", expected_revision=1)
    assert first.context_digest == second.context_digest, \
        "同一任务与同一 canonical 状态 → 同一上下文 digest（§46）"


def test_router_selection_is_deterministic(tmp_path: Path) -> None:
    build_novel(tmp_path, "novel_alpha", title="阿尔法计划", fact_text="主角不会使用枪械")
    service, _provider = blueprint_service(tmp_path, "novel_alpha", [premise_payload()])
    steps = service.plan().steps
    policy = [steps[i]["capabilities"] for i in range(3)]
    assert policy[0] == ["creative", "structured_output"], "premise 只声明 capability"
    assert all(step["contract_id"].startswith("blueprint.")
               for step in steps[:9])
