"""M3：NOVEL_SPEC V2 回归（gaps / proposal / confirmation / compile / repository）。"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from novelforge.story_engine.planning import (
    FORBIDDEN_GENRE_TERMS_IN_CORE,
    PlanningRepository,
    PlanningValidationService,
    planning_digest,
)
from novelforge.story_engine.spec import (
    LLMSpecProposalProvider,
    NovelSpec,
    NovelSpecCompiler,
    SpecCharacterSeed,
    SpecGateError,
    SpecLocationSeed,
    SpecProposalError,
    SpecWorldSeed,
    StaticSpecProposalProvider,
    blocking_gaps,
    extract_proposal_payload,
    find_spec_gaps,
    propose_spec,
)

SPEC_DIR = Path("src/novelforge/story_engine/spec")


def _spec(**overrides) -> NovelSpec:
    payload = {
        "spec_id": "SPEC_DEMO", "novel_id": "demo_m3",
        "logline": "一个修理工想把断掉的桥重新接上。",
        "genre": "", "themes": ["修补意味着承担"], "target_reader": "",
        "commercial_promise": "", "reader_experience": [], "tone": "克制",
        "pace_strategy": "压力前置",
        "characters_seed": [{"seed_id": "lin", "display_name": "林工", "role": "主角",
                             "entity_ref": "ENTITY_PROTAGONIST", "external_goal": "让桥通车",
                             "internal_need": "被信任", "fear": "再塌一次"}],
        "world_seed": [{"seed_id": "bridge", "statement": "桥的承重有上限",
                        "rule_type": "hard_rule"}],
        "locations_seed": [{"seed_id": "bridge_loc", "display_name": "断桥",
                            "story_function": "主线舞台"}],
    }
    payload.update(overrides)
    return NovelSpec.model_validate(payload)


def _compiler() -> NovelSpecCompiler:
    return NovelSpecCompiler(novel_id="demo_m3", canon_snapshot_digest="abc123",
                             known_entity_ids=["ENTITY_PROTAGONIST"])


def _proposal_provider() -> StaticSpecProposalProvider:
    return StaticSpecProposalProvider([
        {"field": "target_reader", "value": "喜欢小镇工程故事的读者",
         "rationale": "读者画像", "confidence": 0.7},
        {"field": "commercial_promise", "value": "每卷修好一样基础设施",
         "rationale": "商业承诺", "confidence": 0.7},
    ])


def test_gap_rules_classify_missing_fields() -> None:
    gaps = find_spec_gaps(_spec(genre="", characters_seed=[]))
    by_field = {gap.field: gap for gap in gaps}
    assert by_field["characters_seed"].severity == "blocking"
    assert by_field["genre"].severity == "important"
    assert by_field["reader_experience"].severity == "optional"
    empty = NovelSpec(spec_id="SPEC_EMPTY", novel_id="demo_m3")
    assert [gap.field for gap in blocking_gaps(empty)] == ["logline", "characters_seed"]
    assert "characters_seed[0].external_goal" not in by_field


def test_character_seed_gaps_are_explicit() -> None:
    spec = _spec(characters_seed=[{"seed_id": "lin", "display_name": "林工"}])
    fields = {gap.field for gap in find_spec_gaps(spec)}
    assert "characters_seed[0].external_goal" in fields
    assert "characters_seed[0].internal_need" in fields


def test_proposal_requires_gap_alignment() -> None:
    spec = _spec()
    gaps = find_spec_gaps(spec)
    proposal = propose_spec(spec, gaps, _proposal_provider())
    assert proposal.field_names() == ["target_reader", "commercial_promise"]
    rogue = StaticSpecProposalProvider([{"field": "not_a_field", "value": "x"}])
    with pytest.raises(SpecProposalError) as error:
        propose_spec(spec, gaps, rogue)
    assert error.value.code == "SPEC_PROPOSAL_FIELD_NOT_IN_GAPS"


def test_unconfirmed_proposal_never_enters_planning() -> None:
    spec = _spec()
    proposal = propose_spec(spec, find_spec_gaps(spec), _proposal_provider())
    result = _compiler().compile(spec, proposal=proposal)
    assert result.plan is not None
    assert result.plan.intent.target_reader == ""
    assert result.plan.intent.commercial_promise == ""
    assert result.ignored_proposal_fields == ["commercial_promise", "target_reader"]
    assert result.validation_ok is True


def test_confirmation_applies_fields_as_supplied() -> None:
    spec = _spec()
    proposal = propose_spec(spec, find_spec_gaps(spec), _proposal_provider())
    confirmed, confirmation = _compiler().confirm(
        spec, proposal, {"target_reader": None, "commercial_promise": None},
        confirmation_id="CONF_DEMO_1")
    assert confirmation.confirmed_by == "author"
    assert confirmation.confirmed_fields["target_reader"] == "喜欢小镇工程故事的读者"
    assert confirmed.provenance_of("target_reader") == "supplied"
    result = _compiler().compile(confirmed, proposal=proposal)
    assert result.plan.intent.target_reader == "喜欢小镇工程故事的读者"
    assert result.plan.intent.provenance == "supplied"
    assert [gap.field for gap in result.gaps] == ["genre", "reader_experience", "constraints"]


def test_confirmation_gate_rejects_unknown_or_unproposed_fields() -> None:
    spec = _spec()
    proposal = propose_spec(spec, find_spec_gaps(spec), _proposal_provider())
    with pytest.raises(SpecGateError) as error:
        _compiler().confirm(spec, proposal, {"not_a_field": "x"}, confirmation_id="CONF_X")
    assert error.value.code == "SPEC_FIELD_NOT_CONFIRMABLE"
    with pytest.raises(SpecGateError) as missing:
        _compiler().confirm(spec, proposal, {"tone": "冷酷"}, confirmation_id="CONF_Y")
    assert missing.value.code == "SPEC_FIELD_NOT_IN_PROPOSAL"


def test_compile_does_not_generate_spine_or_plot_nodes() -> None:
    """M3 边界：StorySpine / PlotNode / Volume / Arc 属于 M6 / M8。"""

    result = _compiler().compile(_spec())
    assert result.plan is not None
    assert result.plan.plot_nodes == []
    assert result.plan.spine is None
    assert result.plan.volumes == []
    assert result.plan.arcs == []
    assert "SPINE_MISSING" in result.validation_codes
    assert {item.character_id for item in result.plan.characters} == {"CHAR_LIN"}
    world_ids = {rule.rule_id for rule in result.plan.world.world_rules}
    assert world_ids == {"RULE_BRIDGE"}


def test_compile_into_repository_creates_validated_revision(tmp_path: Path) -> None:
    spec = _spec()
    proposal = propose_spec(spec, find_spec_gaps(spec), _proposal_provider())
    confirmed, _ = _compiler().confirm(spec, proposal, {"target_reader": None},
                                       confirmation_id="CONF_DEMO_2")
    repo = PlanningRepository(tmp_path, "demo_m3")
    record, result = _compiler().compile_into_repository(confirmed, repo, proposal=proposal)
    assert record.revision == 1
    assert record.planning_id.startswith("PLAN_")
    assert result.revision_id == record.revision_id
    assert record.content_digest == planning_digest(record.plan)
    report = PlanningValidationService(
        repo, known_entity_ids=["ENTITY_PROTAGONIST"]).validate_revision(record.revision_id)
    assert report.ok(), report.findings
    assert report.digest_ok is True
    assert repo.resolve_branch_head("main").revision_id == record.revision_id


def test_llm_payload_must_pass_strict_schema() -> None:
    spec = _spec()
    with pytest.raises(SpecProposalError) as broken:
        extract_proposal_payload("{not json", proposal_id="PROP_X", spec=spec,
                                 provider="llm", model="m")
    assert broken.value.code == "SPEC_PROPOSAL_JSON_INVALID"
    with pytest.raises(SpecProposalError) as shape:
        extract_proposal_payload(json.dumps({"fields": "nope"}), proposal_id="PROP_X",
                                 spec=spec, provider="llm", model="m")
    assert shape.value.code == "SPEC_PROPOSAL_SHAPE_INVALID"
    with pytest.raises(SpecProposalError) as schema:
        extract_proposal_payload(
            json.dumps({"fields": [{"field": "tone", "value": 5, "confidence": "high"}]}),
            proposal_id="PROP_X", spec=spec, provider="llm", model="m")
    assert schema.value.code == "SPEC_PROPOSAL_SCHEMA_INVALID"
    proposal = extract_proposal_payload(
        json.dumps({"fields": [{"field": "tone", "value": "克制", "rationale": "r",
                                "confidence": 0.5}]}),
        proposal_id="PROP_OK", spec=spec, provider="llm", model="m")
    assert proposal.field("tone").value == "克制"
    assert proposal.spec_id == spec.spec_id


def test_llm_provider_retries_on_invalid_json(monkeypatch) -> None:
    spec = _spec()
    gaps = find_spec_gaps(spec)
    calls: list[str] = []

    def chat(messages) -> str:
        calls.append(messages[-1]["content"][:20])
        if len(calls) == 1:
            return "这不是 JSON"
        return json.dumps({"fields": [{"field": "genre", "value": "工程",
                                       "rationale": "题材", "confidence": 0.6}]})

    monkeypatch.setattr(time, "sleep", lambda _seconds: None)
    provider = LLMSpecProposalProvider(chat=chat, max_attempts=3, api_key="fake")
    proposal = provider.propose(spec, gaps)
    assert proposal.field("genre").value == "工程"
    assert len(calls) == 2
    assert proposal.provider == "llm"


def test_llm_provider_requires_key_without_injection() -> None:
    provider = LLMSpecProposalProvider(api_key="")
    with pytest.raises(SpecProposalError) as error:
        provider.propose(_spec(), find_spec_gaps(_spec()))
    assert error.value.code == "BLOCKED_REAL_LLM_PROPOSER_UNAVAILABLE"


def test_no_genre_hardcoding_in_spec_core() -> None:
    offenders: list[str] = []
    for path in sorted(SPEC_DIR.glob("*.py")):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            for term in FORBIDDEN_GENRE_TERMS_IN_CORE:
                if term in line:
                    offenders.append(f"{path.name}:{number}: {term}")
    assert offenders == []
