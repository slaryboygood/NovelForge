"""永久守卫：不存在任何 historical / wasteland 回退（V4-01，作者决策 B）。

断言四件事：

1. 已删除的历史资产在磁盘上确实不存在（不会被悄悄恢复）；
2. 产品侧模块（api / application / story_builder / persistence / core / legacy）
   不再出现历史路径常量（frozen story_engine 历史模块允许保留内部常量）；
3. 导出结果不再包含历史分区（spine / historical_ir）或冻结契约 digest；
4. 产品运行时不需要 historical 数据即可完成一次导出。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from _guard_utils import (
    ROOT,
    identifier_names,
    python_files,
    string_literals,
    write_minimal_novel,
)

#: 产品侧模块：这里绝不允许再出现历史资产引用
PRODUCT_DIRS = ("api", "application", "story_builder", "persistence", "core", "legacy")

#: 禁止作为**路径字面量**出现（文档里可以提到"已删除"，但不能当路径用）
FORBIDDEN_PATH_PREFIXES = (
    "novel/final",
    "workspace/wasteland_001_exports",
    "canon/wasteland_001.sqlite",
    "historical_chapter_ir_v1",
    "repair_adoption_v1",
    "repair_v1",
    "chapter_ir_v1",
    "writer_v1",
)

#: 禁止作为**标识符**出现（V3 里这些名字就是单作品硬编码的载体）
FORBIDDEN_IDENTIFIERS = (
    "RECON_DIR",
    "HISTORY_DIR",
    "LEGACY_WRITER_STORE_DIR",
    "FROZEN_SOURCE_DIGESTS",
    "FROZEN_FOUNDATION_DIGESTS",
    "CANON_DB",
)

DELETED_PATHS = (
    ROOT / "novel" / "final",
    ROOT / "workspace" / "wasteland_001_exports",
)


def test_deleted_assets_stay_deleted() -> None:
    for path in DELETED_PATHS:
        assert not path.exists(), (
            f"{path.relative_to(ROOT)} 已在 V4-01 删除，不得重新引入"
            "（作者决策 A / B：不迁移、不归档、不做 fixture）")


def test_product_modules_do_not_reference_historical_assets() -> None:
    """产品侧模块不得再把已删除资产当作路径使用（文档提及不算违规）。

    检查方式是 AST：

    * 字符串字面量不得以已删除路径前缀开头（裸路径 / f-string 常量部分）
    * 标识符不得再出现 V3 的单作品常量名
    """

    offenders: list[str] = []
    for path in python_files(*PRODUCT_DIRS):
        relative = path.relative_to(ROOT)
        for value, line in string_literals(path):
            cleaned = value.strip().strip("`").replace("\\", "/")
            for prefix in FORBIDDEN_PATH_PREFIXES:
                if cleaned.startswith(prefix):
                    offenders.append(f"{relative}:{line} 路径字面量 {value!r}")
                    break
        for name, line in identifier_names(path):
            if name in FORBIDDEN_IDENTIFIERS:
                offenders.append(f"{relative}:{line} 标识符 {name}")
    assert offenders == [], (
        "产品侧模块仍然引用历史资产，必须在当前 subsystem 内移除：\n"
        + "\n".join(offenders))


def test_no_historical_fallback_in_export(tmp_path: Path) -> None:
    """交付投影不得包含历史分区 / 冻结契约 digest（V3 缺陷 NR-002 的永久守卫）。

    post-release cleanup：legacy `ExportService.projection()` 已退休，
    同一不变式改由 current 交付路径（selection + describe）证明。
    """

    pack_id = write_minimal_novel(tmp_path, "novel_no_hist", title="无历史作品")
    assert pack_id

    from novelforge.application.services import ExportService

    service = ExportService(tmp_path, "novel_no_hist")
    described = service.describe_delivery(service.delivery_selection())
    section_ids = [row["section_id"] for row in described.get("sections", [])]

    assert "historical_ir" not in section_ids
    assert "spine" not in section_ids
    payload = json.dumps(described, ensure_ascii=False, default=str)
    assert "wasteland" not in payload.lower()
    assert "historical" not in payload.lower()

    # 交付投影整体不得出现冻结契约 / 历史 foundation 的 digest 痕迹。
    assert "repair_gate" not in payload
    assert "historical_foundation" not in payload


def test_export_works_without_historical_data(tmp_path: Path) -> None:
    """历史数据完全不存在时，current 交付链路仍可用。"""

    write_minimal_novel(tmp_path, "novel_export_only", title="只有设定")
    from novelforge.application.services import ExportService

    service = ExportService(tmp_path, "novel_export_only")
    selection = service.delivery_selection(formats=("markdown",))
    described = service.describe_delivery(selection)
    assert described["write"] is False
    assert "wasteland" not in json.dumps(described, ensure_ascii=False,
                                        default=str).lower()


def test_historian_layers_are_gone_from_inspector() -> None:
    """Inspector 不再暴露 historical_repair 层。"""

    from novelforge.story_builder import inspector

    assert "historical_repair" not in inspector.LAYERS
    assert not hasattr(inspector, "CANON_DB")
    with pytest.raises(AttributeError):
        getattr(inspector, "history_dir")
