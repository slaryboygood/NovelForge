"""W1-01：创意入口与题材识别。

这一层只解决“这本小说想写什么”，不生成世界 / 人物 / 势力 / 关系 / 成长 / 主线 / 伏笔
（那些属于 W1-02）。

设计约束：

- 复用现有 Genre Template、Content Pack、NovelProfile，不新建配置系统。
- 候选只能指向**真实存在**的模板与内容包；模型提议的 id 必须经过目录校验，越界直接丢弃。
- AI 不可用时走确定性降级：仍然基于真实模板 / 内容包给出候选。
- 结果保存进 NovelProfile.world_profile["creative_brief"]，不写任何 StoryState 事实。
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, Callable

from pydantic import Field

from novelforge.models import StrictModel

from .content import ContentPack, list_packs_from_project
from .profile import NovelProfile, NovelProfileRepository
from .templates import GenreTemplate, get_template, list_templates

BRIEF_KEY = "creative_brief"
MIN_GENRE_CANDIDATES = 3
MAX_GENRE_CANDIDATES = 5
MAX_TONE_CANDIDATES = 4
MAX_SELLING_POINTS = 5

# 题材关键词：用于把创意匹配到真实模板 / 内容包；全部是通用词，不含作品名分支。
GENRE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "xianxia": ("修仙", "修真", "灵气", "境界", "宗门", "灵石", "丹药", "仙", "道", "飞升"),
    "sci_fi": ("科幻", "科技", "机器", "人工智能", "宇宙", "太空", "基因", "赛博", "义体",
               "公司", "能源", "算力", "系统", "代码", "程序", "机械", "维修", "网络"),
    "modern_mystery": ("悬疑", "案件", "侦探", "推理", "证词", "证据", "凶手", "都市", "线索"),
}

TONE_RULES: tuple[tuple[str, tuple[str, ...], str], ...] = (
    ("紧张悬疑", ("悬疑", "追查", "秘密", "真相", "危险", "线索", "阴谋"), "创意涉及追查与隐藏信息"),
    ("成长热血", ("成长", "变强", "升级", "突破", "逆袭", "竞争"), "创意强调角色的成长与跃升"),
    ("冷峻写实", ("现实", "生活", "谋生", "债务", "责任", "职场", "小人物"), "创意贴近现实处境与代价"),
    ("荒诞幽默", ("荒诞", "滑稽", "讽刺", "倒霉", "误会"), "创意本身带有反差与喜剧感"),
    ("温柔治愈", ("治愈", "日常", "守护", "陪伴", "温暖"), "创意关注关系与陪伴"),
    ("史诗宏大", ("文明", "纪元", "战争", "王朝", "势力", "格局"), "创意涉及大尺度的世界与势力"),
)

REASON_BY_GENRE = {
    "xianxia": "创意包含修炼 / 境界 / 宗门方向的要素，可套用该模板的默认目录",
    "sci_fi": "创意包含科技 / 系统 / 能源方向的要素，可套用该模板的默认目录",
    "modern_mystery": "创意包含案件 / 线索 / 现实都市方向的要素，已有可直接运行的演示内容包",
}


class CreativeBriefError(ValueError):
    def __init__(self, code: str, message: str, *, novel_id: str = "") -> None:
        self.code = code
        self.message = message
        self.novel_id = novel_id
        super().__init__(message)

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message, "novel_id": self.novel_id}


class GenreCandidate(StrictModel):
    genre: str = Field(default="", max_length=64)
    label: str = Field(default="", max_length=80)
    template_id: str = Field(default="", max_length=64)
    content_pack_id: str = Field(default="", max_length=96)
    reason: str = Field(default="", max_length=300)


class ToneCandidate(StrictModel):
    tone: str = Field(default="", max_length=64)
    reason: str = Field(default="", max_length=200)


class SellingPointCandidate(StrictModel):
    text: str = Field(default="", max_length=200)
    reason: str = Field(default="", max_length=200)


class CreativeBrief(StrictModel):
    """作者确认后的创意简报；只保存意图，不保存任何故事事实。"""

    original_idea: str = Field(default="", max_length=1000)
    references: list[str] = Field(default_factory=list)
    reader_experience: str = Field(default="", max_length=300)
    selected_genre: str = Field(default="", max_length=64)
    selected_template_id: str = Field(default="", max_length=64)
    selected_content_pack_id: str = Field(default="", max_length=96)
    tone: str = Field(default="", max_length=64)
    selling_points: list[str] = Field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class CreativeSuggestion(StrictModel):
    """一次推荐结果：候选 + 作者当前选择，全部指向真实目录。"""

    novel_id: str = Field(default="", max_length=96)
    original_idea: str = Field(default="", max_length=1000)
    references: list[str] = Field(default_factory=list)
    reader_experience: str = Field(default="", max_length=300)
    genre_candidates: list[GenreCandidate] = Field(default_factory=list)
    tone_candidates: list[ToneCandidate] = Field(default_factory=list)
    selling_point_candidates: list[SellingPointCandidate] = Field(default_factory=list)
    selection: CreativeBrief = Field(default_factory=CreativeBrief)
    source: str = "rule"
    notes: list[str] = Field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


def _keywords_of(genre: str) -> tuple[str, ...]:
    return GENRE_KEYWORDS.get(genre, ())


def _default_provider() -> Any | None:
    """V4-04 §14：legacy 模块的默认 provider 只能来自 `novelforge.ai` 的 Gateway 桥。

    函数内惰性 import → domain 不在模块顶层依赖 ai（边界守卫允许的显式例外）。
    未配置 enabled provider 时返回 None，保持 V3 的确定性行为。
    """

    from novelforge.ai import default_structured_provider

    return default_structured_provider()


def _catalog(project_root: Path) -> tuple[dict[str, GenreTemplate], dict[str, ContentPack]]:
    """真实目录：模板与内容包；候选只能从这里来。"""

    templates = {item.template_id: item for item in list_templates()}
    packs = {item.pack_id: item for item in list_packs_from_project(project_root)}
    return templates, packs


def _match_score(text: str, keywords: tuple[str, ...]) -> int:
    return sum(1 for keyword in keywords if keyword and keyword in text)


def deterministic_candidates(project_root: Path, *, idea: str, references: list[str] | None = None,
                             reader_experience: str = "", offset: int = 0
                             ) -> tuple[list[GenreCandidate], list[ToneCandidate]]:
    """确定性降级路径：只根据真实模板 / 内容包与关键词给出候选，不调用任何模型。"""

    templates, packs = _catalog(project_root)
    text = " ".join([idea or "", *(references or []), reader_experience or ""]).lower()
    scored: list[tuple[int, str, GenreCandidate]] = []
    seen: set[tuple[str, str]] = set()
    for pack_id, pack in sorted(packs.items()):
        for template_id, template in sorted(templates.items()):
            matches_template = template.genre and pack.genre and template.genre == pack.genre
            if not matches_template:
                continue
            key = (template_id, pack_id)
            if key in seen:
                continue
            seen.add(key)
            score = _match_score(text, _keywords_of(template.genre))
            scored.append((score, template_id, GenreCandidate(
                genre=template.genre, label=template.name, template_id=template_id,
                content_pack_id=pack_id,
                reason=REASON_BY_GENRE.get(template.genre, "该模板与内容包可直接运行"))))
    # 只有内容包、没有对应模板的方向也允许作为候选（保留内容包能力）。
    for pack_id, pack in sorted(packs.items()):
        if any(item.content_pack_id == pack_id for _, _, item in scored):
            continue
        score = _match_score(text, _keywords_of(pack.genre))
        scored.append((score, "", GenreCandidate(
            genre=pack.genre, label=pack.title or pack.pack_id, template_id="",
            content_pack_id=pack_id,
            reason="该内容包已可直接运行，可稍后再决定题材模板")))
    # 排序：先按关键词命中，再按模板优先，最后按 id 稳定排序。
    scored.sort(key=lambda item: (-item[0], item[1] == "", item[1], item[2].content_pack_id))
    ordered = [item for _, _, item in scored]
    if ordered and offset:
        pivot = offset % len(ordered)
        ordered = ordered[pivot:] + ordered[:pivot]
    # 保证“至少 3 个候选”：不足时按真实目录再补，补不到就有几个给几个。
    chosen: list[GenreCandidate] = []
    for item in ordered:
        if len(chosen) >= MAX_GENRE_CANDIDATES:
            break
        if item not in chosen:
            chosen.append(item)
    if len(chosen) < MIN_GENRE_CANDIDATES:
        for template_id, template in sorted(templates.items()):
            if len(chosen) >= MIN_GENRE_CANDIDATES:
                break
            if any(item.template_id == template_id and item.content_pack_id for item in chosen):
                continue
            pack_id = next((pid for pid, pack in sorted(packs.items())
                            if pack.genre and pack.genre == template.genre), "")
            chosen.append(GenreCandidate(genre=template.genre, label=template.name,
                                        template_id=template_id, content_pack_id=pack_id,
                                        reason=REASON_BY_GENRE.get(template.genre, "该模板可直接套用")))
    tones = _tone_candidates(text, reader_experience)
    return chosen, tones


def _tone_candidates(text: str, reader_experience: str) -> list[ToneCandidate]:
    pool = reader_experience or text
    rows: list[tuple[int, ToneCandidate]] = []
    for tone, keywords, reason in TONE_RULES:
        score = _match_score(pool, keywords) + _match_score(text, keywords) // 2
        rows.append((score, ToneCandidate(tone=tone, reason=reason)))
    rows.sort(key=lambda item: (-item[0], item[1].tone))
    return [item for _, item in rows[:MAX_TONE_CANDIDATES]]


SELLING_POINT_TEMPLATES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("隐藏规则", "世界表面运行着一套没人明说的规则", ("隐藏", "其实", "秘密", "背后", "地下")),
    ("身份反差", "主角的公开身份与真实处境强烈错位", ("普通", "小人物", "维修", "杂役", "工", "员")),
    ("代价交换", "每一次获得都要付出明确代价", ("代价", "交换", "欠", "债", "换取")),
    ("势力拉扯", "多股势力为了同一份资源互相制衡", ("势力", "公司", "宗门", "组织", "阵营")),
    ("线索拼合", "零散信息逐步拼出一条完整真相", ("线索", "记录", "账", "证据", "数据")),
    ("规则升级", "理解规则本身就是变强的方式", ("规则", "系统", "体系", "权限", "等级")),
    ("关系反噬", "今天的盟友可能变成明天的对手", ("背叛", "对立", "竞争", "反目", "利用")),
)


def deterministic_selling_points(*, idea: str, tone: str = "", genre: str = "",
                                 limit: int = 4) -> list[SellingPointCandidate]:
    text = f"{idea} {tone} {genre}"
    rows: list[tuple[int, SellingPointCandidate]] = []
    for text_value, reason, keywords in SELLING_POINT_TEMPLATES:
        score = _match_score(text, keywords)
        rows.append((score, SellingPointCandidate(text=text_value, reason=reason)))
    rows.sort(key=lambda item: (-item[0], item[1].text))
    return [item for _, item in rows[:max(1, min(limit, MAX_SELLING_POINTS))]]


class CreativeIdeaProvider:
    """把 LLM 提议过滤到真实目录内；越界 id 直接丢弃并记录原因。"""

    def __init__(self, provider: Any | None) -> None:
        self.provider = provider if provider is not None else _default_provider()

    def enrich(self, project_root: Path, *, idea: str, references: list[str],
               reader_experience: str, genre_candidates: list[GenreCandidate],
               tone_candidates: list[ToneCandidate],
               selling_points: list[SellingPointCandidate]
               ) -> tuple[list[GenreCandidate], list[ToneCandidate], list[SellingPointCandidate],
                          list[str]]:
        notes: list[str] = []
        if self.provider is None:
            return genre_candidates, tone_candidates, selling_points, ["AI_UNAVAILABLE"]
        templates, packs = _catalog(project_root)
        prompt = self._prompt(idea, references, reader_experience, genre_candidates,
                              tone_candidates, selling_points)
        try:
            _, draft = self.provider.generate_structured(
                chapter_id="creative_brief", stage="creative_brief_suggestions", skill_name=None,
                prompt=prompt, context={"idea": idea, "references": references,
                                        "reader_experience": reader_experience},
                output_model=None, workspace=None)
        except Exception as exc:  # noqa: BLE001 - AI 失败一律退回确定性候选
            return genre_candidates, tone_candidates, selling_points, [f"AI_ERROR:{exc}"]
        parsed = draft if isinstance(draft, Mapping) else getattr(draft, "__dict__", {})
        if not isinstance(parsed, Mapping):
            return genre_candidates, tone_candidates, selling_points, ["AI_DRAFT_INVALID"]
        # 题材候选：只接受真实模板 / 内容包组合。
        allowed = {(item.template_id, item.content_pack_id) for item in genre_candidates}
        enriched: list[GenreCandidate] = []
        for raw in parsed.get("genre_candidates", []) or []:
            if not isinstance(raw, Mapping):
                continue
            template_id = str(raw.get("template_id", "") or "")
            pack_id = str(raw.get("content_pack_id", "") or "")
            if template_id and template_id not in templates:
                notes.append(f"AI_TEMPLATE_NOT_FOUND:{template_id}")
                continue
            if pack_id and pack_id not in packs:
                notes.append(f"AI_PACK_NOT_FOUND:{pack_id}")
                continue
            if (template_id, pack_id) not in allowed:
                notes.append(f"AI_CANDIDATE_OUTSIDE_CATALOG:{template_id}/{pack_id}")
                continue
            base = next(item for item in genre_candidates
                        if item.template_id == template_id and item.content_pack_id == pack_id)
            enriched.append(base.model_copy(update={
                "label": str(raw.get("label", "") or base.label),
                "reason": str(raw.get("reason", "") or base.reason)}))
        if enriched:
            for item in genre_candidates:
                if item not in enriched:
                    enriched.append(item)
            genre_candidates = enriched[:MAX_GENRE_CANDIDATES]
        tone_texts = {item.tone for item in tone_candidates}
        tones = []
        for raw in parsed.get("tone_candidates", []) or []:
            if not isinstance(raw, Mapping):
                continue
            tone = str(raw.get("tone", "") or "")
            if tone not in tone_texts:
                notes.append(f"AI_TONE_OUTSIDE_CATALOG:{tone}")
                continue
            base = next(item for item in tone_candidates if item.tone == tone)
            tones.append(base.model_copy(update={"reason": str(raw.get("reason", "") or base.reason)}))
        if tones:
            tone_candidates = tones + [item for item in tone_candidates if item not in tones]
        points = {item.text for item in selling_points}
        enriched_points = []
        for raw in parsed.get("selling_point_candidates", []) or []:
            if not isinstance(raw, Mapping):
                continue
            text = str(raw.get("text", "") or "")
            if text not in points:
                continue
            base = next(item for item in selling_points if item.text == text)
            enriched_points.append(base.model_copy(
                update={"reason": str(raw.get("reason", "") or base.reason)}))
        if enriched_points:
            selling_points = enriched_points + [item for item in selling_points
                                                if item not in enriched_points]
        return genre_candidates[:MAX_GENRE_CANDIDATES], tone_candidates[:MAX_TONE_CANDIDATES], \
            selling_points[:MAX_SELLING_POINTS], notes

    @staticmethod
    def _prompt(idea: str, references: list[str], reader_experience: str,
                genre_candidates: list[GenreCandidate], tone_candidates: list[ToneCandidate],
                selling_points: list[SellingPointCandidate]) -> str:
        allowed = [{"template_id": item.template_id, "content_pack_id": item.content_pack_id,
                    "label": item.label} for item in genre_candidates]
        tones = [item.tone for item in tone_candidates]
        points = [item.text for item in selling_points]
        return (
            "你在帮助作者确定小说方向。只能从下面给出的候选中挑选并补充理由，"
            "禁止发明新的模板、内容包、基调或卖点。\n"
            f"创意：{idea}\n参考作品：{references}\n想要的读者体验：{reader_experience}\n"
            f"允许的题材候选：{allowed}\n允许的基调：{tones}\n允许的卖点：{points}\n"
            "输出 JSON：{genre_candidates:[{template_id,content_pack_id,label,reason}],"
            "tone_candidates:[{tone,reason}],selling_point_candidates:[{text,reason}]}"
        )


def suggest_creative_brief(project_root: Path, novel_id: str, *, idea: str,
                           references: list[str] | None = None, reader_experience: str = "",
                           selected_genre: str = "", regenerate: bool = False,
                           provider: Any | None = None) -> CreativeSuggestion:
    """生成一次题材 / 基调 / 卖点候选；不写任何内容，保存由 save_creative_brief 负责。"""

    idea = (idea or "").strip()
    if len(idea) < 4:
        raise CreativeBriefError("IDEA_TOO_SHORT", "请至少写一句完整的小说创意", novel_id=novel_id)
    refs = [item.strip() for item in (references or []) if item and item.strip()]
    offset = 1 if regenerate else 0
    genre_candidates, tone_candidates = deterministic_candidates(
        project_root, idea=idea, references=refs, reader_experience=reader_experience, offset=offset)
    if selected_genre:
        # 作者指定方向时，把匹配该方向的候选提到最前（不改动候选池本身）。
        genre_candidates.sort(key=lambda item: (item.genre != selected_genre, item.label))
    selling_points = deterministic_selling_points(
        idea=idea, tone=tone_candidates[0].tone if tone_candidates else "",
        genre=genre_candidates[0].genre if genre_candidates else "")
    source = "rule"
    genre_candidates, tone_candidates, selling_points, notes = CreativeIdeaProvider(provider)\
        .enrich(project_root, idea=idea, references=refs, reader_experience=reader_experience,
                genre_candidates=genre_candidates, tone_candidates=tone_candidates,
                selling_points=selling_points)
    if provider is not None and "AI_UNAVAILABLE" not in notes and not any(
            item.startswith("AI_ERROR") or item.startswith("AI_DRAFT_INVALID") for item in notes):
        source = "ai"
    first = genre_candidates[0] if genre_candidates else None
    selection = CreativeBrief(
        original_idea=idea, references=refs, reader_experience=reader_experience,
        selected_genre=first.genre if first else selected_genre,
        selected_template_id=first.template_id if first else "",
        selected_content_pack_id=first.content_pack_id if first else "",
        tone=tone_candidates[0].tone if tone_candidates else "",
        selling_points=[item.text for item in selling_points[:3]])
    return CreativeSuggestion(novel_id=novel_id, original_idea=idea, references=refs,
                              reader_experience=reader_experience,
                              genre_candidates=genre_candidates, tone_candidates=tone_candidates,
                              selling_point_candidates=selling_points, selection=selection,
                              source=source, notes=notes)


def validate_selection(project_root: Path, brief: CreativeBrief) -> CreativeBrief:
    """保存前校验：作者选择的模板 / 内容包必须真实存在。"""

    templates, packs = _catalog(project_root)
    if brief.selected_template_id and brief.selected_template_id not in templates:
        raise CreativeBriefError("TEMPLATE_NOT_FOUND",
                                 f"找不到题材模板：{brief.selected_template_id}")
    if brief.selected_content_pack_id and brief.selected_content_pack_id not in packs:
        raise CreativeBriefError("CONTENT_PACK_NOT_FOUND",
                                 f"找不到内容包：{brief.selected_content_pack_id}")
    return brief


def save_creative_brief(project_root: Path, novel_id: str, brief: CreativeBrief | Mapping[str, Any]
                        ) -> tuple[NovelProfile, CreativeBrief]:
    """把确认结果写进 NovelProfile（设计态），不写任何 StoryState 事实。"""

    candidate = brief if isinstance(brief, CreativeBrief) else CreativeBrief.model_validate(dict(brief))
    if not candidate.original_idea.strip():
        raise CreativeBriefError("IDEA_REQUIRED", "原始创意不能为空", novel_id=novel_id)
    candidate = validate_selection(project_root, candidate)
    repository = NovelProfileRepository(project_root)
    profile = repository.ensure(novel_id)
    world_profile = dict(profile.world_profile)
    world_profile[BRIEF_KEY] = candidate.as_dict()
    updates: dict[str, Any] = {"world_profile": world_profile}
    if candidate.selected_genre:
        updates["genre"] = candidate.selected_genre
    if candidate.tone:
        updates["tone"] = candidate.tone
    if candidate.selected_template_id and not profile.template_id:
        updates["template_id"] = candidate.selected_template_id
    saved = repository.save(profile.model_copy(update=updates))
    return saved, candidate


def load_creative_brief(project_root: Path, novel_id: str) -> CreativeBrief | None:
    """读取已保存的创意简报；没有时返回 None（刷新后可恢复）。"""

    profile = NovelProfileRepository(project_root).ensure(novel_id)
    payload = profile.world_profile.get(BRIEF_KEY)
    if not isinstance(payload, Mapping):
        return None
    return CreativeBrief.model_validate(dict(payload))


def suggestion_from_profile(project_root: Path, novel_id: str, *, provider: Any | None = None
                            ) -> CreativeSuggestion | None:
    """基于已保存的创意简报重新给出候选（用于页面刷新后的恢复）。"""

    brief = load_creative_brief(project_root, novel_id)
    if brief is None:
        return None
    result = suggest_creative_brief(project_root, novel_id, idea=brief.original_idea,
                                    references=brief.references,
                                    reader_experience=brief.reader_experience,
                                    selected_genre=brief.selected_genre, provider=provider)
    # 作者已确认的内容优先保留。
    result.selection = brief
    return result
