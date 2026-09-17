"""M16B Writer Integration：分层 context / writer 入口 / Draft Fact Sync 边界回归。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from novelforge.api.story_builder_routes import install_story_builder_api
from novelforge.story_builder import load_story_catalog
from novelforge.story_builder.writer_integration import (
    BLOCK_BUDGET,
    TRUTH_BLOCKS,
    WriterContextBuilder,
    WriterDraftService,
    validate_writer_context,
    writer_export_bundle,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
NOVEL = "wasteland_001"


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def repo_client() -> TestClient:
    app = FastAPI()
    install_story_builder_api(app, PROJECT_ROOT,
                              catalog=load_story_catalog(PROJECT_ROOT))
    return TestClient(app)


# ---------------------------------------------------------------- context
def test_writer_context_layers_and_validation() -> None:
    context = WriterContextBuilder(PROJECT_ROOT, NOVEL).build()
    blocks = {row["block_id"]: row for row in context["blocks"]}
    assert [row["block_id"] for row in context["blocks"]] == [
        block_id for block_id, _, _ in TRUTH_BLOCKS]
    assert blocks["canon_truth"]["truth_layer"] == "occurred"
    assert blocks["story_state"]["truth_layer"] == "occurred"
    assert blocks["historical_repair"]["truth_layer"] == "historical_repair"
    assert blocks["planning"]["truth_layer"] == "planned"
    assert blocks["chapter_plan"]["truth_layer"] == "planned"
    assert blocks["writer_guidance"]["truth_layer"] == "ui_derived"
    for row in context["blocks"]:
        assert row["source"] and row["digest"]
        assert row["item_count"] <= BLOCK_BUDGET
    assert context["writer_package"]["facts"] is not None
    assert context["validation"]["status"] == "PASS"
    assert all(context["validation"]["checks"].values())
    assert context["preview_only"] is True


def test_writer_context_dedup_and_stability() -> None:
    first = WriterContextBuilder(PROJECT_ROOT, NOVEL).build()
    second = WriterContextBuilder(PROJECT_ROOT, NOVEL).build()
    assert first["context_id"] == second["context_id"]
    assert [row["digest"] for row in first["blocks"]] == [
        row["digest"] for row in second["blocks"]]
    # 重复 ownership 必须为 0（同一 item 只归属一个 block）
    ownership = [str(item.get("id") or item.get("text"))
                 for row in first["blocks"] for item in row["items"]]
    assert len(ownership) == len(set(ownership))


def test_context_validation_detects_leakage() -> None:
    context = WriterContextBuilder(PROJECT_ROOT, NOVEL).build()
    broken = json.loads(json.dumps(context))
    for row in broken["blocks"]:
        if row["block_id"] == "historical_repair":
            row["truth_layer"] = "occurred"      # 伪装成已发生事实
    result = validate_writer_context(broken)
    assert result["status"] == "FAIL"
    assert result["checks"]["truth_layer_matches_declaration"] is False


# ---------------------------------------------------------------- drafts + sync
def test_writer_draft_and_fact_sync(tmp_path: Path) -> None:
    service = WriterDraftService(PROJECT_ROOT, NOVEL,
                                 writer_dir="workspace/m16b_test_writer")
    draft = service.create_draft(narration="第一段示例正文。", new_facts=[
        {"character_id": "protagonist", "detail": "示例：左手有一道旧伤"}])
    assert draft["truth_layer"] == "preview"
    assert draft["context_validation"]["status"] == "PASS"
    assert draft["validation"]["accepted"] is True
    assert (PROJECT_ROOT / "workspace/m16b_test_writer" / NOVEL / "drafts" /
            f"{draft['draft_id']}.json").is_file()

    listed = service.list_drafts()
    assert any(row["draft_id"] == draft["draft_id"] for row in listed)

    canon = PROJECT_ROOT / "novel/authoring/story_engine/canon/wasteland_001.sqlite"
    canon_before = _digest(canon)
    sync = service.sync_facts(draft["draft_id"])
    assert sync["status"] != "NOT_FOUND"
    assert sync["wrote_story_state"] is False and sync["wrote_canon"] is False
    assert sync["state_unchanged"] is True
    assert sync["proposal_count"] == 1
    proposal = sync["proposals"][0]
    assert proposal["kind"] == "persistent_fact"
    assert proposal["status"] == "PROPOSED" and proposal["requires_approval"] is True
    assert proposal["approval_boundary"]
    assert _digest(canon) == canon_before
    # proposal 落盘（可追踪）
    assert (PROJECT_ROOT / "workspace/m16b_test_writer" / NOVEL / "proposals" /
            f"{draft['draft_id']}_proposals.json").is_file()


def test_draft_not_found_and_claim_validation() -> None:
    service = WriterDraftService(PROJECT_ROOT, NOVEL,
                                 writer_dir="workspace/m16b_test_writer")
    missing = service.get_draft("draft_does_not_exist")
    assert missing["found"] is False and missing["note"]
    assert service.sync_facts("draft_does_not_exist")["status"] == "NOT_FOUND"

    # 未确认事实 / 不合法 resource claim 必须被既有校验标记，不伪装成功
    bad = service.create_draft(claims=[
        {"kind": "fact", "id": "sample_fact", "holder": "protagonist", "value": "示例"},
        {"kind": "resource", "id": "water", "holder": "protagonist", "value": 9999}])
    assert bad["validation"]["accepted"] is False
    problems = " ".join(bad["validation"]["problems"])
    assert "FACT_UNKNOWN" in problems and "RESOURCE_MISMATCH" in problems
    assert bad["truth_layer"] == "preview"      # 失败草稿仍停在 preview，不写事实


# ---------------------------------------------------------------- endpoints + bundle
def test_writer_endpoints_and_export_bundle() -> None:
    client = repo_client()
    context = client.get(f"/api/story-builder/writer/context?novel_id={NOVEL}").json()
    assert context["validation"]["status"] == "PASS"
    draft = client.post("/api/story-builder/writer/drafts",
                        json={"novel_id": NOVEL,
                              "narration": "端到端示例。",
                              "new_facts": [{"character_id": "protagonist",
                                             "detail": "端到端示例事实"}]})
    assert draft.status_code == 201, draft.text
    draft_id = draft.json()["draft_id"]
    listing = client.get(f"/api/story-builder/writer/drafts?novel_id={NOVEL}").json()
    assert any(row["draft_id"] == draft_id for row in listing["drafts"])
    detail = client.get(
        f"/api/story-builder/writer/drafts/{draft_id}?novel_id={NOVEL}").json()
    assert detail["found"] is True and detail["truth_layer"] == "preview"
    sync = client.post(
        f"/api/story-builder/writer/drafts/{draft_id}/sync-facts?novel_id={NOVEL}"
    ).json()
    assert sync["proposal_count"] == 1 and sync["wrote_canon"] is False
    bundle = writer_export_bundle(PROJECT_ROOT, NOVEL)
    assert bundle["writer_context_id"] == context["context_id"]
    assert bundle["writer_context_validation"]["status"] == "PASS"
