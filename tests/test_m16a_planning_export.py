"""M16A Planning Export：projection / serializer / validation / replay 稳定性回归。"""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from novelforge.api.story_builder_routes import install_story_builder_api
from novelforge.story_builder import load_story_catalog
from novelforge.story_builder.export_package import (
    EXPORT_FORMAT_VERSION,
    build_export_projection,
    export_package,
    serialize_export,
    validate_export_package,
)
from novelforge.story_engine.m11_p15p import FROZEN_SOURCE_DIGESTS

PROJECT_ROOT = Path(__file__).resolve().parents[1]
NOVEL = "wasteland_001"


def repo_client() -> TestClient:
    app = FastAPI()
    install_story_builder_api(app, PROJECT_ROOT,
                              catalog=load_story_catalog(PROJECT_ROOT))
    return TestClient(app)


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def test_projection_sections_and_truth_layers() -> None:
    projection = build_export_projection(PROJECT_ROOT, NOVEL)
    sections = {row["section_id"]: row for row in projection["sections"]}
    assert {"story_bible", "cards.characters", "cards.factions", "cards.locations",
            "timeline", "spine", "outline", "planning", "canon_refs",
            "historical_ir"} <= set(sections)
    assert sections["story_bible"]["truth_layer"] == "planned"
    assert sections["cards.characters"]["truth_layer"] == "occurred"
    assert sections["historical_ir"]["truth_layer"] == "historical_repair"
    assert sections["outline"]["item_count"] > 0
    for row in projection["sections"]:
        assert row["source"] and row["identity"] and row["digest"]
    manifest = projection["manifest"]
    assert manifest["format_version"] == EXPORT_FORMAT_VERSION
    assert manifest["source_digests"]["canon"] == FROZEN_SOURCE_DIGESTS["canon"]
    assert manifest["source_digests"]["story_state"] == FROZEN_SOURCE_DIGESTS["story_state"]
    assert manifest["non_authoritative"] is True
    assert projection["writer_ready"]["entry"].startswith("M16B")


def test_validation_and_identity_stability() -> None:
    first = build_export_projection(PROJECT_ROOT, NOVEL)
    second = build_export_projection(PROJECT_ROOT, NOVEL)
    assert first["manifest"]["export_id"] == second["manifest"]["export_id"]
    validation = validate_export_package(first)
    assert validation["status"] == "PASS"
    assert all(validation["checks"].values()), validation["checks"]
    # 篡改 truth layer 必须被 validation 捕获（不弱化 invariant）
    broken = json.loads(json.dumps(first))
    for row in broken["sections"]:
        if row["section_id"] == "historical_ir":
            row["truth_layer"] = "occurred"
    assert validate_export_package(broken)["status"] == "FAIL"


def test_serializers_json_markdown_docx() -> None:
    projection = build_export_projection(PROJECT_ROOT, NOVEL)
    rows = {fmt: serialize_export(projection, fmt)
            for fmt in ("json", "markdown", "docx")}
    for fmt, row in rows.items():
        assert row["export_id"] == projection["manifest"]["export_id"], fmt
        assert row["format"] == fmt
    payload = json.loads(rows["json"]["content"])
    assert payload["manifest"]["export_id"] == projection["manifest"]["export_id"]
    assert not payload["writer_ready"] is None
    assert rows["markdown"]["content"].startswith("# ")
    docx_bytes = base64.b64decode(rows["docx"]["content_base64"])
    assert docx_bytes[:2] == b"PK" and rows["docx"]["size"] == len(docx_bytes)
    assert serialize_export(projection, "pdf")["error"] == "EXPORT_FORMAT_UNSUPPORTED"


def test_replay_is_deterministic_and_read_only() -> None:
    canon = PROJECT_ROOT / "novel/authoring/story_engine/canon/wasteland_001.sqlite"
    state_dir = PROJECT_ROOT / "novel/authoring/story_engine/state"
    canon_before = _digest(canon)
    state_before = hashlib.sha256("|".join(sorted(
        f"{p.name}:{_digest(p)}" for p in state_dir.rglob("*.json"))).encode()
    ).hexdigest()[:16]
    first = export_package(PROJECT_ROOT, NOVEL, fmt="json")
    second = export_package(PROJECT_ROOT, NOVEL, fmt="json")
    assert first["artifact"]["export_id"] == second["artifact"]["export_id"]
    assert first["artifact"]["content"] == second["artifact"]["content"]
    assert first["validation"]["status"] == "PASS"
    assert _digest(canon) == canon_before
    assert hashlib.sha256("|".join(sorted(
        f"{p.name}:{_digest(p)}" for p in state_dir.rglob("*.json"))).encode()
    ).hexdigest()[:16] == state_before


def test_export_endpoint_and_writer_bundle() -> None:
    client = repo_client()
    for fmt in ("json", "markdown", "docx"):
        response = client.get(
            f"/api/story-builder/export/package?novel_id={NOVEL}&format={fmt}")
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["validation"]["status"] == "PASS"
        assert payload["artifact"]["export_id"]
        assert payload["read_only"] is True
    projection = client.get(
        f"/api/story-builder/export/package?novel_id={NOVEL}&include_projection=true"
    ).json()
    assert projection["projection"]["manifest"]["export_id"]
    bundle = client.get(
        f"/api/story-builder/export/writer-bundle?novel_id={NOVEL}").json()
    assert bundle["writer_context_validation"]["status"] == "PASS"
    assert bundle["blocks"] and bundle["preview_only"] is True
