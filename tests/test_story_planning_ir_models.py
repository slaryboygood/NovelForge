"""M2A：Story Planning IR 模型 / Schema / 稳定 ID / provenance / 题材无关性。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from novelforge.story_engine.planning import (
    FORBIDDEN_GENRE_TERMS_IN_CORE,
    PLANNING_SCHEMA_ID,
    ForeshadowPlan,
    NovelIntent,
    PacingPlan,
    PlanningGateError,
    PlanningValidator,
    PlotNode,
    StoryPlanningIR,
    claims_happened,
    planning_digest,
    planning_id,
    planning_json_schema,
    validate_planning_ir,
)

FIXTURE = Path("tests/fixtures/planning_ir/ONE_SENTENCE_EXAMPLE.json")
PLANNING_DIR = Path("src/novelforge/story_engine/planning")


def _raw() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _plan() -> StoryPlanningIR:
    return validate_planning_ir(_raw())


def test_example_fixture_passes_strict_gate() -> None:
    plan = _plan()
    assert plan.novel_id == "demo_001"
    assert plan.schema_version == 1
    assert plan.spine is not None and len(plan.spine.nodes) == 3
    assert planning_digest(plan) == planning_digest(_plan())


def test_example_fixture_is_clean_for_validator() -> None:
    report = PlanningValidator(known_entity_ids=["ENTITY_PROTAGONIST"]).validate(_plan())
    assert report.ok(), report.findings
    assert report.findings == []


def test_strict_gate_rejects_implicit_coercion() -> None:
    raw = _raw()
    raw["intent"]["target_words"] = "120000"
    with pytest.raises(PlanningGateError) as error:
        validate_planning_ir(raw)
    assert error.value.code == "PLANNING_IR_SCHEMA_INVALID"
    assert "target_words" in " ".join(error.value.issues)


def test_strict_gate_rejects_unknown_field() -> None:
    raw = _raw()
    raw["intent"]["mystery_field"] = 1
    with pytest.raises(PlanningGateError):
        validate_planning_ir(raw)


def test_stable_id_rejects_chapter_number_and_display_text() -> None:
    for bad in ("ch012", "chapter_12", "volume1_ch2"):
        with pytest.raises(ValidationError):
            NovelIntent(intent_id=bad, novel_id="demo_001")
    with pytest.raises(ValueError):
        planning_id("INTENT_主角", "intent")
    with pytest.raises(ValueError):
        planning_id("CHAR_主角", "character")


def test_plot_node_ids_must_use_planning_prefix() -> None:
    with pytest.raises(ValidationError):
        PlotNode(node_id="CHAR_ACCEPT", purpose="前缀不正确")
    node = PlotNode(node_id="NODE_ACCEPT", purpose="接受委托")
    assert node.node_id == "NODE_ACCEPT"
    assert node.provenance == "generated"


def test_future_happened_boundary_inside_models() -> None:
    with pytest.raises(ValidationError):
        ForeshadowPlan(foreshadow_id="FSP_LOAD", plan_status="paid_off")
    with pytest.raises(ValidationError):
        PlotNode(node_id="NODE_X", purpose="既要又要", must_happen=True, optional=True)
    assert claims_happened("主角已经发生过一次失败") is True
    assert claims_happened("主角将要公开停工") is False


def test_confirmed_provenance_is_a_planned_capability() -> None:
    intent = NovelIntent(intent_id="INTENT_DEMO", novel_id="demo_001",
                         provenance="confirmed", confirmation_ref="svc://canon/confirm/1")
    assert intent.provenance == "confirmed"
    report = PlanningValidator().validate(StoryPlanningIR(
        novel_id="demo_001",
        intent=NovelIntent(intent_id="INTENT_DEMO", novel_id="demo_001",
                           provenance="confirmed", confirmation_ref="")))
    assert "UNCONFIRMED_PROVENANCE_WITHOUT_SERVICE_REF" in report.codes()


def test_pacing_channels_are_validated_against_enum() -> None:
    PacingPlan(pacing_id="PACE_DEMO", template_id="xianxia", intensity={"tension": 0.4})
    with pytest.raises(ValidationError):
        PacingPlan(pacing_id="PACE_DEMO", template_id="xianxia",
                   intensity={"climax_burst": 0.4})
    with pytest.raises(ValidationError):
        PacingPlan(pacing_id="PACE_DEMO", template_id="xianxia", intensity={"tension": -1})


def test_pacing_intensity_is_relative_not_a_percentage_budget() -> None:
    """裁决 4：相对强度，不要求和为 1，也不作为章节配额。"""

    plan = PacingPlan(pacing_id="PACE_DEMO", template_id="any_template",
                      intensity={"tension": 3, "reward": 0.5, "climax": 9})
    assert sum(plan.intensity.values()) == pytest.approx(12.5)
    assert plan.target_distribution == {}
    with pytest.raises(ValidationError):
        PacingPlan(pacing_id="PACE_DEMO", target_distribution_is_authoritative=True)


def test_planning_detail_levels_are_first_class() -> None:
    """裁决 1：One Planning Truth + Different Detail Levels。"""

    from novelforge.story_engine.planning import ArcPlan, LocationPlan, VolumePlan

    assert LocationPlan(location_id="LOC_X").detail_level == "concept"
    assert PlotNode(node_id="NODE_X").detail_level == "spine"
    assert VolumePlan(volume_id="VOL_X").detail_level == "volume"
    assert ArcPlan(arc_id="ARC_X", volume_id="VOL_X").detail_level == "arc"
    arc = ArcPlan(arc_id="ARC_X", volume_id="VOL_X", detail_level="chapter_ready")
    assert arc.detail_level == "chapter_ready"
    with pytest.raises(ValidationError):
        ArcPlan(arc_id="ARC_X", volume_id="VOL_X", detail_level="chapter")


def test_timeline_entry_has_stable_id_and_time_kinds() -> None:
    from novelforge.story_engine.planning import TimelineEntry

    entry = TimelineEntry(entry_id="TLE_ERA", label="旧桥时代", time_kind="era", era="旧桥时代",
                          status="legend")
    assert entry.entry_id.startswith("TLE_")
    assert entry.sequence_order == 0
    with pytest.raises(ValidationError):
        TimelineEntry(entry_id="ch012")
    with pytest.raises(ValidationError):
        TimelineEntry(entry_id="TLE_X", time_kind="chapter_number")
    with pytest.raises(ValidationError):
        TimelineEntry(entry_id="TLE_X", status="canonical")


def test_relationship_arc_has_no_numeric_truth_fields() -> None:
    """裁决 3：关系弧只用语义状态，不用 trust=78 这类数值真相。"""

    from novelforge.story_engine.planning import RelationshipArc

    numeric = [name for name, field in RelationshipArc.model_fields.items()
               if field.annotation in (int, float) and name != "order_index"]
    assert numeric == []
    arc = RelationshipArc(arc_id="RELARC_A", participants=["CHAR_A", "CHAR_B"])
    assert not hasattr(arc, "trust")


def test_plot_node_starts_unscheduled() -> None:
    """裁决 5：早期节点可以只存在于 StorySpine，不强制归卷。"""

    node = PlotNode(node_id="NODE_LATE", purpose="远期才会排期")
    assert node.scheduled_volume_id == ""
    assert node.scheduled_position is None
    scheduled = PlotNode(node_id="NODE_LATE", purpose="已排期",
                         scheduled_volume_id="VOL_ONE", scheduled_position=3)
    assert scheduled.scheduled_volume_id == "VOL_ONE"


def test_no_genre_hardcoding_in_planning_core() -> None:
    """题材词只能出现在 enums 的禁用清单里，不能出现在核心模型 / 校验逻辑里。"""

    offenders: list[str] = []
    for path in sorted(PLANNING_DIR.glob("*.py")):
        lines = path.read_text(encoding="utf-8").splitlines()
        in_blacklist = False
        for number, line in enumerate(lines, start=1):
            if "FORBIDDEN_GENRE_TERMS_IN_CORE" in line and "=" in line:
                in_blacklist = True
                continue
            if in_blacklist:
                if line.strip().startswith(")"):
                    in_blacklist = False
                continue
            for term in FORBIDDEN_GENRE_TERMS_IN_CORE:
                if term in line:
                    offenders.append(f"{path.name}:{number}: {term}")
    assert offenders == []


def test_json_schema_is_publishable() -> None:
    schema = planning_json_schema()
    assert schema["$id"] == PLANNING_SCHEMA_ID
    assert schema["x-schema-version"] == 1
    definitions = schema["$defs"]
    for name in ("NovelIntent", "ThemePlan", "WorldPlan", "CharacterPlan", "CharacterArc",
                 "RelationshipArc", "FactionPlan", "FactionArc", "LocationPlan",
                 "LocationGraph", "TimelinePlan", "InformationArc", "ForeshadowPlan",
                 "ProgressionTrack", "PlotNode", "StorySpine", "VolumePlan", "ArcPlan",
                 "PacingPlan"):
        assert name in definitions, name
