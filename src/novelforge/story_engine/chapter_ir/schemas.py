"""S01：IR 严格 Gate（planner / legacy migration 输出都必须过这一层）。

与 Canon 的 gate 相同原则：结构错误直接拒绝，不自动 coercion。
"""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import Field, ValidationError

from novelforge.models import StrictModel

from .models import ChapterSemanticIR


class IRGateError(Exception):
    def __init__(self, code: str, issues: list[str]) -> None:
        self.code = code
        self.issues = issues
        super().__init__(f"{code}: {'; '.join(issues[:5])}")

    def repair_prompt(self) -> str:
        return ("上一版 IR JSON 未通过结构校验，请修正后重新输出完整 JSON：\n- "
                + "\n- ".join(self.issues[:20]))


class ChapterIRBundle(StrictModel):
    novel_id: str = Field(min_length=1, max_length=96)
    schema_version: int = 1
    chapters: list[ChapterSemanticIR] = Field(default_factory=list)


def validate_ir(raw: dict[str, Any]) -> ChapterSemanticIR:
    try:
        return ChapterSemanticIR.model_validate(raw, strict=True)
    except ValidationError as error:
        issues = [f"{'.'.join(str(part) for part in item.get('loc', ()))}: "
                  f"{item.get('msg', '')}" for item in error.errors()]
        raise IRGateError("CHAPTER_IR_SCHEMA_INVALID", issues) from error


def validate_ir_bundle(raw: dict[str, Any]) -> ChapterIRBundle:
    try:
        return ChapterIRBundle.model_validate(raw, strict=True)
    except ValidationError as error:
        issues = [f"{'.'.join(str(part) for part in item.get('loc', ()))}: "
                  f"{item.get('msg', '')}" for item in error.errors()]
        raise IRGateError("CHAPTER_IR_BUNDLE_SCHEMA_INVALID", issues) from error
