"""W5 专项：阶段自动推进、伏笔运行时时间线、世界事件密度调节。"""

from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from novelforge.api.story_builder_routes import install_story_builder_api
from novelforge.story_builder import load_story_catalog
from novelforge.story_engine.creative import CreativeBrief, save_creative_brief
from novelforge.story_engine.context import story_state_preview
from novelforge.story_engine.driver import advance_story, candidates_for
from novelforge.story_engine.effects import EffectSpec, apply_effects
from novelforge.story_engine.foreshadow import foreshadow_timeline
from novelforge.story_engine.linkage import (
    FuturePlan,
    StageGoal,
    advance_stages,
    plot_tracks,
    replan_with_plots,
)
from novelforge.story_engine.profile import NovelProfileRepository
from novelforge.story_engine.settings_gen import build_setting_seed, load_pack_draft, \
    save_setting_seed
from novelforge.story_engine.world import world_event_density

PROJECT_ROOT = Path(__file__).resolve().parents[1]
IDEA = "一个普通维修工发现城市其实运行在一套隐藏的修仙操作系统上。"


def prepared(tmp_path: Path, novel_id: str = "novel_w5"):
    source = PROJECT_ROOT / "novel" / "config" / "story_engine"
    target = tmp_path / "novel" / "config" / "story_engine"
    target.mkdir(parents=True, exist_ok=True)
    for item in source.glob("*.json"):
        target.joinpath(item.name).write_text(item.read_text(encoding="utf-8"), encoding="utf-8")
    save_creative_brief(tmp_path, novel_id,
                        CreativeBrief(original_idea=IDEA, selected_genre="xianxia",
                                      tone="紧张悬疑"))
    save_setting_seed(tmp_path, novel_id, seed=build_setting_seed(tmp_path, novel_id))
    pack = load_pack_draft(tmp_path, f"{novel_id}_pack")
    profile = NovelProfileRepository(tmp_path).load(novel_id)
    return pack, profile, story_state_preview(profile, pack)


def test_stage_auto_advances_with_completed_plots(tmp_path: Path) -> None:
    pack, profile, state = prepared(tmp_path)
    plan = FuturePlan(stages=[
        StageGoal(id="s1", title="表层问题", goal="查清表层问题"),
        StageGoal(id="s2", title="长期方向", goal="取得可以自主行动的位置"),
    ])
    # 一开始：第一个阶段 active，第二个 planned。
    first = advance_stages(plan, state)
    assert [row.status for row in first.stages] == ["active", "planned"]
    # 支线完成后：对应阶段 done，下一个阶段 active。
    track = plot_tracks(state)[0]
    finished = state.model_copy(deep=True)
    finished.plots[track.id] = {**finished.plots[track.id], "status": "completed"}
    advanced = advance_stages(plan, finished)
    assert [row.status for row in advanced.stages] == ["done", "active"]
    # 已经 active 的阶段不会被降级（重规划激活的阶段保持生效）。
    both_active = FuturePlan(stages=[
        StageGoal(id="s1", title="表层问题", goal="查清表层问题", status="active"),
        StageGoal(id="s2", title="长期方向", goal="取得位置", status="active"),
    ])
    kept_active = advance_stages(both_active, state)
    assert [row.status for row in kept_active.stages] == ["active", "active"]
    # 作者显式改过的阶段不被覆盖。
    changed = plan.model_copy(update={"stages": [
        plan.stages[0].model_copy(update={"status": "changed"}),
        plan.stages[1]]})
    kept = advance_stages(changed, finished)
    assert kept.stages[0].status == "changed"
    # replan_with_plots 也会自动推进（驱动器的重规划路径）。
    replanned = replan_with_plots(plan, finished, note="测试")
    assert replanned.stages[0].status == "done"
    assert replanned.stages[1].status == "active"


def test_foreshadow_runtime_timeline(tmp_path: Path) -> None:
    pack, profile, state = prepared(tmp_path)
    plant = apply_effects(state, [EffectSpec(op="update_foreshadow", target="fs_demo",
                                             data={"status": "planted"})],
                          actor="protagonist")
    assert plant.ok
    moved = apply_effects(plant.state, [EffectSpec(op="advance_time", value=3)],
                          actor="protagonist")
    assert moved.ok
    reinforced = apply_effects(moved.state, [
        EffectSpec(op="update_foreshadow", target="fs_demo",
                   data={"status": "reinforced", "reinforce": True})],
        actor="protagonist")
    assert reinforced.ok
    rows = foreshadow_timeline(reinforced.state)
    assert rows and rows[0]["id"] == "fs_demo"
    assert rows[0]["status"] == "reinforced"
    assert rows[0]["planted_tick"] == 0
    assert rows[0]["age"] == 3
    assert rows[0]["reinforce_count"] == 1
    closed = apply_effects(reinforced.state, [
        EffectSpec(op="update_foreshadow", target="fs_demo", data={"status": "resolved"})],
        actor="protagonist")
    rows = foreshadow_timeline(closed.state)
    assert rows[0]["status"] == "resolved"
    assert rows[0]["closed_tick"] == 3
    # 只读投影：状态只存在 StoryState.flags，不新增存储。
    assert "foreshadows" in closed.state.flags


def test_world_event_density_follows_pack_configuration(tmp_path: Path) -> None:
    pack, profile, state = prepared(tmp_path)
    assert pack.world_event_gap == 2, "生成的设定包默认给世界事件留出间隔"
    fired: list[int] = []
    current = state
    for index in range(6):
        rows = [row.action_id for row in candidates_for(current, pack) if row.available]
        result = advance_story(current, pack, action_id=rows[index % len(rows)],
                               actor="protagonist")
        assert result.ok
        current = result.state
        fired.append(len(result.world_events))
    assert fired == [1, 0, 1, 0, 1, 0], "gap=2 时世界事件应隔 turn 触发"
    density = world_event_density(current)
    assert density and density[0]["event_id"] == "ev_world_shift"
    assert density[0]["fired"] == 3 and density[0]["gap"] <= 1
    # gap=0（旧行为）：每回合都允许触发。
    dense_pack = pack.model_copy(update={"world_event_gap": 0})
    dense_state = state
    dense_fired: list[int] = []
    for index in range(4):
        rows = [row.action_id for row in candidates_for(dense_state, dense_pack)
                if row.available]
        result = advance_story(dense_state, dense_pack, action_id=rows[index % len(rows)],
                               actor="protagonist")
        dense_state = result.state
        dense_fired.append(len(result.world_events))
    assert dense_fired[0] == 1 and sum(dense_fired) >= 2


def test_memory_snapshot_exposes_foreshadow_timeline(tmp_path: Path) -> None:
    pack, profile, state = prepared(tmp_path)
    app = FastAPI()
    install_story_builder_api(app, tmp_path, catalog=load_story_catalog(PROJECT_ROOT))
    client = TestClient(app)
    payload = client.get("/api/story-builder/creator/memory?novel_id=novel_w5").json()
    assert "foreshadow_timeline" in payload
    assert isinstance(payload["foreshadow_timeline"], list)


def test_w5_layers_reuse_existing_engine(tmp_path: Path) -> None:
    root = PROJECT_ROOT / "src/novelforge"
    for name, markers in {
        "story_engine/linkage.py": ("def advance_stages", "plot_tracks"),
        "story_engine/foreshadow.py": ("def foreshadow_timeline", "StoryState"),
        "story_engine/world.py": ("def world_event_density", "def run_world_events"),
    }.items():
        source = (root / name).read_text(encoding="utf-8")
        for marker in markers:
            assert marker in source, f"{name} 缺少 {marker}"
    # 内容包字段是数据，不是新系统：默认值保持旧行为。
    from novelforge.story_engine.content import ContentPack
    assert ContentPack.model_fields["world_event_gap"].default == 0
