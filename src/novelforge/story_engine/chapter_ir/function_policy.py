"""S10：ChapterFunctionPolicy —— 章节功能决定 required / optional / N/A。

规则来源：不同功能章节对 decision / turn / payoff / world_state / information / cost / loss
的要求不同；不能用固定模板判定所有章节。

功能判定只看 evidence（IR + legacy 字段），不为了减少 findings 随便降级成 setup。
"""

from __future__ import annotations

import re
from typing import Literal, Mapping

from pydantic import Field

from novelforge.models import StrictModel

from .models import ChapterSemanticIR

ChapterFunction = Literal["setup", "exploration", "investigation", "negotiation", "conflict",
                          "combat", "reveal", "relationship", "progression", "aftermath",
                          "transition", "climax", "resolution"]
Requirement = Literal["required", "optional", "not_applicable"]
TurnScale = Literal["major_turn", "micro_turn", "not_applicable"]

FUNCTIONS: tuple[str, ...] = ("setup", "exploration", "investigation", "negotiation", "conflict",
                              "combat", "reveal", "relationship", "progression", "aftermath",
                              "transition", "climax", "resolution")

FUNCTION_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("climax", ("撤离", "封死", "决战", "最后一战", "撤离", "了断", "终局", "破局", "反攻",
                "永久封", "落幕")),
    ("resolution", ("清算", "裁定", "签署", "生效", "正式成立", "完结", "归位")),
    ("combat", ("交火", "伏击", "扑咬", "突围", "开火", "厮杀", "追兵", "袭击")),
    ("conflict", ("对峙", "翻脸", "撕破", "逼问", "冲突", "威胁", "拒绝", "僵住")),
    ("negotiation", ("谈判", "条款", "条件", "议价", "交换", "按趟", "分成", "署名顺序")),
    ("investigation", ("查", "核对", "比对", "证据", "线索", "审", "盘问", "档案", "名册")),
    ("reveal", ("发现", "揭示", "真相", "看清", "证实", "亮出", "解码")),
    ("relationship", ("关系", "信任", "和解", "道歉", "陪", "分别", "留门", "选择回来")),
    ("progression", ("升级", "突破", "掌握", "学会", "进阶", "拿到权限", "觉醒")),
    ("aftermath", ("余波", "之后", "清点", "养伤", "隔离", "复盘", "封存")),
    ("transition", ("转移", "启程", "入盆", "路标", "改道", "交接")),
    ("exploration", ("探索", "探索", "深入", "侦察", "测绘", "开荒", "探路", "禁区", "废墟",
                     "通道")),
    ("setup", ("准备", "铺", "安顿", "搭", "初见", "日常", "开场")),
)

# function → 每个字段的要求
FUNCTION_REQUIREMENTS: dict[str, dict[str, str]] = {
    "setup": {"decision": "optional", "turn": "micro_turn", "payoff": "optional",
              "world_state_change": "not_applicable", "information_release": "optional",
              "cost": "optional", "loss": "optional"},
    "exploration": {"decision": "optional", "turn": "micro_turn", "payoff": "optional",
                    "world_state_change": "optional", "information_release": "required",
                    "cost": "optional", "loss": "optional"},
    "investigation": {"decision": "optional", "turn": "micro_turn", "payoff": "required",
                      "world_state_change": "optional", "information_release": "required",
                      "cost": "optional", "loss": "optional"},
    "negotiation": {"decision": "required", "turn": "major_turn", "payoff": "required",
                    "world_state_change": "optional", "information_release": "optional",
                    "cost": "required", "loss": "optional"},
    "conflict": {"decision": "required", "turn": "major_turn", "payoff": "required",
                 "world_state_change": "optional", "information_release": "optional",
                 "cost": "required", "loss": "optional"},
    "combat": {"decision": "optional", "turn": "micro_turn", "payoff": "required",
               "world_state_change": "optional", "information_release": "optional",
               "cost": "required", "loss": "required"},
    "reveal": {"decision": "optional", "turn": "major_turn", "payoff": "required",
               "world_state_change": "optional", "information_release": "required",
               "cost": "optional", "loss": "optional"},
    "relationship": {"decision": "optional", "turn": "micro_turn", "payoff": "required",
                     "world_state_change": "not_applicable", "information_release": "optional",
                     "cost": "optional", "loss": "optional"},
    "progression": {"decision": "optional", "turn": "major_turn", "payoff": "required",
                    "world_state_change": "optional", "information_release": "optional",
                    "cost": "required", "loss": "optional"},
    "aftermath": {"decision": "optional", "turn": "not_applicable", "payoff": "optional",
                  "world_state_change": "not_applicable", "information_release": "optional",
                  "cost": "optional", "loss": "optional"},
    "transition": {"decision": "optional", "turn": "micro_turn", "payoff": "optional",
                   "world_state_change": "optional", "information_release": "optional",
                   "cost": "optional", "loss": "optional"},
    "climax": {"decision": "required", "turn": "major_turn", "payoff": "required",
               "world_state_change": "optional", "information_release": "optional",
               "cost": "required", "loss": "optional"},
    "resolution": {"decision": "optional", "turn": "major_turn", "payoff": "required",
                   "world_state_change": "required", "information_release": "optional",
                   "cost": "optional", "loss": "optional"},
}


class FunctionFinding(StrictModel):
    chapter_function: ChapterFunction = "setup"
    decision: Requirement = "optional"
    turn: TurnScale = "optional"
    payoff: Requirement = "optional"
    world_state_change: Requirement = "optional"
    information_release: Requirement = "optional"
    cost: Requirement = "optional"
    loss: Requirement = "optional"
    evidence: str = Field(default="", max_length=200)
    downgraded_forbidden: bool = False


class ChapterFunctionPolicy:
    """根据 evidence 判定章节功能，并给出字段要求。"""

    def classify(self, ir: ChapterSemanticIR,
                 chapter: Mapping[str, object] | None = None) -> FunctionFinding:
        chapter = dict(chapter or {})
        text = " ".join([str(chapter.get("goal") or ""),
                         *[str(item) for item in (chapter.get("events") or [])],
                         str(chapter.get("turn") or ""), str(chapter.get("payoff") or ""),
                         str(chapter.get("world_state_change") or "")])
        scored: list[tuple[int, str, str]] = []
        for function, keywords in FUNCTION_RULES:
            hits = [keyword for keyword in keywords if keyword in text]
            if hits:
                scored.append((len(hits), function, hits[0]))
        if not scored:
            function, evidence = "setup", "无强功能关键词"
        else:
            scored.sort(key=lambda row: (-row[0], FUNCTIONS.index(row[1])))
            function, evidence = scored[0][1], scored[0][2]
        requirements = FUNCTION_REQUIREMENTS[function]
        # transition / climax 必须真的存在状态或战斗证据，避免无理由降级
        if function in ("climax", "resolution") and not (
                ir.state_transitions or any(item.is_narrative_pivot for item in ir.effects)):
            function = "conflict" if any(item.effect_type == "combat" for item in ir.effects) \
                else "aftermath"
            requirements = FUNCTION_REQUIREMENTS[function]
            evidence = f"{evidence}（降级：无 state/pivot 证据）"
        return FunctionFinding(
            chapter_function=function, decision=requirements["decision"],
            turn=requirements["turn"], payoff=requirements["payoff"],
            world_state_change=requirements["world_state_change"],
            information_release=requirements["information_release"],
            cost=requirements["cost"], loss=requirements["loss"],
            evidence=evidence,
            downgraded_forbidden=(function == "setup" and not scored))
