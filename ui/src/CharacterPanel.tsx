import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { api, CreatorCharacterPayload, CreatorGoal } from './api'

const SCOPE_TITLES: Record<string, string> = { long_term: '长期目标', stage: '阶段目标', current: '当前目标' }

function GoalCard({ goal }: { goal: CreatorGoal }) {
  return <div className="world-row">
    <div className="world-row-head">
      <b>{goal.title || goal.id}</b>
      <span>{goal.status} · 优先级 {goal.priority} × 权重 {goal.weight} = {goal.score.toFixed(2)}</span>
    </div>
    {goal.description && <p>{goal.description}</p>}
    <p className="world-note">{goal.source ? `来源 ${goal.source}` : '无来源记录'}{goal.updated_tick ? ` · tick ${goal.updated_tick}` : ''}{goal.has_condition ? ' · 有触发条件' : ''}{goal.note ? ` · ${goal.note}` : ''}</p>
  </div>
}

/**
 * V2-I-02 角色面板：只渲染创作者 API 返回的角色投影，
 * 目标优先级、反应评分都由引擎给出，前端不重新计算。
 */
export default function CharacterPanel({ novelId, header }: { novelId: string; header?: ReactNode }) {
  const [data, setData] = useState<CreatorCharacterPayload | null>(null)
  const [selected, setSelected] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => { setSelected('') }, [novelId])

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError('')
    api.creatorCharacters(novelId, selected)
      .then((payload) => {
        if (cancelled) return
        setData(payload)
        if (!selected && payload.selected) setSelected(payload.selected)
      })
      .catch((reason) => {
        if (cancelled) return
        setData(null)
        setError(reason instanceof Error ? reason.message : String(reason))
      })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [novelId, selected])

  if (loading && !data) return <section className="world-panel">{header}<p className="world-empty">正在读取角色状态…</p></section>
  if (!data) return <section className="world-panel">{header}<p className="world-empty">角色状态读取失败：{error || '请确认后端已启动'}</p></section>

  const detail = data.detail
  return <section className="world-panel">
    {header}
    <div className="world-panel-head">
      <div>
        <span className="story-builder-kicker">角色面板</span>
        <h3>人物正在变成什么样</h3>
      </div>
      <span className={`badge ${data.meta.persisted ? 'pass' : ''}`}>{data.meta.persisted ? 'StoryState 已存档' : '预览状态 · 未落盘'}</span>
    </div>
    <label className="adventure-route-select">角色
      <select aria-label="角色" value={selected} disabled={loading} onChange={(event) => setSelected(event.target.value)}>
        {data.characters.map((item) => <option key={item.id} value={item.id}>{item.name}{item.is_player ? ' · 主角' : ''} · 目标 {item.active_goals} / 记忆 {item.memories}</option>)}
      </select>
    </label>

    {!detail && <p className="world-empty">当前事实里还没有角色。角色只会由内容包或效果写入。</p>}
    {detail && <>
      <div className="world-grid">
        <article className="world-card">
          <h4>当前目标</h4>
          {detail.current_goal
            ? <GoalCard goal={detail.current_goal} />
            : <p className="world-empty">按当前状态没有可选中目标（条件不满足或没有活跃目标）。</p>}
          <dl>
            <div><dt>身份</dt><dd>{detail.kind || '—'}{detail.status ? ` · ${detail.status}` : ''}</dd></div>
            <div><dt>已知信息</dt><dd>{detail.knowledge.length} 条</dd></div>
          </dl>
          {detail.tags.length > 0 && <p className="world-tags">{detail.tags.map((tag) => <span key={tag}>{tag}</span>)}</p>}
        </article>

        <article className="world-card">
          <h4>欲望 / 恐惧 / 底线</h4>
          <dl>
            <div><dt>目标</dt><dd>{detail.drives.goal || '—'}</dd></div>
            <div><dt>欲望</dt><dd>{detail.drives.desire || '—'}</dd></div>
            <div><dt>恐惧</dt><dd>{detail.drives.fear || '—'}</dd></div>
            <div><dt>当前压力</dt><dd>{detail.drives.current_pressure || '—'}</dd></div>
          </dl>
          {detail.drives.personality.length > 0 && <p className="world-tags">{detail.drives.personality.map((tag) => <span key={tag}>{tag}</span>)}</p>}
          {detail.drives.bottom_line.length > 0 && <p className="world-note">底线：{detail.drives.bottom_line.join('、')}</p>}
        </article>

        <article className="world-card">
          <h4>人物弧</h4>
          {detail.arc
            ? <dl>
              <div><dt>当前阶段</dt><dd>{detail.arc.stage || '—'}</dd></div>
              <div><dt>结果</dt><dd>{detail.arc.outcome}</dd></div>
              <div><dt>是否强制</dt><dd>{detail.arc.is_forced ? '是' : '否（由事件推动）'}</dd></div>
              <div><dt>备注</dt><dd>{detail.arc.note || '—'}</dd></div>
            </dl>
            : <p className="world-empty">还没有人物弧记录。</p>}
        </article>
      </div>

      {(['long_term', 'stage', 'current'] as const).map((scope) => <article className="world-card" key={scope}>
        <h4>{SCOPE_TITLES[scope]} · {detail.goals[scope].length}</h4>
        {detail.goals[scope].length === 0 && <p className="world-empty">这一类还没有目标。</p>}
        <div className="world-list">{detail.goals[scope].map((goal) => <GoalCard goal={goal} key={goal.id} />)}</div>
      </article>)}

      <article className="world-card">
        <h4>记忆 · {detail.memories.length}</h4>
        {detail.memories.length === 0 && <p className="world-empty">还没有记忆条目。只有实际经历或被合法告知才会写入。</p>}
        <div className="world-list">
          {detail.memories.map((memory) => <div className="world-row" key={memory.id}>
            <div className="world-row-head"><b>{memory.summary || memory.id}</b><span>tick {memory.tick}{memory.source ? ` · ${memory.source}` : ''}</span></div>
            {memory.participants.length > 0 && <p>相关：{memory.participants.join('、')}</p>}
            {memory.emotion.length > 0 && <p className="world-tags">{memory.emotion.map((tag) => <span key={tag}>{tag}</span>)}</p>}
          </div>)}
        </div>
      </article>

      <article className="world-card">
        <h4>多维关系 · {detail.relationships.length}</h4>
        {detail.relationships.length === 0 && <p className="world-empty">还没有关系记录。</p>}
        <div className="world-list">
          {detail.relationships.map((relation) => <div className="world-row" key={`${relation.direction}-${relation.other_id}`}>
            <div className="world-row-head">
              <b>{relation.other_label}</b>
              <span>{relation.direction === 'outgoing' ? '对方看自己' : '自己看对方'}{relation.stage ? ` · ${relation.stage}` : ''}</span>
            </div>
            <p>{Object.entries(relation.dimensions).map(([key, value]) => `${key} ${value}`).join(' · ') || '无维度数值'}</p>
          </div>)}
        </div>
      </article>

      <article className="world-card">
        <h4>最近自主行动 · {detail.recent_actions.length}</h4>
        {detail.recent_actions.length === 0 && <p className="world-empty">还没有该角色的行动记录。</p>}
        <div className="world-list">
          {detail.recent_actions.map((action) => <div className="world-row" key={`${action.kind}-${action.order}`}>
            <div className="world-row-head"><b>{action.label}</b><span>{action.kind === 'autonomous' ? '自主行动' : '选择'} · 第 {action.order} 条{action.tick ? ` · tick ${action.tick}` : ''}</span></div>
            {action.reason && <p className="world-note">{action.reason}</p>}
          </div>)}
        </div>
      </article>

      <article className="world-card">
        <h4>反应理由 · {detail.reactions.length}</h4>
        {detail.reactions.length === 0 && <p className="world-empty">内容包没有可评分的行动，或该角色缺少决策依据。</p>}
        <div className="world-list">
          {detail.reactions.map((reaction) => <div className="world-row" key={reaction.action_id}>
            <div className="world-row-head"><b>{reaction.name}</b><span>评分 {reaction.score.toFixed(2)}</span></div>
            <p>{reaction.reason || '没有明显偏好'}</p>
          </div>)}
        </div>
      </article>
    </>}
    {error && <p className="design-warning">角色面板刷新失败：{error}</p>}
  </section>
}
