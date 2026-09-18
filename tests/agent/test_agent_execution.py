"""V4-11 §78–§80、§83、§88–§89：Golden goal 执行、幂等、不自动接受、不自动交付。"""

from __future__ import annotations

from pathlib import Path

from agent_support import agent_for, goal_for, seed


def _node(client_services, node_id: str) -> dict:
    return client_services.editor.get_node(node_id)["node"]


def test_golden_agent_goal_end_to_end(tmp_path: Path) -> None:
    stack = seed(tmp_path)
    agent = agent_for(stack)
    services = stack["services"]

    character_id = next(row["node_id"] for row in
                        services.export.blueprint_view()["blueprint"]["nodes"]
                        if row["node_type"] == "character")
    # 作者已经接受了这个人物（Agent 运行期间必须保持不变）
    services.editor.accept(character_id, revision=1)
    character_before = _node(services, character_id)
    preview = agent.plan(goal_for(stack))
    assert preview["dry_run"] is True and preview["mutations"] == 0
    plan = preview["plan"]
    assert plan["plan_revision"] == 1
    actions = [row["action"] for row in preview["preview"]]
    assert actions[0] == "inspect_blueprint"
    assert "generate_node" in actions and "evaluate" in actions
    assert "accept_revision" not in actions     # 默认不自动接受
    assert "deliver" not in actions             # 默认不自动交付

    result = agent.start(preview["session_id"], max_batch_steps=20)
    assert result["status"] == "completed", (result["stop_reason"], result["errors"])
    # 新增章节 / 场景都是 proposed（AI 建议，等待作者接受）
    services_after = stack["services"]
    view = services_after.export.blueprint_view(selection_mode="current")
    nodes = {row["node_id"]: row for row in view["blueprint"]["nodes"]}
    new_chapters = [row for row in nodes.values()
                    if row["node_type"] == "chapter" and row["node_id"] != "ch_001"]
    assert len(new_chapters) == 2
    assert all(row["status"] == "proposed" for row in new_chapters)
    # 已接受的角色设定没有被改动
    character_after = _node(services_after, character_id)
    assert character_after["revision"] == character_before["revision"]
    assert character_after["status"] == character_before["status"] == "accepted"
    # 质量检查真的跑了（step 结果里有 evaluate）
    evaluated = [row for row in result["steps"] if row["action"] == "evaluate"]
    assert evaluated and evaluated[0]["status"] == "completed"
    assert evaluated[0]["result_refs"].get("report_id")
    # 没有产生任何交付快照
    assert services_after.export.delivery_snapshots() == []
    # 审计完整：goal → plan → step → 业务结果
    audit = agent.audit_records(preview["session_id"])
    operations = {row["operation"] for row in audit}
    assert {"plan_created", "inspect_blueprint", "generate_node", "evaluate"} <= operations
    assert all(row["session_id"] == preview["session_id"] for row in audit)
    assert not any("prompt" in str(row).lower() for row in audit)


def test_idempotent_replay_creates_no_duplicates(tmp_path: Path) -> None:
    stack = seed(tmp_path)
    agent = agent_for(stack)
    session_id = agent.plan(goal_for(stack))["session_id"]
    first = agent.start(session_id, max_batch_steps=20)
    assert first["status"] == "completed"
    chapters_after_first = len([row for row in
                                stack["services"].export.blueprint_view()[
                                    "blueprint"]["nodes"]
                                if row["node_type"] == "chapter"])
    # 重放同一个 session（同一 plan / 同一 idempotency_key）
    replay = agent.resume(session_id)
    chapters_after_replay = len([row for row in
                                 stack["services"].export.blueprint_view()[
                                     "blueprint"]["nodes"]
                                 if row["node_type"] == "chapter"])
    assert replay["status"] in ("completed", "paused")
    assert chapters_after_replay == chapters_after_first


def test_agent_never_auto_accepts_even_when_quality_passes(tmp_path: Path) -> None:
    stack = seed(tmp_path)
    agent = agent_for(stack)
    goal = goal_for(stack, instruction="扩展到 3 个章节，运行质量检查，修复可修复问题，"
                                      "不要自动接受")
    session_id = agent.plan(goal)["session_id"]
    result = agent.start(session_id, max_batch_steps=20)
    assert result["status"] == "completed"
    assert [row["action"] for row in result["steps"]].count("accept_revision") == 0
    view = stack["services"].export.blueprint_view()
    new_nodes = [row for row in view["blueprint"]["nodes"]
                 if row["node_id"].startswith("ch_") and row["node_id"] != "ch_001"]
    assert new_nodes and all(row["status"] == "proposed" for row in new_nodes)


def test_agent_does_not_deliver_without_explicit_goal(tmp_path: Path) -> None:
    stack = seed(tmp_path)
    agent = agent_for(stack)
    session_id = agent.plan(goal_for(stack))["session_id"]
    agent.start(session_id, max_batch_steps=20)
    assert stack["services"].export.delivery_snapshots() == []
    # 默认 policy 不允许交付：计划只给 validate_delivery，并明确说明原因
    delivery_goal = goal_for(stack, instruction="导出 nfpack 包")
    preview = agent.plan(delivery_goal)
    actions = [row["action"] for row in preview["preview"]]
    assert "validate_delivery" in actions
    assert "deliver" not in actions
    assert any("allow_delivery" in note for note in
               preview["plan"]["budget_estimate"]["policy_notes"])
    # 显式开启策略后，deliver 出现且必须作者批准
    from novelforge.agent import AgentPolicy
    allowed = agent.plan(delivery_goal, policy=AgentPolicy(allow_delivery=True))
    deliver_steps = [row for row in allowed["preview"] if row["action"] == "deliver"]
    assert deliver_steps and deliver_steps[0]["requires_approval"] is True
