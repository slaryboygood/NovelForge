"""Frozen module inventory（V4-01）。

把 V4-00 分类中的 `COMPATIBILITY_ONLY` 模块登记为**机器可读清单**，用于：

* 说明「哪些 frozen 能力仍然原地保留」；
* 守卫测试：产品写路径不得 import 这些模块；
* 后续阶段决定「何时可以删除 / 迁移」。

注意：这里登记的是**代码模块**，不是被删除的数据资产。
`novel/final/**` 与 `workspace/wasteland_001_exports/**` 已在 V4-01 删除，不在此列。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FrozenModule:
    module_id: str
    path: str
    capability: str
    status: str            # frozen_read_only | compatibility_adapter | historical_milestone
    used_by: tuple[str, ...]
    removal_condition: str


FROZEN_MODULES: tuple[FrozenModule, ...] = (
    FrozenModule(
        module_id="story_engine.repair",
        path="src/novelforge/story_engine/repair.py",
        capability="M11 内容修复（frozen Repair Contract / Gate）",
        status="frozen_read_only",
        used_by=(),
        removal_condition=("frozen contract / gate 被 V4 quality-repair 完全取代，"
                           "且作者确认历史修复证据不再需要引用"),
    ),
    FrozenModule(
        module_id="story_engine.historical_ir",
        path="src/novelforge/story_engine/historical_ir.py",
        capability="570 章 Historical Chapter IR foundation（数据已于 V4-01 删除）",
        status="frozen_read_only",
        used_by=(),
        removal_condition="无产品调用点且作者确认历史 IR 能力不再需要时删除",
    ),
    FrozenModule(
        module_id="story_engine.reconstruction",
        path="src/novelforge/story_engine/reconstruction.py",
        capability="M10 top-down reconstruction（derived artifacts）",
        status="frozen_read_only",
        used_by=(),
        removal_condition="同 historical_ir：无调用点 + 作者确认",
    ),
    FrozenModule(
        module_id="story_engine.historical_adoption",
        path="src/novelforge/story_engine/historical_adoption.py",
        capability="P15g 历史 foundation 接入 M11 repair",
        status="frozen_read_only",
        used_by=(),
        removal_condition="同 repair：随 M11 历史流程整体退役",
    ),
    FrozenModule(
        module_id="story_engine.m11_*",
        path="src/novelforge/story_engine/m11_*.py（18 个文件）",
        capability="M11 production runs / blocker / content design / closeout",
        status="historical_milestone",
        used_by=(),
        removal_condition="V2 里程碑记录不再需要时可整体退役（当前仅保留源码）",
    ),
    FrozenModule(
        module_id="story_engine.m12_*..m18_*",
        path="src/novelforge/story_engine/m1{2..8}_*.py（7 个文件）",
        capability="M12–M18 milestone acceptance / readiness",
        status="historical_milestone",
        used_by=(),
        removal_condition="同上；V4 里程碑验收改用新机制后评估",
    ),
    FrozenModule(
        module_id="story_engine.phase_snapshot",
        path="src/novelforge/story_engine/phase_snapshot.py",
        capability="phase snapshot 机制（write-once + digest manifest）",
        status="compatibility_adapter",
        used_by=("story_engine.milestone_acceptance",),
        removal_condition="V4 验收机制落地后，机制本身保留、V2 语义退役",
    ),
    FrozenModule(
        module_id="story_builder.adventures",
        path="src/novelforge/story_builder/adventures.py",
        capability="旧旅程存档只读兼容（rules_version 1 / 2）",
        status="compatibility_adapter",
        used_by=("api.story_builder_routes（branch / adventure 路由）",),
        removal_condition="作者确认无旧存档需要打开时删除",
    ),
    FrozenModule(
        module_id="story_engine.writer",
        path="src/novelforge/story_engine/writer.py",
        capability="正文 Writer 边界 + 确定性降级文本（preview 层）",
        status="compatibility_adapter",
        used_by=("story_builder.writer_integration",),
        removal_condition="Blueprint Editor（V4-06）落地后，正文预览能力由插件承担",
    ),
)


def frozen_module(module_id: str) -> FrozenModule | None:
    for item in FROZEN_MODULES:
        if item.module_id == module_id:
            return item
    return None


def frozen_module_ids() -> tuple[str, ...]:
    return tuple(item.module_id for item in FROZEN_MODULES)


def frozen_module_paths() -> tuple[str, ...]:
    return tuple(item.path for item in FROZEN_MODULES)


__all__ = [
    "FROZEN_MODULES", "FrozenModule", "frozen_module", "frozen_module_ids",
    "frozen_module_paths",
]

