"""S16：M1B V2 verifier 覆盖 / 错误分类 / Queue V4 / M1 Final Gate 回归。

这些断言只读 shadow 产物；dogfood 数据不在 git 内时自动跳过。
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
V2 = ROOT / "workspace" / "wasteland_001_exports" / "chapter_ir_v1" / "m1b_v2"
RECONCILIATION = V2 / "WASTELAND_001_CHAPTER_IR_RECONCILIATION_FINAL_V2.json"
VERIFY = V2 / "WASTELAND_001_LLM_VERIFICATION_V2.json"
QUEUE = V2 / "WASTELAND_001_CHAPTER_IR_REPAIR_QUEUE_V4.json"
GATE = V2 / "WASTELAND_001_M1_FINAL_GATE.json"
RAW_DIR = V2 / "llm_raw_failures"
CLOSURE = ROOT / "scripts" / "wasteland_001_m1b_closure.py"

ALLOWED_ERRORS = {"network_failure", "timeout_failure", "http_failure", "empty_response",
                  "json_parse_failure", "schema_validation_failure"}
ALLOWED_CATEGORIES = {"SEMANTIC_CONFIRMED", "EXTRACTION_REPAIR", "LEGACY_CONTENT_GAP",
                      "LEGACY_FIELD_CONFLICT", "HUMAN_CANON_DECISION"}
MACHINE_TOKENS = ("ENTITY_", "CE_", "EF_", "ST_", "state_key")
DEBUG_TEMPLATES = ("付出：无", "达成：", "把次序改了")


def _load(path: Path) -> dict:
    if not path.is_file():
        pytest.skip(f"{path.name} 不存在（dogfood 数据不在 git 内）")
    return json.loads(path.read_text(encoding="utf-8"))


def _schema():
    spec = importlib.util.spec_from_file_location("m1b_closure_for_test", CLOSURE)
    module = importlib.util.module_from_spec(spec)
    sys.modules["m1b_closure_for_test"] = module
    spec.loader.exec_module(module)
    return module.LLMVerificationResult


def test_every_chapter_has_current_digest_verification() -> None:
    reconciliation, verify = _load(RECONCILIATION), _load(VERIFY)
    rows = reconciliation["chapters"]
    llm = {row["chapter_uuid"]: row for row in verify["rows"]}
    assert reconciliation["statistics"]["verified_current_digest_count"] == 570
    assert reconciliation["statistics"]["pending_network_count"] == 0
    assert len(rows) == 570 == len(llm)
    for row in rows:
        result = llm.get(row["chapter_uuid"])
        assert result is not None, row["legacy_label"]
        assert result["verifier_input_digest"] == row["verifier_input_digest"], \
            row["legacy_label"]


def test_saved_results_pass_strict_schema() -> None:
    verify = _load(VERIFY)
    schema = _schema()
    fields = set(schema.model_fields)
    for row in verify["rows"]:
        payload = {key: row[key] for key in fields if key in row}
        schema.model_validate(payload, strict=True)


def test_error_classification_separates_failure_types() -> None:
    verify = _load(VERIFY)
    classification = verify["error_classification"]
    assert set(classification) == ALLOWED_ERRORS | {"success"}
    assert classification["success"] >= 1
    for entry in verify["run_log"]:
        assert entry["error_type"] in ALLOWED_ERRORS | {"success"}
        for attempt in entry["attempts"]:
            assert attempt["error_type"] in ALLOWED_ERRORS | {"success"}
            if attempt["error_type"] in ALLOWED_ERRORS:
                assert attempt["raw_failure"], (entry["chapter_id"], attempt)
                assert (RAW_DIR / attempt["raw_failure"]).is_file()


def test_raw_failure_archive_has_no_secret() -> None:
    if not RAW_DIR.is_dir():
        pytest.skip("没有失败存档")
    secrets = []
    env_file = ROOT / ".env.local"
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                value = line.split("=", 1)[1].strip().strip('"').strip("'")
                if len(value) >= 8:
                    secrets.append(value)
    for path in RAW_DIR.glob("*.json"):
        text = path.read_text(encoding="utf-8")
        for token in ("Bearer ", "sk-", '"authorization"'):
            assert token not in text, (path.name, token)
        for secret in secrets:
            assert secret not in text, path.name


def test_queue_v4_keeps_product_and_legacy_findings_separate() -> None:
    reconciliation, queue = _load(RECONCILIATION), _load(QUEUE)
    rows = reconciliation["chapters"]
    categories = {row["category_v4"] for row in rows}
    assert categories <= ALLOWED_CATEGORIES
    assert "EXTRACTION_REPAIR" not in categories
    queued = {row["chapter_uuid"]: row["category_v4"] for row in queue["items"]}
    assert set(queued.values()) <= ALLOWED_CATEGORIES - {"SEMANTIC_CONFIRMED"}
    for row in rows:
        if row["category_v4"] == "SEMANTIC_CONFIRMED":
            assert row["deterministic_issues"] == []
            assert row["ir_corrections"] == []
            assert row["llm_legacy_field_conflicts"] == []
            assert row["chapter_uuid"] not in queued


def test_writer_preview_has_no_machine_token_or_debug_template() -> None:
    reconciliation = _load(RECONCILIATION)
    for row in reconciliation["chapters"]:
        for value in row["writer_preview"].values():
            assert not any(token in str(value) for token in MACHINE_TOKENS), \
                row["legacy_label"]
            assert not any(snippet in str(value) for snippet in DEBUG_TEMPLATES), \
                row["legacy_label"]


def test_m1_final_gate_is_green() -> None:
    gate = _load(GATE)["gate"]
    failed = [key for key, item in gate.items()
              if isinstance(item, dict) and item.get("pass") is False]
    assert failed == []
    assert gate["verified_current_digest_count"]["value"] == 570
    assert gate["golden_exact_semantic_accuracy"]["value"] == 1.0
    for key in ("digest_candidate_unchanged", "digest_story_state_unchanged",
                "digest_canon_unchanged"):
        assert gate[key]["pass"] is True
