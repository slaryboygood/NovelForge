"""V4-05 §18、§52：Q6 Semantic —— normalized 精确 + 结构化相似度（不使用 embedding）。"""

from __future__ import annotations

from pathlib import Path

from quality_support import codes, isolated_gate, scene


def _duplicate_pair(**overrides: object) -> list[object]:
    shared = {"scene_purpose": "让主角拿到被删除日志的第一条证据",
              "conflict": "主管拒绝开放记录", "escalation": "对手把许可撤回",
              "turn": "缓存在设备里仍保留日志编号"}
    shared.update(overrides)
    return [scene("sc_001_01", sequence=1, **shared),
            scene("sc_001_02", sequence=2, **shared)]


def test_consecutive_duplicate_scenes_are_reported(tmp_path: Path) -> None:
    issues, _quality = isolated_gate(tmp_path, _duplicate_pair(), "Q6",
                                     with_novel=False)
    assert codes(issues) == ["SCENE_SEMANTIC_REPETITION"]
    issue = issues[0]
    assert set(issue.scope.node_ids) == {"sc_001_02"}
    assert set(issue.evidence[0].node_ids) == {"sc_001_01", "sc_001_02"}
    assert issue.severity == "major"


def test_single_field_overlap_is_not_repetition(tmp_path: Path) -> None:
    """只重复一个字段不足以判定"承担相同叙事动作"（避免假阳性）。"""

    issues, _quality = isolated_gate(
        tmp_path,
        [scene("sc_001_01", sequence=1),
         scene("sc_001_02", sequence=2,
               scene_purpose="让主角核对被撤回的许可记录",
               conflict="管理局要求先交出设备",
               escalation="设备被列入封存清单",
               turn="封存清单上有主管签名")],
        "Q6", with_novel=False)
    assert "SCENE_SEMANTIC_REPETITION" not in codes(issues)


def test_chapter_goal_repetition(tmp_path: Path) -> None:
    from quality_support import chapter

    issues, _quality = isolated_gate(
        tmp_path,
        [chapter("ch_001", sequence=1, goal="确认内部维修队列是否被人为改写"),
         chapter("ch_002", sequence=2, goal="确认内部维修队列是否被人为改写")],
        "Q6", with_novel=False)
    assert "CHAPTER_GOAL_REPETITION" in codes(issues)


def test_title_semantic_repetition(tmp_path: Path) -> None:
    from quality_support import chapter

    issues, _quality = isolated_gate(
        tmp_path,
        [chapter("ch_001", sequence=1, title="被删除的维修日志"),
         chapter("ch_002", sequence=2, title="被删除的维修日志")],
        "Q6", with_novel=False)
    assert "TITLE_SEMANTIC_REPETITION" in codes(issues)


def test_hollow_node_is_reported(tmp_path: Path) -> None:
    issues, _quality = isolated_gate(
        tmp_path,
        [scene("sc_001_01", sequence=1, scene_purpose="调查", conflict="",
               escalation="", turn="", outcome="", next_hook="",
               information_reveal=[])],
        "Q6", with_novel=False)
    assert "HOLLOW_NODE" in codes(issues)
    assert [row for row in issues if row.code == "HOLLOW_NODE"][0].severity == "minor"


def test_semantic_gate_does_not_use_local_hash_embedding() -> None:
    """§18：embedding 仍非真实语义模型，不得用于真实质量判定。"""

    import ast
    from pathlib import Path as _Path

    from novelforge.quality.evaluators import semantic_gate

    source = _Path(semantic_gate.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    referenced: set[str] = set()
    for item in ast.walk(tree):
        if isinstance(item, ast.Name):
            referenced.add(item.id)
        elif isinstance(item, ast.Attribute):
            referenced.add(item.attr)
        elif isinstance(item, ast.Import):
            referenced.update(alias.name for alias in item.names)
        elif isinstance(item, ast.ImportFrom):
            referenced.add(item.module or "")
            referenced.update(alias.name for alias in item.names)
    assert not [name for name in referenced if "embedding" in name.lower()]
