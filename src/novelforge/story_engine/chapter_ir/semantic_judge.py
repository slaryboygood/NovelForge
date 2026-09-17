"""S05：LLM Semantic Judge（optional，ambiguous reviewer only）。

规则：

- 只有 deterministic validator 给出 AMBIGUOUS 时才调用；
- 输入只有 IR + candidate field，不给生成时的 reasoning；
- 输出严格 schema；判词不能创建 Canon、不能执行 state transition、不能覆盖 happened fact；
- 无 LLM 时返回 NullJudge（系统仍可运行）。
"""

from __future__ import annotations

from typing import Literal, Protocol

from pydantic import Field

from novelforge.models import StrictModel

from .models import ChapterSemanticIR

Verdict = Literal["aligned", "mismatch", "ambiguous"]


class JudgeVerdict(StrictModel):
    chapter_uuid: str = Field(min_length=3, max_length=128)
    field_name: str = Field(min_length=2, max_length=64)
    verdict: Verdict = "ambiguous"
    confidence: float = Field(default=0.0, ge=0, le=1)
    reason: str = Field(default="", max_length=300)
    evidence_event_ids: list[str] = Field(default_factory=list)
    evidence_effect_ids: list[str] = Field(default_factory=list)


class SemanticJudge(Protocol):  # pragma: no cover - 接口
    def review(self, ir: ChapterSemanticIR, field_name: str,
               candidate_text: str) -> JudgeVerdict: ...


class NullJudge:
    """默认实现：无 LLM，一切保持 ambiguous（由 deterministic gate 决定）。"""

    enabled = False

    def review(self, ir: ChapterSemanticIR, field_name: str,
               candidate_text: str) -> JudgeVerdict:
        return JudgeVerdict(chapter_uuid=ir.chapter_uuid, field_name=field_name,
                            verdict="ambiguous", confidence=0.0,
                            reason="semantic judge disabled")


class CallableJudge:
    """把外部模型包装成 judge；输出仍必须通过 JudgeVerdict 严格校验。"""

    enabled = True

    def __init__(self, callable_) -> None:
        self._callable = callable_

    def review(self, ir: ChapterSemanticIR, field_name: str,
               candidate_text: str) -> JudgeVerdict:
        payload = self._callable(ir, field_name, candidate_text)
        return JudgeVerdict.model_validate(payload)


def review_ambiguous(judge: SemanticJudge | None, ir: ChapterSemanticIR, field_name: str,
                     candidate_text: str) -> JudgeVerdict:
    """Gate 层调用点：judge 只提供结构化 verdict，persist 决定仍由 deterministic gate 做出。"""

    judge = judge or NullJudge()
    return judge.review(ir, field_name, candidate_text)
