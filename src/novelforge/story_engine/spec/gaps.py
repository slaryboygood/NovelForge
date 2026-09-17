"""M3：NOVEL_SPEC 缺口识别（确定性规则，不调用 LLM）。"""

from __future__ import annotations

from .models import NovelSpec, SpecGap

GAP_RULES: tuple[tuple[str, str, str, str, str], ...] = (
    ("logline", "intent", "blocking", "没有一句话创意就无法编译 Planning IR",
     "用一句话写清主角、目标与阻力"),
    ("themes", "theme", "important", "没有主题就无法给出戏剧问题与价值冲突",
     "给 1-3 个主题词或一句价值冲突"),
    ("genre", "intent", "important", "题材影响读者预期与模板建议", "填写题材或从模板选择"),
    ("target_reader", "intent", "important", "没有目标读者就没有商业承诺的判据",
     "写清写给谁看"),
    ("commercial_promise", "intent", "important", "缺少承诺会让后续卷 / Arc 失去方向",
     "一句话说明每卷给读者什么"),
    ("reader_experience", "intent", "optional", "缺少阅读体验描述", "列出 2-4 个体验词"),
    ("tone", "intent", "optional", "基调会影响 Pacing 与语言风格", "给一个基调词"),
    ("pace_strategy", "intent", "optional", "节奏策略会影响 PacingPlan", "简述快慢安排"),
    ("characters_seed", "character", "blocking", "没有人物就写不了 CharacterPlan",
     "至少给主角一个 seed（seed_id + 目标 + 内在需求）"),
    ("world_seed", "world", "important", "没有世界规则会让冲突缺少约束",
     "给 1-3 条世界规则（标明 hard_rule / belief / rumor）"),
    ("constraints", "world", "optional", "缺少作者底线 / 禁忌", "列出不可触碰的设定"),
)


def find_spec_gaps(spec: NovelSpec) -> list[SpecGap]:
    """按固定顺序返回缺口；同一 field 只报一次。"""

    gaps: list[SpecGap] = []
    for field, domain, severity, why, suggestion in GAP_RULES:
        if _satisfied(spec, field):
            continue
        gaps.append(SpecGap(field=field, domain=domain, severity=severity, why=why,
                            suggestion=suggestion))
    gaps.extend(_character_gaps(spec))
    return gaps


def blocking_gaps(spec: NovelSpec) -> list[SpecGap]:
    return [item for item in find_spec_gaps(spec) if item.severity == "blocking"]


def _satisfied(spec: NovelSpec, field: str) -> bool:
    value = getattr(spec, field, None)
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return bool(value)
    if isinstance(value, int):
        return value > 0
    return value is not None


def _character_gaps(spec: NovelSpec) -> list[SpecGap]:
    gaps: list[SpecGap] = []
    for index, character in enumerate(spec.characters_seed):
        if not character.external_goal:
            gaps.append(SpecGap(
                field=f"characters_seed[{index}].external_goal", domain="character",
                severity="blocking", why="人物没有外在目标就没有行动理由",
                suggestion=f"给 {character.display_name or character.seed_id} 一个可失败的目标"))
        if not character.internal_need:
            gaps.append(SpecGap(
                field=f"characters_seed[{index}].internal_need", domain="character",
                severity="important", why="内在需求决定角色弧的终点",
                suggestion=f"给 {character.display_name or character.seed_id} 一个内在需求"))
    return gaps


__all__ = ["GAP_RULES", "blocking_gaps", "find_spec_gaps"]
