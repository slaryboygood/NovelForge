/*
 * V3 工作区（世界 / 角色 / 故事 / 推演 / 大纲 / 检查 / 导出）。
 *
 * V3-P0 的职责是：给出正确的信息架构、真实的当前状态与唯一的主动作。
 * 完整编辑能力按 roadmap 分阶段迁移；在迁移完成前，这一屏
 *   * 显示的是真实 application 投影（不是占位数字），
 *   * 主动作永远指向「让故事往前走」的那一步，
 *   * 高级工具（Inspector / Repair / 路线实验室 …）通过 Contextual Tools 打开 legacy 面板，
 *     不会出现在一级导航里。
 */
import Icon from './design-system/icons/IconRegistry'
import {
  Badge, Button, Card, EmptyState, ProgressBar, SectionHeading,
} from './design-system/primitives'
import {
  ChapterCard, CharacterCard, FactionCard, LocationCard, ObjectiveCard,
  RouteCandidateCard,
} from './design-system/components'
import { compareRoutes } from './viewmodel'
import ExportFlow from './ExportFlow'
import type { CommandCenterViewModel, ContentCardViewModel, ObjectiveViewModel,
  ChapterViewModel, CharacterEntityViewModel, FactionEntityViewModel,
  LocationEntityViewModel, RouteCandidateViewModel, StageViewModel } from './viewmodel'
import { VIEW_TITLES, type V3View } from './navModel'

const STAGE_TOOLS: Record<string, { tab: string; label: string; hint: string }[]> = {
  world: [
    { tab: 'world', label: '世界面板（完整）', hint: '地点 / 资源 / 世界事件 / 自主行动' },
    { tab: 'regions', label: '区域卡片', hint: '已知与未知区域、进入条件' },
  ],
  characters: [
    { tab: 'characters', label: '角色面板（完整）', hint: '目标 / 记忆 / 关系 / 人物弧' },
    { tab: 'relations', label: '关系网', hint: '人物—势力—伙伴关系与数值来源' },
  ],
  story: [
    { tab: 'plot', label: '剧情面板（完整）', hint: '主线推进与事件链' },
    { tab: 'memory', label: '记忆与伏笔', hint: '知识 / 伏笔 / 义务' },
    { tab: 'progression', label: '成长面板', hint: '成长节点与代价' },
    { tab: 'director', label: '导演面板', hint: '节奏权重（不改事实）' },
  ],
  simulation: [
    { tab: 'route', label: '路线实验室', hint: '试演 / 对比 / 合并 / 冻结分支' },
    { tab: 'compare', label: '路线对比', hint: '两条分支差异并列高亮' },
  ],
  outline: [
    { tab: 'outline', label: '大纲锻造', hint: '四级大纲生成与确认' },
    { tab: 'tree', label: '大纲结构树', hint: '全书 → 卷 → 篇章 → 章节' },
    { tab: 'linkage', label: '大纲联动', hint: '版本对比与影响分析' },
  ],
  review: [
    { tab: 'inspector', label: 'Canon 检查器', hint: '跨层只读检索与出处' },
    { tab: 'repair', label: '修复中心', hint: '诊断 → 预览 → 审批 → 历史' },
  ],
}

export default function WorkspaceView({ view, model, onOpenObjective, onOpenLegacy,
  onOpenContent, onOpenChapter, onOpenCharacter, onOpenLocation, onOpenFaction,
  onOpenRoute, selectedRouteId, onSelectRoute, onAdvanceSimulation, advancing,
  simulationFeedback, compareRouteId, onToggleCompare, onCloseCompare,
  onOpenView, onChanged }: {
  view: V3View
  model: CommandCenterViewModel
  /** V3 内部工作区跳转（导出工作区用它把作者送到真正缺的那一步）。 */
  onOpenView: (view: string) => void
  /** 写操作之后的投影刷新（导出包与写作草稿都会改变真实状态）。 */
  onChanged: () => Promise<CommandCenterViewModel | null>
  onOpenObjective: (objective: ObjectiveViewModel) => void
  onOpenLegacy: (tab: string, extra?: { step?: string; group?: string }) => void
  onOpenContent: (card: ContentCardViewModel) => void
  onOpenChapter: (chapter: ChapterViewModel) => void
  onOpenCharacter: (character: CharacterEntityViewModel) => void
  onOpenLocation: (location: LocationEntityViewModel) => void
  onOpenFaction: (faction: FactionEntityViewModel) => void
  onOpenRoute: (candidate: RouteCandidateViewModel) => void
  selectedRouteId: string
  onSelectRoute: (candidate: RouteCandidateViewModel) => void
  onAdvanceSimulation: () => void
  advancing: boolean
  simulationFeedback: { title: string; lines: string[] } | null
  compareRouteId: string
  onToggleCompare: (candidate: RouteCandidateViewModel) => void
  onCloseCompare: () => void
}) {
  const stage = model.stages.find((row) => row.stageId === view)
  const objectives = model.objectives.filter((row) => row.stageId === view)
  const recommended = objectives.find((row) => row.recommended) ?? objectives[0]
  const contentIds = CONTENT_BY_VIEW[view] ?? []
  const content = model.content.filter((row) => contentIds.includes(row.cardId))
  const tools = STAGE_TOOLS[view] ?? []
  /**
   * P2：每个 Workspace 的主视觉区域只能有一个 Primary CTA。
   * 有真实对象时由「当前目标 / Next Action」决定；空态时由 EmptyState 承担。
   */
  const entityCount = view === 'characters' ? model.characters.count
    : view === 'world' ? model.world.locationCount + model.world.factionCount
    : -1
  const primaryAction = (view === 'characters' || view === 'world')
    && entityCount > 0 ? recommended : undefined
  /**
   * P4：大纲工作区的主 CTA 由真实大纲状态决定——
   * 故事推进过（大纲已过期）→ 重新锻造；还没有大纲 → 锻造大纲；
   * 已有结构且不过期 → 由「当前目标」决定下一步。
   */
  const outlineCta = view === 'outline'
    ? (model.outline.stale ? '重新锻造大纲'
      : !model.outline.started ? '锻造四级大纲'
      : recommended ? recommended.actionLabel : '')
    : ''
  /** 推演工作区的主 CTA：由真实选中的候选方向决定（§14 Primary Action 唯一）。 */
  const selectedRoute = model.simulation.candidates
    .find((row) => row.candidateId === selectedRouteId) ?? null
  /**
   * NF-008：主 CTA 只能指向「当前真的可执行」的方向。
   * 如果作者选中的方向已经不可执行（例如人情用尽），就自动退回第一条可执行方向，
   * 而不是让主按钮每次都打回 422。
   */
  const availableRoute = model.simulation.candidates.find((row) => row.available) ?? null
  const advanceRoute = selectedRoute?.available ? selectedRoute : availableRoute
  /** P3 CLOSEOUT：V3 Native 路线比较（不跳走，不复制 RouteLab compare）。 */
  const comparedRoute = model.simulation.candidates
    .find((row) => row.candidateId === compareRouteId) ?? null
  const comparisonRows = selectedRoute && comparedRoute
    ? compareRoutes(selectedRoute, comparedRoute) : []
  const comparisonDiffs = comparisonRows.filter((row) => row.differs).length
  const showAdvance = view === 'simulation' && model.simulation.available
    && Boolean(advanceRoute)
  /** 当前没有可执行方向时，主 CTA 变成说明，而不是假装还能推演。 */
  const showAdvanceBlocked = view === 'simulation' && model.simulation.available
    && !advanceRoute
  /**
   * 唯一 Primary CTA：还没有大纲时由章节空态承担；已有结构（或已过期）时由头部承担。
   */
  const showOutlineCta = view === 'outline' && Boolean(outlineCta) && model.outline.started
  /**
   * 检查工作区：主 CTA = 先处理最该处理的那条发现（BLOCKING 优先，其次第一条）。
   * 没有任何发现时由「更深入的检查」承担，不制造假动作。
   */
  const blockingFinding = model.alerts.find((row) => row.level === 'BLOCKING')
    ?? model.alerts[0] ?? null
  const showReviewCta = view === 'review' && Boolean(blockingFinding)
  if (!stage) {
    return <EmptyState icon="current" title="这里还没有内容"
      reason="这一屏会在对应的创作阶段开放。" />
  }

  return (
    <div className="v3-workspace-view" data-testid={`v3-view-${view}`}>
      <Card className="v3-view-head" tone="elevated" testId="v3-view-goal">
        <div className="v3-view-head-icon"><Icon name={stage.icon} size={24} /></div>
        <div>
          <span className="v3-kicker">{VIEW_TITLES[view]}</span>
          <h1 data-testid="v3-view-goal-title">{stage.goal}</h1>
          <p>{stageDescription(view, stage, model)}</p>
        </div>
        <div className="v3-view-head-side">
          <StagePill stage={stage} />
          <ProgressBar percent={stage.progressPercent} label={`${stage.label}进度`} />
          {primaryAction ? (
            <Button variant="primary" iconAfter="next_action"
              onClick={() => onOpenObjective(primaryAction)}
              testId="v3-view-primary-cta">{primaryAction.actionLabel}</Button>
          ) : null}
          {showAdvance && advanceRoute ? (
            <Button variant="primary" iconAfter="next_action" disabled={advancing}
              onClick={onAdvanceSimulation}
              testId="v3-simulation-advance">{advancing
                ? '正在推演…' : `推演「${advanceRoute.title}」`}</Button>
          ) : null}
          {showAdvanceBlocked ? (
            <Button variant="secondary" disabled testId="v3-simulation-blocked">
              当前没有可执行方向（先补齐前置条件）
            </Button>
          ) : null}
          {showOutlineCta ? (
            <Button variant="primary" iconAfter="next_action"
              onClick={() => onOpenLegacy('outline')}
              testId="v3-outline-primary">{outlineCta}</Button>
          ) : null}
          {showReviewCta && blockingFinding ? (
            <Button variant="primary" iconAfter="next_action"
              onClick={() => onOpenLegacy(
                blockingFinding.deepLink.view === 'review'
                  ? (blockingFinding.deepLink.step || 'inspector')
                  : blockingFinding.deepLink.view,
                { step: blockingFinding.deepLink.step, group: blockingFinding.deepLink.group })}
              testId="v3-review-primary">{blockingFinding.actionLabel}</Button>
          ) : null}
        </div>
      </Card>

      {content.length > 0 ? (
        <section className="v3-block">
          <SectionHeading icon="objective" title="当前状态" hint="来自真实作品状态" />
          {content.every((card) => card.count === 0) ? (
            /* 0 数据时不留一张大空卡：给出可读的原因与唯一的下一步。 */
            <EmptyState icon={stage.icon} title={emptyCopy(view).title}
              reason={emptyCopy(view).reason}
              action={recommended ? (
                <Button variant={view === 'export' || view === 'review'
                  ? 'secondary' : 'primary'} iconAfter="next_action"
                  onClick={() => onOpenObjective(recommended)}
                  testId="v3-view-empty-cta">{recommended.actionLabel}</Button>
              ) : undefined} />
          ) : (
            <ul className="v3-entity-grid">
              {content.map((card) => (
                <Card as="li" key={card.cardId} className="v3-entity" tone="default"
                  onClick={() => onOpenContent(card)} testId={`v3-view-content-${card.cardId}`}>
                  <span className="v3-entity-visual" aria-hidden="true">
                    <Icon name={card.icon} size={26} />
                  </span>
                  <span className="v3-entity-label">{card.label}</span>
                  <span className="v3-entity-count">{card.count} {card.unit}</span>
                  <span className="v3-entity-hint">{card.hint}</span>
                </Card>
              ))}
            </ul>
          )}
        </section>
      ) : null}

      {view === 'simulation' ? (
        <>
          <section className="v3-block" data-testid="v3-simulation-situation">
            <SectionHeading icon="simulation" title="当前故事状况"
              hint={model.simulation.available
                ? `第 ${model.simulation.tick} 回合 · 修订 ${model.simulation.revision}`
                : '还不能推演'} />
            {model.simulation.available ? (
              <Card tone="quiet" className="v3-situation">
                {model.simulation.situationRows.length > 0 ? (
                  <ul className="v3-situation-rows" data-testid="v3-simulation-summary">
                    {model.simulation.situationRows.map((row) => (
                      <li key={row.label}>
                        <span>{row.label}</span><b>{row.value}</b>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p data-testid="v3-simulation-summary">
                    故事已经在推演中：下面是当前状态下可以走的真实方向。
                  </p>
                )}
                {model.simulation.branches.length > 0 ? (
                  <ul className="v3-branch-list" data-testid="v3-simulation-branches">
                    {model.simulation.branches.map((branch) => (
                      <li key={branch.branchId}>
                        <b>{branch.displayLabel}</b>
                        <span>第 {branch.tick} 回合 · 修订 {branch.revision}</span>
                      </li>
                    ))}
                  </ul>
                ) : null}
                {/* 引擎原始摘要与路线标识属于诊断信息，默认折叠。 */}
                {model.simulation.summary || model.simulation.branchId ? (
                  <details className="v3-context-advanced" data-testid="v3-simulation-advanced">
                    <summary>高级详情</summary>
                    <ul>
                      {model.simulation.summary ? (
                        <li><b>引擎状态摘要</b><span>{model.simulation.summary}</span></li>
                      ) : null}
                      {model.simulation.branchId ? (
                        <li><b>路线标识</b><span>{model.simulation.branchId}</span></li>
                      ) : null}
                    </ul>
                  </details>
                ) : null}
              </Card>
            ) : (
              <EmptyState icon="simulation" title="故事还没有准备好开始推演"
                artwork="simulation"
                reason={model.simulation.reason}
                value="推演需要先有起点事实：它会成为之后所有章节的唯一依据。"
                action={recommended ? (
                  <Button variant="primary" iconAfter="next_action"
                    onClick={() => onOpenObjective(recommended)}
                    testId="v3-simulation-empty-cta">{recommended.actionLabel}</Button>
                ) : undefined} />
            )}
          </section>

          {model.simulation.available ? (
            <section className="v3-block" data-testid="v3-simulation-routes">
              <SectionHeading icon="route" title="可行方向"
                hint="每条方向都会真的改变故事；选择一条，然后推演下一步" />
              {model.simulation.candidates.length > 0 ? (
                <ul className="v3-entity-list">
                  {model.simulation.candidates.map((candidate) => (
                    <RouteCandidateCard key={candidate.candidateId} candidate={candidate}
                      selected={candidate.candidateId === selectedRouteId}
                      compared={candidate.candidateId === compareRouteId}
                      onOpen={onOpenRoute} onPick={onSelectRoute}
                      onCompare={onToggleCompare} />
                  ))}
                </ul>
              ) : (
                <EmptyState icon="route" title="当前没有可以走的下一步"
                  reason="故事推进到这一步时没有合法行动：先看看设定或检查是否有缺口。" />
              )}
            </section>
          ) : null}

          {selectedRoute && comparedRoute ? (
            <section className="v3-block" data-testid="v3-simulation-comparison">
              <SectionHeading icon="compare" title="路线比较"
                hint={comparisonDiffs > 0
                  ? `「${selectedRoute.title}」vs「${comparedRoute.title}」· ${comparisonDiffs} 处真实差异`
                  : `「${selectedRoute.title}」vs「${comparedRoute.title}」`} />
              <Card tone="elevated" className="v3-compare">
                <div className="v3-compare-head">
                  <span />
                  <b>{selectedRoute.title}</b>
                  <b>{comparedRoute.title}</b>
                </div>
                <ul className="v3-compare-rows">
                  {comparisonRows.map((row) => (
                    <li key={row.label} className={row.differs ? 'is-diff' : ''}>
                      <span className="v3-compare-label">{row.label}</span>
                      <span>{row.left}</span>
                      <span>{row.right}</span>
                    </li>
                  ))}
                </ul>
                {comparisonDiffs === 0 ? (
                  <p className="v3-compare-note">
                    这两条方向在已知维度上没有真实差别：系统不会制造假差异。
                  </p>
                ) : null}
                <Button variant="ghost" size="sm" onClick={onCloseCompare}
                  testId="v3-compare-close">关闭比较</Button>
              </Card>
            </section>
          ) : null}

          {simulationFeedback ? (
            <section className="v3-block" data-testid="v3-simulation-feedback">
              <SectionHeading icon="complete" title="本次推演发生了什么" />
              <Card tone="elevated" className="v3-feedback-card">
                <b>{simulationFeedback.title}</b>
                <ul>
                  {simulationFeedback.lines.map((line) => <li key={line}>{line}</li>)}
                </ul>
              </Card>
            </section>
          ) : null}
        </>
      ) : null}

      {view === 'characters' ? (
        <section className="v3-block" data-testid="v3-characters-block">
          <SectionHeading icon="character" title="主要角色"
            hint={model.characters.count > 0
              ? `共 ${model.characters.count} 个角色 · 点击查看这个角色是谁、要什么、还缺什么`
              : '这本书的角色'} />
          {model.characters.items.length > 0 ? (
            <ul className="v3-entity-list">
              {model.characters.items.map((character) => (
                <CharacterCard key={character.characterId} character={character}
                  onOpen={onOpenCharacter} />
              ))}
            </ul>
          ) : (
            <EmptyState icon="character" title="还没有主要角色"
              artwork="characters"
              reason="角色会帮助故事建立目标、冲突和关系；先定下主角，其它角色才有围绕的中心。"
              value={model.characters.available
                ? '现在还没有已发生的角色事实。' : undefined}
              action={recommended ? (
                <Button variant="primary" iconAfter="next_action"
                  onClick={() => onOpenObjective(recommended)}
                  testId="v3-character-create">{recommended.actionLabel}</Button>
              ) : undefined} />
          )}
        </section>
      ) : null}

      {view === 'world' ? (
        <>
          <section className="v3-block" data-testid="v3-world-locations-block">
            <SectionHeading icon="location" title="关键地点"
              hint={model.world.locationCount > 0
                ? `已知 ${model.world.locationCount} 个地点`
                : '故事发生的地方'} />
            {model.world.locations.length > 0 ? (
              <ul className="v3-entity-list">
                {model.world.locations.map((location) => (
                  <LocationCard key={location.locationId} location={location}
                    onOpen={onOpenLocation} />
                ))}
              </ul>
            ) : (
            <EmptyState icon="location" title="还没有可以写进故事的地点"
              artwork="world"
              reason="地点来自已经发生的事实与设定；先定下世界规则，地点才会成为故事的一部分。"
                action={recommended ? (
                  <Button variant="primary" iconAfter="next_action"
                    onClick={() => onOpenObjective(recommended)}
                    testId="v3-world-create">{recommended.actionLabel}</Button>
                ) : undefined} />
            )}
          </section>

          {model.world.factions.length > 0 ? (
            <section className="v3-block" data-testid="v3-world-factions-block">
              <SectionHeading icon="faction" title="关键势力"
                hint={`共 ${model.world.factionCount} 个势力 · 正在争夺什么`} />
              <ul className="v3-entity-list">
                {model.world.factions.map((faction) => (
                  <FactionCard key={faction.factionId} faction={faction}
                    onOpen={onOpenFaction} />
                ))}
              </ul>
            </section>
          ) : null}
        </>
      ) : null}

      {view === 'outline' ? (
        <>
          <section className="v3-block" data-testid="v3-outline-structure">
            <SectionHeading icon="outline" title="大纲结构"
              hint={model.outline.started
                ? '全书主线 → 卷纲 → 篇章纲 → 详细章纲，四级都来自同一条真实大纲链'
                : '这本书还没有把故事方向锻造成大纲'} />
            {model.outline.started ? (
              <>
                <ul className="v3-outline-levels" data-testid="v3-outline-levels">
                  {model.outline.levels.map((row) => (
                    <li key={row.level} data-level={row.level}
                      data-empty={row.count === 0 ? 'true' : 'false'}>
                      <Icon name={row.level === 'book' ? 'book'
                        : row.level === 'chapter' ? 'chapter' : 'outline'} size={18} />
                      <span>
                        <b>{row.label}</b>
                        <small>{row.count > 0
                          ? `${row.count} ${row.level === 'book' ? '条' : '个'}`
                          : '还缺这一级'}</small>
                      </span>
                      {row.statusLabel ? <Badge tone={row.confirmed ? 'success' : 'warning'}>
                        {row.statusLabel}</Badge> : null}
                    </li>
                  ))}
                </ul>
                {model.outline.stale ? (
                  <p className="v3-outline-stale" data-testid="v3-outline-stale">
                    <Icon name="warning" size={15} />
                    这个故事已经推进过：现在这份大纲是推进前锻造的，和当前事实不一致。
                  </p>
                ) : null}
                {model.outline.bookTitle ? (
                  <p className="v3-outline-book" data-testid="v3-outline-book">
                    <Icon name="book" size={15} />全书主线：{model.outline.bookTitle}
                  </p>
                ) : null}
                {model.outline.volumes.length > 0 ? (
                  <ul className="v3-outline-children" data-testid="v3-outline-volumes">
                    {model.outline.volumes.map((row) => (
                      <li key={row.packageId}>
                        <span>{row.title}</span>
                        <Badge tone={row.confirmed ? 'success' : 'warning'}>
                          {row.statusLabel}</Badge>
                      </li>
                    ))}
                  </ul>
                ) : null}
                {model.outline.arcs.length > 0 ? (
                  <ul className="v3-outline-children" data-testid="v3-outline-arcs">
                    {model.outline.arcs.map((row) => (
                      <li key={row.packageId}>
                        <span>{row.title}</span>
                        <Badge tone={row.confirmed ? 'success' : 'warning'}>
                          {row.statusLabel}</Badge>
                      </li>
                    ))}
                  </ul>
                ) : null}
              </>
            ) : (
            <EmptyState icon="outline" title="还没有大纲"
              artwork="outline"
              reason="大纲把「故事往哪里走」拆成可写的章节：先锻造四级大纲，这里就会显示全书主线、卷、篇章与章节。"
                value="锻造用的是已经推演过的故事方向，不是凭空生成的结构。" />
            )}
          </section>

          {model.outline.gaps.length > 0 ? (
            <section className="v3-block" data-testid="v3-outline-gaps">
              <SectionHeading icon="warning" title="大纲缺口"
                hint="还缺什么，补上以后结构才完整" />
              <ul className="v3-outline-signals">
                {model.outline.gaps.map((row) => (
                  <li key={row} className="is-gap">{row}</li>
                ))}
              </ul>
            </section>
          ) : null}

          {model.outline.warnings.length > 0 || model.outline.quality.length > 0 ? (
            <section className="v3-block" data-testid="v3-outline-warnings">
              <SectionHeading icon="warning" title="大纲警告"
                hint="来自这份大纲自己的待办问题与锻造质量报告" />
              <ul className="v3-outline-signals">
                {model.outline.quality.map((row) => (
                  <li key={`q-${row.message}`}
                    className={row.severity === 'error' ? 'is-blocking' : 'is-warning'}>
                    {row.message}
                  </li>
                ))}
                {model.outline.warnings.map((row) => (
                  <li key={`w-${row.code}-${row.message}`}
                    className={row.code === 'OUTLINE_STALE' ? 'is-blocking' : 'is-warning'}>
                    {row.message}
                  </li>
                ))}
              </ul>
            </section>
          ) : null}

          <section className="v3-block" data-testid="v3-view-chapters">
            <SectionHeading icon="chapter" title="章节"
              hint={model.outline.chapterCount > 0
                ? `共 ${model.outline.chapterCount} 章 · 来自已锻造的章纲`
                : '这本书的章节结构'} />
            {model.outline.chapters.length > 0 ? (
              <ul className="v3-chapter-grid">
                {model.outline.chapters.map((chapter) => (
                  <ChapterCard key={chapter.chapterId} chapter={chapter} onOpen={onOpenChapter} />
                ))}
              </ul>
            ) : (
            <EmptyState icon="chapter" title="还没有章节"
              artwork="outline"
              reason="章节来自已经锻造的章纲：先做出全书主线 → 卷纲 → 篇章纲 → 详细章纲，这里就会逐章列出来。"
                value={model.outline.started ? '全书主线已经存在，但还没有生成章纲。' : undefined}
                action={<Button variant="primary" iconAfter="next_action"
                  onClick={() => onOpenLegacy('outline')}
                  testId="v3-chapter-create">生成章节大纲</Button>} />
            )}
          </section>
        </>
      ) : null}

      {view === 'review' ? (
        <>
          <section className="v3-block" data-testid="v3-review-findings">
            <SectionHeading icon="review" title="这本书现在的情况"
              hint="这里说的是故事本身的问题，不是系统错误；只有「必须处理」会拦住下一步" />
            {model.alerts.length > 0 ? (
              <ul className="v3-finding-list" data-testid="v3-review-finding-list">
                {model.alerts.map((alert) => (
                  <li key={alert.alertId} className={`v3-finding is-${alert.level.toLowerCase()}`}
                    data-level={alert.level}>
                    <span className="v3-finding-level">
                      <Icon name={alert.level === 'BLOCKING' ? 'warning'
                        : alert.level === 'WARNING' ? 'conflict' : 'review'} size={16} />
                      {alert.levelLabel}
                    </span>
                    <b>{alert.title}</b>
                    {alert.detail ? <p>{alert.detail}</p> : null}
                    {alert.hint ? <p className="v3-finding-hint">{alert.hint}</p> : null}
                    {alert.fixLabel || alert.reversibleLabel ? (
                      <p className="v3-finding-fix">
                        {[alert.fixLabel, alert.reversibleLabel].filter(Boolean).join(' · ')}
                      </p>
                    ) : null}
                    <Button variant="secondary" size="sm" iconAfter="next_action"
                      onClick={() => onOpenLegacy(alert.deepLink.view === 'review'
                        ? (alert.deepLink.step || 'inspector') : alert.deepLink.view,
                      { step: alert.deepLink.step, group: alert.deepLink.group })}
                      testId={`v3-review-action-${alert.alertId}`}>{alert.actionLabel}</Button>
                  </li>
                ))}
              </ul>
            ) : (
            <EmptyState icon="complete" title="现在没有需要处理的故事问题"
              artwork="review"
              reason="检查会在这个故事出现前后矛盾、缺口或无法继续的路线时自动出现。"
                value="没有问题时不留空风险框——可以先继续推进故事。" />
            )}
          </section>

          <section className="v3-block" data-testid="v3-review-repair">
            <SectionHeading icon="repair" title="需要修复的旧设定"
              hint={model.repair.available
                ? `${model.repair.issueCount} 处 · 其中 ${model.repair.blockingCount} 处需要你决定`
                : '历史冲突与设定不一致'} />
            {model.repair.available ? (
              <ul className="v3-finding-list" data-testid="v3-repair-issue-list">
                {model.repair.issues.map((issue) => (
                  <li key={issue.issueId} className="v3-finding is-warning">
                    <span className="v3-finding-level">
                      <Icon name="repair" size={16} />{issue.sourceLabel}
                    </span>
                    <b>{issue.title}</b>
                    {issue.why ? <p>{issue.why}</p> : null}
                    <p className="v3-finding-fix">
                      {[issue.approvalLabel, issue.reversibleLabel].filter(Boolean).join(' · ')}
                    </p>
                  </li>
                ))}
              </ul>
            ) : (
              <EmptyState icon="complete" title="没有需要修复的历史冲突"
                reason="修复中心会在设定、事实与大之间出现不一致时给出具体问题和处理方式。"
                action={<Button variant="secondary" iconAfter="next_action"
                  onClick={() => onOpenLegacy('repair')}
                  testId="v3-repair-advanced">打开修复中心</Button>} />
            )}
          </section>

          <section className="v3-block" data-testid="v3-review-tools">
            <SectionHeading icon="repair" title="更深入的检查"
              hint="需要查具体出处、跨层比对时再打开" />
            <ul className="v3-tool-list">
              {(STAGE_TOOLS.review ?? []).map((tool) => (
                <li key={tool.tab}>
                  <Card as="div" className="v3-tool" tone="quiet">
                    <button type="button" className="v3-tool-hit"
                      onClick={() => onOpenLegacy(tool.tab)}
                      data-testid={`v3-tool-${tool.tab}`}>
                      <Icon name="repair" size={18} />
                      <span><b>{tool.label}</b><small>{tool.hint}</small></span>
                      <Icon name="next_action" size={16} />
                    </button>
                  </Card>
                </li>
              ))}
            </ul>
          </section>
        </>
      ) : null}

      {view === 'export' ? (
        <>
          <section className="v3-block" data-testid="v3-export-readiness">
            <SectionHeading icon="export" title="能不能交给写作环节"
              hint={model.exportView.headline} />
            <ul className="v3-outline-levels" data-testid="v3-export-steps">
              {model.exportView.steps.map((row) => (
                <li key={row.stepId} data-done={row.done ? 'true' : 'false'}>
                  <Icon name={row.done ? 'complete' : 'locked'} size={18} />
                  <span>
                    <b>{row.label}</b>
                    <small>{row.done ? '已经满足' : row.why}</small>
                  </span>
                </li>
              ))}
            </ul>
            {model.exportView.blockers.length > 0 ? (
              <ul className="v3-outline-signals" data-testid="v3-export-blockers">
                {model.exportView.blockers.map((row) => (
                  <li key={row} className="is-blocking">{row}</li>
                ))}
              </ul>
            ) : null}
          </section>

          <section className="v3-block" data-testid="v3-export-bundle">
            <SectionHeading icon="book" title="会导出什么"
              hint="导出的是已经发生的事实与确认后的结构，不包括规划中的假设" />
            <ul className="v3-outline-children">
              {model.exportView.bundle.map((row) => (
                <li key={row.label}>
                  <span><b>{row.label}</b> · {row.detail}</span>
                </li>
              ))}
            </ul>
          </section>

          {/* NF-001：导出能力在产品内（不是跳到一个不存在的 legacy 页签）。 */}
          <ExportFlow novelId={model.hero.novelId} model={model}
            onChanged={onChanged} onOpenView={onOpenView} />
        </>
      ) : null}

      {/* 检查 / 导出 已经用自己的区块表达「还缺什么」，不再重复目标卡。 */}
      {view !== 'review' && view !== 'export' ? (
      <section className="v3-block" data-testid="v3-view-objectives">
        <SectionHeading icon="objective" title="这一步要完成的目标"
          hint={recommended ? `建议先做：${recommended.title}` : undefined} />
        {objectives.length > 0 ? (
          <ul className="v3-objective-grid">
                {objectives.map((objective) => (
                  <li key={objective.objectiveId}>
                    <ObjectiveCard objective={objective} onOpen={onOpenObjective}
                      ctaVariant={showOutlineCta || view === 'outline' ? 'secondary' : undefined} />
                  </li>
                ))}
          </ul>
        ) : (
          <EmptyState icon="objective" title="这一步暂时没有需要完成的目标"
            reason="当故事推进到这一阶段时会自动出现。" />
        )}
      </section>
      ) : null}

      {tools.length > 0 ? (
        <section className="v3-block" data-testid="v3-view-tools">
          <SectionHeading icon="repair" title="展开的工具"
            hint="默认隐藏的高级信息，需要时再打开" />
          <ul className="v3-tool-list">
            {tools.map((tool) => (
              <li key={tool.tab}>
                <Card as="div" className="v3-tool" tone="quiet">
                  <button type="button" className="v3-tool-hit" onClick={() => onOpenLegacy(tool.tab)}
                    data-testid={`v3-tool-${tool.tab}`}>
                    <Icon name="repair" size={18} />
                    <span>
                      <b>{tool.label}</b>
                      <small>{tool.hint}</small>
                    </span>
                    <Icon name="next_action" size={16} />
                  </button>
                </Card>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <Card className="v3-view-note" tone="quiet">
        <p>
          <Icon name="foreshadow" size={16} />
          这一屏在当前版本负责「看状态 + 推进下一步」。完整编辑界面按 roadmap
          在后续阶段迁移，期间可以随时用「展开的工具」打开既有面板。
        </p>
      </Card>
    </div>
  )
}

function StagePill({ stage }: { stage: StageViewModel }) {
  const tone = stage.statusClass === 'COMPLETE' ? 'success'
    : stage.statusClass === 'BLOCKED' ? 'danger'
    : stage.statusClass === 'CURRENT' || stage.statusClass === 'IN_PROGRESS' ? 'primary'
    : 'neutral'
  return <Badge tone={tone} icon={stage.icon}>{stage.statusLabel}</Badge>
}

const CONTENT_BY_VIEW: Record<string, string[]> = {
  // 世界 / 角色用实体列表（Location / Faction / Character）呈现，不再重复显示计数卡。
  world: [],
  characters: [],
  story: ['plots', 'factions'],
  // 推演用「当前故事状况 + 可行方向」呈现，不再重复显示计数卡。
  simulation: [],
  // 大纲视图用专门的「章节」区块呈现（数量 + 列表 + 空态），不再重复显示同一张计数卡。
  outline: [],
  review: ['chapters', 'plots'],
  export: ['chapters'],
}

/** 0 数据时每个工作区的说明与下一步（作者语言，不承诺当前系统没有的能力）。 */
const VIEW_EMPTY_COPY: Record<string, { title: string; reason: string }> = {
  world: {
    title: '还没有世界设定',
    reason: '先定下这个世界靠什么运转，地点与势力才会成为故事的一部分。',
  },
  characters: {
    title: '还没有角色',
    reason: '先立起主角：他想要什么、怕什么、底线在哪里，故事才有行动者。',
  },
  story: {
    title: '还没有剧情线',
    reason: '主线来自已经发生的事实：先让故事开始，再整理它。',
  },
  simulation: {
    title: '还没有可以推演的事实',
    reason: '起点事实落盘之后，故事才会真正往前走。',
  },
  review: {
    title: '暂时没有需要检查的问题',
    reason: '检查是只读的：它告诉你哪里可能自相矛盾，不修改任何事实。',
  },
  export: {
    title: '还没有可以导出的内容',
    reason: '先把设定、已发生事实与大纲整理出来，导出才有东西可交。',
  },
}

function emptyCopy(view: V3View): { title: string; reason: string } {
  return VIEW_EMPTY_COPY[view] ?? {
    title: '这里还是空的',
    reason: '完成这一阶段的目标后，这里会显示真实的作品状态。',
  }
}

function stageDescription(view: V3View, stage: StageViewModel,
  model: CommandCenterViewModel): string {
  if (view === 'simulation' && !model.facts.runtimeStarted) {
    return '推演还没开始：起点事实落盘之后，故事才会真正往前走。'
  }
  if (view === 'outline' && !model.facts.runtimeStarted) {
    return '大纲来自已经发生的推演，所以要先开始推演。'
  }
  if (view === 'review') {
    return '检查是只读的：它告诉你哪里可能矛盾，不修改任何事实。'
  }
  if (view === 'export') {
    return '导出把设定、已发生事实与大纲交给写作环节，不写入新事实。'
  }
  return `${stage.label}：${stage.goal}`
}
