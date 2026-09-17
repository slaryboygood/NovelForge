"""V2 Runtime Driver 专项测试（Pilot-01 最小修复）。

覆盖：连续 12 回合、保存 / 重载 / 继续、非法 action、成本不足、stale revision、
no candidates（blocked 不改事实）、延迟后果跨回合、世界 / NPC 自主行动、
事件 + Director、Writer 失败降级。

全部通过正式 `advance_story(...)`，不手工调用底层积木。
"""

from __future__ import annotations

import json
from pathlib import Path

from novelforge.story_engine import (
    ActionResolver,  # noqa: F401 - 用于断言驱动确实走同一条 resolver
    ContentPack,
    StoryState,
    StoryStateRepository,
    content_pack_from_payload,
)
from novelforge.story_engine.driver import (
    advance_story,
    runtime_candidates,
    runtime_tick,
    story_revision,
)

PACK_PAYLOAD = {
    "pack_id": "driver_pack",
    "title": "驱动测试包",
    "initial_flags": {"journey_revision": 0, "ready": True, "ally": False},
    "initial_resources": {"supplies": 30, "spirit_stone": 4},
    "autonomous_rules": [
        {"actor_id": "npc_worker", "action_id": "t_help", "label": "NPC 自行帮忙", "priority": 3,
         "once": True},
    ],
    "actions": [
        {"id": "t_probe", "kind": "investigate", "name": "调查线索",
         "delayed_effects": [
             {"id": "t_delay_witness", "description": "有人看到这次调查",
              "trigger": {"op": "time", "key": "tick", "value": 3, "comparator": ">="},
              "effects": [{"op": "change_relationship", "entity": "protagonist",
                           "target": "npc", "key": "hostility", "value": 1}]}],
         "data": {"weight": 2, "cost_text": "不消耗资源"}},
        {"id": "t_help", "kind": "protect", "name": "帮助同伴",
         "costs": [{"op": "remove_resource", "target": "supplies", "value": 1}],
         "immediate_effects": [{"op": "set_flag", "key": "ally", "value": True}],
         "data": {"weight": 1, "cost_text": "消耗 1 补给"}},
        {"id": "t_locked", "kind": "trade", "name": "需要内门身份",
         "requirements": [{"op": "identity", "entity": "protagonist", "value": "inner_candidate"}],
         "data": {"cost_text": "需要身份"}},
        {"id": "t_paid", "kind": "trade", "name": "花 4 灵石打通关系",
         "costs": [{"op": "remove_resource", "target": "spirit_stone", "value": 4}],
         "data": {"cost_text": "消耗 4 灵石"}},
    ],
    "events": [
        {"event_id": "t_ev_ally", "title": "同伴回应", "kind": "side", "priority": 3,
         "once_only": False, "trigger": {"op": "flag", "key": "clue", "value": True},
         "data": {"event_type": "favor", "pacing": "setup", "payoff": 1}},
        {"event_id": "t_ev_world", "title": "外界风闻", "kind": "world", "priority": 4,
         "once_only": False, "scope": "world", "knowledge_id": "world_rumor",
         "reader_visible": True,
         "trigger": {"op": "flag", "key": "ally", "value": True},
         "consequences": [{"op": "update_faction", "target": "guild",
                           "data": {"influence": 2}}],
         "data": {"world_event": True, "pacing": "turn", "event_type": "rumor"}},
    ],
    "foreshadows": [
        {"id": "t_fs", "title": "测试伏笔", "status": "planned", "planted_in": "开篇",
         "payoff_in": "收束", "data": {"level": "book"}},
    ],
    "progressions": [{"tree_id": "t_tree", "name": "测试成长", "nodes": [
        {"id": "t_node_a", "tree_id": "t_tree", "kind": "ability", "category": "ability",
         "name": "起步能力", "summary": "", "story_impact": ""},
    ]}],
}


def pack() -> ContentPack:
    return content_pack_from_payload(PACK_PAYLOAD)


def initial_state(novel_id: str = "novel_driver") -> StoryState:
    state = StoryState(novel_id=novel_id, flags=dict(PACK_PAYLOAD["initial_flags"]))
    from novelforge.story_engine import Character, Faction, ResourceStock

    state.characters["protagonist"] = Character(id="protagonist", name="主角", kind="player")
    state.characters["npc"] = Character(id="npc", name="同伴", kind="npc")
    state.characters["npc_worker"] = Character(id="npc_worker", name="工匠", kind="npc")
    state.factions["guild"] = Faction(id="guild", name="行会", kind="faction",
                                      data={"influence": 5})
    for key, amount in PACK_PAYLOAD["initial_resources"].items():
        state.resources[key] = ResourceStock(id=key, amount=float(amount), holders=["protagonist"])
    return state


def test_twelve_turns_through_formal_driver(tmp_path: Path) -> None:
    """① 连续 12 回合：每轮成功、revision/tick 正常、持久化、产生 next candidates、不进入旧 rev7 上限。"""

    states = StoryStateRepository(tmp_path)
    state = initial_state()
    states.save(state, "bp_driver_pack_0000000000", 1, "main")
    revisions, ticks = [], []
    for turn in range(1, 13):
        state = states.load("bp_driver_pack_0000000000", 1, "main")
        action = "t_probe" if turn % 2 else "t_help"
        result = advance_story(state, pack(), action_id=action, actor="protagonist",
                               expected_revision=story_revision(state))
        assert result.ok, (turn, result.blocked, result.message)
        assert result.next_candidates, f"第 {turn} 轮必须产生下一轮候选"
        assert result.available_actions, f"第 {turn} 轮必须有可用行动"
        states.save(result.state, "bp_driver_pack_0000000000", 1, "main")
        revisions.append(result.revision)
        ticks.append(result.tick)
    assert revisions == list(range(1, 13)), revisions
    assert ticks == list(range(1, 13)), ticks  # 每个运行回合让世界时间前进一格
    reloaded = states.load("bp_driver_pack_0000000000", 1, "main")
    assert story_revision(reloaded) == 12
    assert reloaded.timeline.tick == 12
    # 旧 Journey 的 rev7 上限在这里完全不存在：运行态 revision 已经到 12。
    assert story_revision(reloaded) == 12


def test_save_reload_continue_is_continuous(tmp_path: Path) -> None:
    """② 跑 6 回合 → 重新 load → 再跑 6 回合。"""

    states = StoryStateRepository(tmp_path)
    states.save(initial_state(), "bp_driver_pack_0000000000", 1, "main")
    for turn in range(6):
        state = states.load("bp_driver_pack_0000000000", 1, "main")
        result = advance_story(state, pack(), action_id="t_probe", actor="protagonist")
        assert result.ok
        states.save(result.state, "bp_driver_pack_0000000000", 1, "main")
    middle = story_revision(states.load("bp_driver_pack_0000000000", 1, "main"))
    assert middle == 6
    for turn in range(6):
        state = states.load("bp_driver_pack_0000000000", 1, "main")
        result = advance_story(state, pack(), action_id="t_help", actor="protagonist",
                               expected_revision=story_revision(state))
        assert result.ok, result.message
        states.save(result.state, "bp_driver_pack_0000000000", 1, "main")
    final = states.load("bp_driver_pack_0000000000", 1, "main")
    assert story_revision(final) == 12
    assert len([item for item in final.effect_log if item.op == "runtime_action"]) == 12


def test_blocked_action_does_not_change_state(tmp_path: Path) -> None:
    """③ 不可用 action 被拒绝，StoryState 不变。④ 成本不足不扣资源。"""

    state = initial_state()
    before = state.model_dump()
    locked = advance_story(state, pack(), action_id="t_locked", actor="protagonist")
    assert locked.ok is False and locked.blocked == "action_not_available"
    assert locked.state.model_dump() == before
    unknown = advance_story(state, pack(), action_id="no_such_action", actor="protagonist")
    assert unknown.ok is False and unknown.blocked == "action_not_in_catalog"
    assert unknown.state.model_dump() == before
    # 成本不足：把灵石清空后 t_paid 不可用，资源不被扣。
    poor = initial_state()
    poor.resources["spirit_stone"] = poor.resources["spirit_stone"].model_copy(update={"amount": 1})
    poor_before = poor.model_dump()
    paid = advance_story(poor, pack(), action_id="t_paid", actor="protagonist")
    assert paid.ok is False and paid.blocked == "action_not_available"
    assert paid.state.model_dump() == poor_before
    assert paid.state.resources["spirit_stone"].amount == 1


def test_stale_revision_is_rejected_without_effects(tmp_path: Path) -> None:
    """⑤ 重复 / 过期请求：expected_revision 校验，不重复产生效果。"""

    states = StoryStateRepository(tmp_path)
    states.save(initial_state(), "bp_driver_pack_0000000000", 1, "main")
    first = advance_story(states.load("bp_driver_pack_0000000000", 1, "main"), pack(),
                          action_id="t_probe", actor="protagonist", expected_revision=0)
    assert first.ok and first.revision == 1
    states.save(first.state, "bp_driver_pack_0000000000", 1, "main")
    stale = advance_story(states.load("bp_driver_pack_0000000000", 1, "main"), pack(),
                          action_id="t_probe", actor="protagonist", expected_revision=0)
    assert stale.ok is False and stale.blocked == "stale_revision"
    assert stale.revision == 1
    assert story_revision(stale.state) == 1


def test_no_candidates_blocks_without_inventing_options() -> None:
    """⑥ 无可用行动：返回 blocked，不改事实，不凭空生成兜底选项。"""

    state = initial_state()
    # 让所有行动都不可用：t_probe / t_help 可用，这里改用只含 t_locked 的包。
    only_locked = content_pack_from_payload({
        **PACK_PAYLOAD,
        "actions": [item for item in PACK_PAYLOAD["actions"] if item["id"] == "t_locked"],
        "autonomous_rules": [],
        "events": [],
    })
    before = state.model_dump()
    result = advance_story(state, only_locked, action_id="", actor="protagonist")
    assert result.ok is False and result.blocked == "no_available_actions"
    assert result.state.model_dump() == before
    # 只读候选查询同样给出 blocked 标记，且没有伪造候选。
    readonly = runtime_candidates(state, only_locked, actor="protagonist")
    assert readonly["available"] == [] and readonly["blocked"] == ["no_available_actions"]


def test_world_tick_can_unblock_through_real_world_change() -> None:
    """⑥ 续：世界推进可以改变状态并重新产生候选，而不是凭空塞一个等待选项。"""

    state = initial_state()
    gated = content_pack_from_payload({
        **PACK_PAYLOAD,
        "actions": [
            {"id": "t_gated", "kind": "investigate", "name": "需要同伴回来的行动",
             "requirements": [{"op": "flag", "key": "ally", "value": True}],
             "data": {"cost_text": "需要同伴"}},
            {"id": "t_help", "kind": "protect", "name": "帮助同伴",
             "costs": [{"op": "remove_resource", "target": "supplies", "value": 1}],
             "immediate_effects": [{"op": "set_flag", "key": "ally", "value": True}]},
        ],
        "autonomous_rules": [
            {"actor_id": "npc_worker", "action_id": "t_help", "label": "工匠主动帮忙",
             "priority": 3, "once": True},
        ],
        "events": [],
    })
    # 开局 ally=false：需要同伴的行动不可用，只有玩家自己帮助同伴才会开锁。
    before = runtime_candidates(state, gated, actor="protagonist")
    assert "t_gated" not in before["available"]
    blocked = advance_story(state, gated, action_id="t_gated", actor="protagonist")
    assert blocked.ok is False and blocked.blocked == "action_not_available"
    ticked = runtime_tick(state, gated, actor="protagonist")
    assert ticked.ok is True and ticked.world_actions, "世界 tick 应产生 NPC 自主行动"
    assert "t_gated" in ticked.available_actions, "世界变化后候选必须重新计算"
    assert ticked.state.flags.get("ally") is True


def test_delayed_effect_settles_across_turns() -> None:
    """⑦ 延迟后果跨回合结算。"""

    state = initial_state()
    first = advance_story(state, pack(), action_id="t_probe", actor="protagonist")
    assert first.ok and "t_delay_witness" in first.state.delayed_effects or \
        first.state.delayed_effects
    assert [item.get("id") for item in first.state.delayed_effects] == ["t_delay_witness"]
    working = first.state
    settled_seen: list[str] = []
    for _ in range(3):
        step = advance_story(working, pack(), action_id="t_probe", actor="protagonist")
        assert step.ok
        settled_seen.extend(step.settled_delayed)
        working = step.state
    # 每次 t_probe 都会排入一条同名延迟后果；世界时间到达 tick 3 后必须结算并移除。
    assert settled_seen, "条件满足后延迟后果必须结算"
    assert "t_delay_witness" in settled_seen
    assert working.timeline.tick >= 3
    assert len(working.delayed_effects) < len(first.state.delayed_effects) + 3
    assert any(item.get("id") == "t_delay_witness" for item in first.state.delayed_effects)
    hostility = [item for item in working.relationships
                 if item.source_id == "protagonist" and item.target_id == "npc"]
    assert hostility and hostility[0].dimensions.get("hostility", 0) >= 1


def test_world_autonomy_and_world_events_run_without_hero_action() -> None:
    """⑧ 主角行动之外，世界仍产生真实变化（NPC 自主行动 + 世界事件）。"""

    state = initial_state()
    result = advance_story(state, pack(), action_id="t_probe", actor="protagonist")
    assert result.ok
    assert result.world_actions, "NPC 自主行动必须被记录"
    assert all(item["actor"] == "npc_worker" for item in result.world_actions)
    assert any(item.op == "world_action" for item in result.state.effect_log)
    # NPC 自主行动把 ally 置真后，世界事件条件成立并在同一轮内触发。
    second = advance_story(result.state, pack(), action_id="t_probe", actor="protagonist")
    assert second.ok and second.state.flags.get("ally") is True
    assert "t_ev_world" in second.world_events, second.world_events
    assert any(item.op == "world_event" for item in second.state.effect_log)
    assert second.state.factions["guild"].data.get("influence") == 2


def test_director_only_ranks_legal_events_and_writer_failure_degrades() -> None:
    """⑨ Director 只排合法事件；⑩ Writer 失败走 fallback 且事实不丢。"""

    state = initial_state()
    locked = advance_story(state, pack(), action_id="t_probe", actor="protagonist")
    # clue 未成立时，t_ev_ally 不合法，不会出现在导演排名里。
    ranked_before = [item["event_id"] for item in locked.director_decision.get("ranked", [])]
    assert "t_ev_ally" not in ranked_before
    helped = advance_story(locked.state, pack(), action_id="t_help", actor="protagonist")
    ranked_after = [item["event_id"] for item in helped.director_decision.get("ranked", [])]
    assert "t_ev_ally" not in ranked_after, "条件未成立时事件不得进入导演排序"
    unlocked = locked.state.model_copy(deep=True)
    unlocked.flags["clue"] = True
    opened = advance_story(unlocked, pack(), action_id="t_probe", actor="protagonist")
    assert "t_ev_ally" in [item["event_id"] for item in opened.director_decision.get("ranked", [])], \
        "条件成立后事件才进入导演排序"

    def broken_generator(package):  # noqa: ANN001 - 模拟 LLM 异常
        raise RuntimeError("llm offline")

    degraded = advance_story(helped.state, pack(), action_id="t_probe", actor="protagonist",
                             writer_generator=broken_generator)
    assert degraded.ok is True
    assert degraded.writer_result["fallback_used"] is True
    assert degraded.writer_result["text"]
    assert story_revision(degraded.state) == story_revision(helped.state) + 1
    assert degraded.state.effect_log, "Writer 失败不得丢失事实"


def test_driver_does_not_mutate_input_state() -> None:
    """驱动只返回新状态，不就地修改传入的 StoryState。"""

    state = initial_state()
    before = state.model_dump()
    advance_story(state, pack(), action_id="t_probe", actor="protagonist")
    assert state.model_dump() == before


def test_driver_has_no_second_engine_or_genre_branching() -> None:
    """架构守卫：驱动只编排既有模块，不重新实现规则，也没有题材分支。"""

    source = (Path(__file__).resolve().parents[1]
              / "src/novelforge/story_engine/driver.py").read_text(encoding="utf-8")
    for pattern in ("if genre ==", "if world_type ==", "if novel_id ==", "class StoryState(",
                    "class ActionResolver(", "class EventTriggerEngine(", "class DirectorWeights(",
                    "class ProgressionTree(", "class KnowledgeEntry("):
        assert pattern not in source, f"driver.py 违反约束：{pattern}"
    # 必须复用既有模块，而不是自建实现。
    for marker in ("generate_candidates", "ActionResolver", "settle_delayed", "run_world_tick",
                   "run_world_events", "EventTriggerEngine", "decide", "build_writer_package",
                   "render_scene"):
        assert marker in source, f"driver.py 必须复用：{marker}"
    assert json.dumps(PACK_PAYLOAD, ensure_ascii=False)  # 保持测试包可序列化


def test_plot_effect_and_driver_sync_produce_real_transitions() -> None:
    """P2-06：支线流转必须由 Action / Effect / 世界状态驱动，并且 Driver 会调用既有 sync_plots。"""

    from novelforge.story_engine import PlotTrack, plot_tracks, upsert_plot

    pack_with_plots = content_pack_from_payload({
        **PACK_PAYLOAD,
        "actions": [
            {"id": "t_open_case", "kind": "investigate", "name": "打开案子",
             "immediate_effects": [{"op": "set_flag", "key": "case_open", "value": True}]},
            {"id": "t_advance_case", "kind": "investigate", "name": "推进案情",
             "immediate_effects": [{"op": "update_plot", "target": "t_plot",
                                    "data": {"steps": 1}}]},
            {"id": "t_close_case", "kind": "report", "name": "结案",
             "immediate_effects": [{"op": "update_plot", "target": "t_plot",
                                    "data": {"status": "completed", "note": "指证成功"}}]},
        ],
        "events": [],
        "autonomous_rules": [],
    })
    state = initial_state()
    state = upsert_plot(state, PlotTrack(id="t_plot", title="测试支线", status="inactive",
                                         trigger={"op": "flag", "key": "case_open", "value": True}))
    # inactive → active：由 flag 打开后 Driver 的 sync_plots 自动激活。
    opened = advance_story(state, pack_with_plots, action_id="t_open_case", actor="protagonist")
    assert opened.ok, opened.message
    assert any(item["plot"] == "t_plot" and item["to"] == "active"
               for item in opened.plot_transitions), opened.plot_transitions
    # active → progressed：由 update_plot 效果的 steps 推进。
    progressed = advance_story(opened.state, pack_with_plots, action_id="t_advance_case",
                               actor="protagonist")
    assert progressed.ok
    track = next(item for item in plot_tracks(progressed.state) if item.id == "t_plot")
    assert track.progress == 1
    # active → completed：同样由效果写入，不手工改状态。
    closed = advance_story(progressed.state, pack_with_plots, action_id="t_close_case",
                           actor="protagonist")
    assert closed.ok
    final = next(item for item in plot_tracks(closed.state) if item.id == "t_plot")
    assert final.status == "completed"
    assert any(item["plot"] == "t_plot" and item["to"] == "completed"
               for item in closed.plot_transitions)


def test_future_plan_replans_only_on_impactful_change_and_keeps_history() -> None:
    """P2-07：关键状态变化触发未来重规划；happened 不得被改写。"""

    from novelforge.story_engine import FuturePlan, StageGoal, build_route

    plan = FuturePlan(plan_id="t_plan", revision=1,
                      stages=[StageGoal(id="s1", title="第一阶段", goal="查清案子",
                                        status="active"),
                              StageGoal(id="s2", title="第二阶段", goal="收束支线",
                                        status="planned")])
    state = initial_state()
    step = advance_story(state, pack(), action_id="t_help", actor="protagonist",
                         future_plan=plan)
    assert step.ok
    assert step.future_plan_changed is True
    assert step.replan_reason
    assert step.old_future_summary != step.new_future_summary
    # 历史不可改写：重规划不会丢记录、也不会改写已有记录（重规划前后用同一状态重建路线）。
    before_replan = build_route(step.state, plan=plan)
    after_replan = build_route(step.state)
    assert after_replan.happened == before_replan.happened
    # 传入状态本身不被就地修改。
    assert build_route(state, plan=plan).happened == []
    # 没有关键变化时不重规划。
    quiet_pack = content_pack_from_payload({**PACK_PAYLOAD,
                                            "actions": [{"id": "t_wait", "kind": "wait",
                                                         "name": "等待"}],
                                            "autonomous_rules": [], "events": []})
    quiet = advance_story(state, quiet_pack, action_id="t_wait", actor="protagonist",
                          future_plan=plan)
    assert quiet.ok and quiet.future_plan_changed is False


def test_foreshadow_runtime_status_is_written_by_effect() -> None:
    """P3-05：伏笔状态必须能由 Action / Event 在运行时推进，并可从 StoryState 读回。"""

    from novelforge.story_engine.memory_view import foreshadow_rows
    from novelforge.story_engine.foreshadow import Foreshadow

    pack_with_foreshadow = content_pack_from_payload({
        **PACK_PAYLOAD,
        "actions": [
            {"id": "t_plant", "kind": "investigate", "name": "埋下线索",
             "immediate_effects": [{"op": "update_foreshadow", "target": "t_fs",
                                    "data": {"status": "planted", "reason": "找到残页"}}]},
            {"id": "t_reinforce", "kind": "investigate", "name": "再次触碰",
             "immediate_effects": [{"op": "update_foreshadow", "target": "t_fs",
                                    "data": {"status": "reinforced", "reinforce": True}}]},
            {"id": "t_payoff", "kind": "report", "name": "回收",
             "immediate_effects": [{"op": "update_foreshadow", "target": "t_fs",
                                    "data": {"status": "resolved", "reason": "当面对质"}}]},
        ],
        "events": [], "autonomous_rules": [],
    })
    state = initial_state()
    planted = advance_story(state, pack_with_foreshadow, action_id="t_plant", actor="protagonist")
    assert planted.ok and planted.state.flags["foreshadows"]["t_fs"]["status"] == "planted"
    reinforced = advance_story(planted.state, pack_with_foreshadow, action_id="t_reinforce",
                               actor="protagonist")
    entry = reinforced.state.flags["foreshadows"]["t_fs"]
    assert entry["status"] == "reinforced" and entry["reinforce_count"] == 1
    assert entry["tick"] >= 1
    paid = advance_story(reinforced.state, pack_with_foreshadow, action_id="t_payoff",
                         actor="protagonist")
    assert paid.ok and paid.state.flags["foreshadows"]["t_fs"]["status"] == "resolved"
    definition = Foreshadow(id="t_fs", title="测试伏笔", status="planned")
    rows = foreshadow_rows([definition], paid.state)
    assert rows[0]["status"] == "resolved" and rows[0]["runtime_tick"] >= 1
    # 非法状态被拒绝，且不写状态。
    bad = content_pack_from_payload({
        **PACK_PAYLOAD,
        "actions": [{"id": "t_bad", "kind": "investigate", "name": "坏状态",
                     "immediate_effects": [{"op": "update_foreshadow", "target": "t_fs",
                                            "data": {"status": "exploded"}}]}],
        "events": [], "autonomous_rules": [],
    })
    rejected = advance_story(state, bad, action_id="t_bad", actor="protagonist")
    assert rejected.ok is False
    assert "foreshadows" not in rejected.state.flags
