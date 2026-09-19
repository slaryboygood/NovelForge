"""V4.0.2 Skill Baseline delta 守卫（继承 V4.0.1，不重写历史）。

V4.0.2 只覆盖真正变化的 skill；未变化的 skill 一律继承 V4.0.1，
V4.0.1 的历史 baseline 必须保持字节级不变。
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]


def _load_validator():
    spec = importlib.util.spec_from_file_location(
        "novelforge_v4_0_2_validator",
        ROOT / "scripts" / "validate_v4_0_2_skills.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def validator():
    return _load_validator()


def test_v4_0_2_baseline_is_valid(validator):
    validator.validate()


def test_v4_0_1_baseline_is_untouched(validator):
    """V4.0.1 是历史 baseline：V4.0.2 只能覆盖，不能改。"""

    payload = json.loads(validator.read_text(validator.BASE_MANIFEST))
    drifted = [row["path"] for row in payload["files"]
               if validator.sha256_of(ROOT / row["path"]) != row["sha256"]]
    assert drifted == [], drifted


def test_every_override_replaces_an_existing_v4_0_1_file(validator):
    for raw in validator.override_relpaths():
        assert (validator.BASE_ROOT / raw).is_file(), raw


def test_delta_is_small_and_intentional(validator):
    payload = json.loads(validator.read_text(validator.MANIFEST_PATH))
    assert payload["override_count"] == len(validator.lib_files())
    assert payload["override_count"] <= 15, payload["override_count"]
    assert sorted(payload["fixed_defects"]) == ["PB-1", "PB-2", "PB-3"]
    assert payload["inherits"]["base_manifest_sha256"] == \
        validator.sha256_of(validator.BASE_MANIFEST)


def test_overridden_skills_are_the_p0_ones(validator):
    payload = json.loads(validator.read_text(validator.MANIFEST_PATH))
    assert set(payload["skill_ids"]) == {
        "novelforge-v4.0.2.agent.approve-agent-run",
        "novelforge-v4.0.2.delivery.validate-delivery",
        "novelforge-v4.0.2.mcp.start-mcp-server",
        "novelforge-v4.0.2.workflows.operate-with-agent",
        "novelforge-v4.0.2.workflows.prepare-final-delivery",
        "novelforge-v4.0.2.workflows.use-novelforge-through-mcp",
    }, payload["skill_ids"]


def test_stale_v4_0_1_warnings_are_gone_in_v4_0_2(validator):
    """V4.0.1 里的临时缺陷警告在 V4.0.2 必须消失（缺陷已修）。"""

    checks = {
        validator.LIB_ROOT / "delivery" / "validate-delivery" / "SKILL.md": (
            "不按 issue.status 过滤", "唯一可用绕过口径"),
        validator.LIB_ROOT / "agent" / "approve-agent-run" / "SKILL.md": (
            "approve 路径本身有缺陷", "不要声称"),
        validator.LIB_ROOT / "mcp" / "start-mcp-server" / "SKILL.md": (
            "启动即崩", "等产品修 stdio 入口"),
    }
    for path, markers in checks.items():
        text = validator.read_text(path)
        for marker in markers:
            assert marker not in text, f"{validator.rel(path)} 仍含过期警告：{marker}"


def test_closure_evidence_tests_exist(validator):
    for raw in validator.CLOSURE_TESTS:
        assert (ROOT / raw).is_file(), raw


def test_readme_documents_inheritance_and_id_namespace(validator):
    text = validator.read_text(validator.LIB_ROOT / "README.md")
    assert "继承" in text and "copy-and-override" in text
    assert "novelforge-v4.0.2." in text and "novelforge-v4.0.1." in text
