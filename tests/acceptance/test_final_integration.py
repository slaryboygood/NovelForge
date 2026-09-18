"""V4-12 Layer B — Cross-module Integration（§12–§23、§27–§31、§43）。"""

from __future__ import annotations

from pathlib import Path

import pytest

from acceptance_support import (
    GOLDEN_SHAPE,
    chapter_payload,
    golden_project,
    node_counts,
    scene_payload,
    service_for,
    services_with_script,
    truth_hashes,
)


def test_golden_project_covers_all_core_concepts(tmp_path: Path) -> None:
    stack = golden_project(tmp_path)
    counts = node_counts(stack["nodes"])
    assert counts.get("premise") and counts.get("theme") and counts.get("world")
    assert counts.get("character", 0) >= GOLDEN_SHAPE["characters"]
    assert counts.get("character_arc", 0) >= 1
    assert counts.get("story_arc", 0) >= 1
    assert counts.get("structural_unit", 0) >= GOLDEN_SHAPE["structural_units"]
    assert counts.get("chapter", 0) >= GOLDEN_SHAPE["chapters"]
    assert counts.get("scene", 0) >= GOLDEN_SHAPE["scenes"]
    assert counts.get("setup", 0) >= 1 and counts.get("payoff", 0) >= 1
    assert counts.get("causal_link", 0) >= 1
    assert str(tmp_path) in str(stack["root"])


def test_end_to_end_workflow_preserves_author_control(tmp_path: Path) -> None:
    """§14–§15：完整链路 + 作者控制权（AI 只产生 proposal）。"""

    stack = golden_project(tmp_path)
    repository = stack["repository"]
    # 需要 2 个 payload：一次 chapter 生成 + 一次 AI rewrite
    services = services_with_script(stack, [chapter_payload(), chapter_payload()])

    generated = services.blueprint.generate_task("chapter", parent_id="unit_01",
                                                 task_input={"index": 5})
    chapter_id = generated.node["node_id"]
    assert repository.get_current(chapter_id).status == "proposed"

    report = services.review.evaluate(node_ids=(chapter_id,), kind="changed")
    assert report.report_id
    assert report.status in ("passed", "failed", "blocked", "needs_human_review")

    before = repository.current_revision(chapter_id)
    patched = services.editor.patch(chapter_id, {"hook": "作者补写的钩子"},
                                   expected_revision=before)
    assert patched["revision"] > before
    assert repository.get_current(chapter_id).status != "accepted"

    preview = services.editor.rewrite(chapter_id, ("hook",), "更有悬念",
                                      expected_revision=patched["revision"],
                                      dry_run=True)
    assert preview["dry_run"] is True
    written = services.editor.rewrite(chapter_id, ("hook",), "更有悬念",
                                     expected_revision=patched["revision"])
    assert written["revision"] > patched["revision"]
    assert repository.get_current(chapter_id).status == "proposed"

    diff = services.editor.diff(chapter_id, from_revision=patched["revision"])
    assert diff["revision_before"] == patched["revision"] and diff["field_changes"]

    assert services.editor.accept(chapter_id)["decision"] == "accepted"
    assert repository.get_current(chapter_id).status == "accepted"
    assert services.editor.reject(chapter_id, reason="先不要")["decision"] == "rejected"

    current = repository.current_revision(chapter_id)
    services.editor.restore(chapter_id, from_revision=1)
    assert repository.current_revision(chapter_id) > current
    assert repository.list_revisions(chapter_id)[0] == 1
    assert repository.novel_id == stack["novel_id"]


def test_revision_chain_is_append_only(tmp_path: Path) -> None:
    stack = golden_project(tmp_path)
    repository, services = stack["repository"], stack["services"]
    node_id = "ch_001"
    revisions = repository.list_revisions(node_id)
    assert revisions == sorted(revisions) and revisions[0] == 1
    for revision in revisions:
        node = repository.get_revision(node_id, revision)
        assert node is not None
        if revision > 1:
            assert node.parent_revision == revision - 1
    first = repository.get_revision(node_id, 1).as_dict()
    services.editor.patch(node_id, {"hook": "新钩子"},
                          expected_revision=repository.current_revision(node_id))
    assert repository.get_revision(node_id, 1).as_dict() == first


def test_restore_creates_new_revision_and_keeps_history(tmp_path: Path) -> None:
    stack = golden_project(tmp_path)
    repository, services = stack["repository"], stack["services"]
    before = repository.list_revisions("ch_001")
    services.editor.restore("ch_001", from_revision=1)
    after = repository.list_revisions("ch_001")
    assert after == [*before, before[-1] + 1]


def test_concurrency_conflict_does_not_overwrite(tmp_path: Path) -> None:
    stack = golden_project(tmp_path)
    services, repository = stack["services"], stack["repository"]
    node_id = "ch_001"
    revision = repository.current_revision(node_id)
    services.editor.patch(node_id, {"hook": "B 的修改"}, expected_revision=revision)
    with pytest.raises(Exception):
        services.editor.patch(node_id, {"hook": "A 的修改"},
                              expected_revision=revision)
    assert repository.current_revision(node_id) == revision + 1
    assert repository.get_current(node_id).payload.model_dump(
        mode="json")["hook"] == "B 的修改"


def test_agent_revision_conflict_pauses_with_zero_mutation(tmp_path: Path) -> None:
    from agent_support import agent_for, goal_for, seed

    from novelforge.agent import AgentScope

    stack = seed(tmp_path, accept=("story_arc",))
    agent = agent_for(stack)
    aces = stack["services"]
    # 重写高层已接受节点属于 novel 级决定（scope=novel）
    session_id = agent.plan(goal_for(stack, instruction="重写已接受的 Story Arc 高潮",
                                     scope=AgentScope(kind="novel"))
                            )["session_id"]
    first = agent.start(session_id, max_batch_steps=20)
    assert first["status"] == "awaiting_approval"
    approval_id = agent.status(session_id)["pending_approvals"][0]["approval_id"]
    revision = aces.editor.get_node("story_arc")["node"]["revision"]
    aces.editor.patch("story_arc", {"resolution": "作者手动改"},
                      expected_revision=revision)
    with pytest.raises(Exception):
        agent.approve(session_id, approval_id)
    assert aces.editor.get_node("story_arc")["node"]["revision"] == revision + 1


def test_idempotency_single_side_effect_per_key(tmp_path: Path) -> None:
    stack = golden_project(tmp_path)
    repository = stack["repository"]
    services = services_with_script(stack, [chapter_payload(), chapter_payload()])

    first = services.blueprint.generate_task("chapter", parent_id="unit_01",
                                             idempotency_key="acceptance-gen-1",
                                             task_input={"index": 6})
    second = services.blueprint.generate_task("chapter", parent_id="unit_01",
                                              idempotency_key="acceptance-gen-1",
                                              task_input={"index": 6})
    assert first.node["node_id"] == second.node["node_id"]
    assert repository.current_revision(first.node["node_id"]) == first.revision

    node_id = first.node["node_id"]
    revision = repository.current_revision(node_id)
    one = services.editor.patch(node_id, {"hook": "幂等钩子"},
                                expected_revision=revision,
                                idempotency_key="acceptance-edit-1")
    two = services.editor.patch(node_id, {"hook": "幂等钩子"},
                                expected_revision=revision,
                                idempotency_key="acceptance-edit-1")
    assert one["revision"] == two["revision"]


def test_agent_step_replay_is_idempotent(tmp_path: Path) -> None:
    from agent_support import agent_for, goal_for, seed

    stack = seed(tmp_path)
    agent = agent_for(stack)
    session_id = agent.plan(goal_for(stack))["session_id"]
    agent.start(session_id, max_batch_steps=20)
    chapters_first = len([row for row in
                          stack["services"].export.blueprint_view()[
                              "blueprint"]["nodes"]
                          if row["node_type"] == "chapter"])
    agent.resume(session_id)
    chapters_second = len([row for row in
                           stack["services"].export.blueprint_view()[
                               "blueprint"]["nodes"]
                           if row["node_type"] == "chapter"])
    assert chapters_second == chapters_first


def test_memory_is_derived_and_rebuildable(tmp_path: Path) -> None:
    stack = golden_project(tmp_path)
    root, novel_id = stack["root"], stack["novel_id"]
    truth_before = truth_hashes(root, novel_id)
    memory_dir = root / "novel" / "authoring" / "story_engine" / "memory"
    if memory_dir.is_dir():
        for path in sorted(memory_dir.rglob("*"), reverse=True):
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                path.rmdir()
    rebuilt = service_for(root, novel_id)
    result = rebuilt.search(novel_id=novel_id, task="供电", entities=("hero",))
    assert result.items is not None
    assert truth_hashes(root, novel_id) == truth_before


def test_generation_uses_context_builder(tmp_path: Path) -> None:
    stack = golden_project(tmp_path)
    services = services_with_script(stack, [scene_payload("ch_004")])
    result = services.blueprint.generate_task("scene", parent_id="ch_004",
                                             task_input={"sequence": 1,
                                                         "chapter_index": 4})
    node = stack["repository"].get_current(result.node["node_id"])
    assert node.context_digest
    assert node.generation_contract.startswith("blueprint.")


def test_canon_and_storystate_unchanged_by_pipeline(tmp_path: Path) -> None:
    stack = golden_project(tmp_path)
    root, novel_id = stack["root"], stack["novel_id"]
    repository = stack["repository"]
    services = services_with_script(stack, [chapter_payload()])
    before = truth_hashes(root, novel_id)
    services.blueprint.generate_task("chapter", parent_id="unit_01",
                                     task_input={"index": 7})
    services.review.evaluate()
    services.editor.patch("ch_001", {"hook": "钩子"},
                          expected_revision=repository.current_revision("ch_001"))
    services.editor.accept("ch_001")
    after = truth_hashes(root, novel_id)
    canon_before = {key: value for key, value in before.items() if "canon" in key}
    canon_after = {key: value for key, value in after.items() if "canon" in key}
    state_before = {key: value for key, value in before.items() if "/state/" in key}
    state_after = {key: value for key, value in after.items() if "/state/" in key}
    assert canon_after == canon_before, "Canon 被流水线修改"
    assert state_after == state_before, "StoryState 被流水线修改"
