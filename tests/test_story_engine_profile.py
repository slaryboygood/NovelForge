from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from novelforge.api.story_builder_routes import install_story_builder_api
from novelforge.story_builder import load_story_catalog
from novelforge.story_engine import (
    Ability,
    Character,
    Faction,
    NovelProfile,
    NovelProfileError,
    NovelProfileRepository,
    ResourceDefinition,
)


ROOT = Path(__file__).resolve().parents[1]
REQUIRED_FIELDS = {"novel_id", "title", "genre", "themes", "tone", "narrative_style",
                   "world_profile", "cast", "factions", "resource_catalog", "ability_catalog",
                   "event_catalog", "story_rules"}


def make_client(tmp_path: Path) -> TestClient:
    app = FastAPI()
    install_story_builder_api(app, tmp_path, catalog=load_story_catalog(ROOT))
    return TestClient(app)


def test_profile_contract_is_generic_and_requires_explicit_novel_id() -> None:
    assert REQUIRED_FIELDS <= set(NovelProfile.model_fields)
    assert NovelProfile.model_fields["title"].default == ""
    assert NovelProfile.model_fields["genre"].default == ""
    with pytest.raises(ValidationError):
        NovelProfile()
    profile = NovelProfile(novel_id="novel_alpha")
    assert profile.cast == {} and profile.story_rules == []


def test_profile_repository_isolation_and_path_safety(tmp_path: Path) -> None:
    repository = NovelProfileRepository(tmp_path)
    alpha = repository.create("novel_alpha", title="甲书", genre="xianxia",
                              cast={"ling": Character(id="ling", kind="disciple", name="凌")},
                              factions={"qingyun": Faction(id="qingyun", kind="sect", name="青云宗")},
                              resource_catalog={"spirit_stone": ResourceDefinition(id="spirit_stone", name="灵石", unit="枚")},
                              ability_catalog={"breath": Ability(id="breath", kind="功法", name="引气诀")})
    beta = repository.create("novel_beta", title="乙书", genre="sci_fi",
                             cast={"unit_7": Character(id="unit_7", kind="android", name="第七单元")})
    assert {item.novel_id for item in repository.list()} == {"novel_alpha", "novel_beta"}
    assert repository.load("novel_alpha") == alpha
    assert repository.load("novel_beta") == beta
    assert repository.path_for("novel_alpha") != repository.path_for("novel_beta")
    repository.save(beta.model_copy(update={"title": "乙书改"}))
    assert repository.load("novel_alpha").title == "甲书"
    with pytest.raises(NovelProfileError):
        repository.create("novel_alpha")
    with pytest.raises(NovelProfileError):
        repository.load("../escape")
    with pytest.raises(NovelProfileError):
        NovelProfileRepository(tmp_path, tmp_path.parent / "outside_profiles")


def test_profile_ensure_creates_minimal_profile_for_legacy_project(tmp_path: Path) -> None:
    repository = NovelProfileRepository(tmp_path)
    assert not repository.exists("novel_project")
    created = repository.ensure("novel_project")
    assert created.novel_id == "novel_project" and created.title == "novel_project"
    assert repository.ensure("novel_project") == created
    assert created.cast == {} and created.story_rules == []


def test_api_keeps_two_novels_separate_when_switching(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    assert client.post('/api/story-builder/novels',
                       json={'novel_id': 'novel_alpha', 'title': '甲书', 'genre': 'xianxia'}).status_code == 201
    assert client.post('/api/story-builder/novels',
                       json={'novel_id': 'novel_beta', 'title': '乙书', 'genre': 'sci_fi'}).status_code == 201
    assert client.post('/api/story-builder/novels',
                       json={'novel_id': 'novel_alpha', 'title': '重复'}).status_code == 409
    listing = client.get('/api/story-builder/novels').json()['novels']
    assert {item['novel_id'] for item in listing} == {'novel_alpha', 'novel_beta'}

    alpha = client.post('/api/story-builder/sessions', json={'project_id': 'novel_alpha'}).json()
    beta = client.post('/api/story-builder/sessions', json={'project_id': 'novel_beta'}).json()
    assert alpha['novel']['novel_id'] == 'novel_alpha' and alpha['novel']['title'] == '甲书'
    assert beta['novel']['novel_id'] == 'novel_beta' and beta['novel']['genre'] == 'sci_fi'
    assert alpha['session']['session_id'] != beta['session']['session_id']

    url = '/api/story-builder/sessions/' + alpha['session']['session_id']
    assert client.post(url + '/selections', json={'step': 'reader_experience',
                                                 'option_ids': ['experience_growth_adventure'],
                                                 'expected_selection_version': 0}).status_code == 200
    assert client.get(url).json()['session']['selection_version'] == 1
    beta_url = '/api/story-builder/sessions/' + beta['session']['session_id']
    assert client.get(beta_url).json()['session']['selection_version'] == 0
    assert client.get(beta_url).json()['novel']['title'] == '乙书'
    assert client.get('/api/story-builder/novels/novel_missing').status_code == 404
    assert client.get(url).json()['novel']['title'] == '甲书'


def test_legacy_session_without_profile_still_loads(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    created = client.post('/api/story-builder/sessions', json={'project_id': 'legacy_novel',
                                                              'session_id': 'session_legacy'}).json()
    assert created['novel']['novel_id'] == 'legacy_novel'
    assert NovelProfileRepository(tmp_path).exists('legacy_novel')
