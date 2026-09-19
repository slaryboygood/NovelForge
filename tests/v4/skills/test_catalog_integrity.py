"""§64 Catalog Integrity：skill id 唯一、catalog ↔ 目录一致、module README 存在、SKILL.md 可解析。"""

from __future__ import annotations

import pytest

from ._skill_lib import load_validator


@pytest.fixture(scope="module")
def validator():
    return load_validator()


def test_every_module_has_readme(validator):
    validator.check_layout()


def test_skill_schema_and_unique_ids(validator):
    paths = validator.skill_files()
    assert paths, "没有找到任何 SKILL.md"
    ids = [validator.check_skill_schema(path) for path in paths]
    assert len(ids) == len(set(ids)), f"skill id 重复：{ids}"
    # 目录名必须等于 skill id 的最后一段（防止目录 / id 漂移）
    for path, skill_id in zip(paths, ids):
        assert skill_id.split(".")[-1] == path.parent.name
        assert skill_id.split(".")[-2] == path.parent.parent.name


def test_catalog_matches_skill_directories(validator):
    skill_ids = {validator.check_skill_schema(path) for path in validator.skill_files()}
    validator.check_catalog(skill_ids)


def test_module_readme_lists_owned_skills(validator):
    """每个 module README 至少列出它自己的 module 名（Public Contract 的锚点）。"""

    for module in validator.MODULES:
        readme = validator.SKILL_ROOT / module / "README.md"
        text = validator.read_text(readme)
        assert f"`{module}`" in text or f"# Module: `{module}`" in text
