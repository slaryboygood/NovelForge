"""V4-07 §21、§60、§84：Application ExportService facade 与 REST 链路。"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from novelforge.api.delivery_routes import install_delivery_api
from novelforge.application.services import ExportService, export_service

from delivery_support import delivery_stack

BASE = "/api/story-builder/delivery"


def test_facade_keeps_legacy_projection_and_export(tmp_path: Path) -> None:
    """§60–§61：legacy 方法仍是 compatibility，但 V4 主路径走 delivery。"""

    stack = delivery_stack(tmp_path)
    service = ExportService(tmp_path, stack["novel_id"])
    projection = service.projection()
    assert projection["manifest"]["novel_id"] == stack["novel_id"]
    legacy = service.export(fmt="markdown")
    assert legacy["artifact"]["filename"].endswith(".md")
    assert service.validate()["status"] in ("PASS", "FAIL")


def test_facade_delivery_methods(tmp_path: Path) -> None:
    stack = delivery_stack(tmp_path)
    service = ExportService(tmp_path, stack["novel_id"])
    selection = service.delivery_selection(formats=("json", "markdown", "nfpack",
                                                    "docx"))
    described = service.describe_delivery(selection)
    assert described["write"] is False
    assert described["selection_outcome"]["selected"]
    validated = service.validate_delivery(selection)
    assert validated["validation"]["ok"] is True
    result = service.deliver(selection)
    assert result["status"] == "delivered"
    assert result["llm_calls"] == 0
    assert {row["format"] for row in result["artifacts"]} == {
        "json", "markdown", "docx", "nfpack"}
    snapshot_id = result["snapshot_id"]
    assert service.delivery_snapshot(snapshot_id)["snapshot_id"] == snapshot_id
    manifest = service.delivery_manifest(snapshot_id)
    assert manifest["selected_revisions"] == result["manifest"]["selected_revisions"]
    artifact = [row for row in result["artifacts"] if row["format"] == "markdown"][0]
    data = service.delivery_artifact(snapshot_id, artifact["path"])
    assert data.decode("utf-8").startswith("# ")
    assert result["checksums"][artifact["path"]] == artifact["checksum"]
    assert any(row["snapshot_id"] == snapshot_id
               for row in service.delivery_snapshots())


def test_facade_factory_and_create_snapshot(tmp_path: Path) -> None:
    stack = delivery_stack(tmp_path)
    service = export_service(tmp_path, stack["novel_id"])
    selection = service.delivery_selection(formats=("json",))
    snapshot = service.create_snapshot(selection)
    assert snapshot["node_revisions"]
    assert service.delivery_snapshot(snapshot["snapshot_id"])["input_digest"]


def _client(root: Path) -> TestClient:
    app = FastAPI()
    install_delivery_api(app, root)
    return TestClient(app)


def test_api_delivery_roundtrip(tmp_path: Path) -> None:
    stack = delivery_stack(tmp_path)
    client = _client(tmp_path)
    response = client.post(BASE, json={
        "novel_id": stack["novel_id"], "selection_mode": "accepted",
        "profile": "author", "formats": ["json", "markdown", "nfpack"]})
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "delivered"
    assert payload["llm_calls"] == 0
    snapshot_id = payload["snapshot_id"]
    manifest = client.get(f"{BASE}/{snapshot_id}",
                          params={"novel_id": stack["novel_id"]})
    assert manifest.status_code == 200
    manifest_row = client.get(f"{BASE}/{snapshot_id}/manifest",
                              params={"novel_id": stack["novel_id"]})
    assert manifest_row.status_code == 200
    assert manifest_row.json()["artifacts"]
    artifact = manifest_row.json()["artifacts"][0]
    download = client.get(f"{BASE}/{snapshot_id}/artifacts/{artifact['path']}",
                          params={"novel_id": stack["novel_id"]})
    assert download.status_code == 200
    assert len(download.content) == artifact["size"]
    assert "attachment" in download.headers["content-disposition"]


def test_api_blocked_delivery_is_explicit(tmp_path: Path) -> None:
    stack = delivery_stack(tmp_path, clean=False)
    client = _client(tmp_path)
    response = client.post(BASE, json={"novel_id": stack["novel_id"],
                                       "formats": ["json"]})
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "blocked"
    assert payload["ok"] is False
    assert payload["validation"]["issues"]


def test_api_unknown_format_and_novel_are_safe(tmp_path: Path) -> None:
    stack = delivery_stack(tmp_path)
    client = _client(tmp_path)
    bad_format = client.post(BASE, json={"novel_id": stack["novel_id"],
                                         "formats": ["epub"]})
    assert bad_format.status_code == 400
    assert bad_format.json()["detail"]["code"] == "DELIVERY_FORMAT_UNSUPPORTED"
    assert "traceback" not in str(bad_format.json()).lower()
    missing = client.get(f"{BASE}/DS_missing",
                         params={"novel_id": stack["novel_id"]})
    assert missing.status_code == 200
    assert missing.json() == {}
    bad_artifact = client.get(f"{BASE}/DS_missing/artifacts/../escape.json",
                              params={"novel_id": stack["novel_id"]})
    assert bad_artifact.status_code in (400, 409, 404)


def test_api_idempotent_delivery(tmp_path: Path) -> None:
    stack = delivery_stack(tmp_path)
    client = _client(tmp_path)
    body = {"novel_id": stack["novel_id"], "formats": ["json"],
            "idempotency_key": "api-k-1"}
    first = client.post(BASE, json=body).json()
    second = client.post(BASE, json=body).json()
    assert first["snapshot_id"] == second["snapshot_id"]
    assert second["idempotent"] is True
