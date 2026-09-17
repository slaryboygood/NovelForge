/*
 * 创作工作区 —— V3 第一条真实迁移的作者主流程：
 *
 * 一句话创意 → 方向候选 → 选择 → 设定候选 → 选择 → 设定自检 → 开始推演
 *
 * 目标驱动而不是向导：顶部说明当前目标，中间是唯一的主动作，
 * 完成后的反馈说明「故事发生了什么变化、解锁了什么、下一步去哪」。
 *
 * 所有状态来自 application 投影与既有 V2 API；这里不复制任何 domain 规则。
 */
import { useCallback, useEffect, useMemo, useState } from 'react'
import { api, CreativeBrief, SettingSeed, SettingsCheckReport } from '../api'
import {
  SETTING_GROUP_LABELS, SETTING_GROUP_ORDER, isMultipleSelectionGroup,
  toggleSelection,
} from '../storyBuilderSelection'
import Icon from './design-system/icons/IconRegistry'
import {
  Badge, Button, Card, Disclosure, EmptyState, LoadingState, ProgressBar,
  SectionHeading,
} from './design-system/primitives'
import { ChoiceCard, FeedbackCard } from './design-system/choices'
import type { CommandCenterViewModel } from './viewmodel'
import type { DeepLinkParams } from './navModel'

type FlowStep = 'idea' | 'settings' | 'check' | 'runtime'

const STEP_ORDER: FlowStep[] = ['idea', 'settings', 'check', 'runtime']

const STEP_TITLES: Record<FlowStep, string> = {
  idea: '一句话创意',
  settings: '设定与起点',
  check: '设定自检',
  runtime: '开始推演',
}

import type { FeedbackViewModel } from './design-system/choices'

export default function CreationFlow({ novelId, model, params, onChanged, onOpenLegacy }: {
  novelId: string
  model: CommandCenterViewModel
  params: DeepLinkParams
  onChanged: () => Promise<CommandCenterViewModel | null>
  onOpenLegacy: (tab: string, extra?: DeepLinkParams) => void
}) {
  const facts = model.facts
  const [step, setStep] = useState<FlowStep>(() => stepFromParams(params, facts))
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [feedback, setFeedback] = useState<FeedbackViewModel | null>(null)

  const [idea, setIdea] = useState('')
  const [reference, setReference] = useState('')
  const [readerExperience, setReaderExperience] = useState('')
  const [draft, setDraft] = useState<CreativeBrief | null>(null)
  const [suggestion, setSuggestion] = useState<Awaited<
    ReturnType<typeof api.creativeSuggest>> | null>(null)
  const [seed, setSeed] = useState<SettingSeed | null>(null)
  const [seedSaved, setSeedSaved] = useState(false)
  const [check, setCheck] = useState<SettingsCheckReport | null>(null)
  const [focusGroup, setFocusGroup] = useState(params.group ?? '')
  const [runtimeInfo, setRuntimeInfo] = useState<{ revision: number; tick: number;
    created: boolean } | null>(null)
  /**
   * NF-010：还没有「确定这个方向」之前的创意与候选只存在内存里，刷新就丢。
   * 现在把它们缓存在本机（localStorage），并在界面上明确说明「还没有保存」。
   */
  const [savedIdea, setSavedIdea] = useState('')
  const localDraftKey = `novelforge.creation-draft.${novelId}`

  useEffect(() => {
    setStep(stepFromParams(params, model.facts))
    if (params.group) setFocusGroup(params.group)
    // 只在深链接变化时同步，避免刷新投影把作者手动切换的步骤重置。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params.step, params.group, novelId])

  useEffect(() => {
    let cancelled = false
    setError('')
    api.creativeBrief(novelId)
      .then((state) => {
        if (cancelled) return
        if (state.suggestion) {
          setSuggestion(state.suggestion)
          setDraft(state.suggestion.selection)
          setIdea(state.suggestion.original_idea || '')
          setReaderExperience(state.suggestion.reader_experience || '')
          setReference(state.suggestion.references?.[0] ?? '')
        } else if (state.brief) {
          setDraft(state.brief)
          setIdea(state.brief.original_idea || '')
        }
        setSavedIdea(state.brief?.original_idea?.trim()
          || state.suggestion?.original_idea?.trim() || '')
      })
      .catch((reason) => { if (!cancelled) setError(text(reason)) })
    return () => { cancelled = true }
  }, [novelId])

  /** 恢复本机缓存的创意草稿与候选（只在输入为空时填充，不覆盖已保存的作品数据）。 */
  useEffect(() => {
    try {
      const raw = localStorage.getItem(localDraftKey)
      if (!raw) return
      const cached = JSON.parse(raw) as { idea?: string; reference?: string;
        readerExperience?: string; suggestion?: unknown }
      setIdea((current) => current || cached.idea || '')
      setReference((current) => current || cached.reference || '')
      setReaderExperience((current) => current || cached.readerExperience || '')
      if (cached.suggestion) {
        setSuggestion((current) => current ?? (cached.suggestion as never))
      }
    } catch { /* 缓存损坏时忽略，不影响正常流程 */ }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [localDraftKey])

  /** 输入变化就更新本机缓存（只有「确定这个方向」才写进作品）。 */
  useEffect(() => {
    try {
      if (!idea.trim() && !reference.trim() && !readerExperience.trim()) {
        localStorage.removeItem(localDraftKey)
        return
      }
      localStorage.setItem(localDraftKey, JSON.stringify({
        idea, reference, readerExperience, suggestion,
      }))
    } catch { /* 隐私模式等场景下静默降级 */ }
  }, [idea, localDraftKey, readerExperience, reference, suggestion])

  const ideaUnsaved = Boolean(idea.trim()) && idea.trim() !== savedIdea

  useEffect(() => {
    let cancelled = false
    api.settingSeed(novelId)
      .then((state) => {
        if (cancelled) return
        setSeed(state.seed)
        setSeedSaved(Boolean(state.saved))
      })
      .catch(() => { /* 还没有创意简报时不提示错误 */ })
    return () => { cancelled = true }
  }, [novelId, model.facts.creativeBriefSaved])

  useEffect(() => {
    if (!model.facts.settingsCheckOk) return
    let cancelled = false
    api.settingsCheck(novelId)
      .then((report) => { if (!cancelled) setCheck(report) })
      .catch(() => { /* 自检不可读时保持上一步 */ })
    return () => { cancelled = true }
  }, [novelId, model.facts.settingsCheckOk, model.facts.contentPackReady])

  const selectedTotal = useMemo(() => Object.values(seed?.selected ?? {})
    .reduce<number>((sum, rows) => sum + (rows?.length ?? 0), 0), [seed])

  const runAction = async (label: string, action: () => Promise<string>) => {
    setBusy(label); setError('')
    try {
      const message = await action()
      const before = snapshot(model)
      const next = await onChanged()
      if (next) setFeedback(buildFeedback(message, before, next))
    } catch (reason) {
      setError(text(reason))
      setFeedback(null)
    } finally {
      setBusy('')
    }
  }

  /* ------------------------------------------------------------ 创意 */
  const suggest = (regenerate: boolean) => runAction(regenerate ? 'regenerate' : 'suggest', async () => {
    if (idea.trim().length < 4) throw new Error('先写一句完整的小说创意（至少 4 个字）。')
    const payload = await api.creativeSuggest(novelId, {
      idea: idea.trim(),
      references: reference.trim() ? [reference.trim()] : [],
      reader_experience: readerExperience.trim(),
      selected_genre: draft?.selected_genre ?? '',
      regenerate,
    })
    setSuggestion(payload)
    setDraft(payload.selection)
    return regenerate ? '已经换了一批方向候选。' : '已经根据你的创意给出方向候选。'
  })

  const saveBrief = () => runAction('saveBrief', async () => {
    if (!draft) throw new Error('先选择题材方向与基调。')
    const result = await api.saveCreativeBrief(novelId, {
      ...draft,
      original_idea: idea.trim(),
      references: reference.trim() ? [reference.trim()] : [],
      reader_experience: readerExperience.trim(),
    })
    setDraft(result.brief)
    setSavedIdea(idea.trim())
    try { localStorage.removeItem(localDraftKey) } catch { /* 忽略 */ }
    // NF-009：保存成功后直接进入下一步，主 CTA 不再把作者留在原地。
    setStep('settings')
    return '创意已经确定：题材、基调与卖点都保存下来了。'
  })

  /* ------------------------------------------------------------ 设定 */
  const suggestSeed = (regenerate: boolean) => runAction(
    regenerate ? 'regenerateSeed' : 'suggestSeed', async () => {
      const payload = await api.suggestSettingSeed(novelId, {
        regenerate, selected: seed?.selected ?? {},
      })
      setSeed(payload.seed)
      setSeedSaved(false)
      return regenerate ? '已换一批设定候选，你确认过的选择保留。' : '已经根据创意生成设定候选。'
    })

  const toggleCandidate = useCallback((group: string, id: string) => {
    setSeed((current) => {
      if (!current) return current
      const rows = current.selected[group] ?? []
      return { ...current, selected: { ...current.selected, [group]: toggleSelection(group, rows, id) } }
    })
    setSeedSaved(false)
  }, [])

  const saveSeed = () => runAction('saveSeed', async () => {
    if (!seed) throw new Error('先生成设定候选。')
    const result = await api.saveSettingSeed(novelId, {
      seed, selected: seed.selected,
    })
    setSeed(result.seed)
    setSeedSaved(true)
    const report = await api.runSettingsCheck(novelId, {})
    setCheck(report)
    return report.ok
      ? '设定已经保存，起点可以运行。'
      : '设定已经保存，但还有需要补齐的地方。'
  })

  /* ------------------------------------------------------------ 自检 / 推演 */
  const runCheck = (repair: boolean) => runAction(repair ? 'repair' : 'check', async () => {
    const report = await api.runSettingsCheck(novelId, repair ? { repair: true } : {})
    setCheck(report)
    if (repair) {
      const refreshed = await api.settingSeed(novelId)
      setSeed(refreshed.seed)
      setSeedSaved(Boolean(refreshed.saved))
    }
    return report.ok ? '自检通过：起点状态可以初始化。' : '自检发现问题，需要先补齐。'
  })

  const startRuntime = () => runAction('runtime', async () => {
    const payload = await api.startRuntime(novelId, {})
    setRuntimeInfo({ revision: payload.revision, tick: payload.tick, created: payload.created })
    return payload.created
      ? '剧情推演已经开始：起点事实正式落盘。'
      : '这本小说已经在推演中。'
  })

  const stepStatus: Record<FlowStep, boolean> = {
    idea: facts.creativeBriefSaved,
    settings: facts.settingSeedSaved && facts.contentPackReady,
    check: facts.settingsCheckOk,
    runtime: facts.runtimeStarted,
  }
  const currentStep = STEP_ORDER.find((row) => !stepStatus[row]) ?? 'runtime'

  return (
    <div className="v3-creation" data-testid="v3-creation-workspace">
      <Card className="v3-creation-goal" tone="elevated" testId="v3-creation-goal">
        <div className="v3-creation-goal-icon"><Icon name="creation" size={24} /></div>
        <div>
          <span className="v3-kicker">当前目标</span>
          <h1 data-testid="v3-creation-goal-title">
            {model.currentObjective?.title ?? '把故事想法变成可发展的核心设定'}
          </h1>
          <p data-testid="v3-creation-goal-desc">
            {model.currentObjective?.description
              ?? '把想法写成一句话，再一步步定下世界、角色与主线。'}
          </p>
        </div>
        <div className="v3-creation-goal-side">
          <ProgressBar percent={model.hero.progressPercent} label={model.hero.progressLabel} />
          <small data-testid="v3-creation-next">
            下一步：{model.nextAction.title}
          </small>
        </div>
      </Card>

      <nav className="v3-flow-steps" aria-label="创作步骤" data-testid="v3-flow-steps">
        {STEP_ORDER.map((row, index) => (
          <button type="button" key={row}
            className={`v3-flow-step ${step === row ? 'is-active' : ''}`
              + (stepStatus[row] ? ' is-done' : '')
              + (currentStep === row ? ' is-current' : '')}
            onClick={() => setStep(row)}
            aria-current={currentStep === row ? 'step' : undefined}
            data-testid={`v3-flow-step-${row}`}>
            <span className="v3-flow-step-index">
              {stepStatus[row] ? <Icon name="complete" size={18} /> : index + 1}
            </span>
            <span className="v3-flow-step-label">{STEP_TITLES[row]}</span>
            <span className="v3-flow-step-state">
              {stepStatus[row] ? '已完成' : currentStep === row ? '当前' : '待处理'}
            </span>
          </button>
        ))}
      </nav>

      {feedback ? (
        <FeedbackCard feedback={feedback} onDismiss={() => setFeedback(null)} />
      ) : null}
      {error ? <div className="v3-error" role="alert" data-testid="v3-flow-error">
        <Icon name="warning" size={20} />
        <div><b>这一步没有完成</b><p>{error}</p></div>
      </div> : null}

      {step === 'idea' ? (
        <Card className="v3-flow-body" tone="default" testId="v3-flow-idea">
          <SectionHeading icon="creation" title="先说清这本小说想写什么"
            hint="一句话就够：系统会给出题材、基调与卖点候选。" />
          <label className="v3-field">
            <span>一句话创意</span>
            <textarea rows={3} maxLength={1000} value={idea} aria-label="一句话创意"
              placeholder="例如：一个普通维修工发现城市其实运行在一套隐藏的修仙操作系统上。"
              onChange={(event) => setIdea(event.target.value)} />
          </label>
          <div className="v3-field-row">
            <label className="v3-field">
              <span>参考作品（可选）</span>
              <input value={reference} maxLength={120} aria-label="参考作品"
                onChange={(event) => setReference(event.target.value)} />
            </label>
            <label className="v3-field">
              <span>想要的读者体验（可选）</span>
              <input value={readerExperience} maxLength={200} aria-label="读者体验"
                onChange={(event) => setReaderExperience(event.target.value)} />
            </label>
          </div>
          <div className="v3-flow-actions">
            <Button variant="primary" disabled={Boolean(busy)} onClick={() => suggest(false)}
              testId="v3-idea-suggest">{busy === 'suggest' ? '正在生成…' : '生成方向候选'}</Button>
            <Button variant="secondary" disabled={Boolean(busy) || !suggestion}
              onClick={() => suggest(true)} testId="v3-idea-regenerate">换一批</Button>
            <Button variant="secondary" disabled={Boolean(busy) || !draft}
              onClick={saveBrief} testId="v3-idea-save">
              {busy === 'saveBrief' ? '正在保存…' : '确定这个方向'}
            </Button>
          </div>
          {ideaUnsaved ? (
            <p className="v3-hint-line" data-testid="v3-idea-unsaved">
              <Icon name="foreshadow" size={16} />
              这份创意还没有保存：它只缓存在本机，刷新不会丢，但只有点「确定这个方向」才会写进作品。
            </p>
          ) : null}

          {suggestion ? (
            <div className="v3-choice-groups" data-testid="v3-idea-candidates">
              <ChoiceGroup title="题材方向" testId="v3-genre-candidates"
                rows={suggestion.genre_candidates.map((item) => ({
                  id: `${item.template_id}|${item.content_pack_id}`,
                  title: item.label || item.genre || item.content_pack_id,
                  summary: item.reason,
                  selected: draft?.selected_content_pack_id === item.content_pack_id
                    && draft?.selected_template_id === item.template_id,
                  onToggle: () => setDraft((current) => current ? {
                    ...current,
                    selected_genre: item.genre,
                    selected_template_id: item.template_id,
                    selected_content_pack_id: item.content_pack_id,
                  } : current),
                }))} />
              <ChoiceGroup title="基调" testId="v3-tone-candidates"
                rows={suggestion.tone_candidates.map((item) => ({
                  id: item.tone,
                  title: item.tone,
                  summary: item.reason,
                  selected: draft?.tone === item.tone,
                  onToggle: () => setDraft((current) => current
                    ? { ...current, tone: item.tone } : current),
                }))} />
              <ChoiceGroup title="核心卖点（可多选）" testId="v3-selling-point-candidates"
                rows={suggestion.selling_point_candidates.map((item) => {
                  const picked = draft?.selling_points?.includes(item.text) ?? false
                  return {
                    id: item.text,
                    title: item.text,
                    summary: item.reason,
                    selected: picked,
                    onToggle: () => setDraft((current) => current ? {
                      ...current,
                      selling_points: picked
                        ? (current.selling_points ?? []).filter((text) => text !== item.text)
                        : [...(current.selling_points ?? []), item.text],
                    } : current),
                  }
                })} />
            </div>
          ) : (
            <EmptyState icon="creation" title="还没有方向候选"
              reason="写下你的创意，点「生成方向候选」。"
              value="候选来自引擎对创意的解析，不是随机内容。" />
          )}
        </Card>
      ) : null}

      {step === 'settings' ? (
        <Card className="v3-flow-body" tone="default" testId="v3-flow-settings">
          <SectionHeading icon="world" title="把这本小说的世界、人物与主线定下来"
            hint={selectedTotal > 0
              ? `已选 ${selectedTotal} 项设定`
              : '每一组都可以只选一项，也可以先跳过。'} />
          <div className="v3-flow-actions">
            <Button variant="primary" disabled={Boolean(busy)} onClick={() => suggestSeed(false)}
              testId="v3-settings-suggest">
              {busy === 'suggestSeed' ? '正在生成…' : seed ? '按当前创意刷新候选' : '生成设定候选'}
            </Button>
            <Button variant="secondary" disabled={Boolean(busy) || !seed}
              onClick={() => suggestSeed(true)} testId="v3-settings-regenerate">换一批</Button>
            <Button variant="primary" disabled={Boolean(busy) || !seed} onClick={saveSeed}
              testId="v3-settings-save">
              {busy === 'saveSeed' ? '正在保存…' : '保存并检查起点'}
            </Button>
          </div>
          {!seed && <EmptyState icon="world" title="还没有设定候选"
            reason="候选需要先有创意：题材与基调决定候选范围。"
            value="生成后你可以逐组挑选，也可以先跳过。" />}
          {seed ? <div className="v3-setting-groups" data-testid="v3-setting-groups">
            {SETTING_GROUP_ORDER.map((group) => {
              const rows = (seed[group as keyof SettingSeed] as unknown as {
                id: string; label: string; summary: string; reason: string }[]) ?? []
              if (!rows.length) return null
              const chosen = seed.selected[group] ?? []
              return (
                <Disclosure key={group} testId={`v3-setting-group-${group}`}
                  open={focusGroup ? focusGroup === group : undefined}
                  summary={`${SETTING_GROUP_LABELS[group]} · ${chosen.length ? `已选 ${chosen.length}` : '可跳过'}`}>
                  <div className="v3-choice-grid">
                    {rows.map((item) => (
                      <ChoiceCard key={item.id} title={item.label || item.id}
                        summary={item.summary} reason={item.reason}
                        selected={chosen.includes(item.id)}
                        multi={isMultipleSelectionGroup(group)}
                        testId={`v3-setting-candidate-${group}`}
                        onToggle={() => toggleCandidate(group, item.id)} />
                    ))}
                  </div>
                </Disclosure>
              )
            })}
          </div> : null}
          {seedSaved ? <p className="v3-hint-line" data-testid="v3-settings-saved">
            <Icon name="complete" size={16} />设定已经保存，可以进入自检。
          </p> : null}
        </Card>
      ) : null}

      {step === 'check' ? (
        <Card className="v3-flow-body" tone="default" testId="v3-flow-check">
          <SectionHeading icon="review" title="确认起点可以真的跑起来"
            hint="检查起点地点、角色与可执行行动是否齐全。" />
          <div className="v3-flow-actions">
            <Button variant="primary" disabled={Boolean(busy) || !model.facts.contentPackReady}
              onClick={() => runCheck(false)} testId="v3-check-run">
              {busy === 'check' ? '正在检查…' : '开始检查'}
            </Button>
            <Button variant="secondary"
              disabled={Boolean(busy) || !model.facts.contentPackReady || Boolean(check?.ok)}
              onClick={() => runCheck(true)} testId="v3-check-repair">
              {busy === 'repair' ? '正在修补…' : '修补缺项并重查'}
            </Button>
          </div>
          {!model.facts.contentPackReady
            ? <EmptyState icon="review" title="还没有可以检查的设定"
              reason="自检读的是你保存的设定草图。"
              value="在「设定与起点」保存一次，就能开始检查。" />
            : check ? (
              <div className="v3-check-result" data-testid="v3-check-result">
                <Badge tone={check.ok ? 'success' : 'warning'}
                  icon={check.ok ? 'complete' : 'warning'}>
                  {check.ok ? '自检通过' : `还有 ${check.findings.filter((row) => row.severity === 'error').length} 处需要补齐`}
                </Badge>
                <ul className="v3-check-list">
                  {check.findings.map((row) => (
                    <li key={`${row.code}-${row.target}`}>
                      <Icon name={row.severity === 'error' ? 'warning' : 'foreshadow'} size={16} />
                      <span>{row.message}</span>
                      {row.hint ? <em>建议：{row.hint}</em> : null}
                      <button type="button" className="v3-link"
                        onClick={() => { setStep('settings'); if (focusGroup) setFocusGroup('') }}
                        data-testid={`v3-check-fix-${row.code}`}>去修补</button>
                    </li>
                  ))}
                  {!check.findings.length
                    ? <li><Icon name="complete" size={16} /><span>没有任何缺项。</span></li>
                    : null}
                </ul>
              </div>
            ) : <LoadingState label="正在读取自检结果…" />}
        </Card>
      ) : null}

      {step === 'runtime' ? (
        <Card className="v3-flow-body" tone="default" testId="v3-flow-runtime">
          <SectionHeading icon="simulation" title="让故事真的开始"
            hint="开始之后，起点事实会落盘成为后续所有面板的唯一依据。" />
          <div className="v3-flow-actions">
            <Button variant="primary" disabled={Boolean(busy) || !facts.settingsCheckOk
              || facts.runtimeStarted} onClick={startRuntime} testId="v3-runtime-start">
              {facts.runtimeStarted ? '已经在推演中'
                : busy === 'runtime' ? '正在开始…' : '开始剧情推演'}
            </Button>
            <Button variant="ghost" onClick={() => onOpenLegacy('world')}
              testId="v3-runtime-open-world">查看世界面板</Button>
          </div>
          {!facts.settingsCheckOk
            ? <EmptyState icon="simulation" title="还不能开始推演"
              reason="起点设定还没通过自检。"
              value="回到「设定自检」，把缺项补齐就能开始。"
              action={<Button variant="secondary" onClick={() => setStep('check')}>
                回到自检
              </Button>} />
            : <div className="v3-runtime-ready" data-testid="v3-runtime-ready">
              <Icon name="complete" size={20} />
              <div>
                <b>{facts.runtimeStarted ? '推演已经在进行' : '起点已经准备好了'}</b>
                <p>{facts.runtimeStarted
                  ? `当前阶段：${model.hero.stageLabel}。可以继续在大纲工作区整理章节结构。`
                  : '点击「开始剧情推演」，起点事实会写进故事状态。'}</p>
              </div>
            </div>}
          {runtimeInfo ? <p className="v3-hint-line" data-testid="v3-runtime-info">
            <Icon name="simulation" size={16} />
            tick {runtimeInfo.tick} · revision {runtimeInfo.revision}
          </p> : null}
        </Card>
      ) : null}
    </div>
  )
}

function ChoiceGroup({ title, rows, testId }: {
  title: string
  rows: { id: string; title: string; summary: string; selected: boolean;
    onToggle: () => void }[]
  testId: string
}) {
  if (rows.length === 0) return null
  return (
    <section className="v3-choice-group" data-testid={testId}>
      <h3>{title}</h3>
      <div className="v3-choice-grid">
        {rows.map((row) => (
          <ChoiceCard key={row.id} title={row.title} summary={row.summary}
            reason="" selected={row.selected} testId={`${testId}-card`}
            onToggle={row.onToggle} />
        ))}
      </div>
    </section>
  )
}

function stepFromParams(params: DeepLinkParams,
  facts: CommandCenterViewModel['facts']): FlowStep {
  const requested = params.step as FlowStep | undefined
  if (requested && STEP_ORDER.includes(requested)) return requested
  if (!facts.creativeBriefSaved) return 'idea'
  if (!facts.settingsCheckOk) return 'settings'
  if (!facts.runtimeStarted) return 'runtime'
  return 'runtime'
}

interface ProgressSnapshot {
  stageId: string
  stageLabel: string
  stageProgress: string
  percent: number
  objectiveTitle: string
}

function snapshot(model: CommandCenterViewModel): ProgressSnapshot {
  const stage = model.stages.find((row) => row.current) ?? model.stages[0]
  return {
    stageId: stage?.stageId ?? '',
    stageLabel: stage?.label ?? '',
    stageProgress: stage?.progressLabel ?? '',
    percent: model.hero.progressPercent,
    objectiveTitle: model.currentObjective?.title ?? '',
  }
}

/**
 * 反馈文案全部由「动作前的真实投影」与「动作后的真实投影」对比生成，
 * 不写死任何数字：进度、解锁与下一步都来自 application 投影。
 */
function buildFeedback(message: string, before: ProgressSnapshot,
  after: CommandCenterViewModel): FeedbackViewModel {
  const stage = after.stages.find((row) => row.current) ?? after.stages[0]
  const stageProgress = stage
    ? stage.stageId === before.stageId && before.stageProgress
      ? `${stage.label}：${before.stageProgress} → ${stage.progressLabel}`
      : before.stageProgress
        ? `${before.stageLabel} 已完成 → 进入「${stage.label}」${stage.progressLabel}`
        : `${stage.label}：${stage.progressLabel}`
    : `总体进度 ${before.percent}% → ${after.hero.progressPercent}%`
  const advanced = after.currentObjective?.title
    && after.currentObjective.title !== before.objectiveTitle
  return {
    title: message,
    stageProgress,
    unlock: advanced
      ? after.currentObjective?.title ?? ''
      : after.currentObjective?.unlockEffects ?? '',
    next: after.nextAction.title,
  }
}

function text(reason: unknown): string {
  return reason instanceof Error ? reason.message : String(reason)
}
