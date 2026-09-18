"""V4-07 §36–§38、§41、§70–§72：NovelForge Package（.nfpack）。"""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

from novelforge.application.services import ExportService
from novelforge.delivery import DeliveryRequest
from novelforge.delivery.exporters import package_exporter

from delivery_support import delivery_stack


def _package(stack: dict, **kwargs) -> tuple[bytes, dict]:
    selection = ExportService(stack["root"], stack["novel_id"]).delivery_selection(
        formats=("nfpack",), **kwargs)
    result = stack["delivery"].deliver(DeliveryRequest(selection=selection))
    assert result.status == "delivered", result.notes
    artifact = [row for row in result.artifacts if row.format == "nfpack"][0]
    return artifact.content, result.manifest.as_dict()


def _names(data: bytes) -> list[str]:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return archive.namelist()


def test_package_structure_and_manifest(tmp_path: Path) -> None:
    stack = delivery_stack(tmp_path)
    data, manifest = _package(stack)
    names = _names(data)
    assert "manifest.json" in names
    assert "blueprint/blueprint.json" in names
    assert "revisions/snapshot.json" in names
    assert "quality/summary.json" in names
    assert "provenance/provenance.json" in names
    assert "editor/review-summary.json" in names
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        embedded = json.loads(archive.read("manifest.json").decode("utf-8"))
        snapshot = json.loads(archive.read("revisions/snapshot.json").decode("utf-8"))
    assert embedded["snapshot_id"] == manifest["snapshot_id"]
    assert embedded["selected_revisions"] == manifest["selected_revisions"]
    assert snapshot["node_revisions"] == manifest["selected_revisions"]


def test_package_carries_requested_exports(tmp_path: Path) -> None:
    stack = delivery_stack(tmp_path)
    selection = ExportService(tmp_path, stack["novel_id"]).delivery_selection(
        formats=("markdown", "docx", "nfpack"))
    result = stack["delivery"].deliver(DeliveryRequest(selection=selection))
    package = [row for row in result.artifacts if row.format == "nfpack"][0]
    names = _names(package.content)
    assert "exports/blueprint.md" in names
    assert "exports/blueprint.docx" in names


def test_package_checksums_match_artifacts(tmp_path: Path) -> None:
    stack = delivery_stack(tmp_path)
    selection = ExportService(tmp_path, stack["novel_id"]).delivery_selection(
        formats=("json", "markdown", "nfpack"))
    result = stack["delivery"].deliver(DeliveryRequest(selection=selection))
    manifest = result.manifest.as_dict()
    from novelforge.delivery import sha256_hex

    for artifact in result.artifacts:
        row = [item for item in manifest["artifacts"]
               if item["path"] == artifact.relative_path][0]
        assert row["checksum"] == sha256_hex(artifact.content)
        assert row["size"] == len(artifact.content)
    assert set(manifest["artifacts"][0]) >= {"path", "mime_type", "checksum", "size",
                                             "exporter_id", "exporter_version"}
    assert manifest["exporters"][0]["exporter_id"].startswith("delivery.")


def test_package_is_not_a_repository_backup(tmp_path: Path) -> None:
    """§38：不打包 cache / 其他作品 / 运行数据，只含明确选择的交付内容。"""

    stack = delivery_stack(tmp_path)
    data, _manifest = _package(stack)
    names = _names(data)
    for row in names:
        lowered = row.lower()
        assert not lowered.startswith(("cache", "logs", "workspace", ".env"))
        assert ".git" not in lowered and "node_modules" not in lowered
    assert all(name.startswith(("manifest.json", "blueprint/", "quality/",
                                "revisions/", "provenance/", "editor/", "exports/"))
               for name in names)
    # node 原始 revision 文件默认不打包（由 profile / selection 决定）
    assert not [name for name in names if name.startswith("blueprint/nodes/")]
    with_node_files = _package(stack, package_includes_node_files=True)[0]
    assert [name for name in _names(with_node_files)
            if name.startswith("blueprint/nodes/")]


def test_package_contains_no_secrets_or_internal_prompts(tmp_path: Path) -> None:
    """§71：不得包含 .env / API key / Authorization / 完整 prompt / raw response。"""

    stack = delivery_stack(tmp_path)
    data, _manifest = _package(stack)
    hits = package_exporter.scan_for_secrets(data)
    assert hits == []
    text = data.decode("utf-8", errors="ignore")
    for token in ("API_KEY", "Authorization", "Bearer ", "sk-", ".env"):
        assert token not in text
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for name in archive.namelist():
            payload = archive.read(name).decode("utf-8", errors="ignore")
            assert "prompt" not in payload.lower() or name.endswith(".json")
            assert "raw_metadata" not in payload


def test_package_contains_no_other_novel_data(tmp_path: Path) -> None:
    """§72：机械扫描 —— 不得出现其他作品的唯一标记。"""

    from delivery_support import editor_stack

    stack = delivery_stack(tmp_path)
    editor_stack(tmp_path, novel_id="novel_beta_beta", repairable=True, script=[])
    data, _manifest = _package(stack)
    text = data.decode("utf-8", errors="ignore")
    assert "novel_beta_beta" not in text
    assert "novel_beta" not in text
    assert "贝塔计划" not in text


def test_package_entry_names_are_safe() -> None:
    """§70：ZIP 条目名不得包含 ../ 或绝对路径。"""

    context = {"manifest": {"a": 1}, "blueprint": {"nodes": [], "node_revisions": {}},
               "snapshot": {}, "extra_exports": [{"path": "../escape.json",
                                                  "data": b"x"}]}
    try:
        package_exporter.build_zip(context)
    except ValueError as exc:
        assert "不安全" in str(exc)
    else:  # pragma: no cover - 必须拒绝
        raise AssertionError("path traversal 未被拒绝")
    for bad in ("/abs.json", "C:/abs.json", "a/../../b.json", ".env"):
        try:
            package_exporter._entry_name(bad)  # noqa: SLF001 - 直接验证守卫
        except ValueError:
            continue
        raise AssertionError(f"不安全条目名未被拒绝：{bad}")


def test_package_paths_are_published_under_delivery_dir(tmp_path: Path) -> None:
    stack = delivery_stack(tmp_path)
    selection = ExportService(tmp_path, stack["novel_id"]).delivery_selection(
        formats=("nfpack",))
    result = stack["delivery"].deliver(DeliveryRequest(selection=selection))
    package_dir = Path(result.package_path)
    assert package_dir.name == result.snapshot_id
    assert package_dir.parent.as_posix().endswith(
        "novel/authoring/story_engine/delivery/novel_alpha/packages")
    assert (package_dir / "package" / "novelforge-package.nfpack").is_file()
    assert (package_dir / "manifest.json").is_file()
