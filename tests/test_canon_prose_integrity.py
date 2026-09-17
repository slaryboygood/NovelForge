"""C12：Writer-visible 叙事完整性防线（人工审核暴露的 6 类盲区）。"""

from __future__ import annotations

from novelforge.story_engine.canon.prose import (
    audit_prose_report,
    chapter_frame_findings,
    cross_field_findings,
    dog_role_object_findings,
    dog_role_presence_findings,
    dog_role_recompute,
    dog_role_alignment,
    first_occurrence_findings,
    future_canon_leak_findings,
    irreversible_state_findings,
    narrative_lifecycle_findings,
    orphaned_reference_fragments,
    validate_sample_pack,
    within_chapter_state_findings,
)


def test_orphaned_reference_fragments_catch_human_found_cases() -> None:
    samples = ["承接 的投靠先例", "按 的先例", "中铭牌编号", "已在被确认", "把的首次开门",
               "而的塔回应", "与 确认的阿灰编号"]
    for sample in samples:
        findings = orphaned_reference_fragments(sample, where="field")
        assert findings and all(item.code == "ORPHANED_REFERENCE_FRAGMENT"
                                for item in findings), sample
    for clean in ("他把半块干粮掰给阿灰", "门开后队伍沿长廊深入", "他第一次主动拧开收音机"):
        assert orphaned_reference_fragments(clean, where="field") == []


def test_audit_prose_spam_and_anchor_repetition() -> None:
    report = audit_prose_report([
        "这是首次回应之后的连锁后果",
        "韩彻把编号记录重新解释为体系的延伸",
        "该编号在首次确认之后使用的登记格式",
        "而不是首次事件，只是后续验证节点"])
    codes = {item.code for item in report.findings}
    assert "CANON_AUDIT_PROSE_SPAM" in codes
    assert report.density >= 0.75
    action = audit_prose_report(["他带人拆下门板", "阿灰先闻到水味", "队伍趁夜把货推进去"])
    assert action.findings == [] and action.audit_events == 0


def test_dog_role_requires_actual_action() -> None:
    codes = {item.code for item in dog_role_alignment({
        "dog_role": "absent", "title": "夜哨", "goal": "绕营一周",
        "concrete_events": ["韩彻带阿灰绕营一周", "他数了火位", "风从北边压过来"]})}
    assert "DOG_ROLE_PRESENCE_MISMATCH" in codes
    passive = {item.code for item in dog_role_alignment({
        "dog_role": "supportive", "title": "谷底", "goal": "救狗",
        "dog_action": "阿灰被困在塌陷口，等人把它挖出来",
        "concrete_events": ["阿灰被困在塌陷口", "韩彻下谷开挖", "余震压住通道"]})}
    assert "DOG_ROLE_ACTION_ALIGNMENT" in passive
    good = dog_role_alignment({
        "dog_role": "involved", "title": "巡边", "goal": "确认退路",
        "dog_action": "阿灰贴地嗅出踩坏的草，把队伍拦在坡下",
        "concrete_events": ["阿灰贴地嗅出踩坏的草", "韩彻改走坡下", "伏击点被绕开"]})
    assert good == []


def test_narrative_lifecycle_conflict() -> None:
    findings = narrative_lifecycle_findings([
        {"id": "chA", "events": ["阿灰离开据点，三天后归队"]},
        {"id": "chB", "goal": "处理阿灰未归后的空缺", "events": ["守夜人手不够"]}])
    assert [item.code for item in findings] and all(
        item.code == "NARRATIVE_EVENT_LIFECYCLE_CONFLICT" for item in findings)
    clean = narrative_lifecycle_findings([
        {"id": "ch1", "events": ["阿灰独自离队，三天没有回来"]},
        {"id": "ch2", "events": ["阿灰自己走回据点，带回猎团的消息"]}])
    assert clean == []


def test_cross_field_semantic_mismatch() -> None:
    findings = cross_field_findings({
        "goal": "调查塔基最早刻写，判断重刻年代",
        "concrete_events": ["韩彻清理塔基泥土", "发现基座叠着两层刻写", "把两层拓印并排比照"],
        "decision": "韩彻以一人一狗名义签署新规矩",
        "world_state_change": "废土第一条共同规矩成立"})
    assert {item.where for item in findings} == {"decision", "world_state_change"}
    clean = cross_field_findings({
        "goal": "调查塔基最早刻写，判断重刻年代",
        "concrete_events": ["韩彻清理塔基泥土", "发现两层刻写", "拓印比照确认后世重刻"],
        "decision": "暂不破坏塔体，先查明重刻者与年代",
        "world_state_change": "确认塔基存在原刻与后世重刻两层记录"})
    assert clean == []


def test_sample_pack_integrity() -> None:
    bad = validate_sample_pack(
        [{"chapter": f"ch{index:03d}", "volume": 2, "category": "normal"}
         for index in range(1, 6)] +
        [{"chapter": "ch002", "volume": 4, "category": "conflict"},
         {"chapter": "ch002", "volume": 4, "category": "climax"}],
        volumes=[2, 4], expected_per_volume=5, min_random=18)
    codes = {item.code for item in bad}
    assert {"SAMPLE_ENTRY_COUNT", "SAMPLE_DUPLICATE_CHAPTER", "SAMPLE_PER_VOLUME_COUNT",
            "SAMPLE_RANDOM_COUNT", "SAMPLE_CHAPTER_MULTI_CATEGORY"} <= codes
    good = validate_sample_pack(
        [{"chapter": f"v{volume}c{index}", "volume": volume,
          "category": "normal" if index <= 4 else "climax"}
         for volume in (2, 4, 6, 7, 8, 9, 10) for index in range(1, 6)],
        volumes=[2, 4, 6, 7, 8, 9, 10], expected_per_volume=5, min_random=18)
    assert good == []


def test_stale_chapter_frame_detects_half_repaired_chapter() -> None:
    findings = chapter_frame_findings({
        "goal": "审讯活口，从货源单据里找出内应",
        "concrete_events": ["韩彻把活口关进旧仓", "活口交代接头暗号", "比对货单锁定副手"],
        "trigger": "伏击队在灰雾路段动手，箭擦过车辕",
        "protagonist_action": "韩彻用残响外放震退伏击",
        "opposition": "阿灰扑咬伏击者",
        "end_state": "韩彻带人货回集"})
    assert {item.where for item in findings} >= {"trigger", "protagonist_action"}
    clean = chapter_frame_findings({
        "goal": "审讯活口，从货源单据里找出内应",
        "concrete_events": ["韩彻把活口关进旧仓", "活口交代接头暗号", "比对货单锁定副手"],
        "trigger": "仓棚里多出一个被绑的活口",
        "protagonist_action": "韩彻先给他水，再问谁付的钱",
        "opposition": "活口不肯先开口",
        "end_state": "内应被锁定但未惊动"})
    assert clean == []


def test_first_occurrence_self_contradiction() -> None:
    findings = first_occurrence_findings({
        "first_occurrence_event_id": "EVENT_ZERO_LAYER_GATE_FIRST_OPEN",
        "concrete_events": ["前六次尝试均失败，门体只升温",
                            "他判断这是第零层门禁首次打开后系统对重复接触的延迟响应，而非门从未被开启过",
                            "第七次尝试门开"]})
    assert [item.code for item in findings] and all(
        item.code == "FIRST_OCCURRENCE_SELF_CONTRADICTION" for item in findings)
    clean = first_occurrence_findings({
        "first_occurrence_event_id": "EVENT_ZERO_LAYER_GATE_FIRST_OPEN",
        "concrete_events": ["前六次尝试均失败", "第七次把铭牌按进凹槽", "门体第一次打开"]})
    assert clean == []


def test_irreversible_state_repeated() -> None:
    findings = irreversible_state_findings([
        {"id": "ch350", "events": ["三方同时抵达第零层，防御系统失控"]},
        {"id": "ch379", "events": ["韩彻决定永久封闭第零层"]},
        {"id": "ch380", "events": ["第零层永久封死，入口坍塌"]}])
    assert [item.code for item in findings] == ["IRREVERSIBLE_STATE_REPEATED"]
    clean = irreversible_state_findings([
        {"id": "ch350", "events": ["韩彻紧急锁闭第零层核心门禁"]},
        {"id": "ch379", "events": ["老鸦带人爆破主通道，把第零层永久封死"]}])
    assert clean == []


def test_within_chapter_state_contradiction() -> None:
    findings = within_chapter_state_findings({
        "protagonist_action": "带阿灰出发去旧观测通道",
        "loss": "阿灰留在据点",
        "end_state": "队伍又带阿灰出发"})
    assert [item.code for item in findings] == ["WITHIN_CHAPTER_STATE_CONTRADICTION"]
    assert within_chapter_state_findings({
        "protagonist_action": "带阿灰出发去旧观测通道",
        "loss": "风声盖住脚步",
        "end_state": "阿灰先一步探到通道口"}) == []


def test_dog_role_object_vs_action() -> None:
    findings = dog_role_object_findings({
        "dog_role": "supportive",
        "concrete_events": ["缝合会代表要求引用阿灰的编号", "韩彻拒绝交出编号", "阿灰被留在营地"],
        "dog_action": "阿灰被留在营地"})
    assert [item.code for item in findings] == ["DOG_ROLE_OBJECT_NOT_SUPPORTIVE"]
    assert dog_role_object_findings({
        "dog_role": "supportive",
        "concrete_events": ["阿灰贴地嗅出踩坏的草", "韩彻改走坡下", "伏击点被绕开"],
        "dog_action": "阿灰贴地嗅出踩坏的草"}) == []


def test_stale_frame_covers_decision_and_legacy_salt_road_structures() -> None:
    """真实结构：events 已改成审讯/改道/封锁，decision/trigger/action 仍是旧伏击 frame。"""

    structures = [
        {"goal": "审讯活口，从货源单据里找出内应",
         "concrete_events": ["韩彻把活口关进旧仓，先给他水", "活口交代接头暗号", "比对货单锁定副手"],
         "decision": "公开协议陷阱，宣布商路归铁锈集控制",
         "trigger": "伏击队在灰雾路段动手，箭擦过车辕",
         "protagonist_action": "韩彻用残响外放震退伏击",
         "turn": "弃货保人"},
        {"goal": "在谈判破裂后把盐路的实际控制权拿到手里",
         "concrete_events": ["管事拒绝交出报备权", "商队改走北线被地裂卡住", "回来接受按趟结算"],
         "decision": "弃部分货保人", "turn": "弃货换全员撤出"},
        {"goal": "顶住封锁并让内应自己暴露",
         "concrete_events": ["封锁方扣下两车货", "改走小水道按时送货", "内应在接头点落网"],
         "decision": "弃一箱货换全员撤出"},
        {"goal": "在低频谷入口完成第一次生态踏勘",
         "concrete_events": ["记录谷口低频节律", "标出三处下撤点", "沿岩脊改道"],
         "decision": "放弃材料先救阿灰", "turn": "外放救出阿灰"},
        {"goal": "处理塌陷救援之后的医疗、隔离与关系后果",
         "concrete_events": ["送阿灰进隔离棚", "分箱封存骨片与拓印", "把再入谷的决定权交回阿灰"],
         "decision": "冒险外放救阿灰"},
    ]
    for structure in structures:
        findings = chapter_frame_findings(structure)
        assert findings, structure["goal"]
    clean = chapter_frame_findings({
        "goal": "审讯活口，从货源单据里找出内应",
        "concrete_events": ["韩彻把活口关进旧仓，先给他水", "活口交代接头暗号", "比对货单锁定副手"],
        "decision": "不抓副手，继续让他按原路线报备，放长线等下一次接头",
        "trigger": "活口开口要水，条件是可以先谈接头暗号",
        "protagonist_action": "韩彻先给他水，再问谁付的钱",
        "turn": "改单上的内印把内应锁定在报备环节"})
    assert clean == []


def test_dog_role_presence_contract() -> None:
    assert [item.code for item in
            dog_role_presence_findings("offscreen_effect", physical_presence=True)] == \
        ["DOG_ROLE_PRESENCE_MISMATCH"]
    assert [item.code for item in
            dog_role_presence_findings("supportive", physical_presence=False)] == \
        ["DOG_ROLE_PRESENCE_MISMATCH"]
    assert dog_role_presence_findings("independent", physical_presence=True) == []
    assert dog_role_presence_findings("offscreen_effect", physical_presence=False) == []
    assert dog_role_recompute({
        "physical_presence": True, "goal": "招揽阿灰",
        "concrete_events": ["阿灰自己来回走了两趟，最后自己跟着那只同类走出旧路钉"],
        "dog_action": "阿灰自己跟随同类离开"}) == "independent"
    assert dog_role_recompute({
        "physical_presence": False, "goal": "处理阿灰离开后的第一夜",
        "concrete_events": ["据点会议上有人要求追回阿灰", "韩彻拒绝用锁链"]}) == "offscreen_effect"


def test_future_canon_leak_natural_language_reference() -> None:
    findings = future_canon_leak_findings([
        {"id": "ch358", "display_number": 358, "goal": "封存第三柜",
         "events": ["韩彻按共守规矩与最终投票所确立的公开规则封存第三柜"]},
        {"id": "ch559", "display_number": 559, "goal": "正式签署共守规矩",
         "events": ["各方依次落笔，新秩序成立"]}])
    assert {item.code for item in findings} == {"FUTURE_CANON_LEAK"}
    assert {item.where for item in findings} == {"ch358"}
