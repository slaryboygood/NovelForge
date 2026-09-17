"""M2A：Story Planning IR 严格 Schema Gate。

和 Canon / Chapter IR 的 gate 同一原则：结构错误直接拒绝，不做隐式 coercion，
把问题列表交回调用方（M2B 的 Planner / LLM）去修。
"""

from __future__ import annotations

from typing import Any

from pydantic import Field, ValidationError

from novelforge.models import StrictModel

from .enums import PLANNING_SCHEMA_VERSION
from .models import StoryPlanningIR

PLANNING_SCHEMA_ID = "novelforge.story_planning_ir.v1"


class PlanningGateError(Exception):
    def __init__(self, code: str, issues: list[str]) -> None:
        self.code = code
        self.issues = issues
        super().__init__(f"{code}: {'; '.join(issues[:5])}")

    def repair_prompt(self) -> str:
        return ("上一版 Planning IR JSON 未通过结构校验，请修正后重新输出完整 JSON：\n- "
                + "\n- ".join(self.issues[:20]))


class PlanningBundle(StrictModel):
    """多份 planning 文档（例如不同 branch）一起过 gate。"""

    novel_id: str = Field(min_length=1, max_length=96)
    schema_version: int = PLANNING_SCHEMA_VERSION
    plans: list[StoryPlanningIR] = Field(default_factory=list)


def _issues_from(error: ValidationError) -> list[str]:
    issues: list[str] = []
    for item in error.errors():
        location = ".".join(str(part) for part in item.get("loc", ()))
        issues.append(f"{location}: {item.get('msg', '')}")
    return issues


def validate_planning_ir(raw: dict[str, Any]) -> StoryPlanningIR:
    """strict 模式：禁止 str→list、数字字符串→int 之类的隐式转换。"""

    try:
        return StoryPlanningIR.model_validate(raw, strict=True)
    except ValidationError as error:
        raise PlanningGateError("PLANNING_IR_SCHEMA_INVALID", _issues_from(error)) from error


def validate_planning_bundle(raw: dict[str, Any]) -> PlanningBundle:
    try:
        return PlanningBundle.model_validate(raw, strict=True)
    except ValidationError as error:
        raise PlanningGateError("PLANNING_BUNDLE_SCHEMA_INVALID", _issues_from(error)) from error


def planning_json_schema() -> dict[str, Any]:
    """供编辑器 / 前端 / LLM 输出约束使用的 JSON Schema。"""

    schema = StoryPlanningIR.model_json_schema()
    schema["$id"] = PLANNING_SCHEMA_ID
    schema["x-schema-version"] = PLANNING_SCHEMA_VERSION
    return schema


__all__ = [
    "PLANNING_SCHEMA_ID",
    "PlanningBundle",
    "PlanningGateError",
    "planning_json_schema",
    "validate_planning_bundle",
    "validate_planning_ir",
]
