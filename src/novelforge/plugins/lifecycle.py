"""生命周期状态机（V4-09 §17–§18）：唯一 SSOT。"""

from __future__ import annotations

from typing import Mapping, Sequence

from .contracts import PLUGIN_STATUSES, PLUGIN_TRANSITIONS
from .errors import PluginError


def can_transition(current: str, target: str) -> bool:
    return str(target) in PLUGIN_TRANSITIONS.get(str(current), ())


def assert_transition(current: str, target: str) -> str:
    if str(current) not in PLUGIN_STATUSES:
        raise PluginError(f"未知插件状态：{current}",
                          details={"known": list(PLUGIN_STATUSES)})
    if not can_transition(current, target):
        raise PluginError(
            f"不允许的插件状态流转：{current} → {target}",
            details={"from": str(current), "to": str(target),
                     "allowed": list(PLUGIN_TRANSITIONS.get(str(current), ()))})
    return str(target)


def next_statuses(current: str) -> tuple[str, ...]:
    return tuple(PLUGIN_TRANSITIONS.get(str(current), ()))


def lifecycle_table() -> Mapping[str, Sequence[str]]:
    """公开的状态机表（供文档 / UI / 契约测试核对）。"""

    return {status: tuple(PLUGIN_TRANSITIONS.get(status, ())) for status in PLUGIN_STATUSES}


__all__ = ["assert_transition", "can_transition", "lifecycle_table", "next_statuses"]
