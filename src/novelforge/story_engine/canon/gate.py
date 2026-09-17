"""C03：Planner / LLM 输出的严格 Schema Gate。

职责边界：Pydantic 只保证**结构正确**；事实正确交给 Canon Validator，时序/因果交给 Graph。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from .schemas import CanonProposalBundle, ChapterPlan


@dataclass
class SchemaGateError(Exception):
    code: str
    issues: list[str] = field(default_factory=list)

    def __str__(self) -> str:  # pragma: no cover - 便于调试
        return f"{self.code}: {'; '.join(self.issues[:5])}"

    def repair_prompt(self) -> str:
        """把校验问题交回模型修复（不自动把错误数据放进系统）。"""

        return ("上一版 JSON 未通过结构校验，请修正后重新输出完整 JSON：\n- "
                + "\n- ".join(self.issues[:20]))


def _issues_from(error: ValidationError) -> list[str]:
    issues: list[str] = []
    for item in error.errors():
        location = ".".join(str(part) for part in item.get("loc", ()))
        issues.append(f"{location}: {item.get('msg', '')}")
    return issues


def validate_chapter_plan(raw: dict[str, Any]) -> ChapterPlan:
    """严格模式：禁止 str→list、数字字符串→int 之类的隐式 coercion。"""

    try:
        return ChapterPlan.model_validate(raw, strict=True)
    except ValidationError as error:
        raise SchemaGateError("CHAPTER_PLAN_SCHEMA_INVALID", _issues_from(error)) from error


def validate_bundle(raw: dict[str, Any]) -> CanonProposalBundle:
    try:
        return CanonProposalBundle.model_validate(raw, strict=True)
    except ValidationError as error:
        raise SchemaGateError("CANON_BUNDLE_SCHEMA_INVALID", _issues_from(error)) from error


def validate_chapters(raw_chapters: list[dict[str, Any]]) -> list[ChapterPlan]:
    plans: list[ChapterPlan] = []
    issues: list[str] = []
    for index, raw in enumerate(raw_chapters, start=1):
        try:
            plans.append(validate_chapter_plan(raw))
        except SchemaGateError as error:
            issues.extend(f"第{index}章 {issue}" for issue in error.issues)
    if issues:
        raise SchemaGateError("CHAPTERS_SCHEMA_INVALID", issues)
    return plans
