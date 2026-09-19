"""§68 Source Reference：每个 skill 都可追溯到 SOURCE_MAP 行；路径与测试真实存在。"""

from __future__ import annotations

import pytest

from ._skill_lib import load_validator


@pytest.fixture(scope="module")
def validator():
    return load_validator()


def test_source_map_complete(validator):
    skill_ids = {validator.check_skill_schema(path) for path in validator.skill_files()}
    validator.check_source_map(skill_ids)


def test_source_map_paths_exist(validator):
    validator.check_source_references()


def test_source_map_has_contract_and_tests_columns(validator):
    text = validator.read_text(validator.SKILL_ROOT / "SOURCE_MAP.md")
    for column in ("Contract", "Source Owner", "REST", "MCP", "Tests"):
        assert column in text, f"SOURCE_MAP.md 缺少列：{column}"


def test_every_skill_has_source_references_section(validator):
    for path in validator.skill_files():
        body = validator.read_text(path)
        section = body.split("## Source references", 1)[1]
        assert validator.PATH_RE.findall(section) or "N/A" in section, \
            f"{validator.rel(path)} 的 Source references 为空"
