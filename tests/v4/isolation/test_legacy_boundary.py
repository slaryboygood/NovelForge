"""永久守卫：legacy 边界（V4-01 → post-release cleanup）。

历史：V4-01 用一个 `novelforge.legacy` manifest + adapter 记录「哪些 frozen 能力
仍原地保留」，并守卫「新的业务路径不得 import frozen 历史模块」。

post-release cleanup 之后，V2/V3 Story Builder 后端与全部 frozen 历史模块
（historical_ir / reconstruction / historical_adoption / phase_snapshot /
milestone_acceptance / repair 之外的 chapter IR 全栈 / planning / spec …）都已删除
（历史证据由 Git + `docs/FROZEN_EVIDENCE_MANIFEST.json` 承担），
因此 `novelforge.legacy` 本身没有 runtime consumer → 一并退休。

保留的永久不变式（断言强度不降低）：

```text
1. legacy 包不存在于 current tree；
2. 新的业务路径不得 import 任何 frozen / 历史模块；
3. 已删除的废弃资产不会作为路径出现在产品模块里。
```
"""

from __future__ import annotations

import importlib

import pytest

from _guard_utils import ROOT, imports_matching, python_files

FROZEN_HISTORICAL_PREFIXES = (
    "novelforge.story_engine.repair",
    "novelforge.story_engine.historical_ir",
    "novelforge.story_engine.reconstruction",
    "novelforge.story_engine.historical_adoption",
    "novelforge.story_engine.phase_snapshot",
    "novelforge.story_engine.milestone_acceptance",
    "novelforge.story_engine.m11_",
    "novelforge.story_engine.m12_",
    "novelforge.story_engine.m13_",
    "novelforge.story_engine.m14_",
    "novelforge.story_engine.m15_",
    "novelforge.story_engine.m16_",
    "novelforge.story_engine.m17_",
    "novelforge.story_engine.m18_",
    "novelforge.story_engine.planning",
    "novelforge.story_engine.spec",
    "novelforge.story_builder",
    "novelforge.legacy",
)


def test_retired_legacy_packages_are_gone() -> None:
    assert not (ROOT / "src" / "novelforge" / "legacy").exists()
    assert not (ROOT / "src" / "novelforge" / "story_builder").exists()
    for module_name in ("novelforge.legacy", "novelforge.story_builder",
                        "novelforge.story_engine.historical_ir",
                        "novelforge.story_engine.planning"):
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module(module_name)


def test_new_write_paths_do_not_import_frozen_history() -> None:
    offenders: list[str] = []
    for path in python_files("application", "persistence", "core"):
        for name, line in imports_matching(path, FROZEN_HISTORICAL_PREFIXES):
            offenders.append(f"{path.relative_to(ROOT)}:{line} → {name}")
    assert offenders == [], (
        "新的业务路径不得 import frozen / 已退休的历史模块：\n"
        + "\n".join(offenders))


def test_frozen_repair_implementation_is_the_only_survivor() -> None:
    """frozen Repair Contract 实现（`story_engine/repair.py`）仍然原地保留。"""

    path = ROOT / "src" / "novelforge" / "story_engine" / "repair.py"
    assert path.is_file(), "REPAIR_GATE_V1 的实现必须保留（AGENTS.md §16.1/§34）"
    source = path.read_text(encoding="utf-8")
    assert "REPAIR_CONTRACT" in source or "repair" in source
