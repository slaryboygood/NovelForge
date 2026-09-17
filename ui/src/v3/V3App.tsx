/*
 * NovelForge V3 应用外壳：路由、数据装载、深链接恢复与上下文面板。
 *
 * 数据流只有一条：/api/story-builder/v3/* 的 application 投影 → ViewModel → UI。
 * 写操作全部交给既有 V2 API（通过 `v3Writes`），写完后重新拉取投影。
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { v3Api, v3Writes, type CommandCenterDto } from './api'
import { commandCenterViewModel, landingCardViewModel } from './viewmodel'
import type { ChapterViewModel, CharacterEntityViewModel, CommandCenterViewModel,
  FactionEntityViewModel, LandingCardViewModel, LocationEntityViewModel,
  ObjectiveViewModel, RouteCandidateViewModel } from './viewmodel'
import {
  legacyHash, novelHash, parseRoute, type DeepLinkParams, type Route, type V3View,
} from './navModel'
import AppShell from './AppShell'
import NovelLanding from './NovelLanding'
import CommandCenter, { JourneyRail } from './CommandCenter'
import CreationFlow from './CreationFlow'
import WorkspaceView from './WorkspaceView'
import Icon from './design-system/icons/IconRegistry'
import {
  Button, Card, EmptyState, ErrorState, LoadingState, ProgressBar,
} from './design-system/primitives'
import { ContextPanel } from './design-system/components'

export default function V3App() {
  const [route, setRoute] = useState<Route>(() => parseRoute(window.location.hash))
  const [cards, setCards] = useState<LandingCardViewModel[]>([])
  const [landingLoading, setLandingLoading] = useState(true)
  const [landingError, setLandingError] = useState('')
  const [projection, setProjection] = useState<CommandCenterDto | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [contextObjective, setContextObjective] = useState<ObjectiveViewModel | null>(null)
  /** Workspace 实体详情：章节 / 角色 / 地点 / 势力共用同一个 ContextPanel。 */
  const [contextEntity, setContextEntity] = useState<ContextEntity | null>(null)
  /** P3 推演：当前选中的方向 + 真实推演结果反馈。 */
  const [selectedRouteId, setSelectedRouteId] = useState('')
  const [compareRouteId, setCompareRouteId] = useState('')
  const [advancing, setAdvancing] = useState(false)
  const [simulationFeedback, setSimulationFeedback]
    = useState<{ title: string; lines: string[] } | null>(null)
  const currentNovel = useRef('')

  /* --------------------------------------------------------------- routing */
  useEffect(() => {
    const onHash = () => setRoute(parseRoute(window.location.hash))
    window.addEventListener('hashchange', onHash)
    if (!window.location.hash || window.location.hash === '#/') {
      window.history.replaceState(null, '', '#/')
    }
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  const go = useCallback((hash: string) => {
    if (window.location.hash === hash) setRoute(parseRoute(hash))
    else window.location.hash = hash
  }, [])

  const goNovel = useCallback((novelId: string, view: V3View = 'home',
    params: DeepLinkParams = {}) => {
    go(novelHash(novelId, view, params))
  }, [go])

  /* ------------------------------------------------------------ landing data */
  const loadLanding = useCallback(async () => {
    setLandingLoading(true); setLandingError('')
    try {
      const payload = await v3Api.novels()
      setCards(payload.novels.map(landingCardViewModel))
    } catch (reason) {
      setLandingError(text(reason))
    } finally {
      setLandingLoading(false)
    }
  }, [])

  useEffect(() => { void loadLanding() }, [loadLanding])

  /* --------------------------------------------------------- projection data */
  const novelId = route.name === 'novel' ? route.novelId : ''

  const loadProjection = useCallback(async (target: string) => {
    if (!target) return null
    setLoading(true); setError('')
    try {
      const payload = await v3Api.commandCenter(target)
      if (currentNovel.current !== target) return null
      setProjection(payload)
      return payload
    } catch (reason) {
      if (currentNovel.current === target) {
        setError(text(reason)); setProjection(null)
      }
      return null
    } finally {
      if (currentNovel.current === target) setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (!novelId) { currentNovel.current = ''; setProjection(null); return }
    currentNovel.current = novelId
    void loadProjection(novelId)
  }, [novelId, loadProjection])

  const model: CommandCenterViewModel | null = useMemo(
    () => (projection ? commandCenterViewModel(projection) : null),
    [projection])

  const refresh = useCallback(async (): Promise<CommandCenterViewModel | null> => {
    const payload = await loadProjection(currentNovel.current)
    return payload ? commandCenterViewModel(payload) : null
  }, [loadProjection])

  /* ------------------------------------------------------------- actions */
  const openLegacy = useCallback((tab: string, extra: DeepLinkParams = {}) => {
    go(legacyHash(novelId, tab, extra))
  }, [go, novelId])

  const createNovel = useCallback(async (id: string, title: string) => {
    await v3Writes.storyBuilderCreateNovel(id, title, '')
    try { localStorage.setItem('novelforge.active-novel', id) } catch { /* 忽略 */ }
    await loadLanding()
    goNovel(id, 'home')
  }, [goNovel, loadLanding])

  /** NF-011：作品级管理（重命名 / 归档删除），两个动作都只动作者可见元数据或归档位置。 */
  const renameNovel = useCallback(async (id: string, title: string) => {
    await v3Api.renameNovel(id, title)
    await loadLanding()
    if (currentNovel.current === id) await loadProjection(id)
  }, [loadLanding, loadProjection])

  const deleteNovel = useCallback(async (id: string) => {
    await v3Api.deleteNovel(id)
    await loadLanding()
  }, [loadLanding])

  const openObjective = useCallback((objective: ObjectiveViewModel) => {
    setContextObjective(objective)
    if (novelId) goNovel(novelId, objective.deepLink.view as V3View,
      { step: objective.deepLink.step, group: objective.deepLink.group, panel: objective.objectiveId })
  }, [goNovel, novelId])

  const openNextAction = useCallback(() => {
    if (!model || !novelId) return
    const link = model.nextAction.deepLink
    goNovel(novelId, (link.view || 'creation') as V3View,
      { step: link.step, group: link.group })
  }, [goNovel, model, novelId])

  /**
   * P3 推演推进：复用既有 runtime/advance，不新建推演引擎。
   * 反馈不是「200 OK」：结果全部来自真实 AdvanceResult 与刷新后的 projection。
   */
  const advanceSimulation = useCallback(async () => {
    if (!model || !novelId) return
    // NF-008：只推「当前真的可执行」的方向；选中的方向失效时退回第一条可执行方向。
    const candidate = model.simulation.candidates
      .find((row) => row.candidateId === selectedRouteId && row.available)
      ?? model.simulation.candidates.find((row) => row.available)
    if (!candidate) return
    const before = { tick: model.simulation.tick, revision: model.simulation.revision,
      objective: model.nextAction.title }
    setAdvancing(true)
    try {
      const result = await v3Writes.advanceRuntime(novelId, {
        action_id: candidate.candidateId,
        branch_id: model.simulation.branchId || 'main',
        expected_revision: model.simulation.revision,
      })
      const after = await refresh()
      const lines: string[] = []
      if (result.outcome || result.message) {
        lines.push(`故事结果：${result.outcome || result.message}`)
      }
      if (result.world_events?.length) {
        const labels = model.simulation.eventLabels
        const named = result.world_events.map((id) => labels[id]).filter(Boolean)
        lines.push(named.length > 0
          ? `世界变化：${named.join('、')}`
          : `世界状态发生了变化（${result.world_events.length} 项）`)
      }
      if (result.plot_transitions?.length) {
        lines.push(`剧情线变化：${result.plot_transitions.length} 条`)
      }
      if (result.triggered_events?.length) {
        const labels = model.simulation.eventLabels
        const named = result.triggered_events.map((id) => labels[id]).filter(Boolean)
        lines.push(named.length > 0
          ? `触发事件：${named.join('、')}`
          : `触发了 ${result.triggered_events.length} 个事件`)
      }
      if (result.future_plan_changed) {
        lines.push(`后续规划已调整：${result.replan_reason || '因为这次行动改变了条件'}`)
      }
      lines.push(`回合 ${before.tick} → ${result.tick} · 修订 ${before.revision} → ${result.revision}`)
      if (after) {
        lines.push(after.nextAction.title === before.objective
          ? `当前目标仍是：${after.nextAction.title}`
          : `当前目标：${before.objective} → ${after.nextAction.title}`)
        if (after.alerts.length > 0) {
          lines.push(`需要留意：${after.alerts[0].title}`)
        }
        lines.push(`下一步：${after.nextAction.actionLabel}`)
      }
      setSimulationFeedback({
        title: `推演了「${candidate.title}」`, lines })
    } catch (reason) {
      setSimulationFeedback({
        title: '这次推演没有执行',
        lines: [text(reason), '故事状态没有被修改；可以换一个方向或先补齐前置条件。'],
      })
    } finally {
      setAdvancing(false)
    }
  }, [model, novelId, refresh, selectedRouteId])

  /**
   * 默认选中一条真实候选方向：让「推演下一步」这个唯一 Primary CTA 永远可执行，
   * 同时选中结果对作者可见可改（不隐藏系统替你选了什么）。
   */
  useEffect(() => {
    if (!model) return
    const candidates = model.simulation.candidates
    if (candidates.length === 0) return
    if (candidates.some((row) => row.candidateId === selectedRouteId)) return
    const first = candidates.find((row) => row.available) ?? candidates[0]
    setSelectedRouteId(first.candidateId)
  }, [model, selectedRouteId])

  /* -------------------------------------------------------------- landing */
  if (route.name === 'landing' || !novelId) {
    return <NovelLanding cards={cards} loading={landingLoading} error={landingError}
      onRetry={() => { void loadLanding() }}
      onOpen={(id) => goNovel(id, 'home')}
      onCreate={createNovel}
      onRename={renameNovel}
      onDelete={deleteNovel} />
  }

  if (loading && !model) {
    return <div className="v3-full-state"><LoadingState label="正在读取作品状态…" /></div>
  }
  if (error && !model) {
    return <div className="v3-full-state">
      <ErrorState message={error} onRetry={() => { void loadProjection(novelId) }} />
      <Button variant="ghost" onClick={() => go('#/')}>回到作品列表</Button>
    </div>
  }
  if (!model) {
    return <div className="v3-full-state">
      <EmptyState icon="book" title="找不到这本作品"
        reason="它可能已经被移动或删除。"
        action={<Button variant="primary" onClick={() => go('#/')}>回到作品列表</Button>} />
    </div>
  }

  const view: V3View = route.name === 'novel' ? route.view : 'home'
  const params: DeepLinkParams = route.name === 'novel' ? route.params : {}

  const rail = <JourneyRail model={model} onRun={openNextAction}
    ctaVariant={view === 'outline' || view === 'review' ? 'secondary' : 'primary'}
    onOpenObjective={() => { if (model.currentObjective) openObjective(model.currentObjective) }}
    onOpenAlert={() => {
      const alert = model.alerts[0]
      if (!alert) return
      goNovel(novelId, alert.deepLink.view as V3View,
        { step: alert.deepLink.step, group: alert.deepLink.group })
    }} />

  return (
    <>
      <AppShell
        novelTitle={model.hero.title}
        stageLabel={model.hero.stageLabel}
        stageProgressLabel={`${model.stages.filter((row) => row.statusClass === 'COMPLETE').length} / ${model.stages.length} 阶段`}
        progressPercent={model.hero.progressPercent}
        stages={model.stages}
        activeView={view}
        onNavigate={(next) => goNovel(novelId, next)}
        onHome={() => goNovel(novelId, 'home')}
        rail={rail}
        alertCount={model.alerts.length}
        onOpenAlerts={() => {
          const alert = model.alerts[0]
          if (alert) {
            goNovel(novelId, alert.deepLink.view as V3View,
              { step: alert.deepLink.step, group: alert.deepLink.group })
          } else {
            goNovel(novelId, 'review')
          }
        }}
        onOpenLegacy={() => openLegacy('builder')}
        onSwitchNovel={() => go('#/')}
      >
        {view === 'home' ? (
          <CommandCenter model={model}
            onContinue={openNextAction}
            onOpenView={(target) => goNovel(novelId, target as V3View)}
            onOpenContent={(card) => goNovel(novelId, card.targetView as V3View)}
            onOpenRecent={(item) => goNovel(novelId, item.targetView as V3View)} />
        ) : view === 'creation' ? (
          <CreationFlow novelId={novelId} model={model} params={params}
            onChanged={refresh} onOpenLegacy={openLegacy} />
        ) : (
          <WorkspaceView view={view} model={model}
            onOpenObjective={openObjective}
            onOpenLegacy={(tab, extra) => openLegacy(tab, extra ?? {})}
            onOpenView={(target) => goNovel(novelId, target as V3View)}
            onChanged={refresh}
            onOpenContent={(card) => goNovel(novelId, card.targetView as V3View)}
            onOpenChapter={(chapter) => {
              setContextObjective(null)
              setContextEntity({ kind: 'chapter', chapter })
            }}
            onOpenCharacter={(character) => {
              setContextObjective(null)
              setContextEntity({ kind: 'character', character })
            }}
            onOpenLocation={(location) => {
              setContextObjective(null)
              setContextEntity({ kind: 'location', location })
            }}
            onOpenFaction={(faction) => {
              setContextObjective(null)
              setContextEntity({ kind: 'faction', faction })
            }}
            onOpenRoute={(candidate) => {
              setContextObjective(null)
              setSelectedRouteId(candidate.candidateId)
              setContextEntity({ kind: 'route', candidate })
            }}
            selectedRouteId={selectedRouteId}
            onSelectRoute={(candidate) => {
              setSelectedRouteId(candidate.candidateId)
              setSimulationFeedback(null)
            }}
            onAdvanceSimulation={() => { void advanceSimulation() }}
            advancing={advancing}
            simulationFeedback={simulationFeedback}
            compareRouteId={compareRouteId}
            onToggleCompare={(candidate) => {
              setSimulationFeedback(null)
              setCompareRouteId((current) => current === candidate.candidateId
                ? '' : candidate.candidateId)
              setSelectedRouteId((current) => current || candidate.candidateId)
            }}
            onCloseCompare={() => setCompareRouteId('')} />
        )}
      </AppShell>

      <ContextPanel open={Boolean(contextObjective)}
        title={contextObjective?.title ?? ''}
        subtitle={contextObjective?.statusLabel}
        onClose={() => setContextObjective(null)}
        footer={contextObjective ? (
          <Button variant="primary" iconAfter="next_action"
            onClick={() => {
              const target = contextObjective
              setContextObjective(null)
              goNovel(novelId, target.deepLink.view as V3View,
                { step: target.deepLink.step, group: target.deepLink.group })
            }}>{contextObjective.actionLabel}</Button>
        ) : null}>
        {contextObjective ? (
          <div className="v3-context-objective">
            <ProgressBar percent={contextObjective.percent}
              label={contextObjective.progressLabel} />
            <p>{contextObjective.description}</p>
            <p className="v3-context-why">
              <Icon name="objective" size={15} />为什么重要：{contextObjective.why}
            </p>
            {contextObjective.checklist.length > 0 ? (
              <ul className="v3-objective-checks">
                {contextObjective.checklist.map((row) => (
                  <li key={row.itemId} className={`v3-check ${row.done ? 'is-done' : ''}`}>
                    <span className="v3-check-mark" aria-hidden="true">
                      {row.done ? <Icon name="complete" size={16} /> : <span className="v3-check-empty" />}
                    </span>
                    <span className="v3-check-label">{row.label}</span>
                  </li>
                ))}
              </ul>
            ) : null}
            <p className="v3-context-unlock">
              <Icon name="next_action" size={15} />{contextObjective.unlockEffects}
            </p>
            <Card tone="quiet" className="v3-context-evidence">
              <h3>依据</h3>
              <ul>
                {contextObjective.evidence.map((row) => (
                  <li key={`${row.source}-${row.ref}`}>
                    <b>{row.source}</b><span>{row.summary}</span>
                  </li>
                ))}
              </ul>
            </Card>
          </div>
        ) : null}
      </ContextPanel>

      <ContextPanel open={Boolean(contextEntity)}
        title={entityTitle(contextEntity)}
        subtitle={entitySubtitle(contextEntity)}
        onClose={() => setContextEntity(null)}
        footer={contextEntity ? (
          contextEntity.kind === 'chapter' ? (
            <Button variant="primary" iconAfter="next_action"
              onClick={() => {
                const target = contextEntity
                setContextEntity(null)
                openLegacy('outline', { step: target.chapter.packageId })
              }} testId="v3-chapter-open-forge">打开大纲锻造</Button>
          ) : contextEntity.kind === 'route' ? (
            <Button variant="primary" iconAfter="next_action" disabled={advancing}
              testId="v3-route-advance"
              onClick={() => { void advanceSimulation() }}>{advancing
                ? '正在推演…' : '推演这条方向'}</Button>
          ) : (
            /* 复杂信息（Canon / provenance / planning）走既有完整面板，不在主界面展开。 */
            <Button variant="secondary" iconAfter="next_action" testId="v3-entity-advanced"
              onClick={() => {
                const target = contextEntity
                setContextEntity(null)
                openLegacy(target.kind === 'character'
                  ? (target.character.hasRelationships ? 'characters' : 'relations')
                  : target.kind === 'location' ? 'world' : 'regions')
              }}>{contextEntity.kind === 'character'
                ? (contextEntity.character.hasRelationships ? '打开完整角色面板' : '完善角色关系')
                : contextEntity.kind === 'location' ? '打开完整世界面板'
                : '打开区域与势力面板'}</Button>
          )
        ) : null}>
        {contextEntity?.kind === 'chapter' ? (
          <div className="v3-context-objective" data-testid="v3-context-chapter">
            {contextEntity.chapter.arcTitle ? (
              <p className="v3-context-why" data-testid="v3-context-chapter-arc">
                <Icon name="outline" size={15} />所属篇章：{contextEntity.chapter.arcTitle}
              </p>
            ) : null}
            {contextEntity.chapter.summary
              ? <p>{contextEntity.chapter.summary}</p>
              : <p className="v3-context-why">这一章还没有摘要：在「大纲锻造」里补充它的目的与冲突。</p>}
            {contextEntity.chapter.metaLabel ? (
              <p className="v3-context-why">
                <Icon name="chapter" size={15} />{contextEntity.chapter.metaLabel}
              </p>
            ) : null}
            {contextEntity.chapter.hook ? (
              <p className="v3-context-why">
                <Icon name="foreshadow" size={15} />结尾推力：{contextEntity.chapter.hook}
              </p>
            ) : null}
            {contextEntity.chapter.goals.length > 0 ? (
              <Card tone="quiet" className="v3-context-evidence">
                <h3>这一章要达成</h3>
                <ul>{contextEntity.chapter.goals.map((goal) => (
                  <li key={goal}><b>目标</b><span>{goal}</span></li>
                ))}</ul>
              </Card>
            ) : null}
            {contextEntity.chapter.conflicts.length > 0 ? (
              <Card tone="quiet" className="v3-context-evidence">
                <h3>这一章的冲突</h3>
                <ul>{contextEntity.chapter.conflicts.map((row) => (
                  <li key={row}><b>冲突</b><span>{row}</span></li>
                ))}</ul>
              </Card>
            ) : null}
            <EntityAdvancedDetails rows={[
              ['章纲包', `${contextEntity.chapter.packageId} · V${contextEntity.chapter.packageVersion}`],
              ['章节条目', contextEntity.chapter.canvasLabel],
            ]} />
          </div>
        ) : null}
        {contextEntity?.kind === 'character' ? (
          <div className="v3-context-objective" data-testid="v3-context-character">
            <p className="v3-context-why">
              <Icon name="character" size={15} />{contextEntity.character.roleLabel}
              {contextEntity.character.statusLabel ? ` · ${contextEntity.character.statusLabel}` : ''}
            </p>
            {contextEntity.character.namePlaceholder ? (
              <p className="v3-context-why" data-testid="v3-context-placeholder-name">
                <Icon name="warning" size={15} />
                「{contextEntity.character.name}」是设定候选给的原型占位名，不是已经命名好的角色名。
              </p>
            ) : null}
            {contextEntity.character.tags.length > 0 ? (
              <p className="v3-context-why">
                <Icon name="story" size={15} />{contextEntity.character.tags.join(' · ')}
              </p>
            ) : null}
            <Card tone="quiet" className="v3-context-evidence">
              <h3>这个角色现在有什么</h3>
              <ul>
                <li><b>进行中的目标</b><span>{contextEntity.character.activeGoals} 个</span></li>
                <li><b>记忆</b><span>{contextEntity.character.memories} 条</span></li>
              </ul>
            </Card>
            <Card tone="quiet" className="v3-context-evidence">
              <h3>关键关系</h3>
              {contextEntity.character.keyRelationships.length > 0 ? (
                <ul data-testid="v3-context-relations">
                  {contextEntity.character.keyRelationships.map((relation) => (
                    <li key={`${relation.sourceId}-${relation.targetId}`}>
                      <b>{relation.pairLabel}</b>
                      <span>
                        {relation.dimensionRows.map((row) => `${row.label} ${row.value}`)
                          .join(' · ') || relation.truthLabel}
                        {relation.tags.length > 0 ? ` · ${relation.tags.join(' / ')}` : ''}
                      </span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="v3-context-why" data-testid="v3-context-relations-empty">
                  <Icon name="relationship" size={15} />
                  还没有建立关键关系：关系会帮助故事形成冲突、合作和推动力。
                </p>
              )}
            </Card>
            <p className="v3-context-why">
              <Icon name="next_action" size={15} />
              {contextEntity.character.hasRelationships
                ? '想调整目标、记忆与人物弧，用下面的完整角色面板。'
                : '想补上关系，用下面的关系网面板建立第一条真实关系。'}
            </p>
            <EntityAdvancedDetails rows={[
              ['角色标识', contextEntity.character.characterId],
              ['事实来源', 'StoryState 已发生事实'],
            ]} />
          </div>
        ) : null}
        {contextEntity?.kind === 'location' ? (
          <div className="v3-context-objective" data-testid="v3-context-location">
            <p className="v3-context-why">
              <Icon name="location" size={15} />{contextEntity.location.kindLabel}
              {contextEntity.location.current ? ' · 当前地点' : ''}
              {contextEntity.location.visited ? ' · 已到访' : ''}
            </p>
            {contextEntity.location.accessLabel ? (
              <p className="v3-context-why">
                <Icon name="story" size={15} />进入条件：{contextEntity.location.accessLabel}
              </p>
            ) : null}
            {contextEntity.location.namePlaceholder ? (
              <p className="v3-context-why" data-testid="v3-context-placeholder-name">
                <Icon name="warning" size={15} />
                「{contextEntity.location.name}」是设定候选给的原型占位名，可以在内容包里改成真实地名。
              </p>
            ) : null}
            <Card tone="quiet" className="v3-context-evidence">
              <h3>这个地方的事实</h3>
              <ul>
                <li><b>危险度</b><span>{contextEntity.location.danger}</span></li>
                <li><b>控制方</b><span>{contextEntity.location.controlLabel || '未知'}</span></li>
              </ul>
            </Card>
            <EntityAdvancedDetails rows={[
              ['地点标识', contextEntity.location.locationId],
              ['事实来源', 'StoryState 已发生事实'],
            ]} />
          </div>
        ) : null}
        {contextEntity?.kind === 'faction' ? (
          <div className="v3-context-objective" data-testid="v3-context-faction">
            {contextEntity.faction.stanceLabel ? (
              <p className="v3-context-why">
                <Icon name="faction" size={15} />立场：{contextEntity.faction.stanceLabel}
              </p>
            ) : null}
            {contextEntity.faction.namePlaceholder ? (
              <p className="v3-context-why" data-testid="v3-context-placeholder-name">
                <Icon name="warning" size={15} />
                「{contextEntity.faction.name}」是设定候选给的原型占位名，可以在内容包里改成真实势力名。
              </p>
            ) : null}
            <Card tone="quiet" className="v3-context-evidence">
              <h3>这个势力的事实</h3>
              <ul>
                <li><b>影响力</b><span>{contextEntity.faction.influence}</span></li>
                <li><b>参与剧情线</b><span>{contextEntity.faction.activePlotCount} 条</span></li>
                <li><b>内部冲突</b><span>{contextEntity.faction.conflictCount} 处</span></li>
              </ul>
            </Card>
            <EntityAdvancedDetails rows={[
              ['势力标识', contextEntity.faction.factionId],
              ['事实来源', 'StoryState 已发生事实'],
            ]} />
          </div>
        ) : null}
        {contextEntity?.kind === 'route' ? (
          <div className="v3-context-objective" data-testid="v3-context-route">
            <p className="v3-context-why">
              <Icon name="route" size={15} />{contextEntity.candidate.kindLabel}
              {' · '}{contextEntity.candidate.stateLabel}
            </p>
            {contextEntity.candidate.reason ? (
              <p>{contextEntity.candidate.reason}</p>
            ) : null}
            {contextEntity.candidate.requirements.length > 0 ? (
              <Card tone="quiet" className="v3-context-evidence">
                <h3>需要满足</h3>
                <ul>{contextEntity.candidate.requirements.map((row) => (
                  <li key={row}><b>条件</b><span>{row}</span></li>
                ))}</ul>
              </Card>
            ) : null}
            {contextEntity.candidate.costs.length > 0
              || contextEntity.candidate.risks.length > 0 ? (
              <Card tone="quiet" className="v3-context-evidence">
                <h3>代价与风险</h3>
                <ul>
                  {contextEntity.candidate.costs.map((row) => (
                    <li key={row}><b>代价</b><span>{row}</span></li>
                  ))}
                  {contextEntity.candidate.risks.map((row) => (
                    <li key={row}><b>风险</b><span>{row}</span></li>
                  ))}
                </ul>
              </Card>
            ) : null}
            {/* 影响面：只显示投影里真实存在的对象。地点 / 势力来自内容包结构化
                entity id 与 P2 世界实体的交集，匹配不到就不显示，不做关键词猜测。 */}
            {contextEntity.candidate.relatedCharacters.length > 0 ? (
              <p className="v3-context-why" data-testid="v3-context-route-characters">
                <Icon name="character" size={15} />
                影响角色：{contextEntity.candidate.relatedCharacters.join('、')}
              </p>
            ) : null}
            {contextEntity.candidate.affectedLocations.length > 0 ? (
              <p className="v3-context-why" data-testid="v3-context-route-locations">
                <Icon name="location" size={15} />
                影响地点：{contextEntity.candidate.affectedLocations.join('、')}
              </p>
            ) : null}
            {contextEntity.candidate.affectedFactions.length > 0 ? (
              <p className="v3-context-why" data-testid="v3-context-route-factions">
                <Icon name="faction" size={15} />
                影响势力：{contextEntity.candidate.affectedFactions.join('、')}
              </p>
            ) : null}
            <EntityAdvancedDetails rows={[
              ['行动标识', contextEntity.candidate.candidateId],
              ['可见性', contextEntity.candidate.visibility],
            ]} />
          </div>
        ) : null}
      </ContextPanel>
    </>
  )
}

function text(reason: unknown): string {
  return reason instanceof Error ? reason.message : String(reason)
}

/** Workspace 实体详情：章节 / 角色 / 地点 / 势力共用同一个 ContextPanel。 */
type ContextEntity =
  | { kind: 'chapter'; chapter: ChapterViewModel }
  | { kind: 'character'; character: CharacterEntityViewModel }
  | { kind: 'location'; location: LocationEntityViewModel }
  | { kind: 'faction'; faction: FactionEntityViewModel }
  | { kind: 'route'; candidate: RouteCandidateViewModel }

function entityTitle(entity: ContextEntity | null): string {
  if (!entity) return ''
  if (entity.kind === 'chapter') return entity.chapter.title
  if (entity.kind === 'character') return entity.character.name
  if (entity.kind === 'location') return entity.location.name
  if (entity.kind === 'route') return entity.candidate.title
  return entity.faction.name
}

function entitySubtitle(entity: ContextEntity | null): string {
  if (!entity) return ''
  if (entity.kind === 'chapter') {
    return `第 ${entity.chapter.order} 章 · ${entity.chapter.statusLabel}`
  }
  if (entity.kind === 'character') return entity.character.roleLabel
  if (entity.kind === 'location') {
    return entity.location.current ? `${entity.location.kindLabel} · 当前地点`
      : entity.location.kindLabel
  }
  if (entity.kind === 'route') {
    return `故事方向 · ${entity.candidate.kindLabel} · ${entity.candidate.stateLabel}`
  }
  return entity.faction.stanceLabel || '势力'
}

/**
 * P2 §3.3：Canon / provenance / planning internals 默认折叠，
 * 只在作者主动展开「高级详情」时才出现。
 */
function EntityAdvancedDetails({ rows }: { rows: [string, string][] }) {
  const visible = rows.filter(([, value]) => Boolean(value))
  if (visible.length === 0) return null
  return (
    <details className="v3-context-advanced" data-testid="v3-context-advanced">
      <summary>高级详情</summary>
      <ul>
        {visible.map(([label, value]) => (
          <li key={label}><b>{label}</b><span>{value}</span></li>
        ))}
      </ul>
    </details>
  )
}
