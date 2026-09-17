import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { api, CreatorPlotPayload } from './api'

type Candidate = CreatorPlotPayload['candidates'][number]

function describe(spec: Record<string, unknown>): string {
  const op = String(spec.op ?? '')
  const target = String(spec.target ?? spec.key ?? '')
  const value = spec.value === undefined || spec.value === null ? '' : ` ${String(spec.value)}`
  const comparator = spec.comparator ? ` ${String(spec.comparator)}` : ''
  return `${op}${target ? ' · ' + target : ''}${comparator}${value}`
}

function CandidateCard({ candidate }: { candidate: Candidate }) {
  return <article className={`plot-candidate ${candidate.available ? 'available' : 'blocked'}`}>
    <div className="world-row-head">
      <b>{candidate.name || candidate.action_id}</b>
      <span className={candidate.available ? 'plot-state ok' : 'plot-state blocked'}>{candidate.available ? 'available' : 'unavailable'}</span>
    </div>
    {candidate.kind && <p>{candidate.kind} · {candidate.visibility}</p>}
    {!candidate.available && <p className="world-note">{candidate.code ? `${candidate.code}：` : ''}{candidate.reason || '当前状态不满足条件'}</p>}
    {candidate.costs.length > 0 && <p>成本：{candidate.costs.map(describe).join('；')}</p>}
    {candidate.requirements.length > 0 && <p>前置：{candidate.requirements.map(describe).join('；')}</p>}
    {candidate.risks.length > 0 && <p>风险：{candidate.risks.join('；')}</p>}
    {candidate.goal_notes.map((note) => <p className="plot-goal" key={note}>{note}</p>)}
    {candidate.memory_notes.map((note) => <p className="world-note" key={note}>{note}</p>)}
  </article>
}

/**
 * V2-I-03 剧情面板：候选行动、事件、支线与世界影响全部来自创作者 API；
 * available / unavailable、成本、风险与影响都由引擎判定，前端只渲染结果。
 */
export default function PlotPanel({ novelId, header }: { novelId: string; header?: ReactNode }) {
  const [data, setData] = useState<CreatorPlotPayload | null>(null)
  const [actor, setActor] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => { setActor('') }, [novelId])

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError('')
    api.creatorPlot(novelId, actor)
      .then((payload) => { if (!cancelled) setData(payload) })
      .catch((reason) => {
        if (cancelled) return
        setData(null)
        setError(reason instanceof Error ? reason.message : String(reason))
      })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [novelId, actor])

  if (loading && !data) return <section className="world-panel">{header}<p className="world-empty">正在读取剧情状态…</p></section>
  if (!data) return <section className="world-panel">{header}<p className="world-empty">剧情状态读取失败：{error || '请确认后端已启动'}</p></section>

  const available = data.candidates.filter((item) => item.available)
  const unavailable = data.candidates.filter((item) => !item.available)
  return <section className="world-panel">
    {header}
    <div className="world-panel-head">
      <div>
        <span className="story-builder-kicker">剧情面板</span>
        <h3>现在能做什么、会发生什么</h3>
      </div>
      <span className={`badge ${data.meta.persisted ? 'pass' : ''}`}>{data.meta.persisted ? 'StoryState 已存档' : '预览状态 · 未落盘'}</span>
    </div>
    <p className="world-source">视角角色 {data.actor || '—'} · tick {data.timeline.tick}{data.timeline.current_time ? ` · ${data.timeline.current_time}` : ''} · 可用 {available.length} / 不可用 {unavailable.length}</p>

    <div className="world-grid">
      <article className="world-card">
        <h4>当前事件 · {data.current_events.length}</h4>
        {data.current_events.length === 0 && <p className="world-empty">当前没有进行中或最近触发的事件。</p>}
        <div className="world-list">
          {data.current_events.map((event) => <div className="world-row" key={event.event_id}>
            <div className="world-row-head"><b>{event.title}</b><span>{event.status === 'active' ? '进行中' : '最近发生'} · 优先级 {event.priority}</span></div>
            {event.scene_goal && <p>目标：{event.scene_goal}</p>}
            {event.conflict && <p className="world-note">冲突：{event.conflict}</p>}
            {event.participants.length > 0 && <p>参与者：{event.participants.join('、')}</p>}
            {event.followups.length > 0 && <p>后续可能：{event.followups.join('、')}</p>}
          </div>)}
        </div>
      </article>

      <article className="world-card">
        <h4>世界变化对剧情的影响</h4>
        <dl>
          <div><dt>最近变化</dt><dd>{data.last_world_change ? `${data.last_world_change.op} · ${data.last_world_change.target || data.last_world_change.entity}` : '—'}</dd></div>
        </dl>
        {data.world_impacts.length === 0 && <p className="world-empty">当前候选行动没有依赖世界状态。</p>}
        <div className="world-list">
          {data.world_impacts.map((impact) => <div className="world-row" key={impact.key}>
            <div className="world-row-head">
              <b>{impact.key}</b>
              <span>{impact.impacts_availability ? '正在影响可用性' : '仅作为条件'}</span>
            </div>
            <p>条件：{impact.ops.join('、') || '—'} · 相关行动 {impact.actions.length}</p>
            {impact.available_actions.length > 0 && <p>可用：{impact.available_actions.join('、')}</p>}
            {impact.unavailable_actions.length > 0 && <p className="world-note">不可用：{impact.unavailable_actions.join('、')}</p>}
          </div>)}
        </div>
      </article>

      <article className="world-card">
        <h4>事件连锁 · {data.event_chain.length}</h4>
        {data.event_chain.length === 0 && <p className="world-empty">还没有事件触发记录。</p>}
        <div className="world-list">
          {data.event_chain.map((event) => <div className="world-row" key={`${event.order}-${event.event_id}`}>
            <div className="world-row-head"><b>{event.title}</b><span>第 {event.order} 条{event.scope ? ` · ${event.scope === 'world' ? '世界事件' : '场景事件'}` : ''}</span></div>
            {event.followups.length > 0 && <p>引出：{event.followups.join('、')}</p>}
          </div>)}
        </div>
      </article>
    </div>

    <article className="world-card">
      <h4>候选行动 · available {available.length}</h4>
      {available.length === 0 && <p className="world-empty">当前状态没有可用行动。</p>}
      <div className="world-list">{available.map((candidate) => <CandidateCard candidate={candidate} key={candidate.action_id} />)}</div>
    </article>

    <article className="world-card">
      <h4>候选行动 · unavailable {unavailable.length}</h4>
      {unavailable.length === 0 && <p className="world-empty">没有不可用行动。</p>}
      <div className="world-list">{unavailable.map((candidate) => <CandidateCard candidate={candidate} key={candidate.action_id} />)}</div>
    </article>

    <article className="world-card">
      <h4>活跃支线 · {data.active_plots.length}</h4>
      {data.active_plots.length === 0 && <p className="world-empty">当前没有活跃支线。</p>}
      <div className="world-list">
        {data.active_plots.map((plot) => <div className="world-row" key={plot.id}>
          <div className="world-row-head"><b>{plot.title}</b><span>{plot.status} · 进度 {plot.progress} · 优先级 {plot.priority}</span></div>
          {plot.factions.length > 0 && <p>相关势力：{plot.factions.join('、')}</p>}
          {plot.locations.length > 0 && <p>相关地点：{plot.locations.join('、')}</p>}
          {plot.has_trigger && <p>有触发条件：满足世界状态时自动激活</p>}
        </div>)}
      </div>
    </article>

    <article className="world-card">
      <h4>事件触发判定 · {data.triggerable_events.length}</h4>
      {data.triggerable_events.length === 0 && <p className="world-empty">内容包没有注册事件。</p>}
      <div className="world-list">
        {data.triggerable_events.map((event) => <div className="world-row" key={event.event_id}>
          <div className="world-row-head"><b>{event.title}</b><span className={event.available ? 'plot-state ok' : 'plot-state blocked'}>{event.available ? '可触发' : '不可触发'}</span></div>
          <p>优先级 {event.priority}{event.scope ? ` · ${event.scope === 'world' ? '世界事件' : '场景事件'}` : ''}{event.available ? '' : ` · ${event.code}：${event.reason}`}</p>
        </div>)}
      </div>
    </article>

    {error && <p className="design-warning">剧情面板刷新失败：{error}</p>}
  </section>
}
