"""永久守卫：不再依赖旧正文（V4-01，作者决策 A + ADR-011）。

断言：

1. `novel/final/**` 已删除且没有产品引用；
2. 产品链路在旧正文缺席时完全可用（作品创建 → 投影 → 导出）；
3. 历史正文 / 历史修复 / 历史 writer 通道（`writer_integration`）在
   post-release cleanup 后既不存在、也不被当前产品模块引用
   （正文 draft 能力已随 V2/V3 Story Builder 后端退休）。
"""

from __future__ import annotations

from pathlib import Path

import importlib

import pytest

from _guard_utils import ROOT, python_files, string_literals, write_minimal_novel

RETIRED_MODULES = ("novelforge.story_builder.writer_integration",
                   "novelforge.story_builder.export_package",
                   "novelforge.story_builder.v3_projection")
CURRENT_PRODUCT_DIRS = ("api", "application", "blueprint", "delivery", "editor",
                        "generation", "memory", "quality", "core", "persistence",
                        "agent", "plugins")


def test_final_prose_is_deleted_and_unreferenced() -> None:
    assert not (ROOT / "novel" / "final").exists(), "旧正文目录已删除"
    offenders: list[str] = []
    for path in python_files("api", "application", "story_builder", "persistence",
                             "core", "legacy"):
        for value, line in string_literals(path):
            if value.strip().strip("`").replace("\\", "/").startswith("novel/final"):
                offenders.append(f"{path.relative_to(ROOT)}:{line} → {value!r}")
    assert offenders == [], (
        "产品侧模块不得把已删除的旧正文当作路径使用：\n" + "\n".join(offenders))


def test_retired_legacy_channels_are_unavailable_and_unreferenced() -> None:
    """历史 writer / export / V3 projection 通道：模块不存在，产品也不引用。"""

    for module_name in RETIRED_MODULES:
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module(module_name)

    banned = ("novel/final", "historical_repair", "writer_integration",
              "writer_v1", "wasteland_001")
    offenders: list[str] = []
    for path in python_files(*CURRENT_PRODUCT_DIRS):
        for value, line in string_literals(path):
            hit = next((token for token in banned if token in value), "")
            if hit:
                offenders.append(
                    f"{path.relative_to(ROOT)}:{line} → {hit}（{value[:60]!r}）")
    assert offenders == [], (
        "当前产品模块不得把已退休的历史资产 / 模块当作路径或字符串使用：\n"
        + "\n".join(offenders))


def test_pipeline_works_without_prose(tmp_path: Path) -> None:
    write_minimal_novel(tmp_path, "novel_no_prose", title="无正文作品")
    from novelforge.application.services import JourneyService

    projection = JourneyService(tmp_path, "novel_no_prose").projection()
    assert projection["journey"]["current_stage"]
    assert projection["profile"].novel_id == "novel_no_prose"
