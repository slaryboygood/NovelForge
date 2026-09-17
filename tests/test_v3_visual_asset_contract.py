"""V3 Visual Asset Contract 回归（不依赖任何图像库，也不联网）。

守卫 Visual Asset Contract 的长期不变量：

* docs/V3_VISUAL_ASSET_REQUIREMENTS.json 声明的 required 资源必须真实存在，
  且文件格式与声明的 format 一致（只看 magic bytes，不引入图像库依赖）；
* artworkManifest.ts 必须为 required slot 接入真实资源（url 非空）；
* 解析顺序必须是 real story asset → product default artwork → semantic icon；
* 组件不允许自己 import 默认美术文件（禁止 hardcode 路径 / 禁止绕过 Manifest）。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REQUIREMENTS = PROJECT_ROOT / "docs" / "V3_VISUAL_ASSET_REQUIREMENTS.json"
MANIFEST = (PROJECT_ROOT / "ui" / "src" / "v3" / "design-system" / "assets"
            / "artworkManifest.ts")

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _requirements() -> dict:
    return json.loads(REQUIREMENTS.read_text(encoding="utf-8"))


def _required_assets() -> list[dict]:
    return [row for row in _requirements()["assets"]
            if row.get("required_for_final_visual_acceptance")]


def _is_webp(path: Path) -> bool:
    head = path.read_bytes()[:12]
    return head[:4] == b"RIFF" and head[8:12] == b"WEBP"


def test_required_assets_exist_with_declared_format() -> None:
    required = _required_assets()
    assert len(required) == 6, f"required 资源必须是 6 个，实际 {len(required)}"
    for row in required:
        path = PROJECT_ROOT / row["target_path"]
        assert path.is_file(), f"{row['asset_id']} 缺失：{row['target_path']}"
        assert row["current_status"] == "available", (
            f"{row['asset_id']} 状态必须反映真实情况，实际 {row['current_status']}")
        declared = str(row["format"]).upper()
        if "PNG" in declared:
            assert path.read_bytes().startswith(PNG_MAGIC), (
                f"{row['asset_id']} 声明支持 PNG，但交付文件既不是 PNG")
        elif "WEBP" in declared:
            assert _is_webp(path), f"{row['asset_id']} 声明为 WebP 但文件不是 WebP"


def test_faction_emblem_target_path_matches_delivered_format() -> None:
    """势力徽记交付为透明 PNG：target_path 必须与交付格式一致，不能改名掩盖。"""

    row = next(item for item in _required_assets() if item["asset_id"] == "default_faction")
    assert row["transparent"] is True
    path = PROJECT_ROOT / row["target_path"]
    assert path.suffix.lower() == ".png", (
        "势力徽记交付为 PNG（透明通道），target_path 必须与交付格式一致")


def test_manifest_wires_every_required_slot() -> None:
    source = MANIFEST.read_text(encoding="utf-8")
    for row in _required_assets():
        slot = row["asset_id"]
        block = re.search(r"\{[^{}]*id: '" + re.escape(slot) + r"'[^{}]*\}", source, re.S)
        assert block, f"Manifest 缺少 {slot} 的 slot 定义"
        assert re.search(r"url:\s*\w+", block.group(0)), (
            f"{slot} 还没有接入真实资源（url 为空）")


def test_resolver_prefers_real_story_asset_then_default_then_icon() -> None:
    source = MANIFEST.read_text(encoding="utf-8")
    body = source.split("export function resolveEntityArtwork", 1)[1]
    story = body.index("storyUrl")
    default = body.index("DEFAULT_ARTWORK[kind]?.url")
    icon = body.index("source: 'icon'")
    assert story < default < icon, (
        "解析顺序必须是 real story asset → product default artwork → semantic icon")


def test_components_do_not_import_default_artwork_directly() -> None:
    """默认美术只能由 Manifest 引用：组件不得自己 import 资源文件。"""

    offenders: list[str] = []
    for path in (PROJECT_ROOT / "ui" / "src").rglob("*"):
        if path.suffix not in (".ts", ".tsx") or path == MANIFEST:
            continue
        text = path.read_text(encoding="utf-8")
        if re.search(r"from\s+['\"][^'\"]*assets/(defaults|empty-states)/", text):
            offenders.append(str(path.relative_to(PROJECT_ROOT)))
    assert not offenders, f"这些文件直接引用了默认美术，必须走 Manifest：{offenders}"


def test_manifest_target_paths_match_requirements() -> None:
    source = MANIFEST.read_text(encoding="utf-8")
    for row in _required_assets():
        assert row["target_path"] in source, (
            f"Manifest 的 {row['asset_id']} targetPath 与 requirements 不一致："
            f"{row['target_path']}")
