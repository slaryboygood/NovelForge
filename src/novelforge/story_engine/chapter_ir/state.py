"""S02：Typed State Registry（轻量、无外部依赖）。

world_state_change 只能引用 registry 中合法的一条迁移；
提前 / 未来 / 重复不可逆迁移都在这里被拦住，不再靠文本语义猜。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from pydantic import Field

from novelforge.models import StrictModel

from .models import ChapterStateTransition


@dataclass(frozen=True)
class StateMachine:
    state_key: str
    states: tuple[str, ...]
    irreversible_states: tuple[str, ...] = ()

    def index(self, state: str) -> int:
        try:
            return self.states.index(state)
        except ValueError:
            return -1

    def is_legal_edge(self, from_state: str, to_state: str) -> bool:
        left, right = self.index(from_state), self.index(to_state)
        return left >= 0 and right >= 0 and right >= left


@dataclass(frozen=True)
class TransitionBinding:
    """某条状态迁移的 canonical 绑定（transition-level，不是“整机属于哪一章”）。"""

    state_key: str
    to_state: str
    chapter_uuid: str
    display_number: int
    note: str = ""

    @property
    def key(self) -> tuple[str, str]:
        return (self.state_key, self.to_state)


class StateFinding(StrictModel):
    code: str
    state_key: str = ""
    transition_id: str = ""
    detail: str = Field(default="", max_length=300)


@dataclass
class TypedStateRegistry:
    machines: dict[str, StateMachine] = field(default_factory=dict)
    bindings: dict[tuple[str, str], TransitionBinding] = field(default_factory=dict)
    # 兼容保留：state_key → 该状态机最后一次不可逆推进的章节位置
    canonical_positions: dict[str, int] = field(default_factory=dict)

    def register(self, machine: StateMachine) -> None:
        self.machines[machine.state_key] = machine

    def bind(self, binding: TransitionBinding) -> None:
        self.bindings[binding.key] = binding
        if binding.to_state in (self.machines.get(binding.state_key).irreversible_states
                               if self.machines.get(binding.state_key) else ()):
            self.canonical_positions[binding.state_key] = binding.display_number

    def binding_for(self, state_key: str, to_state: str) -> TransitionBinding | None:
        return self.bindings.get((state_key, to_state))

    def machine(self, state_key: str) -> StateMachine | None:
        return self.machines.get(state_key)

    # ---- 校验 -------------------------------------------------------------
    def validate(self, transitions: Iterable[ChapterStateTransition], *,
                 chapter_position: int | None = None,
                 chapter_uuid: str = "") -> list[StateFinding]:
        findings: list[StateFinding] = []
        for transition in transitions:
            # 只有 assertion_mode == transition 才允许推动状态机
            if transition.assertion_mode != "transition":
                continue
            machine = self.machine(transition.state_key)
            if machine is None:
                findings.append(StateFinding(code="UNKNOWN_STATE_KEY",
                                             state_key=transition.state_key,
                                             transition_id=transition.transition_id,
                                             detail="state_key 不在 Typed State Registry 中"))
                continue
            if not machine.is_legal_edge(transition.from_state, transition.to_state):
                findings.append(StateFinding(
                    code="ILLEGAL_STATE_EDGE", state_key=transition.state_key,
                    transition_id=transition.transition_id,
                    detail=f"{transition.from_state} → {transition.to_state} 不是合法推进"))
            binding = self.binding_for(transition.state_key, transition.to_state)
            position = chapter_position if chapter_position is not None else transition.effective_at
            if binding is None or position is None:
                continue
            irreversible = (transition.transition_kind == "irreversible"
                            or transition.to_state in machine.irreversible_states
                            or transition.transition_kind in ("acquisition", "resolution"))
            if position < binding.display_number:
                findings.append(StateFinding(
                    code="PREMATURE_STATE_TRANSITION", state_key=transition.state_key,
                    transition_id=transition.transition_id,
                    detail=f"{transition.to_state} 的 canonical 绑定是 "
                           f"{binding.chapter_uuid or 'ch' + str(binding.display_number)}"
                           f"（ch{binding.display_number}），此处提前到 {position}"))
            elif irreversible and position > binding.display_number:
                findings.append(StateFinding(
                    code="REPEATED_IRREVERSIBLE_TRANSITION", state_key=transition.state_key,
                    transition_id=transition.transition_id,
                    detail=f"{transition.to_state} 已在 ch{binding.display_number} 发生，此处重复推进"))
        return findings

    def state_at(self, state_key: str, transitions: Iterable[ChapterStateTransition]) -> str:
        machine = self.machine(state_key)
        if machine is None:
            return ""
        current = machine.states[0]
        for transition in sorted(transitions, key=lambda item: item.effective_at or 0):
            if transition.state_key != state_key:
                continue
            if transition.from_state and transition.from_state != current:
                continue
            if machine.index(transition.to_state) >= 0:
                current = transition.to_state
        return current


def build_default_registry(canonical_positions: dict[str, int] | None = None) -> TypedStateRegistry:
    """Pilot 需要的 6 条状态机（可按实例调整 canonical positions）。"""

    registry = TypedStateRegistry(canonical_positions=dict(canonical_positions or
                                                           DEFAULT_CANONICAL_POSITIONS))
    registry.register(StateMachine(
        "salt_route_control",
        ("uncontrolled", "contested", "controlled_by_rust_settlement")))
    registry.register(StateMachine(
        "zero_layer_access",
        ("closed", "first_opened", "operational", "emergency_locked", "inaccessible",
         "permanently_sealed"),
        irreversible_states=("permanently_sealed",)))
    registry.register(StateMachine(
        "common_rules_status",
        ("idea", "draft", "consulted", "voted", "revised", "approved", "signed", "enacted"),
        irreversible_states=("signed", "enacted")))
    registry.register(StateMachine(
        "dog_departure_status",
        ("present", "considering", "voluntarily_departed", "absent_waiting",
         "voluntarily_returned")))
    registry.register(StateMachine(
        "archive_publication_level",
        ("unpublished", "partial_release", "second_archive_verified",
         "third_archive_pending", "third_archive_released",
         "cross_validation_established", "full_public_truth")))
    registry.register(StateMachine(
        "gray_wall_observation_status",
        ("unobserved", "recorded_historically", "observed_on_page", "mapped"),
        irreversible_states=("observed_on_page",)))
    for binding in DEFAULT_TRANSITION_BINDINGS:
        registry.bind(binding)
    return registry


# Pilot 依据 WASTELAND_001 当前 Canon 约定的 canonical 位置（章节号只作调度，不作 identity）
DEFAULT_CANONICAL_POSITIONS: dict[str, int] = {
    "salt_route_control": 133,
    "zero_layer_access": 379,
    "common_rules_status": 526,
    "archive_publication_level": 504,
    "gray_wall_observation_status": 271,
}


# transition-level canonical 绑定（以 WASTELAND_001 当前 Canon 为准；只绑定有真实证据的迁移）
DEFAULT_TRANSITION_BINDINGS: tuple[TransitionBinding, ...] = (
    TransitionBinding("salt_route_control", "contested", "uuid_wl_ch107", 107,
                      "盐路伏击后控制权进入争夺"),
    TransitionBinding("salt_route_control", "controlled_by_rust_settlement",
                      "uuid_wl_ch133", 133, "按趟结算谈成"),
    TransitionBinding("zero_layer_access", "first_opened", "uuid_wl_ch325", 325,
                      "第七次尝试第一次打开"),
    TransitionBinding("zero_layer_access", "emergency_locked", "uuid_wl_ch350", 350,
                      "交火中紧急锁闭"),
    TransitionBinding("zero_layer_access", "permanently_sealed", "uuid_wl_ch379", 379,
                      "爆破主通道永久封死"),
    TransitionBinding("common_rules_status", "consulted", "uuid_wl_ch515", 515,
                      "草案带到边缘聚落征求意见"),
    TransitionBinding("common_rules_status", "voted", "uuid_wl_ch526", 526,
                      "第一轮表决通过程序"),
    TransitionBinding("common_rules_status", "signed", "uuid_wl_ch559", 559,
                      "并列署名完成正式签署"),
    TransitionBinding("dog_departure_status", "considering", "uuid_wl_ch389", 389,
                      "第一次同类招揽压力"),
    TransitionBinding("dog_departure_status", "voluntarily_departed", "uuid_wl_ch436", 436,
                      "阿灰自主离开"),
    TransitionBinding("dog_departure_status", "absent_waiting", "uuid_wl_ch437", 437,
                      "离开后的第一夜"),
    TransitionBinding("dog_departure_status", "voluntarily_returned", "uuid_wl_ch438", 438,
                      "第三日自主返回"),
    TransitionBinding("archive_publication_level", "partial_release", "uuid_wl_ch449", 449,
                      "前一份档案公开后的回声"),
    TransitionBinding("archive_publication_level", "second_archive_verified",
                      "uuid_wl_ch502", 502, "第二份档案与验证者名单"),
    TransitionBinding("archive_publication_level", "third_archive_released",
                      "uuid_wl_ch504", 504, "第三份档案公开"),
    TransitionBinding("gray_wall_observation_status", "observed_on_page",
                      "uuid_wl_ch271", 271, "现场实测灰墙整体东移"),
)


def default_registry() -> TypedStateRegistry:
    return build_default_registry()
