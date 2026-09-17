"""永久守卫：legacy 边界（V4-01，`docs/v4/V4_MODULE_BOUNDARIES.md` §3.5）。

断言：

1. frozen 模块清单完整（每个条目有 path / capability / status / removal_condition）；
2. 适配器只读（describe / status 不产生任何文件写入）；
3. 已删除的废弃数据没有进入 `legacy/`；
4. 新业务路径（application / persistence）不 import frozen 历史模块。
"""

from __future__ import annotations

import json
from pathlib import Path

from _guard_utils import ROOT, imports_matching, python_files

FROZEN_HISTORICAL_PREFIXES = (
    "novelforge.story_engine.repair",
    "novelforge.story_engine.historical_ir",
    "novelforge.story_engine.reconstruction",
    "novelforge.story_engine.historical_adoption",
    "novelforge.story_engine.m11_",
    "novelforge.story_engine.m12_",
    "novelforge.story_engine.m13_",
    "novelforge.story_engine.m14_",
    "novelforge.story_engine.m15_",
    "novelforge.story_engine.m16_",
    "novelforge.story_engine.m17_",
    "novelforge.story_engine.m18_",
)


def test_frozen_manifest_is_well_formed() -> None:
    from novelforge.legacy import FROZEN_MODULES, frozen_module_ids

    assert FROZEN_MODULES, "legacy manifest 必须登记仍保留的 frozen 能力"
    ids = frozen_module_ids()
    assert len(ids) == len(set(ids)), "module_id 不得重复"
    for item in FROZEN_MODULES:
        assert item.module_id and item.path and item.capability
        assert item.status in {"frozen_read_only", "compatibility_adapter",
                               "historical_milestone"}
        assert item.removal_condition, f"{item.module_id} 必须写明移除条件"


def test_legacy_describe_is_read_only(tmp_path: Path) -> None:
    from novelforge.legacy import describe_legacy_capabilities, legacy_adventure_status

    before = sorted(p.name for p in tmp_path.iterdir())
    payload = describe_legacy_capabilities()
    status = legacy_adventure_status(tmp_path, "novel_legacy_probe")
    after = sorted(p.name for p in tmp_path.iterdir())

    assert payload["read_only"] is True
    assert status["read_only"] is True
    assert status["exists"] is False
    assert before == after == [], "legacy 适配器不得在数据根产生任何文件"
    assert payload["deleted_assets"], "必须显式声明已删除的废弃资产"


def test_legacy_package_holds_no_deleted_assets() -> None:
    legacy_dir = ROOT / "src" / "novelforge" / "legacy"
    blob = "\n".join(path.read_text(encoding="utf-8")
                     for path in sorted(legacy_dir.rglob("*.py")))
    for token in ("novel/final", "workspace/wasteland_001_exports",
                  "historical_chapter_ir_v1"):
        # 允许出现在"已删除资产"说明里，但不允许作为可访问路径参与逻辑
        assert f'"{token}"' not in blob, (
            f"legacy/ 不得把已删除资产当作可用路径：{token}")


def test_new_write_paths_do_not_import_frozen_history() -> None:
    offenders: list[str] = []
    for path in python_files("application", "persistence", "core"):
        for name, line in imports_matching(path, FROZEN_HISTORICAL_PREFIXES):
            offenders.append(f"{path.relative_to(ROOT)}:{line} → {name}")
    assert offenders == [], (
        "新的业务路径不得 import frozen 历史模块（必须经 legacy adapter）：\n"
        + "\n".join(offenders))


def test_legacy_boundary_rejects_writes() -> None:
    from novelforge.legacy import LegacyAdapterError
    from novelforge.legacy.adapters import forbid_write

    try:
        forbid_write("promote_historical_fact")
    except LegacyAdapterError as exc:
        assert exc.as_dict()["code"] == "LEGACY_READ_ONLY"
    else:  # pragma: no cover - 防御性
        raise AssertionError("legacy 边界必须拒绝写操作")


def test_manifest_is_serialisable_for_tooling() -> None:
    from novelforge.legacy import describe_legacy_capabilities

    json.dumps(describe_legacy_capabilities(), ensure_ascii=False)

