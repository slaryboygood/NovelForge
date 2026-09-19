"""§69 Frozen Baseline：SKILL_MANIFEST.json 的哈希必须与磁盘一致（防止 silent drift）。

必须纠正文档错误时，走显式 SKILL_BASELINE_UPDATE：

```text
python scripts/validate_v4_0_1_skills.py --write-manifest
```

并在提交信息里说明原因（更新哈希 + 更新测试）。
"""

from __future__ import annotations

import json

import pytest

from ._skill_lib import load_validator


@pytest.fixture(scope="module")
def validator():
    return load_validator()


def test_manifest_exists_with_expected_metadata(validator):
    payload = json.loads(validator.read_text(validator.MANIFEST_PATH))
    assert payload["product"] == "NovelForge"
    assert payload["version"] == "4.0.1"
    assert payload["skill_library_version"] == "novelforge-v4.0.1"
    assert payload["skill_schema_version"] == 1
    assert payload["status"] == "frozen-baseline"
    assert payload["hash_algorithm"] == "sha256"
    assert payload["skill_count"] == len(validator.skill_files())
    assert payload["module_count"] == len(validator.MODULES)


def test_manifest_hashes_match_disk(validator):
    validator.check_manifest()


def test_manifest_covers_root_and_module_readmes(validator):
    recorded = {row["path"] for row in
                json.loads(validator.read_text(validator.MANIFEST_PATH))["files"]}
    for name in ("README.md", "SKILL_CATALOG.md", "SOURCE_MAP.md", "DEPENDENCY_MAP.md",
                 "manifest.yaml"):
        assert f"skills/novelforge-v4.0.1/{name}" in recorded
    for path in validator.module_readmes():
        assert validator.rel(path) in recorded


def test_manifest_skill_ids_match_directories(validator):
    rows = json.loads(validator.read_text(validator.MANIFEST_PATH))["files"]
    for row in rows:
        if row["skill_id"]:
            assert validator.rel(validator.SKILL_ROOT / row["module"] /
                                 row["skill_id"].split(".")[-1] / "SKILL.md") == row["path"]


def test_dependency_map_exists(validator):
    text = validator.read_text(validator.SKILL_ROOT / "DEPENDENCY_MAP.md")
    assert "project.create-novel" in text
    assert "禁止的依赖" in text
