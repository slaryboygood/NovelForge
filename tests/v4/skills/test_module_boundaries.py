"""§65 Module Boundary：一个 skill 只属于一个 capability module；workflow 不是 owner。"""

from __future__ import annotations

import re

import pytest

from ._skill_lib import load_validator


@pytest.fixture(scope="module")
def validator():
    return load_validator()


def test_skills_live_in_declared_modules(validator):
    expected = set(validator.MODULES)
    for path in validator.skill_files():
        module = path.parent.parent.name
        assert module in expected, f"{validator.rel(path)} 不在已声明的 module 里"
        # physical structure: <module>/<skill>/SKILL.md（loader 无关；见 SKILL_LIBRARY README）
        assert path.parent.parent.parent == validator.SKILL_ROOT


def test_workflows_only_compose_skill_ids(validator):
    """workflow 的 Procedure 只能引用 skill id，不得出现 REST / MCP 具体调用。"""

    workflow_root = validator.SKILL_ROOT / "workflows"
    for path in sorted(workflow_root.glob("*/SKILL.md")):
        body = validator.read_text(path)
        procedure = body.split("## Procedure", 1)[1].split("## Expected result", 1)[0]
        assert "novelforge-v4.0.1." in procedure, f"{validator.rel(path)} 未引用任何 skill id"
        assert not validator.REST_RE.findall(procedure), \
            f"{validator.rel(path)} 的 Procedure 里出现了 REST 调用（应只引用 skill id）"
        assert not validator.TOOL_REF_RE.findall(procedure), \
            f"{validator.rel(path)} 的 Procedure 里出现了 MCP tool 名（应只引用 skill id）"


def test_workflows_do_not_redefine_capabilities(validator):
    """workflow 不得声明自己拥有能力（Product owner 必须写「无」）。"""

    for path in sorted((validator.SKILL_ROOT / "workflows").glob("*/SKILL.md")):
        body = validator.read_text(path)
        assert "- **Product owner**: 无" in body, f"{validator.rel(path)} 不应声明 product owner"


def test_atomic_skill_ids_are_referenced_by_catalog_and_source_map(validator):
    skill_ids = {validator.check_skill_schema(path) for path in validator.skill_files()}
    validator.check_catalog(skill_ids)
    validator.check_source_map(skill_ids)
    validator.check_skill_id_references(skill_ids)


def test_no_retired_feature_markers(validator):
    """§12 / §90：V2/V3 retired 能力不得作为 current 出现在 skill 里。"""

    for path in validator.skill_files() + validator.module_readmes():
        text = validator.read_text(path)
        for marker in validator.RETIRED_MARKERS:
            assert marker not in text, f"{validator.rel(path)} 出现 retired 标记 {marker!r}"
    assert re.search(r"V2|V3", validator.read_text(validator.SKILL_ROOT / "README.md"))
