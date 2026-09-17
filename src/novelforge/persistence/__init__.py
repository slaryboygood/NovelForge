"""Persistence boundary（V4-01）。

本包是「物理存储访问」的唯一入口：所有 artifact 路径都必须由 `paths` 显式解析，
不允许其他模块自行拼路径，也不允许出现隐式的「当前作品」。

边界（见 docs/v4/V4_MODULE_BOUNDARIES.md §3.3）：

* 允许依赖：`core`、domain 的模型定义、python stdlib
* 禁止依赖：`interfaces`（api / mcp）、`ai`、`ui`
* 禁止：GLOBAL_CURRENT_NOVEL、默认作品、磁盘扫描推断作品、跨作品 fallback
"""

from .paths import (
    ARTIFACT_KINDS,
    NOVEL_ID_PATTERN,
    ArtifactContext,
    OwnershipError,
    canon_db_path,
    content_pack_path,
    memory_dir,
    memory_episodes_path,
    memory_manifest_path,
    memory_preferences_path,
    blueprint_dir,
    blueprint_index_path,
    blueprint_manifest_path,
    blueprint_node_dir,
    blueprint_node_path,
    quality_dir,
    quality_issues_dir,
    quality_manifest_path,
    quality_repair_history_dir,
    quality_reports_dir,
    novel_context,
    planning_dir,
    planning_index_path,
    profiles_path,
    require_same_novel,
    story_state_dir,
    writer_store_dir,
)

__all__ = [
    "ARTIFACT_KINDS", "NOVEL_ID_PATTERN", "ArtifactContext", "OwnershipError",
    "canon_db_path", "content_pack_path", "novel_context", "planning_dir",
    "planning_index_path", "profiles_path", "require_same_novel", "story_state_dir",
    "writer_store_dir", "memory_dir", "memory_episodes_path",
    "memory_manifest_path", "memory_preferences_path",
    "blueprint_dir", "blueprint_index_path", "blueprint_manifest_path",
    "blueprint_node_dir", "blueprint_node_path",
    "quality_dir", "quality_issues_dir", "quality_manifest_path",
    "quality_repair_history_dir", "quality_reports_dir",
]
