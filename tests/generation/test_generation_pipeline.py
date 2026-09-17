"""完整 Blueprint 流水线 golden 测试（V4-04 §6、§50）。"""

from __future__ import annotations

from pathlib import Path

from gen_support import (
    blueprint_service,
    build_novel,
    chapter_payload,
    character_arc_payload,
    character_payload,
    premise_payload,
    scene_payload,
    story_arc_payload,
    theme_payload,
    unit_payload,
    world_payload,
)


def _payloads() -> list:
    return [
        premise_payload(), theme_payload(), world_payload(),
        character_payload("韩彻", kind="player"),
        character_arc_payload("system-assigned"),
        character_payload("老鸦"),
        character_arc_payload("system-assigned"),
        story_arc_payload(), unit_payload("act"),
        chapter_payload(), chapter_payload("第二日：许可被撤回"),
        scene_payload("system-assigned"), scene_payload("system-assigned"),
    ]


def _build(tmp_path: Path):
    build_novel(tmp_path, "novel_alpha", title="阿尔法计划", fact_text="主角不会使用枪械")
    service, provider = blueprint_service(tmp_path, "novel_alpha", _payloads())
    service.generate_task("premise")
    service.generate_task("theme")
    service.generate_task("world")
    hero = service.generate_task("character", task_input={"index": 1, "kind": "player"})
    service.generate_task("character_arc", parent_id=hero.node["node_id"],
                          task_input={"characters": [hero.node["node_id"]]})
    rival = service.generate_task("character", task_input={"index": 2, "kind": "npc"})
    service.generate_task("character_arc", parent_id=rival.node["node_id"],
                          task_input={"characters": [rival.node["node_id"]]})
    story_arc = service.generate_task("story_arc")
    unit = service.generate_task("structural_unit",
                                 task_input={"index": 1, "unit_type": "act", "total": 1})
    ch1 = service.generate_task("chapter", parent_id=unit.node["node_id"],
                               task_input={"index": 1, "total": 2,
                                           "characters": [hero.node["node_id"],
                                                          rival.node["node_id"]]})
    ch2 = service.generate_task("chapter", parent_id=unit.node["node_id"],
                               task_input={"index": 2, "total": 2,
                                           "characters": [hero.node["node_id"]]})
    sc1 = service.generate_task("scene", parent_id=ch1.node["node_id"],
                               task_input={"sequence": 1, "total": 1, "chapter_index": 1,
                                           "characters": [hero.node["node_id"]]})
    sc2 = service.generate_task("scene", parent_id=ch2.node["node_id"],
                               task_input={"sequence": 1, "total": 1, "chapter_index": 2,
                                           "characters": [hero.node["node_id"]]})
    links = service.build_links()
    return service, provider, {"hero": hero, "rival": rival, "story_arc": story_arc,
                               "unit": unit, "ch1": ch1, "ch2": ch2,
                               "sc1": sc1, "sc2": sc2, "links": links}


def test_pipeline_produces_the_full_node_graph(tmp_path: Path) -> None:
    service, provider, nodes = _build(tmp_path)
    tree = service.tree()
    assert tree["by_type"]["premise"] == 1
    assert tree["by_type"]["character"] == 2
    assert tree["by_type"]["character_arc"] == 2
    assert tree["by_type"]["chapter"] == 2
    assert tree["by_type"]["scene"] == 2
    assert tree["by_type"]["setup"] >= 1
    assert tree["by_type"]["causal_link"] >= 1
    assert provider.calls == 13, "每个生成任务一次调用（不含确定性 links）"


def test_parent_child_and_sequence_are_structural(tmp_path: Path) -> None:
    service, _provider, nodes = _build(tmp_path)
    unit_children = service.children(nodes["unit"].node["node_id"], node_type="chapter")
    assert [row["node_id"] for row in unit_children] == ["ch_001", "ch_002"]
    chapters = service.children(nodes["unit"].node["node_id"], node_type="chapter")
    assert [row["sequence"] for row in chapters] == [1, 2]
    scenes = service.read(nodes["sc1"].node["node_id"])
    assert scenes["parent_id"] == "ch_001"
    assert scenes["payload"]["chapter_id"] == "ch_001", "chapter_id 由系统分配（§47）"


def test_scene_cards_express_story_function_and_state_intent(tmp_path: Path) -> None:
    service, _provider, nodes = _build(tmp_path)
    scene = service.read(nodes["sc1"].node["node_id"])
    payload = scene["payload"]
    assert payload["scene_purpose"], "必须回答「这一场为什么存在」"
    assert "advance_plot" in payload["story_function"]
    intent = payload["state_transition_intent"]
    assert intent and intent[0]["kind"] == "knowledge"
    assert payload["next_hook"]
    assert not any(key in payload for key in ("prose", "body", "text")), \
        "Scene Card 不得包含正文"


def test_causal_links_and_setup_payoff_are_derived(tmp_path: Path) -> None:
    service, _provider, nodes = _build(tmp_path)
    links = nodes["links"]
    assert links["counts"]["causal_link"] >= 1
    causal = service.read(links["causal_link"][0])
    assert causal["payload"]["relation"] in {"causes", "enables", "pays_off"}
    assert causal["payload"]["reason"]
    setup = service.read(links["setup"][0])
    assert setup["payload"]["content"]
    assert setup["payload"]["status"] in {"open", "paid", "partially_paid"}


def test_graph_validation_passes_and_reports_unpaid_setups(tmp_path: Path) -> None:
    service, _provider, nodes = _build(tmp_path)
    report = service.validate()
    assert report["ok"] is True, report["issues"]
    assert report["node_count"] >= 12
    assert isinstance(report["unpaid_setups"], list)


def test_every_node_has_provenance_and_contract(tmp_path: Path) -> None:
    service, _provider, _nodes = _build(tmp_path)
    for row in service.tree()["nodes"]:
        if row["node_type"] in ("setup", "payoff", "causal_link"):
            continue  # 确定性结构关系没有 LLM contract
        assert row["generation_contract"].startswith("blueprint.")
        assert row["generation_contract_version"] == 1
        assert row["context_digest"]
        assert row["provenance"]["context_blocks"]
        assert row["source_ids"], "每个生成节点都必须保留 source_ids"


def test_pipeline_is_rebuildable_from_saved_revisions(tmp_path: Path) -> None:
    service, _provider, _nodes = _build(tmp_path)
    snapshot = service.tree()
    fresh = blueprint_service(tmp_path, "novel_alpha", [])[0]
    assert fresh.tree()["by_type"] == snapshot["by_type"], \
        "Blueprint 可从 canonical store 重新读出同一结构"
