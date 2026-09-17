"""M1B Closure：真实 LLM verifier 覆盖、Repair Queue V3、Golden V3、硬边界。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

M1B = Path("workspace/wasteland_001_exports/chapter_ir_v1/m1b")
VERIFY = M1B / "WASTELAND_001_LLM_VERIFICATION.json"
FINAL = M1B / "WASTELAND_001_CHAPTER_IR_RECONCILIATION_FINAL.json"
QUEUE = M1B / "WASTELAND_001_CHAPTER_IR_REPAIR_QUEUE_V3.json"
GOLDEN = M1B / "WASTELAND_001_CHAPTER_IR_GOLDEN_REGRESSION_V3.md"
CANDIDATE = Path("workspace/wasteland_001_exports/"
                 "WASTELAND_001_OUTLINE_CANON_FINAL_CANDIDATE_V5.json")


def _load(path: Path) -> dict:
    if not path.is_file():
        pytest.skip(f"{path.name} 不存在（dogfood 数据不在 git 内）")
    return json.loads(path.read_text(encoding="utf-8"))


def test_real_llm_verifier_covers_all_chapters() -> None:
    data = _load(VERIFY)
    stats = data["stats"]
    assert stats["llm_verifier_invoked"] == 570
    assert stats["llm_calls"] > 0 and stats["prompt_tokens"] > 0
    assert stats["batch_failures"] == 0
    rows = {row["chapter_uuid"] for row in data["rows"]}
    assert len(rows) == 570


def test_queue_v3_covers_every_chapter_with_one_primary_category() -> None:
    data = _load(FINAL)
    rows = data["chapters"]
    assert len(rows) == 570
    allowed = {"SEMANTIC_CONFIRMED", "EXTRACTION_REPAIR", "LEGACY_CONTENT_GAP",
               "LEGACY_FIELD_CONFLICT", "HUMAN_CANON_DECISION",
               "SEMANTIC_ADJUDICATION_REQUIRED"}
    assert {row["category"] for row in rows} <= allowed
    queue = _load(QUEUE)
    queued = {row["chapter_uuid"] for row in queue["items"]}
    confirmed = {row["chapter_uuid"] for row in rows if row["category"] == "SEMANTIC_CONFIRMED"}
    assert not (confirmed & queued)
    assert len(queued) == 570 - len(confirmed)


def test_golden_v3_reports_expected_actual_and_differences() -> None:
    data = _load(FINAL)
    golden = data["golden"]
    assert len(golden) >= 35
    for chapter_id, row in golden.items():
        assert "expect" in row and "actual" in row and "differences" in row
        if not row["matched"]:
            assert row["differences"], chapter_id
    assert GOLDEN.is_file()
    assert "expected" in GOLDEN.read_text(encoding="utf-8")


def test_shadow_only_and_digest_unchanged() -> None:
    data = _load(FINAL)
    assert data["llm_stats"]["llm_verifier_invoked"] == 570
    digest = hashlib.sha256(CANDIDATE.read_bytes()).hexdigest()[:16]
    baseline = json.loads((M1B / "M1B_BASELINE.json").read_text(encoding="utf-8"))
    assert baseline["candidate_digest"] == digest
    assert data["statistics"]["writer_machine_token"] == 0


def test_human_canon_decision_list_is_explicit() -> None:
    """§29：只要存在 HUMAN_CANON_DECISION，就必须显式列出并停止进入 M2。"""

    data = _load(FINAL)
    humans = [row["legacy_label"] for row in data["chapters"]
              if row["category"] == "HUMAN_CANON_DECISION"]
    report = (M1B / "WASTELAND_001_CHAPTER_IR_RECONCILIATION_FINAL_REPORT.md")
    assert report.is_file()
    if humans:
        assert data["statistics"]["human_canon_decision_count"] == len(humans)
