# Canon Defense Coverage Matrix（C11）

来源：`run_mutation_suite()` 的真实执行结果（fault injection → 预期防线 → StoryState / Canon / Outline digest 校验）。
测试：`tests/test_canon_mutation_unit.py`、`tests/test_canon_mutation_integration.py`；模块：`src/novelforge/story_engine/canon/mutation.py`。

## 汇总

- mutation total：**51**（passed 51 / failed 0 / blocked 0）
- mutation_kill_rate：**100.00%**
- state_pollution_rate：**0.00%**（0 个污染失败）
- undetected mutations：无
- expected detector mismatch：无

## 分层覆盖（by_layer）

| target layer | total | passed | failed |
| --- | --- | --- | --- |
| bootstrap | 4 | 4 | 0 |
| canon | 4 | 4 | 0 |
| context | 4 | 4 | 0 |
| graph | 11 | 11 | 0 |
| outline | 2 | 2 | 0 |
| planner | 4 | 4 | 0 |
| repository | 3 | 3 | 0 |
| schema | 3 | 3 | 0 |
| semantic | 3 | 3 | 0 |
| source_ref | 4 | 4 | 0 |
| writer | 9 | 9 | 0 |

## 防线命中统计（by_detector）

| detector | passed cases |
| --- | --- |
| CanonAwareOutlinePlanner.plan | 1 |
| CanonAwareOutlinePlanner.plan + CanonService.update_fact | 1 |
| CanonAwareOutlinePlanner.plan + sanitize_writer_text | 2 |
| CanonAwareOutlinePlanner.shadow_plan | 1 |
| CanonBootstrap.bootstrap | 1 |
| CanonBootstrap.coverage | 1 |
| CanonBootstrap.rebuild | 2 |
| CanonContextBuilder._apply_budget | 1 |
| CanonContextBuilder.character_context | 1 |
| CanonContextBuilder.character_context + CanonGraphValidator.knowledge_leak | 1 |
| CanonContextBuilder.planner_context | 1 |
| CanonContextBuilder.writer_context | 1 |
| CanonGraphValidator.ability_before_unlock | 1 |
| CanonGraphValidator.causal_cycle | 1 |
| CanonGraphValidator.dead_character_action | 1 |
| CanonGraphValidator.identity_before_acquired | 1 |
| CanonGraphValidator.location_impossibility | 1 |
| CanonGraphValidator.payoff_before_reveal | 1 |
| CanonGraphValidator.prerequisite_missing | 1 |
| CanonGraphValidator.reveal_before_plant | 1 |
| CanonGraphValidator.run | 1 |
| CanonOutlineFlags / CanonAwareOutlinePlanner | 1 |
| ChapterLineageStore.merge | 1 |
| ChapterLineageStore.renumber + CanonRepository.renumber_render_refs | 1 |
| ChapterLineageStore.split + SourceReferenceValidator | 1 |
| SchemaGate.validate_chapter_plan | 3 |
| SemanticIndex.classify_relation | 3 |
| SourceReferenceValidator.promotion_conflicts | 2 |
| SourceReferenceValidator.validate_refs | 4 |
| StoryStateCanonSync.sync + CanonRepository.find_mapping | 1 |
| prose.audit_prose_report | 1 |
| prose.chapter_frame_findings | 1 |
| prose.cross_field_findings | 1 |
| prose.dog_role_alignment | 1 |
| prose.dog_role_object_findings | 1 |
| prose.first_occurrence_findings | 1 |
| prose.irreversible_state_findings | 1 |
| prose.narrative_lifecycle_findings | 1 |
| prose.orphaned_reference_fragments | 1 |
| prose.validate_sample_pack | 1 |
| prose.within_chapter_state_findings | 1 |

## 逐条 mutation

| Mutation ID | Injected fault | Target layer | Expected detector | Actual detector | Persist blocked? | StoryState clean? | Canon clean? | Outline clean? | PASS/FAIL |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| MUT-001 | 错误 source：伏击章被声明支持「门禁首次开门」 | source_ref | SourceReferenceValidator.validate_refs | SourceReferenceValidator.validate_refs | blocked | clean | clean | clean | PASS |
| MUT-002 | 缺失 source：引用不存在的 fact / UUID | source_ref | SourceReferenceValidator.validate_refs | SourceReferenceValidator.validate_refs | blocked | clean | clean | clean | PASS |
| MUT-003 | 未来泄漏：当前章节引用未来事实 | source_ref | SourceReferenceValidator.validate_refs | SourceReferenceValidator.validate_refs | blocked | clean | clean | clean | PASS |
| MUT-004 | planned 当成 happened：状态不一致 | source_ref | SourceReferenceValidator.validate_refs | SourceReferenceValidator.validate_refs | blocked | clean | clean | clean | PASS |
| MUT-005 | 改写 happened fact：描述 / 状态 / 不可变标记 | canon | CanonAwareOutlinePlanner.plan + CanonService.update_fact | CanonAwareOutlinePlanner.plan + CanonService.update_fact | blocked | clean | clean | clean | PASS |
| MUT-006 | planned → occurred 重复：同一事件出现两个 canonical occurrence | canon | SourceReferenceValidator.promotion_conflicts | SourceReferenceValidator.promotion_conflicts | blocked | clean | clean | clean | PASS |
| MUT-007 | 知识泄漏：角色在 unknown 状态下拿到真相 | context | CanonContextBuilder.character_context + CanonGraphValidator.knowledge_leak | CanonContextBuilder.character_context + CanonGraphValidator.knowledge_leak | blocked | clean | clean | clean | PASS |
| MUT-008 | 误信被真相覆盖：早期上下文直接给出事实 | context | CanonContextBuilder.character_context | CanonContextBuilder.character_context | blocked | clean | clean | clean | PASS |
| MUT-009 | 未来揭示泄漏：writer context 带出未到期的 payoff | writer | CanonContextBuilder.writer_context | CanonContextBuilder.writer_context | blocked | clean | clean | clean | PASS |
| MUT-010 | 伏笔倒置：reveal 在 plant 之前 | graph | CanonGraphValidator.reveal_before_plant | CanonGraphValidator.reveal_before_plant | blocked | clean | clean | clean | PASS |
| MUT-011 | 回收倒置：payoff 在 reveal 之前 | graph | CanonGraphValidator.payoff_before_reveal | CanonGraphValidator.payoff_before_reveal | blocked | clean | clean | clean | PASS |
| MUT-012 | 时间顺序倒置：resolved 事件被重新打开 | graph | CanonGraphValidator.run | CanonGraphValidator.run | blocked | clean | clean | clean | PASS |
| MUT-013 | 已死亡角色继续行动 | graph | CanonGraphValidator.dead_character_action | CanonGraphValidator.dead_character_action | blocked | clean | clean | clean | PASS |
| MUT-014 | 能力在解锁前被使用 | graph | CanonGraphValidator.ability_before_unlock | CanonGraphValidator.ability_before_unlock | blocked | clean | clean | clean | PASS |
| MUT-015 | 身份在获得前被使用 | graph | CanonGraphValidator.identity_before_acquired | CanonGraphValidator.identity_before_acquired | blocked | clean | clean | clean | PASS |
| MUT-016 | 不可能位移：跨地点无 travel 事件 | graph | CanonGraphValidator.location_impossibility | CanonGraphValidator.location_impossibility | blocked | clean | clean | clean | PASS |
| MUT-017 | 因果环：A 依赖 B 且 B 依赖 A | graph | CanonGraphValidator.causal_cycle | CanonGraphValidator.causal_cycle | blocked | clean | clean | clean | PASS |
| MUT-018 | 缺失前置：prerequisite 不在 Canon | graph | CanonGraphValidator.prerequisite_missing | CanonGraphValidator.prerequisite_missing | blocked | clean | clean | clean | PASS |
| MUT-019 | concrete_events 传 str：禁止逐字符展开 | schema | SchemaGate.validate_chapter_plan | SchemaGate.validate_chapter_plan | blocked | clean | clean | clean | PASS |
| MUT-020 | 同章事件重复：三条完全相同 | schema | SchemaGate.validate_chapter_plan | SchemaGate.validate_chapter_plan | blocked | clean | clean | clean | PASS |
| MUT-021 | 事件碎片：单字被当成具体事件 | schema | SchemaGate.validate_chapter_plan | SchemaGate.validate_chapter_plan | blocked | clean | clean | clean | PASS |
| MUT-022 | 缺失 graph metadata key：必须与显式空列表区分 | planner | CanonAwareOutlinePlanner.plan | CanonAwareOutlinePlanner.plan | blocked | clean | clean | clean | PASS |
| MUT-023 | Writer metadata leak：ch142 / FACT_* / chapter_uuid 混入正文层 | writer | CanonAwareOutlinePlanner.plan + sanitize_writer_text | CanonAwareOutlinePlanner.plan + sanitize_writer_text | blocked | clean | clean | clean | PASS |
| MUT-024 | 规划元数据泄漏：Arc / 卷号 / 内部字段名 | writer | CanonAwareOutlinePlanner.plan + sanitize_writer_text | CanonAwareOutlinePlanner.plan + sanitize_writer_text | blocked | clean | clean | clean | PASS |
| MUT-025 | 重大事件换措辞重复：语义索引必须报 duplicate | semantic | SemanticIndex.classify_relation | SemanticIndex.classify_relation | blocked | clean | clean | clean | PASS |
| MUT-026 | 合法复现误报：日常巡逻连续两次 | semantic | SemanticIndex.classify_relation | SemanticIndex.classify_relation | blocked | clean | clean | clean | PASS |
| MUT-027 | 后果误报：报复性封锁不是重复事件 | semantic | SemanticIndex.classify_relation | SemanticIndex.classify_relation | blocked | clean | clean | clean | PASS |
| MUT-028 | 章节重编号：display number 325 → 318 | repository | ChapterLineageStore.renumber + CanonRepository.renumber_render_refs | ChapterLineageStore.renumber + CanonRepository.renumber_render_refs | expected persist | clean | changed | clean | PASS |
| MUT-029 | 拆章：uuid_split → 两个新 uuid | repository | ChapterLineageStore.split + SourceReferenceValidator | ChapterLineageStore.split + SourceReferenceValidator | expected persist | clean | clean | clean | PASS |
| MUT-030 | 合章：uuid_merge_a/b → 合并 uuid | repository | ChapterLineageStore.merge | ChapterLineageStore.merge | expected persist | clean | clean | clean | PASS |
| MUT-031 | Shadow 污染：shadow planner 不得触碰正式 Canon / Outline / StoryState | outline | CanonAwareOutlinePlanner.shadow_plan | CanonAwareOutlinePlanner.shadow_plan | blocked | clean | clean | clean | PASS |
| MUT-032 | Bootstrap 优先级：legacy outline 不得覆盖 StoryState confirmed | bootstrap | CanonBootstrap.bootstrap | CanonBootstrap.bootstrap | blocked | clean | changed | clean | PASS |
| MUT-033 | 部分 Canon：只有 StoryState 也要能启动（CANON_PARTIAL） | bootstrap | CanonBootstrap.coverage | CanonBootstrap.coverage | blocked | clean | changed | clean | PASS |
| MUT-034 | Rebuild 失败回滚：validator 阶段拒绝候选库 | bootstrap | CanonBootstrap.rebuild | CanonBootstrap.rebuild | blocked | clean | clean | clean | PASS |
| MUT-035 | Rebuild 异常回滚：导入中途 exception | bootstrap | CanonBootstrap.rebuild | CanonBootstrap.rebuild | blocked | clean | clean | clean | PASS |
| MUT-036 | 上下文确定性：打乱 DB 返回顺序后 digest 必须一致 | context | CanonContextBuilder.planner_context | CanonContextBuilder.planner_context | blocked | clean | clean | clean | PASS |
| MUT-037 | 预算裁剪：hard prerequisite / knowledge boundary 不可被裁掉 | context | CanonContextBuilder._apply_budget | CanonContextBuilder._apply_budget | blocked | clean | clean | clean | PASS |
| MUT-038 | Promotion 歧义：相似度高但参与者 / 地点不完全一致 | canon | SourceReferenceValidator.promotion_conflicts | SourceReferenceValidator.promotion_conflicts | blocked | clean | clean | clean | PASS |
| MUT-039 | Source mapping 持久化：重开 DB 后 identity 不变 | canon | StoryStateCanonSync.sync + CanonRepository.find_mapping | StoryStateCanonSync.sync + CanonRepository.find_mapping | expected persist | clean | changed | clean | PASS |
| MUT-040 | Legacy flag off：新基础设施不得偷偷改变旧产品行为 | planner | CanonOutlineFlags / CanonAwareOutlinePlanner | CanonOutlineFlags / CanonAwareOutlinePlanner | blocked | clean | clean | clean | PASS |
| MUT-041 | 孤立引用残片：删除 ch###/anchor 后留下「承接 的…」「已在被…」 | writer | prose.orphaned_reference_fragments | prose.orphaned_reference_fragments | blocked | clean | clean | clean | PASS |
| MUT-042 | Canon 审计腔刷屏：连续 event 都在解释历史 anchor | writer | prose.audit_prose_report | prose.audit_prose_report | blocked | clean | clean | clean | PASS |
| MUT-043 | 狗角色语义：role 必须由实际动作支撑，payload 不得是字段拼接 | writer | prose.dog_role_alignment | prose.dog_role_alignment | blocked | clean | clean | clean | PASS |
| MUT-044 | 已解决的人物事件被重开：阿灰去而复返之后又「未归」 | graph | prose.narrative_lifecycle_findings | prose.narrative_lifecycle_findings | blocked | clean | clean | clean | PASS |
| MUT-045 | 跨字段语义矛盾：goal/event 是一章，decision/world_state 是另一章 | planner | prose.cross_field_findings | prose.cross_field_findings | blocked | clean | clean | clean | PASS |
| MUT-046 | Sample Pack 完整性：35 条 / 35 唯一 / 每卷 5 / 真随机 ≥18 | outline | prose.validate_sample_pack | prose.validate_sample_pack | blocked | clean | clean | clean | PASS |
| MUT-047 | Stale Chapter Semantic Frame：只改 events，trigger/action/opposition 仍是旧剧情 | planner | prose.chapter_frame_findings | prose.chapter_frame_findings | blocked | clean | clean | clean | PASS |
| MUT-048 | First Occurrence Self Contradiction：首次发生章自称「首次之后 / 再次」 | writer | prose.first_occurrence_findings | prose.first_occurrence_findings | blocked | clean | clean | clean | PASS |
| MUT-049 | Repeated Irreversible Transition：第零层被多次声明永久封闭 | graph | prose.irreversible_state_findings | prose.irreversible_state_findings | blocked | clean | clean | clean | PASS |
| MUT-050 | Within Chapter State Contradiction：同行与留守在同一章并存 | writer | prose.within_chapter_state_findings | prose.within_chapter_state_findings | blocked | clean | clean | clean | PASS |
| MUT-051 | Dog Role Object vs Action：对象化场景不得判 supportive | writer | prose.dog_role_object_findings | prose.dog_role_object_findings | blocked | clean | clean | clean | PASS |

## 逐条备注

- **MUT-001**（['SOURCE_REF_SEMANTIC_MISMATCH']）：把「伏击章」当成「门禁首次开门」的来源，必须判语义不匹配
- **MUT-002**（['CANON_FACT_UNKNOWN', 'SOURCE_REF_MISSING']）：source_ref 指向不存在的 fact（UUID 与 fact 均不存在）
- **MUT-003**（['SOURCE_REF_FUTURE_LEAK']）：cutoff=100 的章节引用 T=150 才出现的事实
- **MUT-004**（['SOURCE_REF_STATUS_MISMATCH']）：planned fact 被声明为已发生
- **MUT-005**（['HAPPENED_FACT_REWRITE', 'SOURCE_REF_FUTURE_LEAK', 'HAPPENED_FACT_IMMUTABLE']）：happened fact 不可改写：planner 拒绝 + service 拒绝 + 不可变标记保留
- **MUT-006**（['PROMOTION_CONFLICT']）：不静默合并；同 canonical_key 可安全 promotion=True，事件数仍为 2
- **MUT-007**（['KNOWLEDGE_LEAK']）：角色未知的事实不进入其上下文；无来源的 known 知识报 KNOWLEDGE_LEAK
- **MUT-008**（['FALSE_BELIEF_PRESERVED']）：T=50 只能表达误信；真相要到 T=100 之后才进入角色视角
- **MUT-009**（['FUTURE_REVEAL_BLOCKED']）：planned payoff（T=200）在 T=80 的 writer context 不可渲染
- **MUT-010**（['REVEAL_BEFORE_PLANT']）：reveal T=50 早于 plant T=70
- **MUT-011**（['PAYOFF_BEFORE_REVEAL']）：payoff T=40 早于 reveal T=60
- **MUT-012**（['RESOLVED_EVENT_REOPENED']）：离开→回归（resolved）之后又出现「仍未归来」事件
- **MUT-013**（['DEAD_CHARACTER_ACTION']）：dead_at=80 的角色出现在 T=100 事件
- **MUT-014**（['ABILITY_BEFORE_UNLOCK']）：能力解锁 T=100，却在 T=70 被使用
- **MUT-015**（['IDENTITY_BEFORE_ACQUIRED']）：身份获得 T=120，却在 T=90 被使用
- **MUT-016**（['LOCATION_IMPOSSIBILITY']）：角色只在 A 地，却无位移事件地出现在 B 地
- **MUT-017**（['CAUSAL_CYCLE', 'FUTURE_FACT_DEPENDENCY']）：A requires B 且 B requires A
- **MUT-018**（['PREREQUISITE_MISSING']）：前置 EVENT_NOT_IMPORTED 不存在
- **MUT-019**（['CHAPTER_SCHEMA_INVALID', 'CHAPTER_PLAN_SCHEMA_INVALID']）：planner 层与 gate 层都拒绝 str；无任何自动 coercion / 逐字符展开
- **MUT-020**（['CHAPTER_SCHEMA_INVALID']）：同章 concrete_events 完全重复
- **MUT-021**（['CHAPTER_SCHEMA_INVALID']）：事件是单字碎片（field fragment）
- **MUT-022**（['GRAPH_METADATA_MISSING']）：key 缺失 → GRAPH_METADATA_MISSING；显式 [] 合法（missing ≠ empty）
- **MUT-023**（['WRITER_VISIBLE_METADATA_LEAK']）：章节号 / canon ID / 内部字段名出现在 writer-visible 字段（trigger 等全覆盖）
- **MUT-024**（['WRITER_VISIBLE_METADATA_LEAK']）：Arc / 卷号 / 内部字段名全部拒绝；普通数字不误伤 | checks={'negative_control': True}
- **MUT-025**（['duplicate']）：换措辞的同一重大事件必须产生 duplicate candidate（只提示，不自动合并）
- **MUT-026**（['legitimate_recurrence']）：可重复事件不得被判为 duplicate canonical occurrence
- **MUT-027**（['consequence']）：显式 consequence 关系优先于相似度
- **MUT-028**（['DISPLAY_RENUMBERED']）：只允许 display_number 325→318；fact / event / knowledge / foreshadow / mapping / chapter_uuid 全部不变（render_refs 表与 payload 同步）
- **MUT-029**（['SPLIT_TRACEABLE']）：拆章后旧 uuid 标 superseded_by，Canon fact 与 source tracing 不丢失
- **MUT-030**（['MERGE_TRACEABLE']）：合章后旧 uuid 标 merged_into，原 source refs 不被静默丢弃
- **MUT-031**（['SHADOW_ISOLATED']）：shadow 产物只在隔离 sink（ARC_GATE.json）；正式 lineage 不新增（1→1）；shadow 仍写 1 条 context manifest 0→1（规划工件，非 Canon truth）
- **MUT-032**（['CONFIRMED_PRIORITY_KEPT']）：confirmed facts=2，低置信 imported facts=1；legacy outline 不覆盖 StoryState
- **MUT-033**（['CANON_PARTIAL']）：只有 StoryState（无 route / outline）时 Bootstrap 必须成功：missing_areas=['events', 'source_refs']
- **MUT-034**（['REBUILD_REJECTED']）：候选库校验失败（KNOWLEDGE_BEFORE_FACT）→ 原 Canon 保留；note=REBUILD_REJECTED：KNOWLEDGE_BEFORE_FACT
- **MUT-035**（['REBUILD_FAILED_KEPT_ORIGINAL']）：导入中途抛异常 → transaction rollback，原 Canon 完整；note=REBUILD_FAILED_KEPT_ORIGINAL：int() argument must be a string
- **MUT-036**（['CONTEXT_DETERMINISTIC']）：同一 Canon / purpose / cutoff / scope / budget，打乱 DB 返回顺序后 digest 仍一致
- **MUT-037**（['HARD_CONSTRAINTS_KEPT']）：max_items=1 / max_chars=1 仍保留 P0/P1（['EVENT_RITUAL', 'FACT_GATE_OPEN']）；低优先级被裁剪 ['EVENT_PLAIN', 'FACT_LATER_PLAN', 'FS_TIDE']
- **MUT-038**（['PROMOTION_CONFLICT']）：参与者相同但地点不一致 → 必须报冲突且不自动 merge（auto_merge=False）
- **MUT-039**（['MAPPING_STABLE']）：关闭并重开 repository 后再次 sync：source X → 同一 FACT identity；追加的新 effect 只新增自己的 fact（3 facts = 2 effect + 1 knowledge）
- **MUT-040**（['SHADOW_DISABLED']）：flag 默认关闭：canon path=False；shadow 未执行（0 个产物）
- **MUT-041**（['ORPHANED_REFERENCE_FRAGMENT']）：7 处人工发现的残句全部命中（metadata_leak 检测不到这类损坏）
- **MUT-042**（['CANON_AUDIT_PROSE_SPAM']）：audit_events=3 density=0.75；动作章（3 条 action）不误报=True
- **MUT-043**（['DOG_ROLE_ACTION_ALIGNMENT', 'DOG_ROLE_PAYLOAD_SUMMARY_COPY', 'DOG_ROLE_PRESENCE_MISMATCH']）：absent 出场 / 被保护当 supportive / 字段拼接 payload 全部命中；真实嗅探+拦截动作不误报
- **MUT-044**（['NARRATIVE_EVENT_LIFECYCLE_CONFLICT', 'NARRATIVE_EVENT_LIFECYCLE_CONFLICT']）：departure → resolved return 之后又回到未归状态必须报冲突；正常 departure → return → 余波不误报
- **MUT-045**（['CROSS_FIELD_SEMANTIC_MISMATCH']）：同一章字段跨剧情 frame 必须报错；同 frame 字段不误报
- **MUT-046**（['SAMPLE_CHAPTER_MULTI_CATEGORY', 'SAMPLE_DUPLICATE_CHAPTER', 'SAMPLE_ENTRY_COUNT', 'SAMPLE_PER_VOLUME_COUNT', 'SAMPLE_RANDOM_COUNT']）：重复章 / 每卷数量 / 真随机数量 / 同章多类别全部命中；合规样本（28 normal ≥ 18）零 finding 不误报
- **MUT-047**（['STALE_CHAPTER_FRAME', 'REAL_FIXTURE_1:cost,decision,opposition,protagonist_action,trigger', 'REAL_FIXTURE_2:decision,turn', 'REAL_FIXTURE_3:decision', 'REAL_FIXTURE_4:decision,turn', 'REAL_FIXTURE_5:decision,goal', 'REAL_FIXTURE_6:cost,decision,protagonist_action']）：半改章必须报 stale frame；命中字段=['opposition', 'protagonist_action', 'trigger']；5 个真实结构全部命中=True；整章同 frame 不误报
- **MUT-048**（['FIRST_OCCURRENCE_SELF_CONTRADICTION']）：first occurrence 自相矛盾 + V7 引用 V10 institution（future canon leak）都必须报错；正常首次章与合法位置不误报
- **MUT-049**（['IRREVERSIBLE_STATE_REPEATED']）：永久封闭重复声明必须报错；紧急锁闭 → 唯一永久封死 不误报
- **MUT-050**（['WITHIN_CHAPTER_STATE_CONTRADICTION']）：同章「带阿灰出发」+「阿灰留在据点」必须报错；同行章不误报
- **MUT-051**（['DOG_ROLE_OBJECT_NOT_SUPPORTIVE']）：被保护 / 被交易 / 被讨论 / 受伤 / 不在场不能判 supportive；在场=independent(independent)、不在场=offscreen_effect(offscreen_effect)；在场/不在场契约与真实动作证据均校验；真实嗅探帮忙动作不误报
