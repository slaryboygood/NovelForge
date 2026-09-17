import { useCallback, useEffect, useState } from 'react'
import { api, GuidedFlowState, SettingImpactPayload, SettingsCheckReport } from './api'
import CreativeBriefPanel from './CreativeBriefPanel'
import SettingSeedPanel from './SettingSeedPanel'

/**
 * W6-01：单页引导式创作流（创意 → 设定 → 自检 → 开始推演）。
 *
 * 状态与“下一步”全部来自 `/guided-flow`（只读投影）；
 * 写操作仍走既有 API：创意简报、设定候选、自检、runtime/start。
 */
export default function GuidedFlowPanel({ novelId, initialStep = '', initialGroup = '',
  onAdvanced }: {
  novelId: string
  initialStep?: string
  initialGroup?: string
  onAdvanced?: (target: { tab: string; step: string }) => void
}) {
  const [flow, setFlow] = useState<GuidedFlowState | null>(null)
  const [check, setCheck] = useState<SettingsCheckReport | null>(null)
  const [impact, setImpact] = useState<SettingImpactPayload | null>(null)
  const [step, setStep] = useState(initialStep || '')
  const [group, setGroup] = useState(initialGroup || '')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  const refresh = useCallback(async () => {
    try {
      const state = await api.guidedFlow(novelId)
      setFlow(state)
      if (!step) setStep(state.current_step || 'idea')
      return state
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
      return null
    }
  }, [novelId, step])

  useEffect(() => {
    let cancelled = false
    setFlow(null); setCheck(null); setError(''); setMessage('')
    setStep(initialStep || ''); setGroup(initialGroup || '')
    api.guidedFlow(novelId)
      .then((state) => {
        if (cancelled) return
        setFlow(state)
        setStep(initialStep || state.current_step || 'idea')
      })
      .catch((reason) => { if (!cancelled) setError(reason instanceof Error ? reason.message : String(reason)) })
    return () => { cancelled = true }
    // 只在小说切换时整体重置；深链接导航（step/group 变化）由下面单独同步，
    // 否则自己触发的导航会清掉刚写入的提示信息。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [novelId])

  useEffect(() => {
    if (initialStep) setStep(initialStep)
    if (initialGroup) setGroup(initialGroup)
  }, [initialStep, initialGroup])

  useEffect(() => {
    if (!flow?.facts.content_pack_ready) { setCheck(null); return }
    let cancelled = false
    api.settingsCheck(novelId)
      .then((report) => { if (!cancelled) setCheck(report) })
      .catch(() => { if (!cancelled) setCheck(null) })
    return () => { cancelled = true }
  }, [novelId, flow?.facts.settings_check_ok, flow?.facts.content_pack_ready])

  useEffect(() => {
    let cancelled = false
    api.settingsImpact(novelId)
      .then((payload) => { if (!cancelled) setImpact(payload) })
      .catch(() => { if (!cancelled) setImpact(null) })
    return () => { cancelled = true }
  }, [novelId, flow?.facts.content_pack_ready])

  const startRuntime = async () => {
    setBusy(true); setError(''); setMessage('')
    try {
      const payload = await api.startRuntime(novelId, {})
      setMessage(`已开始剧情推演（revision ${payload.revision}，分支 ${payload.branch_id}）。`)
      await refresh()
      onAdvanced?.({ tab: 'world', step: 'runtime' })
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    } finally { setBusy(false) }
  }

  const afterChange = async (nextMessage: string) => {
    setMessage(nextMessage)
    await refresh()
  }

  const steps = flow?.steps ?? []
  const active = steps.find((row) => row.step_id === step) ?? flow?.next_step ?? null

  return <section className="guided-flow" data-testid="guided-flow">
    <div className="world-panel-head">
      <div>
        <span className="story-builder-kicker">引导流 · W6-01</span>
        <h3>从一句创意走到「开始推演」</h3>
      </div>
      <span className="badge" data-testid="guided-current-stage">
        {flow ? `当前阶段：${flow.current_stage_label}` : '正在读取…'}
      </span>
    </div>
    <p className="world-source">
      事实分层：设计（设定 / 内容包）→ 已发生事实（StoryState）；引导流只读，写操作仍走既有接口。
    </p>

    <ol className="guided-steps" data-testid="guided-steps">
      {steps.map((row) => <li key={row.step_id}
        className={`guided-step ${row.status} ${row.step_id === step ? 'active' : ''}`}>
        <button type="button" className="guided-step-button"
          onClick={() => { setStep(row.step_id); setGroup(row.deep_link.group || '') }}>
          <span className={`guided-step-status ${row.status}`}>{STATUS_LABELS[row.status]}</span>
          <b>{row.title}</b>
          <small>{row.detail}</small>
        </button>
      </li>)}
    </ol>

    {flow?.next_step && <p className="guided-next" data-testid="guided-next-step">
      下一步：{flow.next_step.title}（{flow.next_step.stage_label}）
    </p>}
    {!flow && !error && <p className="world-empty">正在读取引导流状态…</p>}

    <div className="guided-step-body">
      {active?.step_id === 'idea' && <CreativeBriefPanel novelId={novelId} compact
        onChanged={() => afterChange('创意简报已保存：下一步可以生成设定候选。')} />}
      {(active?.step_id === 'settings' || active?.step_id === 'check') &&
        <SettingSeedPanel novelId={novelId} compact focusGroup={group}
          onChanged={async (text, report) => {
            if (report) setCheck(report)
            await afterChange(text)
          }} />}
      {active?.step_id === 'runtime' && <article className="world-card" data-testid="guided-runtime-step">
        <h4>开始剧情推演</h4>
        <p>自检通过后点击开始：起点事实会落盘成为 StoryState，之后所有面板都以它为准。</p>
        <dl>
          <div><dt>自检</dt><dd>{flow?.facts.settings_check_ok ? '通过' : '未通过'}</dd></div>
          <div><dt>推演状态</dt><dd>{flow?.facts.runtime_started ? '已开始' : '未开始'}</dd></div>
        </dl>
        <div className="builder-actions">
          <button type="button" className="btn primary" disabled={busy
            || !flow?.facts.settings_check_ok || flow?.facts.runtime_started}
            onClick={startRuntime}>
            {flow?.facts.runtime_started ? '已开始推演' : (busy ? '正在开始…' : '开始剧情推演')}
          </button>
        </div>
      </article>}
      {active && !['idea', 'settings', 'check', 'runtime'].includes(active.step_id)
        && <article className="world-card"><h4>{active.title}</h4><p>{active.detail}</p></article>}
    </div>

    {check && !check.ok && <article className="world-card" data-testid="guided-check-findings">
      <h4>设定自检未通过（{check.findings.length} 项）</h4>
      <ul className="guided-findings">
        {check.findings.map((finding) => <li key={`${finding.code}-${finding.target}`}>
          <b>{finding.message}</b>
          <span>{finding.hint}</span>
          <button type="button" className="btn" onClick={() => {
            setStep('settings')
            setGroup(impact?.finding_groups?.[finding.code] ?? '')
          }}>去修补</button>
        </li>)}
      </ul>
    </article>}

    {message && <p className="plot-goal" data-testid="guided-message">{message}</p>}
    {error && <div role="alert" className="story-builder-message error">{error}</div>}
  </section>
}

const STATUS_LABELS: Record<string, string> = {
  done: '✓ 已完成',
  current: '当前步骤',
  pending: '待处理',
  blocked: '需修补',
}
