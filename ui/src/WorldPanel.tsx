import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { api, CreatorWorldPayload } from './api'

/**
 * V2-I-01 世界面板：只渲染创作者 API 返回的 StoryState 投影，
 * 不在前端重新计算时间、地点、势力或事件规则。
 */
export default function WorldPanel({ novelId, header }: { novelId: string; header?: ReactNode }) {
  const [data, setData] = useState<CreatorWorldPayload | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError('')
    api.creatorWorld(novelId)
      .then((payload) => { if (!cancelled) setData(payload) })
      .catch((reason) => {
        if (cancelled) return
        setData(null)
        setError(reason instanceof Error ? reason.message : String(reason))
      })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [novelId])

  if (loading && !data) return <section className="world-panel">{header}<p className="world-empty">正在读取世界状态…</p></section>
  if (!data) {
    return <section className="world-panel">
      {header}
      <p className="world-empty">世界状态读取失败：{error || '请确认后端已启动'}</p>
    </section>
  }

  const { meta, timeline, location, factions } = data
  const currentTime = timeline.current_time || (timeline.tick ? `第 ${timeline.tick} 刻` : '尚未开始')

  return <section className="world-panel">
    {header}
    <div className="world-panel-head">
      <div>
        <span className="story-builder-kicker">世界面板</span>
        <h3>世界正在发生什么</h3>
      </div>
      <span className={`badge ${meta.persisted ? 'pass' : ''}`}>{meta.persisted ? 'StoryState 已存档' : '预览状态 · 未落盘'}</span>
    </div>
    <p className="world-source">
      {meta.content_pack_title || meta.content_pack_id || '未选择内容包'} · {meta.blueprint_id ? `蓝图 ${meta.blueprint_version}` : '尚无已确认蓝图'} · 路线 {meta.branch_id}
    </p>
    {meta.pack_error && <p className="design-warning">内容包读取失败：{meta.pack_error}</p>}

    <div className="world-grid">
      <article className="world-card">
        <h4>世界时间</h4>
        <dl>
          <div><dt>当前时间</dt><dd>{currentTime}</dd></div>
          <div><dt>Tick</dt><dd>{timeline.tick}</dd></div>
          <div><dt>已推进</dt><dd>{timeline.elapsed || '—'}</dd></div>
          <div><dt>世界推进次数</dt><dd>{timeline.world_ticks}</dd></div>
        </dl>
        {timeline.markers.length > 0 && <p className="world-tags">{timeline.markers.map((marker) => <span key={marker}>{marker}</span>)}</p>}
      </article>

      <article className="world-card">
        <h4>当前地点</h4>
        <dl>
          <div><dt>地点</dt><dd>{location.name || location.current || '未指明'}</dd></div>
          <div><dt>类型</dt><dd>{location.kind || '—'}</dd></div>
          <div><dt>控制方</dt><dd>{location.control || '—'}</dd></div>
          <div><dt>危险度</dt><dd>{location.danger === null || location.danger === undefined ? '—' : location.danger}</dd></div>
          <div><dt>通行条件</dt><dd>{location.access || '—'}</dd></div>
          <div><dt>已去过</dt><dd>{location.visited_labels.length ? location.visited_labels.join('、') : '—'}</dd></div>
        </dl>
      </article>
    </div>

    <article className="world-card">
      <h4>势力状态 · {factions.length}</h4>
      {factions.length === 0 && <p className="world-empty">当前小说还没有势力事实。势力状态只会由事件或效果写入。</p>}
      <div className="world-list">
        {factions.map((faction) => <div className="world-row" key={faction.id}>
          <div className="world-row-head">
            <b>{faction.name}</b>
            <span>{faction.stance || '未表态'}{faction.influence === null || faction.influence === undefined ? '' : ` · 影响力 ${faction.influence}`}</span>
          </div>
          {faction.tags.length > 0 && <p className="world-tags">{faction.tags.map((tag) => <span key={tag}>{tag}</span>)}</p>}
          {Array.isArray(faction.internal_conflicts) && faction.internal_conflicts.length > 0
            && <p>内部矛盾：{(faction.internal_conflicts as string[]).join('、')}</p>}
          {faction.active_plots.length > 0 && <p>相关支线：{faction.active_plots.join('、')}</p>}
        </div>)}
      </div>
    </article>

    <article className="world-card">
      <h4>最近世界事件 · {data.recent_world_events.length}</h4>
      {data.recent_world_events.length === 0 && <p className="world-empty">还没有发生世界事件。世界事件可以在主角不参与时发生。</p>}
      <div className="world-list">
        {data.recent_world_events.map((event) => <div className="world-row" key={`${event.event_id}-${event.order}`}>
          <div className="world-row-head"><b>{event.title}</b><span>第 {event.order} 条记录 · tick {event.tick}</span></div>
          <p>{event.actor_label || event.actor || '世界'}{event.kind ? ` · ${event.kind}` : ''}{event.scope ? ` · ${event.scope}` : ''}{event.knowledge_id ? ` · 知识 ${event.knowledge_id}` : ''}</p>
        </div>)}
      </div>
    </article>

    <article className="world-card">
      <h4>最近 NPC / 势力自主行动 · {data.recent_autonomous_actions.length}</h4>
      {data.recent_autonomous_actions.length === 0 && <p className="world-empty">还没有自主行动记录。world_tick 让非主角角色按自身目标行动。</p>}
      <div className="world-list">
        {data.recent_autonomous_actions.map((action) => <div className="world-row" key={`${action.actor_id}-${action.action_id}-${action.order}`}>
          <div className="world-row-head"><b>{action.actor_label}</b><span>{action.actor_kind === 'faction' ? '势力' : action.actor_kind === 'character' ? '角色' : '世界'}</span></div>
          <p>{action.action_label} · 第 {action.order} 条记录{action.tick ? ` · tick ${action.tick}` : ''}</p>
          {action.reason && action.reason !== action.source && <p className="world-note">{action.reason}</p>}
        </div>)}
      </div>
    </article>

    <article className="world-card">
      <h4>当前可触发事件 · {data.available_events.length}</h4>
      {data.available_events.length === 0 && <p className="world-empty">当前状态下没有可触发事件。</p>}
      <div className="world-list">
        {data.available_events.map((event) => <div className="world-row" key={event.event_id}>
          <div className="world-row-head"><b>{event.title}</b><span>优先级 {event.priority}</span></div>
          <p>{event.kind || '未分类'} · {event.scope === 'world' ? '世界事件' : '场景事件'}{event.source === 'active_event' ? ' · 进行中' : ''}</p>
        </div>)}
      </div>
    </article>

    {data.active_plots.length > 0 && <article className="world-card">
      <h4>活跃支线 · {data.active_plots.length}</h4>
      <div className="world-list">
        {data.active_plots.map((plot) => <div className="world-row" key={plot.id}>
          <div className="world-row-head"><b>{plot.title}</b><span>{plot.status} · 进度 {plot.progress} · 优先级 {plot.priority}</span></div>
          {plot.factions.length > 0 && <p>相关势力：{plot.factions.join('、')}</p>}
        </div>)}
      </div>
    </article>}

    {Object.keys(data.world_flags).length > 0 && <article className="world-card">
      <h4>世界标记</h4>
      <dl>
        {Object.entries(data.world_flags).map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{String(value)}</dd></div>)}
      </dl>
    </article>}

    {error && <p className="design-warning">世界面板刷新失败：{error}</p>}
  </section>
}
