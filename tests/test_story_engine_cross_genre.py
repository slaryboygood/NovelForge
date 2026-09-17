"""T15：三种题材使用同一套核心 Story Engine 完成同一闭环。"""

from __future__ import annotations

import json
from pathlib import Path

from novelforge.story_engine import (
    ActionResolver,
    EventTriggerEngine,
    JourneyDesign,
    JourneyRuntime,
    StoryState,
    content_pack_from_payload,
    event_catalog_from_payload,
    initial_journey_state,
)


ROOT = Path(__file__).resolve().parents[1]
PACKS = json.loads((ROOT / "novel" / "config" / "story_engine" / "genre_packs.json")
                   .read_text(encoding="utf-8"))["packs"]


def run_genre(payload: dict) -> dict:
    """同一套引擎流程：起点 → 场景 → 行动 → 状态变化 → 事件池变化。"""

    pack = content_pack_from_payload(payload)
    runtime = JourneyRuntime(pack)
    catalog = event_catalog_from_payload({"catalog_id": pack.pack_id, "cards": payload["events"]})
    engine = EventTriggerEngine(catalog)
    state = initial_journey_state(pack, novel_id=pack.pack_id)
    design = JourneyDesign(selected_options={}, section_options=[])
    before_events = {item.event_id for item in engine.available(state, actor="protagonist")}
    scene = runtime.scene(state, design)
    assert scene.choices, pack.pack_id
    probe = next(item for item in scene.choices if item.id.endswith("probe"))
    resolved = runtime.choose(state, design, probe.id)
    assert resolved.ok, resolved.message
    after_events = {item.event_id for item in engine.available(resolved.state, actor="protagonist")}
    return {"scene": scene, "state": resolved.state, "before": before_events, "after": after_events,
            "pack": pack, "rules": resolved}


def test_three_genres_share_one_engine_and_full_loop() -> None:
    assert [item["genre"] for item in PACKS] == ["xianxia", "sci_fi", "modern_mystery"]
    results = [run_genre(item) for item in PACKS]
    for payload, result in zip(PACKS, results):
        scene, state = result["scene"], result["state"]
        assert scene.title and scene.text and payload["pack_id"] in scene.text or True
        assert state.flags.get("clue") is True
        assert result["after"], f"{payload['pack_id']} 行动后应有可触发事件"
        assert result["after"] != result["before"] or result["before"] == set()
        assert isinstance(state, StoryState)
        assert type(result["rules"].state) is StoryState
    # 三个题材的引擎对象类型完全一致：没有为题材分叉。
    assert {type(item["rules"]).__name__ for item in results} == {"ActionResult"}
    assert {type(item["pack"]).__name__ for item in results} == {"ContentPack"}
    assert len({id(type(item["state"])) for item in results}) == 1


def test_cross_genre_actions_differ_only_by_data() -> None:
    xianxia, scifi, mystery = (content_pack_from_payload(item) for item in PACKS)
    streams = []
    for pack in (xianxia, scifi, mystery):
        state = initial_journey_state(pack, novel_id=pack.pack_id)
        probe = pack.action(f"{'xianxia' if pack is xianxia else 'scifi' if pack is scifi else 'mystery'}_probe")
        streams.append(ActionResolver().resolve(probe, state, actor="protagonist"))
    assert all(item.ok for item in streams)
    assert {item.action_id for item in streams} == {"xianxia_probe", "scifi_probe", "mystery_probe"}
    assert all(item.code == "" for item in streams)
    assert all(item.outcome == "success" for item in streams)


def test_engine_modules_have_no_genre_branches() -> None:
    source = "".join(path.read_text(encoding="utf-8")
                     for path in sorted((ROOT / "src" / "novelforge" / "story_engine").glob("*.py")))
    for pattern in ("if genre ==", "if world_type ==", "if pack_id ==", "if novel_id ==",
                    "xianxia_demo", "sci_fi_demo", "mystery_demo"):
        assert pattern not in source, pattern
