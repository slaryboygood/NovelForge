"""Author Preferences（V4-03 §15–§16）。"""

from __future__ import annotations

from pathlib import Path

import pytest

from novelforge.memory import AuthorPreferenceService, MemoryError
from novelforge.memory.preferences import PREFERENCE_SCOPE_ORDER
from novelforge.persistence.paths import memory_preferences_path


def test_scope_precedence_is_deterministic() -> None:
    service = AuthorPreferenceService("novel_a", project_id="proj_1")
    service.set("global", "pacing", "慢")
    service.set("project", "pacing", "中")
    service.set("novel", "pacing", "快")
    service.set("operation", "pacing", "极快", scope_id="scene_plan")
    assert service.resolve(operation="scene_plan")["pacing"]["value"] == "极快"
    assert service.resolve(operation="other")["pacing"]["value"] == "快"
    assert service.resolve()["pacing"]["scope"] == "novel"


def test_scope_order_constant_matches_spec() -> None:
    assert PREFERENCE_SCOPE_ORDER == ("global", "project", "novel", "operation")


def test_inferred_preferences_are_marked_and_do_not_override_explicit() -> None:
    service = AuthorPreferenceService("novel_a", project_id="proj_1")
    service.set("novel", "reversal_frequency", "低", inferred=True, source="model")
    resolved = service.resolve()
    assert resolved["reversal_frequency"]["inferred"] is True
    assert resolved["reversal_frequency"]["source"] == "model"

    service.set("novel", "reversal_frequency", "中")
    resolved = service.resolve()
    assert resolved["reversal_frequency"]["value"] == "中"
    assert resolved["reversal_frequency"]["inferred"] is False


def test_scope_validation() -> None:
    with pytest.raises(MemoryError):
        AuthorPreferenceService("")
    service = AuthorPreferenceService("novel_a")
    with pytest.raises(MemoryError):
        service.set("galaxy", "pacing", "x")
    with pytest.raises(MemoryError):
        service.set("operation", "pacing", "x")  # 缺少 scope_id
    with pytest.raises(MemoryError):
        service.set("novel", "pacing", object())
    with pytest.raises(MemoryError):
        service.set("novel", "", "x")


def test_preferences_persist_through_persistence_path(tmp_path: Path) -> None:
    service = AuthorPreferenceService("novel_alpha", project_root=tmp_path,
                                      project_id="novel_alpha", persist=True)
    service.set("novel", "scene_density", "低")
    service.set("global", "forbidden_tropes", ["穿越", "失忆"])
    path = service.save()
    assert path is not None and path == memory_preferences_path(tmp_path, "novel_alpha")
    assert service.path() == path

    reloaded = AuthorPreferenceService("novel_alpha", project_root=tmp_path,
                                       project_id="novel_alpha", persist=True)
    resolved = reloaded.resolve()
    assert resolved["scene_density"]["value"] == "低"
    assert resolved["forbidden_tropes"]["value"] == ["穿越", "失忆"]


def test_preferences_are_novel_scoped(tmp_path: Path) -> None:
    alpha = AuthorPreferenceService("novel_alpha", project_root=tmp_path,
                                    project_id="novel_alpha", persist=True)
    alpha.set("novel", "pacing", "快")
    alpha.save()
    beta = AuthorPreferenceService("novel_beta", project_root=tmp_path,
                                   project_id="novel_beta", persist=True)
    assert beta.resolve() == {}
    assert alpha.path() != beta.path()


def test_as_items_exposes_provenance() -> None:
    service = AuthorPreferenceService("novel_a", project_id="proj_1")
    service.set("novel", "chapter_granularity", "粗", note="作者明确要求")
    rows = service.as_items()
    assert rows[0]["scope"] == "novel"
    assert rows[0]["source"] == "author"
    assert rows[0]["inferred"] is False
    assert rows[0]["updated_at"]

