"""C12：Writer-visible 叙事完整性防线（C11 人工审核暴露的 blind spots）。

覆盖五类「机器指标为 0 但人眼可见」的缺陷（MUT-041…MUT-046）：

- orphaned reference fragment：删除旧 anchor 后留下的残句（“承接 的投靠先例”“已在被确认”）
- canon audit prose spam：每条 event 都在解释历史 anchor，而不是推进当前动作
- dog role semantic alignment：role 与阿灰实际动作/影响不符，payload 只是 title+goal 拼接
- narrative event lifecycle conflict：departure → return 之后又回到 unresolved departure
- cross-field semantic mismatch：同一章不同字段属于不同剧情 frame

全部为确定性规则；不引入 LLM，不改变既有 Canon 语义。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

ORPHAN_PATTERNS: tuple[re.Pattern[str], ...] = (
    # 1) “承接 的…” / “按 的…”
    re.compile(r"(?:承接|按|依|据)\s*的"),
    # 2) 介词 + 空格槽位（删除 anchor 后剩下的空格）
    re.compile(r"(?:把|而|由|与|和|在|从|向|对|为|将|被|按|依|据|承接)\s+的[\u4e00-\u9fff]"),
    re.compile(r"(?:与|和|按|依|据|承接)\s+(?:确认|先例|投靠|首次|第一次|编号|记录|登记|条款|原则|格式)"),
    re.compile(r"(?:把|将|和|与|由|被|在|从|向|对|按|依|据)\s+(?:之后|之前|首次|第一次|先例|确认)"),
    # 3) 介词 + 的 + 锚点名词（“把的首次开门”“而的塔回应”）
    re.compile(r"(?:把|而|由|与|和|在|从|向|对|为|将|被)的"
               r"(?:首次|第一次|先例|投靠|确认|开门|回应|移动|公开|记录|编号|铭牌|档案|条款|原则|格式|塔)"),
    re.compile(r"(?:把|而|将|被)的(?:登记|规矩|决定|立场|说法|结果)"),
    # 4) 双被动 / 残句
    re.compile(r"已在被|将被被|已被在|已被的|，\s*的[\u4e00-\u9fff]"),
    # 5) “中铭牌编号”这类被删掉前缀名词的残片
    re.compile(r"(?:^|[，。；：、\s])中(?=(?:铭牌|编号|档案|记录|先例|条款))"),
    # 6) “首次开门 的” 悬挂结构
    re.compile(r"(?:首次|第一次)(?:开门|回应|移动|公开|确认)\s*的(?=[，。；：]|$)"),
    # 7) 句首/句尾残片
    re.compile(r"^[的，、；：]+"),
    re.compile(r"的\s*的|确认\s*的\s*的"),
)

AUDIT_PROSE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?:首次|第一次)[^，。；]{0,12}(?:之后|以来|后)"),
    re.compile(r"这是[^，。；]{0,24}(?:的后续|的后果|的延续|的连锁|的余波|的结果)"),
    re.compile(r"被重新(?:解释|定义)为|重新解释为"),
    re.compile(r"连锁后果|连锁反应"),
    re.compile(r"而不是(?:首次|新的首次)事件|而非新的首次事件"),
    re.compile(r"已过去(?:数月|多年|一年|数日)|距离[^，。；]{0,12}已过去"),
    re.compile(r"作为[^，。；]{0,16}(?:的先例|的依据|的前例)"),
    re.compile(r"(?:标志|证明|说明)着?[^，。；]{0,20}(?:已|曾|系统|制度|体系)"),
    re.compile(r"该(?:编号|记录|条款|格式|原则)[^，。；]{0,16}(?:时|之后)(?:使用|确立|留下|形成)的"),
)

ANCHOR_KEYWORDS: tuple[str, ...] = ("第零层", "门禁", "灰墙", "铭牌", "编号", "灾变档案",
                                    "新秩序", "三方结盟", "共同通行", "最初的塔", "旧广播",
                                    "观测区", "配给", "过路费")

DOG_ACTION_VERBS: tuple[str, ...] = ("顶", "嗅", "闻", "预警", "低吼", "守", "拖", "叼", "拦",
                                     "扑", "咬", "护", "带路", "发现", "提醒", "找到", "看住",
                                     "盯", "冲", "拉", "拽", "护送", "巡", "救", "扒", "刨",
                                     "压住", "按住", "挡住", "扶", "稳住", "协助")
DOG_INDEPENDENT_PATTERN = re.compile(r"阿灰[^。；]{0,16}(?:独自|自行|自己决定|自己|主动)")
DOG_PASSIVE_PATTERN = re.compile(r"阿灰[^。；]{0,10}(?:被困|被救|被偷|被抓|被带|被运|被卖|被扣|受伤)")


@dataclass
class ProseFinding:
    code: str
    where: str
    detail: str = ""
    snippet: str = ""


@dataclass
class AuditProseReport:
    audit_events: int = 0
    action_events: int = 0
    anchor_mentions: dict[str, int] = field(default_factory=dict)
    findings: list[ProseFinding] = field(default_factory=list)

    @property
    def density(self) -> float:
        total = self.audit_events + self.action_events
        return round(self.audit_events / total, 4) if total else 0.0


def orphaned_reference_fragments(text: str, *, where: str = "") -> list[ProseFinding]:
    """MUT-041：检测删除 anchor 之后留下的残句 / 空引用槽位。"""

    findings: list[ProseFinding] = []
    value = text or ""
    for pattern in ORPHAN_PATTERNS:
        for match in pattern.finditer(value):
            start = max(0, match.start() - 12)
            findings.append(ProseFinding(code="ORPHANED_REFERENCE_FRAGMENT", where=where,
                                         detail=pattern.pattern[:40],
                                         snippet=value[start:match.end() + 12]))
    # 连续介词 / 介词收尾
    if re.search(r"(?:^|[，。；：、\s])(?:承接|按|依|据|与|和|把|将|被|由|在|于|向|对|为)"
                 r"[，。；：]", value):
        findings.append(ProseFinding(code="ORPHANED_PREPOSITION_TAIL", where=where,
                                     snippet=value[-30:]))
    return findings


def audit_prose_report(events: Sequence[str]) -> AuditProseReport:
    """MUT-042：判断一章是否在「解释历史 anchor」而不是推进当前动作。"""

    report = AuditProseReport()
    for event in events:
        text = str(event or "")
        anchor_hits = [keyword for keyword in ANCHOR_KEYWORDS if keyword in text]
        is_audit = any(pattern.search(text) for pattern in AUDIT_PROSE_PATTERNS)
        if is_audit:
            report.audit_events += 1
        else:
            report.action_events += 1
        for keyword in anchor_hits:
            report.anchor_mentions[keyword] = report.anchor_mentions.get(keyword, 0) + 1
    repeated = {keyword: count for keyword, count in report.anchor_mentions.items() if count >= 2}
    if report.audit_events >= 3:
        report.findings.append(ProseFinding(
            code="CANON_AUDIT_PROSE_SPAM", where="events",
            detail=f"audit_events={report.audit_events} density={report.density}"))
    elif report.audit_events >= 2 and report.density >= 0.5:
        report.findings.append(ProseFinding(
            code="CANON_AUDIT_PROSE_WARN", where="events",
            detail=f"audit_events={report.audit_events} density={report.density}"))
    for keyword, count in sorted(repeated.items()):
        report.findings.append(ProseFinding(
            code="CANONICAL_ANCHOR_REPETITION", where="events",
            detail=f"{keyword} 在同章被解释 {count} 次"))
    return report


def dog_role_alignment(plan: Mapping[str, Any], *, dog_name: str = "阿灰") -> list[ProseFinding]:
    """MUT-043：role 必须由阿灰的实际动作 / 实际影响支撑，payload 不得是字段拼接。"""

    findings: list[ProseFinding] = []
    role = str(plan.get("dog_role") or "")
    events = [str(item) for item in (plan.get("concrete_events") or plan.get("events") or [])]
    dog_note = str(plan.get("dog_action") or plan.get("dog_note") or "")
    action_text = " ".join(events)
    dog_text = " ".join([dog_note, action_text])
    dog_present = dog_name in dog_text
    dog_events = [item for item in events if dog_name in item]
    performed = any(verb in item for item in dog_events + [dog_note] for verb in DOG_ACTION_VERBS)
    independent = any(DOG_INDEPENDENT_PATTERN.search(item) for item in dog_events + [dog_note])
    passive_only = bool(dog_events) and all(DOG_PASSIVE_PATTERN.search(item) for item in dog_events) \
        and not performed
    if role == "absent" and dog_present:
        findings.append(ProseFinding(code="DOG_ROLE_PRESENCE_MISMATCH", where="dog_role",
                                     detail="role=absent 但正文出现阿灰参与"))
    if role in ("supportive", "involved", "independent") and not dog_present:
        findings.append(ProseFinding(code="DOG_ROLE_PRESENCE_MISMATCH", where="dog_role",
                                     detail=f"role={role} 但正文没有阿灰"))
    if role in ("supportive", "involved") and not performed:
        findings.append(ProseFinding(
            code="DOG_ROLE_ACTION_ALIGNMENT", where="dog_role",
            detail=f"role={role} 但阿灰没有明确动作（被动/被保护不算 supportive）" +
                   ("（被动出现）" if passive_only else "")))
    if role == "independent" and not independent:
        findings.append(ProseFinding(code="DOG_ROLE_ACTION_ALIGNMENT", where="dog_role",
                                     detail="role=independent 但没有自主目标/自主选择"))
    # payload 不得是 title + goal + 前半句拼接
    title = str(plan.get("title") or "")
    goal = str(plan.get("goal") or "")
    first_event = events[0] if events else ""
    if dog_note:
        copy_candidates = [f"{title}{goal}", f"{title}{first_event}", f"{goal}{first_event}",
                           title, goal]
        if any(candidate and len(candidate) >= 6 and
               (dog_note.strip() == candidate.strip() or dog_note.strip().startswith(candidate.strip()))
               for candidate in copy_candidates):
            findings.append(ProseFinding(
                code="DOG_ROLE_PAYLOAD_SUMMARY_COPY", where="dog_action",
                detail="dog payload 疑似 title/goal/event 拼接，不是阿灰的实际动作",
                snippet=dog_note[:40]))
    return findings


LIFECYCLE_DEPARTURE = re.compile(
    r"阿灰[^。；]{0,20}(?:(?:自行|主动|独自)?(?:离开|出走|离队)[^。；]{0,20}(?:[两三数几]天|[两三数几]日|未归|没有回来)"
    r"|(?:未归|还没回来|仍未回来|下落不明|一直没有回来))")
LIFECYCLE_RETURN = re.compile(
    r"阿灰[^。；]{0,16}(?:自行|主动|自己)?(?:走回|回来|返回|归队)[^。；]{0,10}"
    r"|(?:自行|主动|自己)(?:回来|返回)"
    r"|(?:三天|三日)[^。；]{0,6}(?:回来|归来|归队)")
LIFECYCLE_UNRESOLVED = re.compile(
    r"阿灰[^。；]{0,16}(?:未归|还没回来|仍未回来|下落不明|一直没有回来|没有消息)")


def narrative_lifecycle_findings(chapters: Sequence[Mapping[str, Any]]) -> list[ProseFinding]:
    """MUT-044：departure → resolved return 之后，不得重新进入同一 unresolved departure。"""

    findings: list[ProseFinding] = []
    returned = False
    departed_at = ""
    for chapter in chapters:
        text = " ".join([str(chapter.get("goal") or ""),
                         *[str(item) for item in (chapter.get("events") or [])],
                         str(chapter.get("start_state") or ""),
                         str(chapter.get("end_state") or "")])
        chapter_id = str(chapter.get("id") or chapter.get("chapter_uuid") or "")
        has_departure = bool(LIFECYCLE_DEPARTURE.search(text))
        has_return = bool(LIFECYCLE_RETURN.search(text))
        if has_departure and has_return:
            # 同一章内写完 departure → resolved return：完整闭环，不算冲突
            departed_at = departed_at or chapter_id
            returned = True
            continue
        if has_departure:
            if returned:
                findings.append(ProseFinding(
                    code="NARRATIVE_EVENT_LIFECYCLE_CONFLICT", where=chapter_id,
                    detail=f"已经回归（{departed_at} 之后 resolved）又进入未解决离别状态"))
            departed_at = departed_at or chapter_id
        if has_return:
            significant = bool(re.search(r"(?:三天|三日|归队|自行回来|主动回来|自己走回)", text))
            if not returned and not departed_at and significant:
                findings.append(ProseFinding(
                    code="NARRATIVE_EVENT_LIFECYCLE_CONFLICT", where=chapter_id,
                    detail="回归事件出现在任何 departure 之前"))
            returned = True
        elif LIFECYCLE_UNRESOLVED.search(text) and returned:
            findings.append(ProseFinding(
                code="NARRATIVE_EVENT_LIFECYCLE_CONFLICT", where=chapter_id,
                detail="回归之后又回到「未归」状态"))
    return findings


CROSS_FIELD_KEYWORDS: dict[str, tuple[str, ...]] = {
    "signing": ("签署", "签下", "签字", "表决", "投票", "新规矩", "共守规矩", "共同规矩",
                "第一条规矩", "新秩序成立", "共守进程", "共守规矩"),
    "excavation": ("刻写", "铭文", "塔基", "拓印", "年代", "地层", "重刻"),
}


def cross_field_findings(plan: Mapping[str, Any]) -> list[ProseFinding]:
    """MUT-045：字段必须属于同一个 chapter semantic frame。"""

    findings: list[ProseFinding] = []
    events = " ".join(str(item) for item in (plan.get("concrete_events") or plan.get("events") or []))
    goal = str(plan.get("goal") or "")
    frame = f"{goal} {events}"
    for field_name in ("decision", "decision_result", "turn", "payoff", "end_state",
                       "world_state_change"):
        value = str(plan.get(field_name) or "")
        if not value:
            continue
        for topic, keywords in CROSS_FIELD_KEYWORDS.items():
            field_topic = any(keyword in value for keyword in keywords)
            frame_topic = any(keyword in frame for keyword in keywords)
            other_topics = {name for name, words in CROSS_FIELD_KEYWORDS.items()
                            if name != topic and any(word in frame for word in words)}
            if field_topic and not frame_topic and other_topics:
                findings.append(ProseFinding(
                    code="CROSS_FIELD_SEMANTIC_MISMATCH", where=field_name,
                    detail=f"{field_name} 属于 {topic} 剧情，但本章 frame 属于 {sorted(other_topics)}",
                    snippet=value[:40]))
    return findings


def validate_sample_pack(entries: Sequence[Mapping[str, Any]], *, volumes: Iterable[int] = (),
                         expected_per_volume: int = 5, min_random: int = 18) -> list[ProseFinding]:
    """MUT-046：Final Sample Pack 完整性（数量 / 唯一 / 每卷 5 章 / 真随机 ≥18）。"""

    findings: list[ProseFinding] = []
    ids = [str(entry.get("chapter") or entry.get("chapter_uuid") or "") for entry in entries]
    if len(entries) < 35:
        findings.append(ProseFinding(code="SAMPLE_ENTRY_COUNT", where="pack",
                                     detail=f"expected 35, got {len(entries)}"))
    duplicates = sorted({item for item in ids if ids.count(item) > 1})
    if duplicates:
        findings.append(ProseFinding(code="SAMPLE_DUPLICATE_CHAPTER", where="pack",
                                     detail=f"重复章节：{duplicates}"))
    for volume in volumes:
        count = sum(1 for entry in entries if int(entry.get("volume") or 0) == int(volume))
        if count != expected_per_volume:
            findings.append(ProseFinding(code="SAMPLE_PER_VOLUME_COUNT", where=f"V{volume}",
                                         detail=f"expected {expected_per_volume}, got {count}"))
    random_count = sum(1 for entry in entries if str(entry.get("category")) == "normal")
    if random_count < min_random:
        findings.append(ProseFinding(code="SAMPLE_RANDOM_COUNT", where="pack",
                                     detail=f"random_selected={random_count} < {min_random}"))
    per_chapter: dict[str, set[str]] = {}
    for entry in entries:
        chapter = str(entry.get("chapter") or "")
        per_chapter.setdefault(chapter, set()).add(str(entry.get("category") or ""))
    for chapter, categories in sorted(per_chapter.items()):
        if len(categories) > 1:
            findings.append(ProseFinding(
                code="SAMPLE_CHAPTER_MULTI_CATEGORY", where=chapter,
                detail=f"同一章同时充当 {sorted(categories)}"))
    return findings


# --------------------------------------------------------------------------- C13：MUT-047…051


def _tokens(text: str) -> set[str]:
    clean = re.sub(r"[^\w\u4e00-\u9fff]+", " ", (text or "").lower())
    words = {word for word in clean.split() if len(word) > 1}
    grams = {clean[index:index + 2].strip() for index in range(max(0, len(clean) - 1))}
    return {token for token in words | grams if token}

# 同一章内互斥的剧情 frame 关键词（用于 stale frame 检测）
FRAME_CONTRAST: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (("审讯", "活口", "内应", "改道", "谈判", "封锁", "落网", "报备", "按趟结算"),
     ("伏击", "箭", "扑咬", "弃货", "弃箱", "弃一箱", "保人", "外放", "突围",
      "救阿灰", "放弃材料", "救援")),
    (("踏勘", "入口", "生态", "下撤", "标记", "路线", "岩脊"),
     ("塌陷", "被困", "救援", "二阶", "涌出", "救阿灰", "外放")),
    (("草案", "表决", "程序", "修订", "第一轮"),
     ("签署", "签下", "两个名字", "新秩序成立", "主线关闭")),
)
FRAME_FIELDS = ("goal", "trigger", "protagonist_action", "opposition", "escalation",
                "decision", "decision_result", "turn", "payoff", "cost", "loss",
                "end_state", "world_state_change", "hook", "next_chapter_causality",
                "information_release")


def chapter_frame_findings(plan: Mapping[str, Any]) -> list[ProseFinding]:
    """MUT-047：整章字段必须属于 concrete_events 的同一事件框架（stale frame）。"""

    findings: list[ProseFinding] = []
    events = " ".join(str(item) for item in (plan.get("concrete_events") or plan.get("events") or []))
    event_tokens = _tokens(events)
    event_poles = {index for index, (_, right) in enumerate(FRAME_CONTRAST)
                   if any(word in events for word in right) or
                   any(word in events for word in FRAME_CONTRAST[index][0])}
    for field_name in FRAME_FIELDS:
        value = str(plan.get(field_name) or "")
        if len(value) < 6:
            if field_name in ("decision", "decision_result", "turn", "payoff", "cost", "loss") \
                    and len(value) >= 10 and re.search(
                        r"(?:宣布|决定|放弃|救|突围|成立|签署|控制|交出)", value) \
                    and re.search(r"(?:商路|盐路|阿灰|灰墙|第零层|编号|档案|塔|盆地|据点|仓|门禁)",
                                  value) \
                    and event_tokens and not (_tokens(value) & event_tokens):
                findings.append(ProseFinding(
                    code="STALE_CHAPTER_FRAME", where=field_name,
                    detail="decision/turn/payoff 谈论的对象不在本章 concrete_events 里",
                    snippet=value[:40]))
            continue
        if field_name in ("decision", "decision_result", "turn", "payoff", "cost", "loss") \
                and len(value) >= 10 and re.search(
                    r"(?:宣布|决定|放弃|救|突围|成立|签署|控制|交出)", value) \
                and re.search(r"(?:商路|盐路|阿灰|灰墙|第零层|编号|档案|塔|盆地|据点|仓|门禁)", value) \
                and event_tokens and not (_tokens(value) & event_tokens):
            findings.append(ProseFinding(
                code="STALE_CHAPTER_FRAME", where=field_name,
                detail="decision/turn/payoff 谈论的对象不在本章 concrete_events 里",
                snippet=value[:40]))
            continue
        # (e) 字段里的「新对象 + 动作」在本章 events 中完全不存在（如 events=正式签署，
        #     field=公开 observatory_data / 分残响力量）
        if field_name in ("protagonist_action", "decision", "decision_result", "turn", "payoff",
                          "cost", "loss"):
            objects = {token for token in _tokens(value) if len(token) >= 4 and
                       re.search(r"[a-z_]{4,}|[\u4e00-\u9fff]{4,}", token)}
            absent = {token for token in objects if token not in events}
            if absent and re.search(r"(?:公开|分|留|完成|刻写|宣布|决定|放弃|救|交出|接下)", value) \
                    and not (objects & _tokens(events)):
                findings.append(ProseFinding(
                    code="STALE_CHAPTER_FRAME", where=field_name,
                    detail="字段描述的对象 / 动作在本章 concrete_events 中不存在",
                    snippet=value[:40]))
                continue
        field_tokens = _tokens(value)
        if not field_tokens:
            continue
        # 只保留「frame 互斥」与「引用本章缺席 storyline」两类精确判定；
        # 纯词汇不重叠不算 stale（否则会把正常写法全判错）
        for index, (left, right) in enumerate(FRAME_CONTRAST):
            if index not in event_poles:
                # (c) 字段引用本章事件里完全缺席的 storyline（右侧为“高潮/旧 frame”侧）
                if any(word in value for word in right):
                    findings.append(ProseFinding(
                        code="STALE_CHAPTER_FRAME", where=field_name,
                        detail="字段引用了本章 concrete_events 之外的 storyline",
                        snippet=value[:40]))
                continue
            event_is_left = any(word in events for word in left)
            opposite = right if event_is_left else left
            if any(word in value for word in opposite):
                findings.append(ProseFinding(
                    code="STALE_CHAPTER_FRAME", where=field_name,
                    detail="字段仍使用被替换掉的旧 frame 关键词",
                    snippet=value[:40]))
                break
    return findings


FIRST_OCCURRENCE_CONTRADICTION = re.compile(
    r"(?:上次|再次|又一次|重演|延续第一次|延续上一次|首次(?:回应|开门|打开|开启|开放|移动|公开|确认|揭示|激活)"
    r"[^。；]{0,8}(?:之后|以后|后)|而非(?:首次|新的首次)|不是首次|并非首次)")


def first_occurrence_findings(plan: Mapping[str, Any]) -> list[ProseFinding]:
    """MUT-048：被标为 first occurrence 的章节，不得自称「上次 / 再次 / 首次之后」。"""

    event_id = str(plan.get("first_occurrence_event_id") or "")
    if not event_id:
        return []
    findings: list[ProseFinding] = []
    for field_name in ("goal", *FRAME_FIELDS, "concrete_events"):
        value = plan.get(field_name)
        values = value if isinstance(value, list) else [value]
        for item in values:
            text = str(item or "")
            match = FIRST_OCCURRENCE_CONTRADICTION.search(text)
            if match:
                findings.append(ProseFinding(
                    code="FIRST_OCCURRENCE_SELF_CONTRADICTION", where=field_name,
                    detail=f"first occurrence（{event_id}）出现自相矛盾措辞",
                    snippet=text[max(0, match.start() - 10):match.end() + 10]))
    return findings


IRREVERSIBLE_CLOSED = re.compile(
    r"(?:永久(?:封死|封闭|封存|不可进入|关闭)|彻底(?:封死|封住)|再也(?:打不开|进不去))")
REVERSIBLE_LOCK = re.compile(r"(?:紧急锁闭|撤销开放权限|暂时隔绝|暂时封|锁定核心)")


def irreversible_state_findings(chapters: Sequence[Mapping[str, Any]]) -> list[ProseFinding]:
    """MUT-049：OPEN → PERMANENTLY_CLOSED 之后，后续章节不得再次声明同一不可逆转换。"""

    findings: list[ProseFinding] = []
    closed_at = ""
    reopened = False
    for chapter in chapters:
        text = " ".join([str(chapter.get("goal") or ""),
                         *[str(item) for item in (chapter.get("events") or [])],
                         str(chapter.get("end_state") or ""),
                         str(chapter.get("world_state_change") or "")])
        chapter_id = str(chapter.get("id") or chapter.get("chapter_uuid") or "")
        if "第零层" not in text:
            continue
        if IRREVERSIBLE_CLOSED.search(text):
            if closed_at:
                findings.append(ProseFinding(
                    code="IRREVERSIBLE_STATE_REPEATED", where=chapter_id,
                    detail=f"第零层已在 {closed_at} 永久封闭，此处再次声明不可逆封闭"))
            else:
                closed_at = chapter_id
        elif REVERSIBLE_LOCK.search(text):
            reopened = reopened or bool(closed_at)
    return findings


PRESENCE_CLAIMS = ("带阿灰", "与阿灰同行", "阿灰随行", "两人一犬")
ABSENCE_CLAIMS = ("阿灰留在", "阿灰留守", "阿灰不在", "没有带阿灰", "留下阿灰")


def within_chapter_state_findings(plan: Mapping[str, Any]) -> list[ProseFinding]:
    """MUT-050：同一章内「带阿灰出发」与「阿灰留在据点」不得同时出现。"""

    findings: list[ProseFinding] = []
    hits: dict[str, list[str]] = {"presence": [], "absence": []}
    for field_name in ("protagonist_action", "loss", "end_state", "turn", "payoff",
                       "start_state", "decision"):
        value = str(plan.get(field_name) or "")
        if not value:
            continue
        if any(claim in value for claim in PRESENCE_CLAIMS):
            hits["presence"].append(field_name)
        if any(claim in value for claim in ABSENCE_CLAIMS):
            hits["absence"].append(field_name)
    if hits["presence"] and hits["absence"]:
        findings.append(ProseFinding(
            code="WITHIN_CHAPTER_STATE_CONTRADICTION", where="dog_presence",
            detail=f"同章同时声明同行 {hits['presence']} 与留守 {hits['absence']}"))
    return findings


DOG_OBJECT_PATTERN = re.compile(
    r"阿灰[^。；]{0,16}(?:被保护|被交易|被讨论|被引用|被利用|被扣|被运|被卖|被带走|受伤|留在|不在场)"
    r"|(?:编号|身份)[^。；]{0,12}阿灰")


def dog_role_object_findings(plan: Mapping[str, Any], *, dog_name: str = "阿灰") -> list[ProseFinding]:
    """MUT-051：阿灰只是被保护 / 被交易 / 被讨论 / 编号被引用 / 受伤 / 不在场时不能判 supportive。"""

    findings: list[ProseFinding] = []
    role = str(plan.get("dog_role") or "")
    if role not in ("supportive", "involved"):
        return findings
    events = [str(item) for item in (plan.get("concrete_events") or plan.get("events") or [])]
    note = str(plan.get("dog_action") or plan.get("dog_note") or "")
    dog_actions = [item for item in events if dog_name in item] + ([note] if note else [])
    performed = any(verb in item for item in dog_actions for verb in DOG_ACTION_VERBS)
    object_only = bool(dog_actions) and all(
        DOG_OBJECT_PATTERN.search(item) or not any(verb in item for verb in DOG_ACTION_VERBS)
        for item in dog_actions)
    if role == "supportive" and not performed and object_only:
        findings.append(ProseFinding(
            code="DOG_ROLE_OBJECT_NOT_SUPPORTIVE", where="dog_role",
            detail="阿灰在本章只是被保护 / 被交易 / 被讨论 / 受伤 / 不在场，不能判 supportive",
            snippet=(dog_actions[0][:40] if dog_actions else "")))
    return findings


def dog_role_recompute(plan: Mapping[str, Any], *, dog_name: str = "阿灰") -> str:
    """按固定规则重算 dog_role（对象化场景不得默认 supportive）。"""

    events = [str(item) for item in (plan.get("concrete_events") or plan.get("events") or [])]
    note = str(plan.get("dog_action") or plan.get("dog_note") or "")
    haystack = " ".join(events + ([note] if note else []))
    goal = str(plan.get("goal") or "")
    presence = plan.get("physical_presence")
    if presence is False:
        return "offscreen_effect" if (dog_name in haystack or dog_name in goal) else "absent"
    if dog_name not in haystack and dog_name not in goal:
        return "absent"
    mentions = [item for item in events + ([note] if note else []) if dog_name in item]
    if not mentions:
        return "offscreen_effect" if dog_name in goal else "absent"
    if any(DOG_INDEPENDENT_PATTERN.search(item) for item in mentions):
        return "independent"
    if any(verb in item for item in mentions for verb in DOG_ACTION_VERBS):
        return "supportive"
    if any(DOG_PASSIVE_PATTERN.search(item) or DOG_OBJECT_PATTERN.search(item)
           for item in mentions):
        return "offscreen_effect"
    if any(verb in item for item in mentions for verb in ("低吼", "盯", "跟", "走", "站", "退")):
        return "involved"
    return "involved" if presence is True else "offscreen_effect"


def dog_role_presence_findings(role: str, *, physical_presence: bool) -> list[ProseFinding]:
    """MUT-051 强化：physical_presence 与 role 必须自洽。

    physical_presence=True → 不得 offscreen_effect；
    physical_presence=False → 只能是 offscreen_effect / absent。
    """

    findings: list[ProseFinding] = []
    if physical_presence and role == "offscreen_effect":
        findings.append(ProseFinding(
            code="DOG_ROLE_PRESENCE_MISMATCH", where="dog_role",
            detail="阿灰实际在场，不能判 offscreen_effect"))
    if not physical_presence and role in ("supportive", "involved", "independent"):
        findings.append(ProseFinding(
            code="DOG_ROLE_PRESENCE_MISMATCH", where="dog_role",
            detail=f"阿灰不在场，不能判 {role}（只能是 offscreen_effect / absent）"))
    return findings


FUTURE_INSTITUTIONS: tuple[tuple[str, int], ...] = (
    # 新秩序草案在 registry 里的 canonical 位置是 ch153（V4），不算未来 institution
    ("最终投票", 526), ("共守规矩", 526), ("共守规则", 526),
    ("交叉验证机制", 504), ("两个名字", 559),
)


def future_canon_leak_findings(chapters: Sequence[Mapping[str, Any]]) -> list[ProseFinding]:
    """自然语言引用未来 canonical institution 也必须被检出（future canon leak）。"""

    findings: list[ProseFinding] = []
    for chapter in chapters:
        raw = str(chapter.get("display_number") or chapter.get("index") or
                  re.sub(r"\D", "", str(chapter.get("id") or "0")))
        index = int(raw or 0)
        text = " ".join([str(chapter.get("goal") or ""),
                         *[str(item) for item in (chapter.get("events") or [])],
                         str(chapter.get("end_state") or ""),
                         str(chapter.get("world_state_change") or ""),
                         str(chapter.get("information_release") or "")])
        for institution, position in FUTURE_INSTITUTIONS:
            if institution in text and index and index < position:
                findings.append(ProseFinding(
                    code="FUTURE_CANON_LEAK", where=str(chapter.get("id") or ""),
                    detail=f"{institution} 的 canonical 位置是 ch{position}，此处提前引用",
                    snippet=text[:40]))
    return findings


STATE_TRANSITIONS: tuple[tuple[str, int, tuple[str, ...]], ...] = (
    # (状态名, canonical 取得章节, 提前声明该状态的措辞)
    ("盐路控制权", 133, ("正式受铁锈集控制", "归铁锈集控制", "取得盐路控制权", "掌握盐路控制权")),
    ("共守规矩", 526, ("共守规矩成立", "共守规矩生效", "新秩序成立")),
    ("第零层永久封闭", 379, ("永久封闭第零层", "第零层永久封死")),
)


def state_transition_findings(chapters: Sequence[Mapping[str, Any]],
                              transitions: Sequence[tuple[str, int, tuple[str, ...]]] | None = None
                              ) -> list[ProseFinding]:
    """state transition 不能在 canonical acquisition 之前提前完成（MUT-047 跨章例）。"""

    table = transitions if transitions is not None else STATE_TRANSITIONS
    findings: list[ProseFinding] = []
    for chapter in chapters:
        raw = str(chapter.get("display_number") or chapter.get("index") or
                  re.sub(r"\D", "", str(chapter.get("id") or "0")))
        index = int(raw or 0)
        if not index:
            continue
        text = " ".join([str(chapter.get("goal") or ""), *[str(item) for item in
                                                          (chapter.get("events") or [])],
                         str(chapter.get("world_state_change") or ""),
                         str(chapter.get("end_state") or ""),
                         str(chapter.get("payoff") or "")])
        for name, position, phrases in table:
            for phrase in phrases:
                if phrase in text and index < position:
                    findings.append(ProseFinding(
                        code="STATE_TRANSITION_PREMATURE", where=str(chapter.get("id") or ""),
                        detail=f"{name} 的 canonical 取得位置是 ch{position}，此处提前声明：{phrase}",
                        snippet=text[:40]))
    return findings


def dog_payload_evidence_findings(plan: Mapping[str, Any], *,
                                  dog_name: str = "阿灰") -> list[ProseFinding]:
    """dog payload 必须能在 concrete_events 里定位到实际动作证据。"""

    findings: list[ProseFinding] = []
    role = str(plan.get("dog_role") or "")
    if role == "absent":
        return findings
    note = str(plan.get("dog_action") or plan.get("dog_note") or "")
    events = [str(item) for item in (plan.get("concrete_events") or plan.get("events") or [])]
    if not note:
        findings.append(ProseFinding(
            code="DOG_ROLE_PAYLOAD_UNSUPPORTED", where="dog_action",
            detail=f"role={role} 但 payload 为空"))
        return findings
    actions = [verb for verb in DOG_ACTION_VERBS if verb in note]
    if actions and not any(verb in event for event in events for verb in actions):
        findings.append(ProseFinding(
            code="DOG_ROLE_PAYLOAD_UNSUPPORTED", where="dog_action",
            detail=f"payload 的动作（{actions[:3]}）在 concrete_events 里找不到证据",
            snippet=note[:40]))
    if len(note) > 40 and any(note[:20] in event or event[:20] in note for event in events):
        findings.append(ProseFinding(
            code="DOG_ROLE_PAYLOAD_SUMMARY_COPY", where="dog_action",
            detail="payload 与 concrete_events 首句高度重合，疑似拼接",
            snippet=note[:40]))
    return findings
