"""M2B：Repository E2E（§27）。

load fixture → validate → R1 → branch experiment → 改一个 future 字段 → R2 → diff
→ rollback → scoped context → CanonBootstrapProposal → StoryStateInitProposal，
全部 gate PASS，并把可复现的轨迹写成 `tests/fixtures/planning_ir/M2B_REPOSITORY_E2E.json`。

artifact 里不含时间戳 / 随机 ID（revision id 显式给定），因此可重复生成、可进 git。
"""

from __future__ import annotations

import json
from pathlib import Path

from novelforge.story_engine.planning import (
    PlanningRepository,
    PlanningValidationService,
    StoryPlanningContextBuilder,
    assert_no_future_content,
    build_canon_bootstrap_proposal,
    build_story_state_init_proposal,
    planning_digest,
    planning_json_schema,
    summarize_plan,
    validate_planning_ir,
)

FIXTURES = Path("tests/fixtures/planning_ir")
FIXTURE = FIXTURES / "ONE_SENTENCE_EXAMPLE.json"
ARTIFACT = FIXTURES / "M2B_REPOSITORY_E2E.json"
R1 = "PREV_E2E00000R1"
R2 = "PREV_E2E00000R2"
R3 = "PREV_E2E00000R3"


def _raw() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _run(tmp_path: Path) -> dict:
    plan = validate_planning_ir(_raw())
    repo = PlanningRepository(tmp_path, "demo_001")
    service = PlanningValidationService(repo, known_entity_ids=["ENTITY_PROTAGONIST"])

    first = repo.create(plan, status="proposed", note="R1 初始规划", revision_id=R1)
    report_r1 = service.validate_revision(first.revision_id)
    assert report_r1.ok(), report_r1.findings

    repo.create_branch("experiment-a", from_revision_id=first.revision_id)
    raw = _raw()
    raw["plot_nodes"][1]["payoff"] = "换到真材料与调查时间（实验线修订）"
    raw["arcs"][0]["turns"][0] = "材料问题变成责任问题（实验线修订）"
    experiment_plan = validate_planning_ir(raw)
    second = repo.create(experiment_plan, branch_id="experiment-a", status="proposed",
                         note="R2 实验线：改 future 字段", revision_id=R2)
    report_r2 = service.validate_revision(second.revision_id,
                                          previous_revision_id=first.revision_id)
    assert report_r2.ok(), report_r2.findings

    diff = repo.compare(first.revision_id, second.revision_id)
    by_domain: dict[str, int] = {}
    by_change: dict[str, int] = {}
    for row in diff.rows:
        by_domain[row.domain] = by_domain.get(row.domain, 0) + 1
        by_change[row.change] = by_change.get(row.change, 0) + 1
    assert by_change == {"modified": 2}

    second_bytes = repo.revision_path(second.revision_id).read_bytes()
    third = repo.rollback_head(first.revision_id, branch_id="experiment-a", note="回到 R1",
                               new_revision_id=R3)
    assert repo.revision_path(second.revision_id).read_bytes() == second_bytes
    assert third.status == "rolled_back"
    assert planning_digest(third.plan) == planning_digest(first.plan)
    report_r3 = service.validate_revision(third.revision_id)
    assert report_r3.ok(), report_r3.findings
    assert repo.load(second.revision_id).status == "superseded"

    context_builder = StoryPlanningContextBuilder(third.plan, revision_id=third.revision_id,
                                                 content_digest=third.content_digest)
    chapter_context = context_builder.build("chapter_planning")
    plot_context = context_builder.build("plot")
    assert chapter_context.boundary == "planning_future_not_happened"
    assert "mystery" not in json.dumps(plot_context.payload, ensure_ascii=False)

    summary = summarize_plan(third.plan, revision_id=third.revision_id,
                             content_digest=third.content_digest)
    bootstrap = build_canon_bootstrap_proposal(third.plan, revision_id=third.revision_id)
    init = build_story_state_init_proposal(third.plan, revision_id=third.revision_id,
                                          starting_location_ids=["LOC_TOWN"])
    assert_no_future_content("CanonBootstrapProposal", bootstrap.model_dump(mode="json"))
    assert_no_future_content("StoryStateInitProposal", init.model_dump(mode="json"))
    assert bootstrap.require_confirmation is True and bootstrap.applied is False
    assert init.require_confirmation is True and init.applied is False and init.resources == []

    return {
        "planning_id": third.planning_id,
        "novel_id": third.novel_id,
        "schema_id": planning_json_schema()["$id"],
        "fixture": FIXTURE.name,
        "fixture_digest": planning_digest(plan),
        "canon_snapshot_digest": third.plan.canon_snapshot_digest,
        "branches": repo.list_branches(),
        "revisions": [
            {"revision_id": row.revision_id, "revision": row.revision,
             "parent_revision_id": row.parent_revision_id,
             "source_revision": row.source_revision, "branch_id": row.branch_id,
             "status": row.status, "content_digest": row.content_digest, "note": row.note}
            for row in repo.list_revisions()],
        "diff_r1_r2": {"rows": len(diff.rows), "by_domain": by_domain, "by_change": by_change,
                       "domains": diff.domains(),
                       "sample": [f"{row.change}:{row.domain}:{row.path}" for row in diff.rows]},
        "rollback": {"revision_id": third.revision_id,
                     "restored_digest": planning_digest(third.plan),
                     "superseded": second.revision_id},
        "context": {
            "chapter_planning": {"included_ids": chapter_context.included_ids,
                                 "excluded_domains": chapter_context.excluded_domains,
                                 "boundary": chapter_context.boundary,
                                 "gaps": len(chapter_context.payload.get("planning_gaps", []))},
            "plot": {"included_ids": plot_context.included_ids,
                     "excluded_domains": plot_context.excluded_domains}},
        "projection": {"coverage": summary.coverage, "completeness": summary.completeness,
                       "read_only": summary.read_only},
        "proposals": {
            "canon_bootstrap": {
                "proposal_id": bootstrap.proposal_id,
                "entities": len(bootstrap.entities), "facts": len(bootstrap.facts),
                "relationships": len(bootstrap.relationships),
                "locations": len(bootstrap.locations),
                "excluded_non_baseline": bootstrap.excluded_non_baseline,
                "future_refs_excluded": bootstrap.future_refs_excluded,
                "require_confirmation": bootstrap.require_confirmation,
                "applied": bootstrap.applied},
            "story_state_init": {
                "proposal_id": init.proposal_id,
                "characters": [item.character_id for item in init.characters],
                "location_ids": init.location_ids, "knowledge": len(init.knowledge),
                "resources": init.resources,
                "future_refs_excluded": init.future_refs_excluded,
                "require_confirmation": init.require_confirmation, "applied": init.applied}},
        "gates": {
            "strict_schema": "PASS",
            "validation_r1": "PASS", "validation_r2": "PASS", "validation_r3": "PASS",
            "immutable_r2_after_rollback": "PASS",
            "diff_domains": "PASS",
            "context_boundary_declared": "PASS",
            "proposal_no_future": "PASS",
        },
    }


def test_m2b_repository_e2e_and_artifact(tmp_path: Path) -> None:
    artifact = _run(tmp_path)
    body = json.dumps(artifact, ensure_ascii=False, indent=1) + "\n"
    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    if not ARTIFACT.is_file() or ARTIFACT.read_text(encoding="utf-8") != body:
        ARTIFACT.write_text(body, encoding="utf-8")
    assert ARTIFACT.is_file()
    print("M2B E2E gates:", artifact["gates"])


def test_m2b_artifact_is_reproducible(tmp_path: Path) -> None:
    """同一 fixture 跑两次，除了临时目录以外 artifact 完全一致。"""

    first = json.dumps(_run(tmp_path / "a"), ensure_ascii=False, sort_keys=True)
    second = json.dumps(_run(tmp_path / "b"), ensure_ascii=False, sort_keys=True)
    assert first == second
