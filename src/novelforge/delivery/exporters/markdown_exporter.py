"""Markdown exporter（V4-07 §29–§30、§56）：人类阅读格式。

只输出作者语言的故事内容（visible fields）；**不**输出 request_id / digest /
provider / revision bookkeeping 等内部 metadata。
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence

from . import ExporterRegistry, ExporterSpec

EXPORTER_ID = "delivery.markdown.v1"
EXPORTER_VERSION = 1

#: 分区顺序（与 compiler.NODE_TYPE_ORDER 对齐）
SECTION_TITLES: tuple[tuple[str, str], ...] = (
    ("premise", "故事前提"),
    ("theme", "主题"),
    ("world", "世界"),
    ("character", "人物"),
    ("character_arc", "人物弧"),
    ("story_arc", "故事结构"),
    ("structural_unit", "单元结构"),
    ("chapter", "章节"),
    ("scene", "场景"),
    ("setup", "伏笔"),
    ("payoff", "回收"),
    ("causal_link", "因果关系"),
)

FIELD_LABELS: Mapping[str, str] = {
    "premise": "前提", "central_conflict": "核心冲突", "protagonist_goal": "主角目标",
    "stakes": "代价", "dramatic_question": "戏剧问题", "story_promise": "故事承诺",
    "genre": "题材", "tone": "基调", "constraints": "约束",
    "theme": "主题", "statement": "主张", "counter_theme": "反向主题", "motifs": "母题",
    "rules": "规则", "locations": "地点", "factions": "势力", "resources": "资源",
    "technology_or_magic": "技术与超自然", "social_constraints": "社会限制",
    "conflict_sources": "冲突来源", "story_relevant_history": "相关历史",
    "name": "姓名", "role": "身份", "kind": "类型", "goal": "目标",
    "motivation": "动机", "need": "需要", "fear": "恐惧", "misbelief": "错误信念",
    "strength": "长处", "flaw": "缺陷", "conflict_source": "冲突来源",
    "relationships": "关系", "story_function": "叙事功能",
    "start_state": "起点状态", "internal_conflict": "内在冲突",
    "external_pressure": "外部压力", "key_turns": "关键转折",
    "midpoint_change": "中点变化", "crisis": "危机", "climax_choice": "高潮选择",
    "end_state": "终点状态", "initial_state": "初始状态",
    "inciting_incident": "触发事件", "progressive_complications": "递进复杂化",
    "major_turns": "主要转折", "midpoint": "中点", "climax": "高潮",
    "resolution": "收束", "unit_type": "单元类型", "title": "标题",
    "conflict": "冲突", "turn": "转折", "outcome": "结果", "hook": "钩子",
    "location": "地点", "scene_purpose": "场景目的", "time": "时间",
    "escalation": "升级", "information_reveal": "信息释放",
    "character_change": "人物变化", "relationship_change": "关系变化",
    "next_hook": "下一个钩子", "content": "内容", "expected_payoff": "预期回收",
    "status": "状态", "result": "回收结果", "relation": "关系", "reason": "原因",
}

#: §30：Markdown 里绝不允许出现的内部字段名
FORBIDDEN_TOKENS: tuple[str, ...] = (
    "request_id", "context_digest", "generation_contract", "provenance",
    "provider", "cache_key", "export_id", "sqlite", "wtr_", "node_id",
    "revision", "truth_layer", "(player)", "(npc)",
)


def _fmt(value: Any) -> str:
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, Mapping):
                parts.append("；".join(f"{key}：{_fmt(val)}"
                                       for key, val in item.items()))
            else:
                parts.append(str(item))
        return "、".join(part for part in parts if part)
    if isinstance(value, Mapping):
        return "；".join(f"{key}：{_fmt(val)}" for key, val in value.items())
    return str(value)


def _node_title(node: Mapping[str, Any]) -> str:
    visible = dict(node.get("visible") or {})
    for key in ("title", "name", "premise", "theme", "scene_purpose", "content",
                "result", "goal", "statement", "relation"):
        value = visible.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    # §30：绝不回落到内部 id（node_id 属于 internal metadata）
    return "（无标题条目）"


def render(context: Mapping[str, Any]) -> str:
    blueprint = dict(context.get("blueprint") or {})
    nodes = [dict(row) for row in (blueprint.get("nodes") or [])]
    title = str(context.get("title") or context.get("novel_id") or "Story Blueprint")
    lines: list[str] = [f"# {title} 故事蓝图", ""]
    for node_type, section_title in SECTION_TITLES:
        rows = [row for row in nodes if str(row.get("node_type")) == node_type]
        if not rows:
            continue
        lines.append(f"## {section_title}")
        lines.append("")
        for row in rows:
            visible = dict(row.get("visible") or {})
            heading = _node_title(row)
            lines.append(f"### {heading}")
            lines.append("")
            for field, value in visible.items():
                if field in ("title", "name", "premise", "theme", "result") and \
                        str(value).strip() == heading:
                    continue
                if value in ("", [], {}, None):
                    continue
                label = FIELD_LABELS.get(field, field)
                lines.append(f"- {label}：{_fmt(value)}")
            lines.append("")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def export(context: Mapping[str, Any]) -> bytes:
    return render(context).encode("utf-8")


def register(registry: ExporterRegistry) -> ExporterSpec:
    return registry.register(ExporterSpec(
        format="markdown", exporter_id=EXPORTER_ID, version=EXPORTER_VERSION,
        mime_type="text/markdown", extension="md", text=True,
        description="human-readable Story Blueprint document"), export)


__all__ = ["EXPORTER_ID", "EXPORTER_VERSION", "FIELD_LABELS", "FORBIDDEN_TOKENS",
           "SECTION_TITLES", "export", "register", "render"]
