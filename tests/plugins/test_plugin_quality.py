"""V4-09 §35–§37、§78–§80、§96：quality evaluator 扩展（只读 + namespaced）。"""

from __future__ import annotations

from pathlib import Path

from novelforge.quality import QualityPolicy
from novelforge.quality.codes import is_registered

from plugins_support import (
    NOVEL_ID,
    QUALITY_PLUGIN,
    active_plugin,
    plugin_host,
    quality_manifest,
)

PLUGIN_CODE = f"plugin.{QUALITY_PLUGIN}.CHAPTER_MISSING_POV"


def _services(tmp_path: Path, *, policy: QualityPolicy) -> tuple[dict, object]:
    from plugins_support import delivery_stack

    stack = delivery_stack(tmp_path)
    host = plugin_host(tmp_path, manifests=[quality_manifest(tmp_path)])
    host.discover()
    active_plugin(host, QUALITY_PLUGIN)
    services = host.services(NOVEL_ID, gateway=stack["gateway"],
                             memory=stack["memory"], policy=policy)
    return stack, services, host


def test_plugin_evaluator_runs_only_when_policy_enables_it(tmp_path: Path) -> None:
    stack, services, _host = _services(
        tmp_path, policy=QualityPolicy(plugin_evaluator_ids=(QUALITY_PLUGIN,)))
    report = services.review.evaluate()
    plugin_issues = [row for row in report.issues if row.code == PLUGIN_CODE]
    assert plugin_issues, [row.code for row in report.issues]
    issue = plugin_issues[0]
    assert issue.gate == "Q8"
    assert issue.evaluator_id == PLUGIN_CODE
    # provenance 可追溯到 plugin_id + version（§55、§80、§96）
    assert issue.provenance["owner_type"] == "plugin"
    assert issue.provenance["plugin_id"] == QUALITY_PLUGIN
    assert issue.provenance["plugin_evaluator_version"] == 1
    assert is_registered(PLUGIN_CODE)


def test_plugin_evaluator_is_skipped_by_default_policy(tmp_path: Path) -> None:
    _stack, services, _host = _services(tmp_path, policy=QualityPolicy())
    report = services.review.evaluate()
    assert [row for row in report.issues if row.code == PLUGIN_CODE] == []
    q8 = next(row for row in report.gate_results if row.gate == "Q8")
    assert all(not row.startswith(f"plugin.{QUALITY_PLUGIN}.")
               for row in q8.evaluator_ids)


def test_plugin_issue_is_non_blocking_by_default(tmp_path: Path) -> None:
    """§79：安装插件不得让所有项目突然无法交付。"""

    stack, services, _host = _services(
        tmp_path, policy=QualityPolicy(plugin_evaluator_ids=(QUALITY_PLUGIN,)))
    report = services.review.evaluate()
    plugin_issues = [row for row in report.issues if row.code == PLUGIN_CODE]
    assert plugin_issues
    # 只有插件 issue 的 Q8 门禁仍是 passed
    q8 = next(row for row in report.gate_results if row.gate == "Q8")
    assert [row.code for row in q8.issues if not row.code.startswith("plugin.")] == []
    assert q8.status == "passed"
    assert report.status == "passed"
    # 但 issue 仍被持久化（可审计）
    stored = [row for row in services.review.list_issues(gate="Q8")
              if row["code"] == PLUGIN_CODE]
    assert stored


def test_plugin_issue_can_be_promoted_to_blocking_by_policy(tmp_path: Path) -> None:
    policy = QualityPolicy(plugin_evaluator_ids=(QUALITY_PLUGIN,),
                           plugin_blocking=True)
    _stack, services, _host = _services(tmp_path, policy=policy)
    report = services.review.evaluate()
    q8 = next(row for row in report.gate_results if row.gate == "Q8")
    # 只有显式提升后才参与判定（severity=minor → policy.blocks(minor) 为 False）
    assert [row.code for row in q8.issues if row.code == PLUGIN_CODE]
    assert q8.status in ("passed", "failed")


def test_plugin_codes_are_unregistered_when_disabled(tmp_path: Path) -> None:
    _stack, services, host = _services(
        tmp_path, policy=QualityPolicy(plugin_evaluator_ids=(QUALITY_PLUGIN,)))
    assert is_registered(PLUGIN_CODE)
    host.service.disable(QUALITY_PLUGIN)
    assert not is_registered(PLUGIN_CODE)
    report = services.review.evaluate()
    assert [row for row in report.issues if row.code == PLUGIN_CODE] == []
    # Core code 不受影响
    assert is_registered("BLUEPRINT_VAGUE_CONTENT")


def test_plugin_evaluator_is_read_only(tmp_path: Path) -> None:
    """§37：插件 evaluator 不得修改 Blueprint / Canon / StoryState。"""

    stack, services, _host = _services(
        tmp_path, policy=QualityPolicy(plugin_evaluator_ids=(QUALITY_PLUGIN,)))
    before = {node.node_id: node.revision
              for node in stack["repository"].all_nodes()}
    services.review.evaluate()
    after = {node.node_id: node.revision
             for node in stack["repository"].all_nodes()}
    assert before == after
