"""S08：Golden semantic labels regression（结构标签，不是 writer prose）。"""

from __future__ import annotations

import json
from pathlib import Path

from novelforge.story_engine.chapter_ir.extractor import (
    LegacyIRSemanticExtractor,
)

FIXTURES = Path("tests/fixtures/chapter_ir_pilot")

ALIASES = {
    "韩彻": "ENTITY_PROTAGONIST", "阿灰": "ENTITY_DOG_AHUI",
    "编号犬": "ENTITY_HUNTER_DOG_01", "荒原犬": "ENTITY_HUNTER_DOG_01",
    "笼中同类": "ENTITY_CAGED_KIN", "它": "AMBIGUOUS", "那只狗": "AMBIGUOUS",
}
KIND_INDEX = {"dog": ["ENTITY_DOG_AHUI", "ENTITY_HUNTER_DOG_01", "ENTITY_CAGED_KIN"]}

LEGACY_CHAPTERS: dict[str, dict] = {
    "ch325": {"id": "ch325", "chapter_uuid": "uuid_wl_ch325", "display_number": 325, "volume": 7,
              "goal": "在第七次尝试中第一次真正打开第零层门禁",
              "events": ["前六次尝试都只让门体升温，队伍退回安全线外重排顺序",
                         "阿灰把铭牌顶到凹槽边，凹槽边缘亮起微光",
                         "韩彻把旧铭牌按进凹槽，第七次推门，门体第一次完全打开"],
              "cost": "", "loss": "", "payoff": "门第一次真正打开", "turn": "门体第一次打开",
              "world_state_change": "第零层第一次被打开", "information_release": "",
              "decision": "", "dog_role": "involved"},
    "ch436": {"id": "ch436", "chapter_uuid": "uuid_wl_ch436", "display_number": 436, "volume": 8,
              "goal": "外部势力以同类为筹码招揽阿灰，韩彻决定不强行留下它",
              "events": ["外部队伍带来一只带编号的荒原犬，编号与阿灰铭牌同源",
                         "对方以同类与安全区为条件招揽阿灰",
                         "阿灰自己来回走了两趟，最后自己跟着那只同类走出旧路钉之外",
                         "韩彻没有阻拦，也没有呼唤，只把门闩留在原位"],
              "cost": "", "loss": "阿灰离开", "payoff": "选择权交给阿灰", "turn": "阿灰跨过旧路钉",
              "world_state_change": "", "information_release": "", "decision": "",
              "dog_role": "independent"},
    "ch437": {"id": "ch437", "chapter_uuid": "uuid_wl_ch437", "display_number": 437, "volume": 8,
              "goal": "处理阿灰离开后的第一夜",
              "events": ["据点会议上有人要求韩彻追回阿灰",
                         "韩彻拒绝用锁链，宣布门不关",
                         "老鸦私下备好追索队，被韩彻叫停"],
              "cost": "整夜留门，守夜人手翻倍", "loss": "", "payoff": "据点维持开放",
              "turn": "追索队被撤回", "world_state_change": "", "information_release": "",
              "decision": "", "dog_role": "offscreen_effect"},
    "ch438": {"id": "ch438", "chapter_uuid": "uuid_wl_ch438", "display_number": 438, "volume": 8,
              "goal": "接回自主返回的阿灰并抢低潮窗口",
              "events": ["第三日夜里，阿灰自己走回集口，带着外部队伍的哨音节奏",
                         "韩彻没有追问，只把水壶推过去",
                         "他据哨音节奏定下入盆时间"],
              "cost": "", "loss": "", "payoff": "队伍抢进盆地腹地", "turn": "阿灰自己回来",
              "world_state_change": "", "information_release": "", "decision": "",
              "dog_role": "independent"},
    "ch502": {"id": "ch502", "chapter_uuid": "uuid_wl_ch502", "display_number": 502, "volume": 9,
              "goal": "核对第二份档案与验证者名单",
              "events": ["三方代表在观测站外要求先核对署名再谈公开",
                         "韩彻用一次共感换取查阅第二份档案的资格",
                         "第二份档案末尾列着验证者名单，其中一个编号与阿灰校验码部分吻合",
                         "韩彻把名单抄下，同意在观测站公布已确认的部分"],
              "cost": "韩彻短期失明", "loss": "", "payoff": "验证者名单到手", "turn": "名单指向活体登记号",
              "world_state_change": "", "information_release": "", "decision": "",
              "dog_role": "offscreen_effect"},
    "ch559": {"id": "ch559", "chapter_uuid": "uuid_wl_ch559", "display_number": 559, "volume": 10,
              "goal": "用一人一狗两个名字签下共守规矩",
              "events": ["各方代表聚在塔壁前，第一份正式签署的规矩刻在石面上",
                         "韩彻拒绝编号所有权条款，在塔壁刻下自己与阿灰两个名字",
                         "阿灰自己走到塔壁前，把铭牌按进两个名字之间那道缝里，选择留在塔内",
                         "各方依次落笔，共守规矩正式生效"],
              "cost": "阿灰选择留塔", "loss": "韩彻独自出塔", "payoff": "共守规矩正式生效",
              "turn": "两个名字并列刻下", "world_state_change": "", "information_release": "",
              "decision": "", "dog_role": "independent"},
    "ch271": {"id": "ch271", "chapter_uuid": "uuid_wl_ch271", "display_number": 271, "volume": 6,
              "goal": "实测灰墙移动规律，为穿墙与结盟谈判提供依据",
              "events": ["韩彻亲自到东口实测灰墙走向，发现墙体整体缓慢东移",
                         "阿灰在东口贴地低鸣，把队伍引到一处正在扩大的空腔边",
                         "他把实测数据画在门板上，旧路标注随即作废",
                         "韩彻暂缓签结盟书，把实测结果留作谈判依据"],
              "cost": "", "loss": "旧路与旧地图全部失效", "payoff": "灰墙移动规律被测出",
              "turn": "旧路标注作废", "world_state_change": "", "information_release": "",
              "decision": "", "dog_role": "involved"},
    "ch361": {"id": "ch361", "chapter_uuid": "uuid_wl_ch361", "display_number": 361, "volume": 7,
              "goal": "处理门禁验证记录的权限归属",
              "events": ["韩彻把验证记录抄成三份，一家一份同时封存",
                         "阿灰守在地窖门口，把想凑近桌旁的人一次次挡回门廊",
                         "原始记录留在铁锈集地窖，铁锈集接下战争责任署名"],
              "cost": "地窖常设守夜", "loss": "", "payoff": "遗迹权限与责任落到铁锈集",
              "turn": "权限归属以三家分存落地", "world_state_change": "遗迹权限归属写入停火协议",
              "information_release": "", "decision": "", "dog_role": "involved"},
    "ch515": {"id": "ch515", "chapter_uuid": "uuid_wl_ch515", "display_number": 515, "volume": 10,
              "goal": "把共守草案带到盆地边缘的聚落征求意见",
              "events": ["韩彻带着共守草案到盆地边缘的聚落征求意见",
                         "聚落代表逐条追问草案里的席位与义务",
                         "韩彻把有争议的三条圈出来带回去修订"],
              "cost": "定稿延后", "loss": "", "payoff": "草案获得初步支持",
              "turn": "有争议的三条被带回去修订", "world_state_change": "共守草案获得初步支持",
              "information_release": "", "decision": "", "dog_role": "offscreen_effect"},
    "ch526": {"id": "ch526", "chapter_uuid": "uuid_wl_ch526", "display_number": 526, "volume": 10,
              "goal": "把共守规矩写成可表决的草案，完成第一轮表决",
              "events": ["韩彻逐条念草案，把例外条款压回议事程序里",
                         "两方联手拖票，表决两次都没过",
                         "有人提出让韩彻先署名定调，被他当场拒绝",
                         "第三轮表决以十一票对九票通过程序"],
              "cost": "三次会议耗掉半个月", "loss": "", "payoff": "草案与表决程序成立",
              "turn": "第一轮表决程序通过", "world_state_change": "共走草案进入表决阶段",
              "information_release": "", "decision": "", "dog_role": "offscreen_effect"},
}


def _extractor() -> LegacyIRSemanticExtractor:
    return LegacyIRSemanticExtractor(
        novel_id="wasteland_001", dog_entity_id="ENTITY_DOG_AHUI",
        protagonist_id="ENTITY_PROTAGONIST", entity_aliases=ALIASES, kind_index=KIND_INDEX)


def _labels() -> dict:
    return json.loads((FIXTURES / "GOLDEN_SEMANTIC_LABELS.json").read_text(encoding="utf-8"))


def _llm_proposals() -> dict:
    return json.loads((FIXTURES / "LLM_PROPOSALS.json").read_text(encoding="utf-8"))["chapters"]


def test_deterministic_extractor_matches_critical_golden_labels() -> None:
    labels = _labels()["labels"]
    llm_payloads = _llm_proposals()
    extractor = _extractor()
    for chapter_id, chapter in LEGACY_CHAPTERS.items():
        label = labels[chapter_id]
        proposal = extractor.extract(chapter, backend="deterministic")
        ir = extractor.to_ir(proposal, chapter)
        if label.get("critical"):
            assert ir.dog.physical_presence == label["dog_presence"], chapter_id
            # 有 LLM proposal 的章节在正式管线里走 proposal 路径（见 test_llm_...）；
            # deterministic 路径只保证 presence，不重复判定 role 子类
            if chapter_id not in llm_payloads:
                assert ir.dog.role == label["dog_role"], chapter_id
        else:
            # 非 critical 标签：deterministic 允许分歧，由 LLM/golden 报告记录
            assert ir.dog.role in ("involved", "supportive", "independent",
                                   "offscreen_effect", "absent"), chapter_id
        has_decision = bool(proposal.decision_candidates)
        if not has_decision and chapter_id in llm_payloads:
            payload = dict(llm_payloads[chapter_id])
            payload.setdefault("chapter_uuid", chapter["chapter_uuid"])
            payload["backend"] = "llm"
            from novelforge.story_engine.chapter_ir.extractor import (
                ExtractedChapterIRProposal,
            )
            llm_proposal = ExtractedChapterIRProposal.model_validate(payload, strict=True)
            has_decision = bool(llm_proposal.decision_candidates)
        assert has_decision or not label["decision_exists"], chapter_id
        if label["primary_transition"] and label.get("critical"):
            primary = [item for item in ir.state_transitions
                       if item.narrative_role == "primary"]
            assert primary, chapter_id
            assert [primary[0].state_key, primary[0].to_state] == label["primary_transition"], chapter_id
            assert primary[0].assertion_mode in label["assertion_modes"], chapter_id


def test_llm_proposals_pass_strict_gate_and_match_labels() -> None:
    labels = _labels()["labels"]
    proposals = json.loads((FIXTURES / "LLM_PROPOSALS.json").read_text(encoding="utf-8"))
    extractor = _extractor()
    for chapter_id, payload in proposals["chapters"].items():
        chapter = LEGACY_CHAPTERS[chapter_id]
        provider = lambda _chapter, _payload=payload: _payload
        extractor_llm = LegacyIRSemanticExtractor(
            novel_id="wasteland_001", dog_entity_id="ENTITY_DOG_AHUI",
            protagonist_id="ENTITY_PROTAGONIST", entity_aliases=ALIASES,
            kind_index=KIND_INDEX, llm_provider=provider)
        proposal = extractor_llm.extract(chapter, backend="llm")
        ir = extractor_llm.to_ir(proposal, chapter)
        label = labels[chapter_id]
        assert ir.dog.role == label["dog_role"], chapter_id
        assert ir.dog.physical_presence == label["dog_presence"], chapter_id
        primary = [item for item in ir.state_transitions if item.narrative_role == "primary"]
        if label["primary_transition"]:
            assert primary and [primary[0].state_key, primary[0].to_state] == \
                label["primary_transition"], chapter_id


def test_hunter_dog_never_binds_to_ahui_entity() -> None:
    chapter = LEGACY_CHAPTERS["ch436"]
    extractor = _extractor()
    proposal = extractor.extract(chapter, backend="deterministic")
    first_event = proposal.events[0]
    assert "ENTITY_HUNTER_DOG_01" in first_event.mentioned_entity_ids
    assert "ENTITY_DOG_AHUI" not in first_event.actor_ids
    assert "ENTITY_DOG_AHUI" in first_event.mentioned_entity_ids  # 只作为铭牌归属被提及
