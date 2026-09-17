from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from novelforge.api.story_builder_routes import install_story_builder_api
from novelforge.story_builder import load_story_catalog
from novelforge.story_engine import (
    GENERIC_CONCEPTS,
    GenreTemplate,
    GenreTemplateError,
    NovelProfile,
    ResourceDefinition,
    StoryState,
    apply_template,
    get_template,
    list_templates,
)


ROOT = Path(__file__).resolve().parents[1]


def make_client(tmp_path: Path) -> TestClient:
    app = FastAPI()
    install_story_builder_api(app, tmp_path, catalog=load_story_catalog(ROOT))
    return TestClient(app)


def test_builtin_templates_share_the_same_generic_contract() -> None:
    templates = list_templates()
    assert {item.template_id for item in templates} == {"sci_fi", "xianxia"}
    for template in templates:
        assert isinstance(template, GenreTemplate)
        assert set(template.concepts) == set(GENERIC_CONCEPTS)
        assert template.rules and template.resource_catalog and template.ability_catalog


def test_apply_template_keeps_author_content_and_marks_defaults() -> None:
    author_profile = NovelProfile(
        novel_id="novel_author",
        story_rules=["作者自己的规则"],
        factions={"my_guild": {"id": "my_guild", "kind": "sect", "name": "我的宗门"}},
    )
    applied = apply_template(author_profile, "xianxia")
    assert applied.template_id == "xianxia"
    assert set(applied.factions) == {"my_guild", "sect"}
    assert applied.factions["my_guild"].name == "我的宗门"
    assert applied.factions["my_guild"].data == {}
    assert applied.factions["sect"].data["source"] == "xianxia"
    assert applied.story_rules[0] == "作者自己的规则"
    assert applied.world_profile["concepts"]["progression"] == ["境界"]
    assert applied.world_profile["template"] == "xianxia"


def test_template_definitions_are_not_story_facts() -> None:
    assert "amount" not in ResourceDefinition.model_fields
    xianxia = apply_template(NovelProfile(novel_id="novel_xianxia"), "xianxia")
    sci_fi = apply_template(NovelProfile(novel_id="novel_scifi"), "sci_fi")
    assert set(xianxia.model_dump()) == set(sci_fi.model_dump())
    assert set(xianxia.world_profile["concepts"]) == set(GENERIC_CONCEPTS)
    state = StoryState()
    assert state.resources == {} and state.abilities == {} and state.knowledge == []
    assert xianxia.resource_catalog["spirit_stone"].name == "灵石"
    assert sci_fi.resource_catalog["energy"].name == "能源"


def test_custom_genre_and_unknown_template() -> None:
    profile = NovelProfile(novel_id="novel_custom")
    assert apply_template(profile, "") == profile
    with pytest.raises(GenreTemplateError):
        get_template("not_a_template")


def test_engine_modules_contain_no_genre_branching() -> None:
    source = "".join(
        path.read_text(encoding="utf-8")
        for path in sorted((ROOT / "src" / "novelforge" / "story_engine").glob("*.py"))
    )
    for pattern in ("if genre ==", "if world_type ==", "if template_id ==", "if novel_id ==",
                    "elif genre ==", "elif template_id =="):
        assert pattern not in source, pattern


def test_novel_api_applies_template_and_lists_templates(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    templates = client.get('/api/story-builder/templates').json()['templates']
    assert {item['template_id'] for item in templates} == {'sci_fi', 'xianxia'}
    created = client.post('/api/story-builder/novels',
                          json={'novel_id': 'novel_scifi', 'title': '乙书', 'template_id': 'sci_fi'})
    assert created.status_code == 201
    novel = created.json()['novel']
    assert novel['template_id'] == 'sci_fi'
    assert 'corporation' in novel['factions'] and 'energy' in novel['resource_catalog']
    assert client.post('/api/story-builder/novels',
                       json={'novel_id': 'novel_bad', 'template_id': 'not_a_template'}).status_code == 422
