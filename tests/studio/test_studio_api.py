"""V4-10：Story Studio REST facade（thin routes → application.services）。

覆盖：overview / blueprint / generate / quality（evaluate·repair·verify）/ delivery.formats /
plugins 只读，以及「UI 不推导 truth」所依赖的稳定错误码。
"""

from __future__ import annotations

from pathlib import Path

from studio_support import (
    EXPORTER_PLUGIN,
    NOVEL_ID,
    clean_studio,
    empty_studio,
    premise_payload,
)

CORE_FORMATS = ("docx", "json", "markdown", "nfpack")


def _overview(client, novel_id: str = NOVEL_ID) -> dict:
    response = client.get("/api/story-builder/studio/overview",
                          params={"novel_id": novel_id})
    assert response.status_code == 200, response.text
    return response.json()


def test_overview_reports_backend_truth(tmp_path: Path) -> None:
    stack = clean_studio(tmp_path)
    payload = _overview(stack["client"])
    assert payload["novel_id"] == NOVEL_ID
    assert payload["blueprint"]["node_count"] > 0
    assert payload["blueprint"]["by_type"]["chapter"] >= 1
    assert payload["blueprint"]["accepted"] >= 1
    # 质量来自 Quality Store / Gate（不是前端计算）
    assert payload["quality"]["status"] in ("passed", "failed", "blocked",
                                            "unevaluated", "needs_human_review")
    gates = {row["gate"] for row in payload["quality"]["gates"]}
    assert {"Q0", "Q1", "Q8"} <= gates
    # setup / payoff 统计来自 Blueprint 节点
    assert set(payload["setup"]["counts"]) >= {"open", "paid"}
    assert payload["delivery"]["snapshots"] >= 0
    # 下一步来自 journey 投影（后端唯一公式）
    assert isinstance(payload["next_action"], dict)
    assert payload["read_only"] is True


def test_blueprint_view_returns_visible_fields_and_status(tmp_path: Path) -> None:
    stack = clean_studio(tmp_path)
    response = stack["client"].get("/api/story-builder/studio/blueprint",
                                   params={"novel_id": NOVEL_ID,
                                           "node_type": "scene"})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["count"] >= 1
    row = payload["nodes"][0]
    assert row["node_type"] == "scene"
    assert row["status"] in ("proposed", "draft", "accepted", "superseded")
    assert "visible" in row and "payload" in row
    # 内部 metadata 默认不下发（debug 细节不进普通页面）
    assert "context_digest" not in row
    assert payload["read_only"] is True


def test_generate_creates_proposal_via_stub_model(tmp_path: Path) -> None:
    stack = empty_studio(tmp_path, script=[premise_payload()])
    response = stack["client"].post(
        "/api/story-builder/studio/generate",
        json={"novel_id": stack["novel_id"], "task": "premise"})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["ok"] is True
    assert payload["node"]["node_type"] == "premise"
    assert payload["node"]["status"] == "proposed"      # AI 建议，不是 accepted
    assert payload["next_status"] == "proposed"
    # 生成后 Blueprint 真的多了一个节点（不是本地假象）
    view = stack["client"].get("/api/story-builder/studio/blueprint",
                               params={"novel_id": stack["novel_id"]}).json()
    assert view["count"] == 1


def test_generate_without_model_is_stable_error(tmp_path: Path) -> None:
    from studio_support import build_novel, studio_app

    build_novel(tmp_path, "studio_no_ai", title="无模型",
                fact_text="无模型作品：只验证错误码，不做生成。")
    client = studio_app(tmp_path)          # 未注入 gateway
    response = client.post("/api/story-builder/studio/generate",
                           json={"novel_id": "studio_no_ai", "task": "premise"})
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "GENERATION_UNAVAILABLE"
    assert "traceback" not in detail["message"].lower()


def test_unknown_generate_task_is_rejected(tmp_path: Path) -> None:
    stack = empty_studio(tmp_path)
    response = stack["client"].post(
        "/api/story-builder/studio/generate",
        json={"novel_id": stack["novel_id"], "task": "not_a_task"})
    assert response.status_code in (400, 422)
    assert response.json()["detail"]["code"]


def test_quality_center_reads_gates_and_issues(tmp_path: Path) -> None:
    stack = clean_studio(tmp_path)
    response = stack["client"].get("/api/story-builder/studio/quality",
                                   params={"novel_id": NOVEL_ID})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "passed"
    assert [row["gate"] for row in payload["gates"]] == \
        sorted(row["gate"] for row in payload["gates"])
    # issue 列表只反映 Quality Store 的内容（历史 issue 也在，带 revision/provenance）
    for row in payload["issues"]:
        assert {"issue_id", "code", "gate", "severity", "status"} <= set(row)
    open_rows = stack["client"].get("/api/story-builder/studio/quality",
                                    params={"novel_id": NOVEL_ID,
                                            "status": "open"}).json()["issues"]
    assert all(row["status"] == "open" for row in open_rows)
    assert payload["report"]["report_id"]


def test_quality_evaluate_then_repair_preview(tmp_path: Path) -> None:
    stack = clean_studio(tmp_path)
    client = stack["client"]
    evaluated = client.post("/api/story-builder/studio/quality/evaluate",
                            json={"novel_id": NOVEL_ID})
    assert evaluated.status_code == 200, evaluated.text
    assert evaluated.json()["status"] in ("passed", "failed", "blocked")

    preview = client.post("/api/story-builder/studio/quality/repair",
                          json={"novel_id": NOVEL_ID, "issue_ids": [],
                                "dry_run": True})
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["status"] == "planned" and body["dry_run"] is True
    # 干净作品没有 open issue → 明确 empty 语义（UI 显示“无需要修复的问题”）
    assert body["preview"]["status"] in ("empty", "planned")


def test_quality_verify_returns_verification(tmp_path: Path) -> None:
    stack = clean_studio(tmp_path)
    response = stack["client"].post("/api/story-builder/studio/quality/verify",
                                    json={"novel_id": NOVEL_ID, "issue_ids": []})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] in ("resolved", "partial", "regressed",
                                 "unresolved", "needs_human_review")


def test_delivery_formats_include_core_and_plugin(tmp_path: Path) -> None:
    stack = clean_studio(tmp_path)
    core = stack["client"].get("/api/story-builder/studio/delivery/formats",
                               params={"novel_id": NOVEL_ID}).json()
    assert tuple(sorted(core["format_ids"])) == CORE_FORMATS
    assert core["default_selection_mode"] == "accepted"
    assert all(row["owner_type"] == "core" for row in core["formats"])

    with_plugin = clean_studio(tmp_path / "plugin_root", plugin_formats=True)
    payload = with_plugin["client"].get(
        "/api/story-builder/studio/delivery/formats",
        params={"novel_id": NOVEL_ID}).json()
    assert "tlist" in payload["format_ids"]
    plugin_row = next(row for row in payload["formats"] if row["format"] == "tlist")
    assert plugin_row["owner_type"] == "plugin"
    assert plugin_row["owner_id"] == EXPORTER_PLUGIN


def test_plugins_endpoint_is_read_only(tmp_path: Path) -> None:
    stack = clean_studio(tmp_path)
    payload = stack["client"].get("/api/story-builder/studio/plugins").json()
    assert payload["trust_model"] == "trusted_in_process"
    assert "sandbox" in payload["note"]
    assert payload["plugins"] == []
    assert payload["available"] is False       # 未装配插件平台

    with_plugin = clean_studio(tmp_path / "plugin_root", plugin_formats=True)
    rows = with_plugin["client"].get("/api/story-builder/studio/plugins").json()
    assert rows["available"] is True
    assert [row["plugin_id"] for row in rows["plugins"]] == [EXPORTER_PLUGIN]
    assert rows["plugins"][0]["capabilities"] == ["exporter"]
    assert rows["plugins"][0]["permissions"] == ["delivery.export"]
    assert rows["read_only"] is True


def test_studio_does_not_leak_internal_paths(tmp_path: Path) -> None:
    """§92：普通页面 payload 不出现绝对路径 / 内部目录名。"""

    import json

    stack = clean_studio(tmp_path)
    text = json.dumps(_overview(stack["client"]), ensure_ascii=False)
    assert str(tmp_path) not in text
    assert "novel/authoring" not in text
    assert "C:\\\\" not in text
