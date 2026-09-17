from __future__ import annotations

from collections import Counter
from copy import deepcopy
from pathlib import Path

import pytest
import yaml

from novelforge.story_builder import (
    STORY_STEP_ORDER,
    StoryCatalogError,
    StoryCatalogLoader,
    StoryChoiceCatalog,
    StoryStep,
    load_story_catalog,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = PROJECT_ROOT / "novel" / "config" / "story_builder" / "step_catalogs.yaml"


def load_catalog() -> StoryChoiceCatalog:
    data = yaml.safe_load(CATALOG_PATH.read_text(encoding="utf-8"))
    return StoryChoiceCatalog.model_validate(data)


def catalog_payload() -> dict:
    return yaml.safe_load(CATALOG_PATH.read_text(encoding="utf-8"))


def write_catalog(root: Path, payload: object) -> Path:
    path = root / "novel" / "config" / "story_builder" / "step_catalogs.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


def test_real_story_choice_catalog_is_complete_and_chinese() -> None:
    catalog = load_catalog()

    assert catalog.language == "zh-CN"
    assert tuple(step.step for step in catalog.steps) == STORY_STEP_ORDER
    assert len(catalog.options) == 30
    assert Counter(option.step for option in catalog.options) == {
        step: 3 for step in StoryStep
    }
    assert all(any("\u4e00" <= char <= "\u9fff" for char in step.title) for step in catalog.steps)
    assert all(any("\u4e00" <= char <= "\u9fff" for char in option.name) for option in catalog.options)


def test_real_catalog_contains_minimum_product_directions() -> None:
    catalog = load_catalog()
    option_ids = {option.id for option in catalog.options}

    assert {
        "experience_growth_adventure",
        "world_silicon_mmo",
        "background_ruined_board",
        "protagonist_nonhuman_awakening",
        "events_survival_to_world",
        "progression_rule_discovery",
        "style_light_fast_webnovel",
        "boundary_character_consistency",
    } <= option_ids


def test_real_catalog_source_references_exist() -> None:
    catalog = load_catalog()

    missing = [
        source_ref
        for option in catalog.options
        for source_ref in option.source_refs
        if not (PROJECT_ROOT / source_ref).is_file()
    ]
    assert missing == []


def test_loader_builds_stable_read_only_indexes() -> None:
    index = load_story_catalog(PROJECT_ROOT)

    assert index.require_step("worldview").title == "世界观"
    assert index.require_option("world_silicon_mmo").name == "硅基拟人冒险世界"
    assert [option.priority for option in index.options_for_step(StoryStep.WORLDVIEW)] == [50, 20, 10]
    with pytest.raises(TypeError):
        index.options_by_id["new_option"] = index.require_option("world_silicon_mmo")  # type: ignore[index]


def test_loader_reports_missing_catalog_in_chinese(tmp_path: Path) -> None:
    with pytest.raises(StoryCatalogError) as caught:
        StoryCatalogLoader(tmp_path).load()

    assert caught.value.code == "CATALOG_NOT_FOUND"
    assert "找不到故事选项目录" in str(caught.value)


def test_loader_reports_invalid_yaml(tmp_path: Path) -> None:
    path = tmp_path / "broken.yaml"
    path.write_text("steps: [\n", encoding="utf-8")

    with pytest.raises(StoryCatalogError) as caught:
        StoryCatalogLoader(tmp_path).load(path)

    assert caught.value.code == "CATALOG_YAML_INVALID"
    assert caught.value.details


def test_loader_rejects_duplicate_ids_with_schema_details(tmp_path: Path) -> None:
    payload = catalog_payload()
    payload["options"][1]["id"] = payload["options"][0]["id"]
    path = write_catalog(tmp_path, payload)

    with pytest.raises(StoryCatalogError) as caught:
        StoryCatalogLoader(tmp_path).load(path)

    assert caught.value.code == "CATALOG_SCHEMA_INVALID"
    assert any("unique" in detail["message"] for detail in caught.value.details)


def test_loader_rejects_unknown_option_reference(tmp_path: Path) -> None:
    payload = catalog_payload()
    payload["options"][0]["unlocks"].append("missing_option")
    path = write_catalog(tmp_path, payload)

    with pytest.raises(StoryCatalogError) as caught:
        StoryCatalogLoader(tmp_path).load(path)

    assert caught.value.code == "CATALOG_SCHEMA_INVALID"
    assert any("unknown references" in detail["message"] for detail in caught.value.details)


def test_loader_rejects_missing_and_external_source_refs(tmp_path: Path) -> None:
    payload = catalog_payload()
    payload["options"][0]["source_refs"] = ["novel/config/missing.yaml"]
    path = write_catalog(tmp_path, payload)

    with pytest.raises(StoryCatalogError) as missing:
        StoryCatalogLoader(tmp_path).load(path)
    assert missing.value.code == "SOURCE_NOT_FOUND"
    assert missing.value.details[0]["option_id"] == "experience_growth_adventure"

    external = deepcopy(payload)
    external["options"][0]["source_refs"] = ["../outside.yaml"]
    write_catalog(tmp_path, external)
    with pytest.raises(StoryCatalogError) as outside:
        StoryCatalogLoader(tmp_path).load(path)
    assert outside.value.code == "SOURCE_OUTSIDE_PROJECT"


def test_index_lookup_reports_unknown_ids() -> None:
    index = load_story_catalog(PROJECT_ROOT)

    with pytest.raises(StoryCatalogError) as missing_option:
        index.require_option("option_does_not_exist")
    assert missing_option.value.code == "OPTION_NOT_FOUND"

    with pytest.raises(StoryCatalogError) as missing_step:
        index.require_step("step_does_not_exist")
    assert missing_step.value.code == "STEP_NOT_FOUND"
