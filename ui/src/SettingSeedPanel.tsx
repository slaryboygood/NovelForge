import { useEffect, useState } from 'react'
import {
  api, RuntimeCandidateRow, SettingCandidate, SettingImpactPayload, SettingSeed,
  SettingsCheckReport,
} from './api'
import CandidateCard from './components/CandidateCard'
import {
  SETTING_GROUP_LABELS, isMultipleSelectionGroup, toggleSelection,
} from './storyBuilderSelection'

/**
 * W1-02 设定候选面板：creative_brief → 8 组候选 → 作者挑选 / 改写 / 跳过 → 保存设定草图。
 *
 * 只展示引擎生成的候选：候选 id / 结构 / 合法性全部来自 API。
 * 前端不做题材判断，也不自行推导世界状态；保存后的内容包由引擎校验。
 */
export default function SettingSeedPanel({ novelId, compact = false, focusGroup = '',
  onChanged }: {
  novelId: string
  compact?: boolean
  focusGroup?: string
  onChanged?: (message: string, report?: SettingsCheckReport) => void | Promise<void>
}) {
  const [seed, setSeed] = useState<SettingSeed | null>(null)
  const [saved, setSaved] = useState(false)
  const [savedPackId, setSavedPackId] = useState('')
  const [check, setCheck] = useState<SettingsCheckReport | null>(null)
  const [runtime, setRuntime] = useState<{ revision: number; tick: number; created: boolean
    candidates: RuntimeCandidateRow[]; runtime_id: string } | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [impact, setImpact] = useState<SettingImpactPayload | null>(null)

  useEffect(() => {
    let cancelled = false
    setSeed(null); setSaved(false); setSavedPackId(''); setError(''); setMessage('')
    setCheck(null)
    setRuntime(null)
    api.settingSeed(novelId)
      .then((state) => {
        if (cancelled) return
        setSeed(state.seed)
        setSaved(state.saved)
        setSavedPackId(state.pack_id)
      })
      .catch((reason) => {
        if (cancelled) return
        const text = reason instanceof Error ? reason.message : String(reason)
        // 还没有创意简报时不算错误：提示先去写创意。
        if (text.includes('创意')) { setError(''); return }
        setError(text)
      })
    return () => { cancelled = true }
  }, [novelId])

  const loadImpact = async () => {
    try { setImpact(await api.settingsImpact(novelId)) } catch { setImpact(null) }
  }

  useEffect(() => { void loadImpact() }, [novelId, saved, savedPackId])

  useEffect(() => {
    if (!focusGroup) return
    const target = document.getElementById(`setting-group-${focusGroup}`)
    target?.scrollIntoView({ block: 'center' })
  }, [focusGroup, seed])

  const request = async (regenerate: boolean) => {
    setBusy(true); setError(''); setMessage('')
    try {
      const payload = await api.suggestSettingSeed(novelId, {
        regenerate, selected: seed?.selected ?? {},
      })
      setSeed(payload.seed)
      setSaved(false)
      setMessage(regenerate ? '已换一批候选（已确认的选择保留）。' : '已根据创意生成设定候选。')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    } finally { setBusy(false) }
  }

  const toggle = (group: string, id: string) => {
    setSeed((current) => {
      if (!current) return current
      const rows = current.selected[group] ?? []
      const next = toggleSelection(group, rows, id)
      return { ...current, selected: { ...current.selected, [group]: next } }
    })
  }

  const edit = (group: string, id: string, patch: { label?: string; summary?: string }) => {
    setSeed((current) => {
      if (!current) return current
      const rows = (current[group as keyof SettingSeed] as SettingCandidate[]).map((item) =>
        item.id === id ? { ...item, ...patch } : item)
      return { ...current, [group]: rows } as SettingSeed
    })
  }

  const save = async () => {
    if (!seed) return
    setBusy(true); setError(''); setMessage('')
    try {
      const result = await api.saveSettingSeed(novelId, {
        seed, selected: seed.selected, pack_id: savedPackId || undefined,
      })
      setSeed(result.seed)
      setSaved(true)
      setSavedPackId(result.pack_id)
      await runCheck(false)
      setMessage(`设定已保存为内容包 ${result.pack_id}（刷新后仍然保留）。`)
      await loadImpact()
      await onChanged?.(`设定已保存为内容包 ${result.pack_id}。`)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    } finally { setBusy(false) }
  }

  const runCheck = async (repair: boolean) => {
    setBusy(true); setError(''); setMessage('')
    try {
      const report = await api.runSettingsCheck(novelId, repair ? { repair: true } : {})
      setCheck(report)
      setSaved(true)
      setSavedPackId(report.pack_id)
      if (repair && report.applied_fixes.length) {
        const refreshed = await api.settingSeed(novelId)
        setSeed(refreshed.seed)
        setMessage(`已修补可运行性缺项：${report.applied_fixes.join('、')}。`)
      } else {
        setMessage(report.ok ? '自检通过：起点状态可以初始化，候选行动非空。' : '自检发现问题，见下方清单。')
      }
      await onChanged?.(report.ok ? '自检通过。' : '自检发现问题，见下方清单。', report)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    } finally { setBusy(false) }
  }

  const startStory = async () => {
    setBusy(true); setError(''); setMessage('')
    try {
      const payload = await api.startRuntime(novelId, {})
      setRuntime({ revision: payload.revision, tick: payload.tick, created: payload.created,
        candidates: payload.candidates, runtime_id: payload.runtime_id })
      setMessage(payload.created
        ? '已开始剧情推演：起点事实已经写进 StoryState（七个创作者面板读同一份事实）。'
        : '这本小说已经开始了，以下是当前事实与候选行动。')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    } finally { setBusy(false) }
  }

  return <section className="setting-seed-panel">
    <div className="world-panel-head">
      <div>
        <span className="story-builder-kicker">设定候选 · W1-02</span>
        <h3>把这本小说的世界、人物与主线定下来</h3>
      </div>
      <span className={`badge ${saved ? 'pass' : ''}`}>{saved ? '设定已保存' : '尚未保存'}</span>
    </div>
    {!compact && <p className="world-source">
      候选来自引擎对创意的解析；同一组可以多选或只选一个，留空表示先跳过（引擎按默认值生成骨架）。
    </p>}
    <div className="builder-actions">
      <button className="btn primary" disabled={busy} onClick={() => request(false)}>
        {busy ? '正在生成…' : seed ? '按当前创意刷新候选' : '生成设定候选'}
      </button>
      <button className="btn" disabled={busy || !seed} onClick={() => request(true)}>换一批</button>
      <button className="btn" disabled={busy || !seed} onClick={save}>保存设定草图</button>
      <button className="btn" disabled={busy || !saved} onClick={() => runCheck(false)}>自检可运行性</button>
      <button className="btn" disabled={busy || !saved || !check || check.ok}
        onClick={() => runCheck(true)}>修补缺项并重查</button>
      <button className="btn primary" disabled={busy || !check?.ok} onClick={startStory}>
        开始剧情推演
      </button>
    </div>
    {seed && <p className="world-source">
      来源：{seed.source === 'ai' ? 'AI 补充文案（结构由引擎生成）' : '确定性规则（AI 不可用时的降级路径）'}
      {seed.notes.length ? ` · 记录：${seed.notes.slice(0, 3).join('、')}` : ''}
    </p>}
    {message && <div className="story-builder-message">{message}</div>}
    {error && <div className="story-builder-message error">{error}</div>}

    {check && <article className="world-card settings-check-card">
      <div className="world-row-head">
        <h4>起点自检 · {check.ok ? '通过' : `${check.findings.filter((item) => item.severity === 'error').length} 个阻塞问题`}</h4>
        <span>内容包 {check.pack_id}</span>
      </div>
      <p>起点地点：{String((check.story_state as Record<string, unknown>).location ?? '')} ·
        角色 {((check.story_state as Record<string, unknown>).characters as string[] | undefined)?.length ?? 0} ·
        开局可用行动 {check.available_candidates.length} 条</p>
      <div className="world-list">
        <div className="world-row">
          <b>可用候选</b>
          <p>{check.available_candidates.join('、') || '（空）'}</p>
        </div>
        <div className="world-row">
          <b>被挡住的候选与原因</b>
          {check.blocked_candidates.map((row) => <p key={row.action}>{row.action}：{row.reason || row.code}</p>)}
          {!check.blocked_candidates.length && <p>（无）</p>}
        </div>
        {check.findings.map((row) => <div className="world-row" key={`${row.code}-${row.target}`}>
          <b className={row.severity === 'error' ? 'world-note' : ''}>
            {row.severity === 'error' ? '阻塞' : '提示'} · {row.code}
          </b>
          <p>{row.message}{row.hint ? `（建议：${row.hint}）` : ''}</p>
        </div>)}
        {!check.findings.length && <div className="world-row"><p>没有任何缺项。</p></div>}
      </div>
    </article>}

    {runtime && <article className="world-card settings-runtime-card">
      <div className="world-row-head">
        <h4>剧情推演已就绪</h4>
        <span>revision {runtime.revision} · tick {runtime.tick}</span>
      </div>
      <p>事实槽：{runtime.runtime_id} · 这批候选由 StoryState 生成，不是模拟数据。</p>
      <div className="world-list">
        {runtime.candidates.map((row) => <div className="world-row" key={row.action_id}>
          <div className="world-row-head">
            <b>{row.name || row.action_id}</b>
            <span>{row.available ? '可执行' : `不可用：${row.reason || row.code}`}</span>
          </div>
          <p>{row.action_id}</p>
        </div>)}
      </div>
      <p>下一步：点上方的「开始构筑」建立故事会话后，可在七个创作者面板复核世界 / 角色 / 剧情 /
        成长 / 记忆 / 导演 / 大纲联动。</p>
    </article>}

    {seed && <div className="setting-seed-groups">
      {Object.keys(SETTING_GROUP_LABELS).map((group) => {
        const rows = (seed[group as keyof SettingSeed] as SettingCandidate[]) ?? []
        if (!rows.length) return null
        const chosen = seed.selected[group] ?? []
        const groupImpact = impact?.groups.find((row) => row.group === group) ?? null
        const unlockIds = groupImpact?.unlocks.map((row) => row.action_id) ?? []
        return <article className="world-card" key={group}
          data-testid={`setting-group-${group}`}
          data-focused={focusGroup === group ? 'true' : undefined}
          id={`setting-group-${group}`}>
          <div className="world-row-head">
            <h4>{SETTING_GROUP_LABELS[group]}</h4>
            <span>{chosen.length ? `已选 ${chosen.length} 项` : '可跳过'}</span>
          </div>
          <p className="world-source">
            影响范围：NovelProfile {groupImpact?.profile_fields.join('、') || '—'} ·
            内容包段 {groupImpact?.pack_sections.join('、') || '—'}
            {impact && !impact.pack_ready ? '（保存设定后生成内容包，才可计算解锁）' : ''}
          </p>
          <div className="world-list candidate-grid">
            {rows.map((item) => <CandidateCard key={item.id}
              testId={`setting-candidate-${group}`}
              className="plot-candidate"
              title={item.label || item.id}
              summary={item.summary}
              reason={item.reason}
              source={`${group}/${item.id}`}
              multi={isMultipleSelectionGroup(group)}
              selected={chosen.includes(item.id)}
              impact={groupImpact ? {
                profile_fields: groupImpact.profile_fields,
                pack_sections: groupImpact.pack_sections,
                unlock_action_ids: unlockIds,
              } : null}
              impactNote={impact && !impact.pack_ready
                ? '尚未保存设定：解锁行动需要先保存内容包。' : ''}
              onToggle={() => toggle(group, item.id)}
              onEdit={(patch) => edit(group, item.id, patch)} />)}
          </div>
        </article>
      })}
    </div>}
  </section>
}
