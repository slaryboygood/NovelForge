"""永久守卫：不存在隐式磁盘发现（V4-01）。

仅仅在磁盘上创建另一个作品目录，不得：

```text
自动成为当前作品
自动参与其他作品的 export
自动进入其他作品的 state
```
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from _guard_utils import write_minimal_novel


def test_paths_require_explicit_novel_id(tmp_path: Path) -> None:
    from novelforge.persistence.paths import OwnershipError, canon_db_path

    for bad in ("", "   "):
        with pytest.raises(OwnershipError) as exc:
            canon_db_path(tmp_path, bad)
        assert exc.value.code == "NOVEL_ID_REQUIRED"

    with pytest.raises(OwnershipError) as exc:
        canon_db_path(tmp_path, "../escape")
    assert exc.value.code == "NOVEL_ID_INVALID"


def test_extra_novel_on_disk_does_not_leak_into_other_novel(tmp_path: Path) -> None:
    write_minimal_novel(tmp_path, "novel_primary", title="主线作品")
    # 只在磁盘上多出一个作品（模拟"别的作品躺在那里"）
    write_minimal_novel(tmp_path, "novel_sidecar", title="旁挂作品")

    from novelforge.application.services import JourneyService

    projection = JourneyService(tmp_path, "novel_primary").projection()
    blob = json.dumps(projection, ensure_ascii=False, default=str)
    assert "novel_sidecar" not in blob
    assert "旁挂作品" not in blob


def test_scanning_disk_does_not_bind_current_novel(tmp_path: Path) -> None:
    """没有 profile 的作品目录存在时，服务层不会把它当作"当前作品"。"""

    stray = tmp_path / "novel" / "authoring" / "story_engine" / "profiles"
    stray.mkdir(parents=True, exist_ok=True)
    (stray / "stray_novel.json").write_text("{not-json}", encoding="utf-8")

    from novelforge.application.services import ProjectService

    service = ProjectService(tmp_path)
    listed = [row["novel_id"] for row in service.list_novels()]
    # 损坏的 profile 不得被静默跳过或"猜"成一个作品
    with pytest.raises(Exception):
        service.get_novel("stray_novel")
    assert all(row != "stray_novel" for row in listed) or listed == []


def test_service_requires_novel_id(tmp_path: Path) -> None:
    from novelforge.application.services import ExportService, JourneyService

    with pytest.raises(ValueError):
        JourneyService(tmp_path, "")
    with pytest.raises(ValueError):
        ExportService(tmp_path, "")

