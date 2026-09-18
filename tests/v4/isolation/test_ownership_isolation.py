"""永久守卫：跨作品隔离（V4-01）。

两个极小 fixture（Novel A / Novel B）证明：

```text
执行 A 的 state / journey / export 读操作时
→ 结果里不得出现 B 的任何数据
```

这不是"完整多作品 UI"的承诺，只证明 ownership 不依赖全局路径。
"""

from __future__ import annotations

import json
from pathlib import Path

from _guard_utils import write_minimal_novel


def _prepare_two_novels(tmp_path: Path) -> tuple[str, str]:
    write_minimal_novel(tmp_path, "novel_alpha", title="阿尔法计划")
    write_minimal_novel(tmp_path, "novel_beta", title="贝塔计划")
    return "novel_alpha", "novel_beta"


def test_journey_projection_only_contains_own_novel(tmp_path: Path) -> None:
    alpha, beta = _prepare_two_novels(tmp_path)
    from novelforge.application.services import JourneyService

    projection = JourneyService(tmp_path, alpha).projection()
    blob = json.dumps(projection, ensure_ascii=False, default=str)

    assert projection["profile"].novel_id == alpha
    assert projection["profile"].title == "阿尔法计划"
    assert "贝塔计划" not in blob
    assert beta not in blob, "A 的投影里不得出现 B 的 novel_id"


def test_paths_are_per_novel(tmp_path: Path) -> None:
    from novelforge.persistence.paths import (
        canon_db_path,
        planning_index_path,
        profiles_path,
        writer_store_dir,
    )

    alpha, beta = "novel_alpha", "novel_beta"
    assert canon_db_path(tmp_path, alpha) != canon_db_path(tmp_path, beta)
    assert alpha in canon_db_path(tmp_path, alpha).name
    assert beta not in str(canon_db_path(tmp_path, alpha))
    assert planning_index_path(tmp_path, alpha) != planning_index_path(tmp_path, beta)
    assert profiles_path(tmp_path, alpha) != profiles_path(tmp_path, beta)
    assert writer_store_dir(tmp_path, alpha) == writer_store_dir(tmp_path, beta), (
        "writer store 根目录共用，但内部必须按 novel_id 分目录")


def test_export_projection_is_novel_scoped(tmp_path: Path) -> None:
    alpha, beta = _prepare_two_novels(tmp_path)
    from novelforge.application.services import ExportService

    # post-release cleanup：legacy `projection()` 已退休；同一"作品隔离"不变式
    # 改由 current 交付投影（selection + describe）证明。
    service = ExportService(tmp_path, alpha)
    described = service.describe_delivery(service.delivery_selection())
    blob = json.dumps(described, ensure_ascii=False, default=str)

    assert described["selection"]["novel_id"] == alpha
    for section in described.get("sections", []):
        identity = section.get("identity", "")
        assert identity in {"", alpha, "main"} or alpha in identity, (
            f"section {section['section_id']} 的 identity 不属于 {alpha}")
    assert beta not in blob
    assert "贝塔计划" not in blob


def test_story_state_reads_are_novel_scoped(tmp_path: Path) -> None:
    alpha, beta = _prepare_two_novels(tmp_path)
    from novelforge.story_engine.context import resolve_novel_context
    from novelforge.story_engine.profile import NovelProfileRepository
    from novelforge.story_engine.storage import StoryStateRepository

    alpha_context = resolve_novel_context(tmp_path, alpha)
    beta_context = resolve_novel_context(tmp_path, beta)
    assert alpha_context.novel_id == alpha
    assert beta_context.novel_id == beta
    assert alpha_context.profile.title != beta_context.profile.title

    # 事实状态槽按 novel_id 隔离：写入 A 的运行槽不影响 B
    repositories = StoryStateRepository(tmp_path)
    alpha_state = alpha_context.state.model_copy(update={"novel_id": alpha})
    repositories.save(alpha_state, f"runtime_{alpha}", 1)
    assert repositories.exists(f"runtime_{alpha}", 1) is True
    assert repositories.exists(f"runtime_{beta}", 1) is False
    loaded = repositories.load(f"runtime_{alpha}", 1)
    assert loaded.novel_id == alpha
    assert NovelProfileRepository(tmp_path).load(beta).title == "贝塔计划"
