"""内部标识 → 作者语言 的唯一展示层映射（引擎生成 / V3 投影 / 导出 / 错误文案共用）。

为什么需要这一层：

引擎内部用稳定 id 表达实体（行动 `act_*`、事件 `ev_*`、地点 `start_place`、
角色 `protagonist` / `npc_1`、资源 `favors`、知识线索 `core_record`…）。这些 id
是 Domain 的正确表示，但**不是**作者可见内容。V3 验收发现同一份数据在不同的
位置一半被翻译、一半原样透出（`favors` 在候选卡里是「人情」、在错误提示里是
`favors`）。

因此约定：

```text
Domain 保留 id  →  展示层（本模块）统一翻译  →  UI / 导出 / 错误文案
```

规则：

* 只翻译**真实存在**的实体：名称来自内容包 / StoryState，不靠猜、不编造；
* 查不到名称时退化为可读描述（例如「未知地点」），绝不把原始 id 交给作者；
* 结果是纯函数：同样的输入得到同样的输出，便于投影与导出交叉验证。
"""

from __future__ import annotations

from typing import Any, Mapping

# 引擎 / 内容包里的资源 key → 作者语言（资源名由内容包定义，这里统一展示名）。
RESOURCE_LABEL: dict[str, str] = {
    "supplies": "补给",
    "favors": "人情",
    "water": "饮水",
    "salvage": "可用材料",
    "echo_shard": "回响碎片",
}

# 关系 / 世界数值维度 key → 作者语言。
TRACK_LABEL: dict[str, str] = {
    "trust": "信任",
    "affection": "亲近",
    "respect": "尊重",
    "fear": "忌惮",
    "debt": "亏欠",
    "hostility": "敌意",
    "dependency": "依赖",
    "influence": "影响力",
    "danger": "危险度",
}

# 引擎按内容包生成的知识线索 id（不是作者命名的故事元素，没有标题可查）。
KNOWLEDGE_LABEL: dict[str, str] = {
    "core_record": "被抹去的那条记录",
}

# 引擎身份 key → 作者语言。
IDENTITY_LABEL: dict[str, str] = {
    "acting_permit": "仍在有效期内的凭证",
}

# 引擎固定保留 id → 作者语言（内容包里通常同时有真实名字，优先用真实名字）。
SYSTEM_LABEL: dict[str, str] = {
    "protagonist": "主角",
    "start_place": "起点场所",
    "work_place": "工作场所",
    "hidden_place": "隐藏节点",
}

# 条件 op / 行动类别 → 作者语言（投影与错误文案共用，避免两套说法）。
ACTION_KIND_LABEL: dict[str, str] = {
    "move": "移动",
    "investigate": "调查",
    "negotiate": "交涉",
    "conflict": "冲突",
    "fight": "冲突",
    "rest": "休整",
    "observe": "观察",
    "trade": "交易",
    "use": "使用",
    "explore": "探索",
}

OP_LABEL: dict[str, str] = {
    "remove_resource": "消耗",
    "add_resource": "获得",
    "resource": "需要",
    "state": "需要状态",
    "knowledge": "需要情报",
    "relationship": "需要关系",
    "flag": "需要标记",
    "location": "需要地点",
    "character": "需要角色",
}

# 兜底：查不到真实名称时使用的可读描述（绝不回落到原始 id）。
FALLBACK_LABEL: dict[str, str] = {
    "location": "未知地点",
    "character": "未知角色",
    "resource": "未知资源",
    "knowledge": "未记录的线索",
    "identity": "未记录的身份",
}


def content_labels(pack: Any) -> dict[str, str]:
    """内容包 / 引擎里真实存在的元素 id → 作者可读名称。

    只收录**真的有名字**的元素；缺失的 id 不在表里（调用方按类型兜底）。
    """

    def field(row: Any, *names: str) -> str:
        for name in names:
            if isinstance(row, Mapping):
                value = row.get(name)
            else:
                value = getattr(row, name, None)
            text = str(value or "").strip()
            if text:
                return text
        return ""

    labels: dict[str, str] = {}
    for card in list(getattr(pack, "events", None) or [])[:200]:
        event_id = field(card, "event_id", "id")
        title = field(card, "title", "name", "label")
        if event_id and title:
            labels[event_id] = title
    for item in list(getattr(pack, "actions", None) or [])[:400]:
        action_id = field(item, "id", "action_id")
        name = field(item, "name", "title", "label")
        if action_id and name:
            labels[action_id] = name
    for item in list(getattr(pack, "foreshadows", None) or [])[:200]:
        item_id = field(item, "id", "foreshadow_id")
        title = field(item, "title", "name", "label")
        if item_id and title:
            labels[item_id] = title
    for item in list(getattr(pack, "initial_plots", None) or [])[:200]:
        item_id = field(item, "id", "plot_id")
        title = field(item, "name", "title", "label")
        if item_id and title:
            labels[item_id] = title
    for item in list(getattr(pack, "initial_locations", None) or [])[:200]:
        item_id = field(item, "id", "location_id")
        title = field(item, "name", "title", "label")
        if item_id and title:
            labels[item_id] = title
    for item in list(getattr(pack, "initial_factions", None) or [])[:200]:
        item_id = field(item, "id", "faction_id")
        title = field(item, "name", "title", "label")
        if item_id and title:
            labels[item_id] = title
    characters = dict(getattr(pack, "initial_characters", {}) or {})
    for character_id, entry in list(characters.items())[:200]:
        name = field(entry, "name", "label", "title")
        if character_id and name:
            labels[str(character_id)] = name
    for tree in list(getattr(pack, "progressions", None) or [])[:200]:
        tree_id = field(tree, "tree_id", "id")
        name = field(tree, "name", "title", "label")
        if tree_id and name:
            labels[tree_id] = name
    return labels


def label_table(pack: Any = None, extra: Mapping[str, str] | None = None
                ) -> dict[str, str]:
    """展示层完整映射表：真实名称 > 关键词表 > 系统保留名。"""

    table: dict[str, str] = {}
    for source in (SYSTEM_LABEL, IDENTITY_LABEL, KNOWLEDGE_LABEL, RESOURCE_LABEL,
                   TRACK_LABEL):
        table.update(source)
    if pack is not None:
        table.update(content_labels(pack))
    if extra:
        table.update({str(key): str(value) for key, value in extra.items() if value})
    return table


def translate(text: Any, labels: Mapping[str, str] | None = None) -> str:
    """把一段引擎文本里的真实 id 换成作者语言（不改写句子结构）。"""

    out = str(text or "")
    if not out:
        return ""
    table = {str(key): str(value) for key, value in dict(labels or {}).items()
             if key and value and str(key) != str(value)}
    for raw, name in sorted(table.items(), key=lambda item: -len(item[0])):
        if raw in out:
            out = out.replace(raw, name)
    return out


def resource_label(key: Any) -> str:
    raw = str(key or "")
    return RESOURCE_LABEL.get(raw) or (raw if _looks_author_facing(raw) else
                                       FALLBACK_LABEL["resource"])


def _looks_author_facing(text: str) -> bool:
    """判断一个 key 是否本身就是作者语言（不含 ASCII 标识符形状 / 下划线）。

    资源 key 由内容包定义：作者可能直接写中文名（「符纸」），也可能写引擎 id
    （`echo_shard`）。前者原样保留，后者回落到可读描述。
    """

    if not text:
        return False
    if "_" in text:
        return False
    return not all(ord(char) < 128 for char in text)


__all__ = [
    "ACTION_KIND_LABEL", "FALLBACK_LABEL", "IDENTITY_LABEL", "KNOWLEDGE_LABEL",
    "OP_LABEL", "RESOURCE_LABEL", "SYSTEM_LABEL", "TRACK_LABEL",
    "content_labels", "label_table", "resource_label", "translate",
]
