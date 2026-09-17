import { useEffect, useMemo, useRef, useState } from 'react'
import AdventurePanel from './AdventurePanel'
import CharacterPanel from './CharacterPanel'
import CreativeBriefPanel from './CreativeBriefPanel'
import GuidedFlowPanel from './GuidedFlowPanel'
import CandidateCard from './components/CandidateCard'
import PanelBoundary from './components/PanelBoundary'
import {
  RegionCardsPanel, RelationshipPanel, SettingOverviewPanel,
} from './VisualOverviewPanels'
import {
  MoodboardPanel, OutlineTreePanel, RouteComparePanel,
} from './VisualOutputPanels'
import { CanonInspectorPanel, RepairCenterPanel } from './InspectorPanels'
import DesignTreePanel from './DesignTreePanel'
import DirectorPanel from './DirectorPanel'
import LinkagePanel from './LinkagePanel'
import OutlineItemEditor from './OutlineItemEditor'
import MemoryPanel from './MemoryPanel'
import OutlineForgePanel from './OutlineForgePanel'
import PlotPanel from './PlotPanel'
import ProgressionPanel from './ProgressionPanel'
import RouteLabPanel from './RouteLabPanel'
import SettingSeedPanel from './SettingSeedPanel'
import WorldPanel from './WorldPanel'

import {
  api,
  ApiError,
  GuidedFlowState,
  StoryBuilderCatalog,
  StoryBuilderOption,
  StoryBuilderRecommendation,
  StoryBuilderSessionPayload,
  StoryBlueprintPayload,
  StoryOutlinePackage,
} from './api'
import {
  CreatorTab, DeepLink, STAGE_LABELS, TAB_GROUPS, hintOfTab, isKnownTab, labelOfTab,
  readDeepLink, stageOfTab, writeDeepLink,
} from './guidedFlow'

const PROJECT_ID = 'novel_project'
const ACTIVE_NOVEL_KEY = 'novelforge.active-novel'
/** 当前故事按小说分别记录，避免切换小说后显示另一本小说的会话。 */
function activeStoryKey(novelId: string) {
  return 'novelforge.active-story.' + novelId
}
function rememberStory(novelId: string, storyId: string) {
  try { localStorage.setItem(activeStoryKey(novelId), storyId) } catch { /* 浏览器禁止存储时仍可使用会话 */ }
}
function forgetStory(novelId: string) {
  try { localStorage.removeItem(activeStoryKey(novelId)) } catch { /* 忽略 */ }
}

function readActiveStory(novelId: string) {
  try {
    // 兼容旧版按默认项目记录的键；读取后会再校验它属于哪本小说，避免串小说。
    return localStorage.getItem(activeStoryKey(novelId)) || LEGACY_ACTIVE_STORY_KEY() || ''
  } catch { return '' }
}

function LEGACY_ACTIVE_STORY_KEY() {
  try { return localStorage.getItem('novelforge.active-story.' + PROJECT_ID) || '' } catch { return '' }
}
const OUTLINE_LEVELS: { level: StoryOutlinePackage['level']; title: string; note: string }[] = [
  { level: 'BOOK', title: '全书主线', note: '先确定整本书从哪里开始、如何变化、在哪里收束。' },
  { level: 'VOLUME', title: '卷纲', note: '把全书主线分成可独立推进和收束的大阶段。' },
  { level: 'ARC', title: '篇章纲', note: '每篇围绕一个具体问题，以一次选择或后果收束。' },
  { level: 'CHAPTER', title: '详细章纲', note: '把篇章因果链展开为每章的目标、冲突和转折。' },
]

export default function StoryBuilderPage() {
  const [catalog, setCatalog] = useState<StoryBuilderCatalog | null>(null)
  const [payload, setPayload] = useState<StoryBuilderSessionPayload | null>(null)
  /** 当前正在读取的小说；异步结果只有在仍然匹配时才写回，避免切换小说时串数据。 */
  const currentNovel = useRef('')
  const [options, setOptions] = useState<StoryBuilderOption[]>([])
  const [recommendations, setRecommendations] = useState<StoryBuilderRecommendation[]>([])
  const [chosen, setChosen] = useState<string[]>([])
  const [customText, setCustomText] = useState('')
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(false)
  const [entryStep, setEntryStep] = useState('reader_experience')
  const [saving, setSaving] = useState(false)
  const [loadingRecommendations, setLoadingRecommendations] = useState(false)
  const [blueprint, setBlueprint] = useState<StoryBlueprintPayload['blueprint'] | null>(null)
  const [compiling, setCompiling] = useState(false)
  const [outlines, setOutlines] = useState<StoryOutlinePackage[]>([])
  const [outlineBusy, setOutlineBusy] = useState<string>('')
  const [error, setError] = useState('')
  const [designExpanded, setDesignExpanded] = useState(false)
  const [sessions, setSessions] = useState<{ session_id: string; created_at: string; label: string; selection_version: number }[]>([])
  const [novels, setNovels] = useState<{ novel_id: string; title: string; genre: string }[]>([])
  const [packs, setPacks] = useState<{ pack_id: string; title: string; genre: string }[]>([])
  const [newNovelId, setNewNovelId] = useState('')
  const [newPackId, setNewPackId] = useState('')
  const [projectId, setProjectId] = useState(() => {
    // W6-05：深链接里的 novel_id 优先于本地记忆，保证链接可直接分享/刷新恢复。
    try {
      return readDeepLink().novel_id || localStorage.getItem(ACTIVE_NOVEL_KEY) || PROJECT_ID
    } catch { return PROJECT_ID }
  })
  const initialLink = readDeepLink()
  // NF-014：未知页签（例如旧链接里的 tab=export）不允许渲染空壳，
  // 直接回落到默认面板，避免作者看到只有外壳的空白页。
  const [creatorTab, setCreatorTab] = useState<CreatorTab>(
    isKnownTab(initialLink.tab) ? initialLink.tab as CreatorTab : 'guided')
  const [deepLink, setDeepLink] = useState<DeepLink>(initialLink)
  const [flowState, setFlowState] = useState<GuidedFlowState | null>(null)

  /** W6-05：深链接导航（携带 novel_id / branch_id / package_id / step / group 上下文）。 */
  const goTo = (link: DeepLink) => {
    const next: DeepLink = { novel_id: projectId, ...link }
    if (link.tab) setCreatorTab(isKnownTab(link.tab) ? link.tab : 'guided')
    setDeepLink(next)
    writeDeepLink(next)
  }

  /** W6-01 / W6-03：顶部阶段徽标与“下一步”提示（只读投影，失败不影响主流程）。 */
  const refreshFlow = () => {
    api.guidedFlow(projectId)
      .then((state) => setFlowState(state))
      .catch(() => setFlowState(null))
  }

  useEffect(() => {
    refreshFlow()
  }, [projectId])

  /** W6-05：页内 hash 变化（深链接跳转）时同步小说 / 页签 / 步骤上下文。 */
  useEffect(() => {
    const onHashChange = () => {
      const link = readDeepLink()
      if (link.novel_id && link.novel_id !== projectId) {
        setProjectId(link.novel_id)
        try { localStorage.setItem(ACTIVE_NOVEL_KEY, link.novel_id) } catch { /* 忽略 */ }
      }
      if (link.tab) setCreatorTab(isKnownTab(link.tab) ? link.tab : 'guided')
      setDeepLink(link)
    }
    window.addEventListener('hashchange', onHashChange)
    return () => window.removeEventListener('hashchange', onHashChange)
  }, [projectId])

  /** 解析要恢复的故事：本地记录必须属于当前小说，否则退回最近故事。 */
  const resolveSession = async (
    novelId: string,
    hasSessions: boolean,
  ): Promise<StoryBuilderSessionPayload | null> => {
    const active = readActiveStory(novelId)
    if (active) {
      try {
        const candidate = await api.storyBuilderSession(active)
        if (candidate.session.project_id === novelId) return candidate
      } catch (reason) {
        if (!(reason instanceof ApiError) || reason.status !== 404) throw reason
      }
    }
    // 该作品没有任何构筑会话，这是合法业务状态而不是错误：
    // 已有列表接口的结果足以证明，因此不再请求 latest，避免把预期空状态打成 404。
    if (!hasSessions) return null
    try {
      return await api.storyBuilderLatest(novelId)
    } catch (reason) {
      if (reason instanceof ApiError && reason.status === 404) return null
      throw reason
    }
  }

  /** 读取当前小说的会话与列表；异步结果过期（已经切换小说）时直接丢弃。 */
  const load = async () => {
    const requested = projectId
    currentNovel.current = requested
    const stale = () => currentNovel.current !== requested
    setLoading(true)
    setError('')
    try {
      const nextCatalog = await api.storyBuilderCatalog()
      if (stale()) return
      setCatalog(nextCatalog)
      const nextNovels = (await api.storyBuilderNovels()).novels
      if (stale()) return
      setNovels(nextNovels)
      const nextPacks = (await api.storyBuilderContentPacks()).packs
      if (stale()) return
      setPacks(nextPacks)
      const nextSessions = (await api.storyBuilderSessions(requested)).sessions
      if (stale()) return
      setSessions(nextSessions)
      const nextPayload = await resolveSession(requested, nextSessions.length > 0)
      if (stale()) return
      setPayload(nextPayload)
      if (nextPayload) rememberStory(requested, nextPayload.session.session_id)
    } catch (reason) {
      if (stale()) return
      setError(reason instanceof Error ? reason.message : String(reason))
    } finally {
      if (!stale()) setLoading(false)
    }
  }

  useEffect(() => { void load() }, [projectId])

  useEffect(() => {
    if (!payload) { setOptions([]); return }
    let cancelled = false
    const step = payload.session.current_step
    const existing = payload.selected.filter((item) => item.step === step)
    setChosen(existing.flatMap((item) => item.option_id ? [item.option_id] : []))
    setCustomText(existing.find((item) => item.custom_text)?.custom_text ?? '')
    setLoadingRecommendations(true)
    Promise.all([api.storyBuilderStep(step), api.storyBuilderRecommend(payload.session.session_id, step)])
      .then(([stepResult, result]) => {
        if (cancelled) return
        setOptions(stepResult.options)
        setRecommendations(result.recommendation.recommendations)
      })
      .catch((reason) => { if (!cancelled) setError(reason instanceof Error ? reason.message : String(reason)) })
      .finally(() => { if (!cancelled) setLoadingRecommendations(false) })
    return () => { cancelled = true }
  }, [payload?.session.current_step, payload?.session.session_id, payload?.selected.map((item) => item.selection_id).join('|')])

  useEffect(() => {
    if (!payload) { setBlueprint(null); return }
    let cancelled = false
    api.storyBuilderBlueprint(payload.session.session_id)
      .then((result) => { if (!cancelled) setBlueprint(result.blueprint) })
      .catch((reason) => {
        if (cancelled) return
        if (!(reason instanceof ApiError) || reason.status !== 404) {
          setError(reason instanceof Error ? reason.message : String(reason))
        } else setBlueprint(null)
      })
    return () => { cancelled = true }
  }, [payload?.session.session_id, payload?.session.selection_version])

  useEffect(() => {
    if (!blueprint || blueprint.status !== 'CONFIRMED') { setOutlines([]); return }
    api.storyBuilderOutlines(blueprint.blueprint_id)
      .then((result) => setOutlines(result.outlines))
      .catch((reason) => setError(reason instanceof Error ? reason.message : String(reason)))
  }, [blueprint?.blueprint_id, blueprint?.version, blueprint?.status])

  const selectedByStep = useMemo(() => {
    const grouped = new Map<string, string[]>()
    for (const selection of payload?.selected ?? []) {
      const values = grouped.get(selection.step) ?? []
      values.push(selection.display_name || selection.custom_text || selection.option_id || '未命名选择')
      grouped.set(selection.step, values)
    }
    return grouped
  }, [payload])

  const novelOptions = useMemo(() => {
    const items = novels.map((item) => ({ id: item.novel_id, label: item.title || item.novel_id }))
    if (!items.some((item) => item.id === projectId)) {
      items.unshift({ id: projectId, label: payload?.novel?.title || projectId })
    }
    return items
  }, [novels, projectId, payload])

  const novelSelector = <label>小说<select aria-label="小说" value={projectId} disabled={saving || creating || compiling} onChange={(event) => {
    const id = event.target.value
    // 重复选择当前小说时保持现状，避免把已经载入的故事清空再重新读取。
    if (id === projectId) return
    try { localStorage.setItem(ACTIVE_NOVEL_KEY, id) } catch { /* 浏览器禁止存储时仍可切换 */ }
    setPayload(null); setBlueprint(null); setOutlines([]); setDesignExpanded(false)
    setProjectId(id)
  }}>{novelOptions.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select></label>

  const start = async () => {
    setCreating(true)
    setError('')
    try {
      const next = await api.storyBuilderCreate(projectId, entryStep)
      rememberStory(projectId, next.session.session_id); setPayload(next); setBlueprint(null); setOutlines([]); setDesignExpanded(false)
      setSessions((await api.storyBuilderSessions(projectId)).sessions)
    }
    catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)) }
    finally { setCreating(false) }
  }

  /** 新建小说：没有构筑会话时也要能创建，因此从 onboarding 表单抽成命名函数。 */
  const createNovel = async () => {
    const id = newNovelId.trim()
    if (id.length < 3) { setError('作品编号至少 3 个字符'); return }
    setCreating(true)
    setError('')
    try {
      await api.storyBuilderCreateNovel(id, id, newPackId)
      try { localStorage.setItem(ACTIVE_NOVEL_KEY, id); forgetStory(id) } catch { /* 忽略 */ }
      setProjectId(id); setNewNovelId('')
    } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)) }
    finally { setCreating(false) }
  }

  const refreshSession = async () => {
    // 没有会话时不再回退到 latest：那是合法空状态，不是需要恢复的错误。
    if (!payload) return null
    const latest = await api.storyBuilderSession(payload.session.session_id)
    setPayload(latest)
    return latest
  }

  const handleFailure = async (reason: unknown) => {
    const message = reason instanceof Error ? reason.message : String(reason)
    setError(message)
    if (reason instanceof ApiError && reason.status === 409) {
      try {
        await refreshSession()
        setError(`${message}，已为你刷新到最新进度。`)
      } catch { /* 保留原错误，页面仍可重试 */ }
    }
  }

  const toggleOption = (optionId: string) => {
    if (!payload) return
    if (payload.current_step.selection_mode === 'single') {
      setChosen([optionId])
      setCustomText('')
      return
    }
    setChosen((current) => current.includes(optionId)
      ? current.filter((id) => id !== optionId)
      : current.length < payload.current_step.max_selections ? [...current, optionId] : current)
  }

  const submitStep = async () => {
    if (!payload) return
    const custom = customText.trim()
    const count = chosen.length + (custom ? 1 : 0)
    if (count < payload.current_step.min_selections || count > payload.current_step.max_selections) {
      setError(`请选择 ${payload.current_step.min_selections} 至 ${payload.current_step.max_selections} 个方向。`)
      return
    }
    setSaving(true)
    setError('')
    try {
      const recommendedIds = new Set(recommendations.flatMap((item) => item.option_id ? [item.option_id] : []))
      const optionSource = chosen.length > 0 && chosen.every((id) => recommendedIds.has(id)) ? 'recommended' : 'author'
      const next = await api.storyBuilderSelect(payload.session.session_id, {
        step: payload.session.current_step,
        option_ids: chosen,
        custom_texts: custom ? [custom] : [],
        expected_selection_version: payload.session.selection_version,
        option_source: optionSource,
      })
      setPayload(next)
      if (catalog?.steps.every((step) => next.session.completed_steps.includes(step.step)) && !next.session.needs_review_steps.length && !next.design_tree?.some((node) => node.needs_review)) {
        setBlueprint((await api.storyBuilderCompileBlueprint(next.session.session_id)).blueprint)
        document.querySelector('.story-builder-page')?.scrollTo({ top: 0, behavior: 'smooth' })
      }
    } catch (reason) { await handleFailure(reason) }
    finally { setSaving(false) }
  }

  const goBack = async (step: string) => {
    if (!payload) return
    setSaving(true)
    setError('')
    try {
      setPayload(await api.storyBuilderBack(
        payload.session.session_id,
        step,
        payload.session.selection_version,
      ))
    } catch (reason) { await handleFailure(reason) }
    finally { setSaving(false) }
  }

  const compileBlueprint = async () => {
    if (!payload) return
    setCompiling(true)
    setError('')
    try { setBlueprint((await api.storyBuilderCompileBlueprint(payload.session.session_id)).blueprint) }
    catch (reason) { await handleFailure(reason) }
    finally { setCompiling(false) }
  }

  const confirmBlueprint = async () => {
    if (!blueprint) return
    setCompiling(true)
    setError('')
    try {
      setBlueprint((await api.storyBuilderConfirmBlueprint(blueprint.blueprint_id, blueprint.version)).blueprint)
      await refreshSession()
    } catch (reason) { await handleFailure(reason) }
    finally { setCompiling(false) }
  }

  const replaceOutline = (next: StoryOutlinePackage) => {
    setOutlines((current) => [...current.filter((item) => item.level !== next.level), next]
      .sort((a, b) => OUTLINE_LEVELS.findIndex((item) => item.level === a.level) - OUTLINE_LEVELS.findIndex((item) => item.level === b.level)))
  }

  const compileOutline = async (level: StoryOutlinePackage['level'], regenerate = false) => {
    if (!blueprint) return
    setOutlineBusy(level)
    setError('')
    try {
      replaceOutline((await api.storyBuilderCompileOutline(
        blueprint.blueprint_id, level, blueprint.version, regenerate,
      )).outline)
    } catch (reason) { await handleFailure(reason) }
    finally { setOutlineBusy('') }
  }

  const confirmOutline = async (outline: StoryOutlinePackage) => {
    setOutlineBusy(outline.level)
    setError('')
    try {
      replaceOutline((await api.storyBuilderConfirmOutline(outline.package_id, outline.version)).outline)
      if (blueprint) {
        const refreshed = await api.storyBuilderOutlines(blueprint.blueprint_id)
        setOutlines(refreshed.outlines)
      }
    } catch (reason) { await handleFailure(reason) }
    finally { setOutlineBusy('') }
  }

  if (loading) return <div className="story-builder-state">正在读取构筑进度…</div>
  if (!catalog) {
    // 读取失败时仍然允许切换小说，避免卡在加载失败的页面。
    return <div className="story-builder-state error">
      故事构筑加载失败：{error || '请确认后端已启动'}
      <div className="story-switcher">{novelSelector}</div>
      <button className="btn" onClick={() => { void load() }}>重新读取</button>
    </div>
  }

  const entrySelector = <label>新故事起点<select aria-label="新故事起点" value={entryStep} disabled={creating} onChange={(event) => setEntryStep(event.target.value)}>
    <option value="reader_experience">读者体验</option>
    <option value="worldview">世界观</option>
    <option value="protagonist">人物灵感</option>
    <option value="major_events">开场事件</option>
  </select></label>

  /*
   * Phase 1：没有 V2 构筑会话是合法业务状态。
   *
   * 页面 Shell、顶部导航、TAB_GROUPS 与 URL tab 状态必须照常渲染；只有真正依赖
   * 会话数据的面板内容（十步构筑 / 蓝图）才进入初始化态。不能因为没有 session
   * 就让整个高级工具系统消失。
   */
  const completed = new Set(payload?.session.completed_steps ?? [])
  const needsReview = new Set(payload?.session.needs_review_steps ?? [])
  const current = payload?.current_step ?? catalog.steps[0]
  const currentIndex = payload
    ? catalog.steps.findIndex((step) => step.step === payload.session.current_step) : -1
  const allComplete = payload
    ? catalog.steps.length > 0 && catalog.steps.every((step) => completed.has(step.step))
    : false
  const recommendationById = new Map(
    recommendations.flatMap((item) => item.option_id ? [[item.option_id, item] as const] : []),
  )
  const customRecommendations = recommendations.filter((item) => item.custom_text)
  const blueprintCurrent = Boolean(payload && blueprint
    && blueprint.source_selection_version === payload.session.selection_version)
  const settingsReady = allComplete && needsReview.size === 0
  const headerTitle = payload
    ? (settingsReady ? '设定已完成，开始你的故事' : current.title)
    : (creatorTab === 'builder' ? '这本书还没有构筑会话' : `高级工具 · ${labelOfTab(creatorTab)}`)
  const headerPrompt = payload
    ? (settingsReady ? '确认故事蓝图，进入剧情闯关。' : current.prompt)
    : '没有构筑会话也能直接使用下方的高级工具面板；建立会话后这里会显示十步构筑进度。'

  return (
    <main className="story-builder-page">
      <header className="story-builder-head">
        <div>
          <span className="story-builder-kicker">故事构筑</span>
          <h2>{headerTitle}</h2>
          <p>{headerPrompt}</p>
        </div>
        <div className="story-switcher">
          {novelSelector}
          {entrySelector}
          {payload ? <>
            <label>已保存故事<select aria-label="已保存故事" data-testid="story-builder-session-select" value={payload.session.session_id} disabled={saving || creating || compiling || Boolean(outlineBusy)} onChange={async (event) => {
              const id = event.target.value; setSaving(true); setError('')
              try { const next = await api.storyBuilderSession(id); rememberStory(next.session.project_id, id); setPayload(next); setBlueprint(null); setOutlines([]); setDesignExpanded(false) }
              catch (reason) { await handleFailure(reason) } finally { setSaving(false) }
            }}>{sessions.map((session) => <option key={session.session_id} value={session.session_id}>{session.label} · {new Date(session.created_at).toLocaleString('zh-CN')}</option>)}</select></label>
            <button className="btn" disabled={saving || creating || compiling || Boolean(outlineBusy)} onClick={start}>{creating ? '正在创建…' : '新建故事'}</button>
            <div className="story-builder-version">小说：{payload.novel?.title || payload.session.project_id} · 选择版本 {payload.session.selection_version}</div>
          </> : <>
            {/* 没有会话时：新建小说入口必须仍然可达（原来是 onboarding 独占的能力）。 */}
            <label>新小说编号<input aria-label="新小说编号" data-testid="story-builder-new-novel-id" value={newNovelId} maxLength={64}
              onChange={(event) => setNewNovelId(event.target.value)} placeholder="例如 novel_xianxia" /></label>
            <label>内容包<select aria-label="内容包" data-testid="story-builder-new-pack" value={newPackId} disabled={creating}
              onChange={(event) => setNewPackId(event.target.value)}>
              <option value="">默认内容包</option>
              {packs.map((item) => <option key={item.pack_id} value={item.pack_id}>{item.title || item.pack_id}</option>)}
            </select></label>
            <button className="btn" data-testid="story-builder-new-novel-submit"
              disabled={creating || !newNovelId.trim()} onClick={createNovel}>新建小说</button>
          </>}
        </div>
      </header>

      <div className="creator-block">
        <div className="creator-stage-bar" data-testid="creator-stage-bar">
          <span className="story-builder-kicker">创作者面板</span>
          <span className="badge" data-testid="stage-badge">
            {flowState ? flowState.current_stage_label : '正在读取阶段…'}
          </span>
          <span className="stage-next" data-testid="stage-next">
            {flowState?.next_step
              ? `下一步：${flowState.next_step.title}（${flowState.next_step.stage_label}）`
              : '下一步：从引导流开始一句创意'}
          </span>
          <span className="stage-current" data-testid="stage-current">
            我在：{labelOfTab(creatorTab)} · {hintOfTab(creatorTab)}
          </span>
        </div>
        {TAB_GROUPS.map((group) => <div className="creator-tab-group" key={group.stage}
          data-testid={`tab-group-${group.stage}`}>
          <span className="creator-tab-group-label">{STAGE_LABELS[group.stage]}</span>
          <div className="creator-tabs" role="tablist" aria-label={`${group.stage} 面板`}>
            {group.tabs.map((row) => <button type="button" role="tab" key={row.tab}
              aria-selected={creatorTab === row.tab}
              className={creatorTab === row.tab ? 'active' : ''}
              onClick={() => goTo({ novel_id: projectId, tab: row.tab })}>{row.label}</button>)}
          </div>
        </div>)}
      </div>
      <PanelBoundary resetKey={creatorTab} label={labelOfTab(creatorTab)}>
      {creatorTab === 'guided' && <GuidedFlowPanel novelId={projectId}
        initialStep={deepLink.step ?? ''} initialGroup={deepLink.group ?? ''}
        onAdvanced={(target) => { refreshFlow(); goTo({ tab: target.tab as CreatorTab, step: target.step }) }} />}
      {creatorTab === 'world' && <WorldPanel novelId={projectId} />}
      {creatorTab === 'characters' && <CharacterPanel novelId={projectId} />}
      {creatorTab === 'plot' && <PlotPanel novelId={projectId} />}
      {creatorTab === 'route' && <RouteLabPanel novelId={projectId}
        onDeepLink={(link) => goTo(link)} />}
      {creatorTab === 'outline' && <OutlineForgePanel novelId={projectId}
        initialBranchId={deepLink.branch_id ?? ''}
        initialPackageId={deepLink.package_id ?? ''}
        initialVersion={deepLink.version ?? ''}
        onDeepLink={(link) => goTo(link)} />}
      {creatorTab === 'progression' && <ProgressionPanel novelId={projectId} />}
      {creatorTab === 'memory' && <MemoryPanel novelId={projectId} />}
      {creatorTab === 'director' && <DirectorPanel novelId={projectId} />}
      {creatorTab === 'overview' && <SettingOverviewPanel novelId={projectId} />}
      {creatorTab === 'regions' && <RegionCardsPanel novelId={projectId} />}
      {creatorTab === 'relations' && <RelationshipPanel novelId={projectId} />}
      {creatorTab === 'compare' && <RouteComparePanel novelId={projectId}
        initialBranchId={deepLink.branch_id ?? ''} />}
      {creatorTab === 'tree' && <OutlineTreePanel novelId={projectId}
        initialBranchId={deepLink.branch_id ?? ''} />}
      {creatorTab === 'mood' && <MoodboardPanel novelId={projectId} />}
      {creatorTab === 'inspector' && <CanonInspectorPanel novelId={projectId}
        initialRef={deepLink.step ?? ''} onDeepLink={(link) => goTo(link)} />}
      {creatorTab === 'repair' && <RepairCenterPanel novelId={projectId}
        onDeepLink={(link) => goTo(link)} />}
      {creatorTab === 'linkage' && <LinkagePanel novelId={projectId} />}
      {creatorTab === 'builder' && (payload ? <div className="story-builder-layout">
        <nav className="builder-steps" aria-label="故事构筑步骤">
          {catalog.steps.map((step, index) => {
            const isCurrent = step.step === payload.session.current_step
            const isDone = completed.has(step.step)
            const review = needsReview.has(step.step)
            return (
              <button
                type="button"
                className={`builder-step ${isCurrent ? 'current' : ''} ${isDone ? 'done' : ''}`}
                key={step.step}
                disabled={saving || (!isDone && !isCurrent)}
                onClick={() => isDone && !isCurrent && goBack(step.step)}
              >
                <span className="builder-step-number">{String(index + 1).padStart(2, '0')}</span>
                <span><b>{step.title}</b><small>{review ? '待复核' : isDone ? '已确认' : isCurrent ? '当前' : '未解锁'}</small></span>
              </button>
            )
          })}
        </nav>

        <section className="builder-choice-area">
          {allComplete && !needsReview.size && !blueprintCurrent && <div className="builder-ready"><b>十步设定已保存</b><button className="btn primary" disabled={compiling || saving} onClick={compileBlueprint}>{compiling ? '正在整合…' : '整合并查看故事蓝图'}</button></div>}
          <details open={!allComplete || needsReview.size > 0} className="builder-config-details">
          <summary>{allComplete ? '查看 / 调整十步设定' : '当前设定'}</summary>
          <div className="builder-section-title">
            <div><h3>选择你的方向</h3><span>{current.selection_mode === 'multiple' ? `可选 ${current.min_selections}-${current.max_selections} 项` : '选择 1 项'}</span></div>
          </div>
          <div className="builder-option-grid">
            {options.map((option) => {
              const selected = chosen.includes(option.id)
              const recommendation = recommendationById.get(option.id)
              const available = selected || Boolean(recommendation)
              return (
              <CandidateCard key={option.id} className="builder-option"
                testId="builder-option-card"
                title={option.name}
                summary={option.summary}
                reason={recommendation?.reason ?? ''}
                source={`十步目录 · ${current.title}`}
                selected={selected}
                disabled={!available || saving}
                impact={Object.keys(option.effects).length > 0 ? {
                  profile_fields: Object.keys(option.effects).slice(0, 2),
                  pack_sections: option.tags.slice(0, 3),
                } : null}
                onToggle={() => toggleOption(option.id)} />
            )})}
          </div>
          {loadingRecommendations && <div className="story-builder-message">正在根据已有选择整理推荐…</div>}
          {!loadingRecommendations && !options.length && <div className="story-builder-message">当前步骤暂无可用方向，请返回检查前置选择。</div>}
          {customRecommendations.length > 0 && <div className="builder-custom-recommendations"><h4>还可以这样设定</h4>{customRecommendations.map((item) => <button type="button" className="btn" key={item.custom_text} onClick={() => { setCustomText(item.custom_text); if (current.selection_mode === 'single') setChosen([]) }}>{item.custom_text}<small>{item.reason}</small></button>)}</div>}
          <label className="builder-custom-input">
            <span>或写下你自己的方向</span>
            <textarea value={customText} rows={3} maxLength={2000} onChange={(event) => { setCustomText(event.target.value); if (current.selection_mode === 'single' && event.target.value.trim()) setChosen([]) }} placeholder={`例如：写下你对“${current.title}”的具体想法`} />
          </label>
          <div className="builder-actions">
            <button className="btn" disabled={saving || currentIndex <= 0} onClick={() => goBack(catalog.steps[currentIndex - 1].step)}>返回上一步</button>
            <span>{needsReview.has(current.step) ? '前置选择已变化，请重新确认本步。' : allComplete ? '十步选择已齐全。' : '确认后将根据本步选择推荐下一步。'}</span>
            <button className="btn primary" disabled={saving || loadingRecommendations} onClick={submitStep}>{saving ? '正在保存…' : allComplete ? '重新确认本步' : currentIndex === catalog.steps.length - 1 ? '完成构筑' : '确认并继续'}</button>
          </div>
          </details>
          <details className="builder-config-details design-expansion" open={!allComplete || designExpanded || payload.design_tree?.some((node) => node.needs_review)}>
            <summary onClick={(event) => { event.preventDefault(); setDesignExpanded((value) => !value) }}>细化背景、人物与开篇（可选）</summary>
            <DesignTreePanel payload={payload} all={allComplete} busy={saving || compiling} onBusy={setSaving} onChange={setPayload} onFailure={handleFailure} />
          </details>
          {blueprint && <section className={`builder-blueprint ${blueprintCurrent ? '' : 'stale'}`}>
            <div className="builder-blueprint-head"><div><span>故事蓝图 V{blueprint.version}</span><h3>{blueprint.status === 'CONFIRMED' ? '已确认蓝图' : '蓝图候选'}</h3></div><span className={`badge ${blueprint.status === 'CONFIRMED' ? 'pass' : ''}`}>{blueprint.status === 'CONFIRMED' ? '已确认' : blueprintCurrent ? '待确认' : '已过期'}</span></div>
            <p className="builder-premise">{blueprint.premise}</p>
            {Object.entries(blueprint.design_summaries || {}).map(([key, value]) => <p key={key}>{value}</p>)}
            {!blueprintCurrent && <div className="story-builder-message error">你的选择已经变化，请重新生成蓝图。</div>}
            {blueprint.unresolved_conflicts.map((conflict, index) => <div className="builder-conflict" key={`${conflict.code}-${index}`}>{conflict.message}</div>)}
            <div className="builder-blueprint-sections">{blueprint.sections.map((section) => <details key={section.step}><summary>{catalog.steps.find((step) => step.step === section.step)?.title ?? section.step}</summary><p>{section.summary}</p><small>来源：{section.source_selection_ids.length} 条作者选择</small></details>)}</div>
            {blueprint.status !== 'CONFIRMED' && <div className="builder-blueprint-actions"><span>{blueprint.unresolved_conflicts.length ? '请先处理待复核选择。' : '确认后才能继续生成分层大纲。'}</span><button className="btn primary" disabled={!blueprintCurrent || blueprint.unresolved_conflicts.length > 0 || compiling} onClick={confirmBlueprint}>{compiling ? '正在确认…' : '确认故事蓝图'}</button></div>}
          </section>}
          {blueprintCurrent && !needsReview.size && blueprint?.status === 'CONFIRMED' && <AdventurePanel key={`${blueprint.blueprint_id}-${blueprint.version}`} id={blueprint.blueprint_id} version={blueprint.version} onOutline={() => { api.storyBuilderOutlines(blueprint.blueprint_id).then((result) => { setOutlines(result.outlines); document.querySelector('.builder-outline-flow')?.scrollIntoView({ behavior: 'smooth' }) }).catch(handleFailure) }} />}
          {blueprintCurrent && !needsReview.size && blueprint?.status === 'CONFIRMED' && <section className="builder-outline-flow">
            <div className="builder-outline-title"><span>分层大纲</span><h3>一层一层确认</h3><p>只有上一层确认后，才会开放下一层。重新生成会创建新版本，不覆盖旧稿。</p></div>
            {OUTLINE_LEVELS.map((config, index) => {
              const outline = outlines.find((item) => item.level === config.level)
              const previous = index > 0 ? outlines.find((item) => item.level === OUTLINE_LEVELS[index - 1].level) : null
              const unlocked = index === 0 || previous?.status === 'CONFIRMED'
              return <article className={`builder-outline-level ${outline?.status === 'NEEDS_REVIEW' ? 'needs-review' : ''}`} key={config.level}>
                <div className="builder-outline-level-head"><span>{String(index + 1).padStart(2, '0')}</span><div><h4>{config.title}</h4><p>{config.note}</p></div><span className="badge">{outline ? `V${outline.version} · ${outline.status === 'CONFIRMED' ? '已确认' : outline.status === 'NEEDS_REVIEW' ? '待复核' : '待确认'}` : unlocked ? '可生成' : '未解锁'}</span></div>
                {!outline && <button className="btn primary" disabled={!unlocked || Boolean(outlineBusy)} onClick={() => compileOutline(config.level)}>{outlineBusy === config.level ? '正在生成…' : `生成${config.title}`}</button>}
                {outline && <>
                  {outline.route_source && <p>当前路线：{outline.route_source.branch_id === 'main' ? '原路线' : '所选分支'} · {outline.route_history?.length} 次实际选择</p>}
                  {outline.level === 'BOOK' && outline.design_sections && <details><summary>人物、世界与作者设定</summary>{Object.entries(outline.design_sections).map(([key, value]) => <p key={key}>{value}</p>)}</details>}
                  {outline.pending_questions?.map((question, i) => <p className="design-warning" key={i}>{question}</p>)}
                  <div className="builder-outline-items">{outline.items.map((item) => <details key={`${item.item_id}-${outline.version}`}><summary>{item.title}</summary><p>{item.summary}</p><dl><div><dt>开始</dt><dd>{item.start_state}</dd></div><div><dt>结束</dt><dd>{item.end_state}</dd></div><div><dt>结尾推力</dt><dd>{item.ending_hook}</dd></div></dl>
                    {item.pov && <p>{item.pov} · {item.time} · {item.location}</p>}
                    {item.must_keep.length > 0 && <details><summary>设计要求与来源</summary>{item.must_keep.map((note, i) => <p key={i}>{note}</p>)}</details>}
                    <OutlineItemEditor outline={outline} item={item} onSaved={async () => { if (blueprint) setOutlines((await api.storyBuilderOutlines(blueprint.blueprint_id)).outlines) }} />
                  </details>)}</div>
                  <button className="btn" disabled={Boolean(outlineBusy)} onClick={async () => {
                    setOutlineBusy(config.level)
                    try {
                      const file = await api.exportOutline(outline.package_id, outline.version)
                      const href = URL.createObjectURL(new Blob([file.content], { type: 'text/markdown;charset=utf-8' }))
                      const a = document.createElement('a'); a.href = href; a.download = file.filename; a.click(); setTimeout(() => URL.revokeObjectURL(href), 1000)
                    } catch (reason) { await handleFailure(reason) } finally { setOutlineBusy('') }
                  }}>导出{config.title}</button>
                  <div className="builder-outline-actions"><button className="btn" disabled={Boolean(outlineBusy)} onClick={() => compileOutline(config.level, true)}>{outlineBusy === config.level ? '正在生成…' : '重新生成新版本'}</button>{outline.status !== 'CONFIRMED' && outline.status !== 'NEEDS_REVIEW' && <button className="btn primary" disabled={Boolean(outlineBusy)} onClick={() => confirmOutline(outline)}>确认{config.title}</button>}{outline.status === 'NEEDS_REVIEW' && <button className="btn primary" disabled={Boolean(outlineBusy)} onClick={() => compileOutline(config.level)}>根据新上层重新生成</button>}</div>
                </>}
              </article>
            })}
          </section>}
        </section>

        <aside className="builder-summary">
          <h3>你的故事</h3>
          <p>已确认的选择会在这里汇合。</p>
          {catalog.steps.map((step) => {
            const values = selectedByStep.get(step.step)
            if (!values?.length) return null
            return <div className="builder-summary-item" key={step.step}><b>{step.title}</b>{values.map((value) => <span key={value}>{value}</span>)}</div>
          })}
          {!payload.selected.length && <div className="builder-summary-empty">还没有选择。从当前步骤开始，故事会逐渐显出轮廓。</div>}
        </aside>
      </div> : (
        <section className="story-builder-init" data-testid="story-builder-init">
          <h3>这本书还没有构筑会话</h3>
          <p>十步构筑与故事蓝图需要先建立一个构筑会话。建立后，这里会显示当前步骤、
            候选方向与分层大纲；在此之前，其他高级工具面板已经可以使用。</p>
          <div className="story-builder-init-actions">
            <button className="btn primary" disabled={creating} onClick={start}
              data-testid="story-builder-init-start">
              {creating ? '正在创建…' : '建立构筑会话'}
            </button>
            <button className="btn" onClick={() => goTo({ novel_id: projectId, tab: 'guided' })}
              data-testid="story-builder-init-guided">
              先走引导流
            </button>
          </div>
        </section>
      ))}
      </PanelBoundary>
      {error && <div className="story-builder-message error">{error}</div>}
    </main>
  )
}
