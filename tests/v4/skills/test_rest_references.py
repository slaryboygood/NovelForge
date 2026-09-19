"""§66 REST Reference：skill / module README 里声明的 REST 端点必须真实存在。"""

from __future__ import annotations

import pytest

from ._skill_lib import load_validator


@pytest.fixture(scope="module")
def validator():
    return load_validator()


def test_skill_rest_references_exist(validator):
    validator.check_rest_references(validator.real_routes())


def test_rest_reference_scan_is_not_empty(validator):
    """守卫：如果正则失效（0 命中），测试必须失败，而不是静默通过。"""

    hits = 0
    for path in validator.skill_files() + validator.module_readmes():
        hits += len(validator.REST_RE.findall(validator.read_text(path)))
    assert hits >= 40, f"REST 引用扫描命中过少（{hits}）—— 正则或技能内容可能失效"


def test_route_normalisation_handles_path_params(validator):
    routes = validator.real_routes()
    assert validator._normalise_route(
        "GET", "/editor/nodes/{node_id}?novel_id=x") in routes
    assert validator._normalise_route(
        "GET", "/delivery/{snapshot_id}/artifacts/{artifact_path:path}") in routes
