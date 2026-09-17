import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { api, CreatorDirectorPayload } from './api'

/**
 * V2-I-06 导演面板：排序、逐维得分、加分 / 扣分原因与 chosen 全部来自导演 API。
 * 权重调整只提交配置数值，评分仍由后端 director.py 计算。
 */
export default function DirectorPanel({ novelId, header }: { novelId: string; header?: ReactNode }) {
  const [data, setData] = useState<CreatorDirectorPayload | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [weightKey, setWeightKey] = useState('')
  const [weightValue, setWeightValue] = useState('1')

  /**
   * 后端只在这本书已经有已发生事实时才返回 weights_keys；
   * 未开始的作品只返回 weights / weights_config，因此这里从实际字段推导，
   * 避免未开始的作品把整个面板（以及整个应用）打崩。
   */
  const weightKeysOf = (payload: CreatorDirectorPayload): string[] => {
    if (payload.weights_keys?.length) return payload.weights_keys
    const configured = Object.keys(payload.weights_config ?? {})
    return configured.length > 0 ? configured : Object.keys(payload.weights ?? {})
  }

  const load = async () => {
    setLoading(true)
    setError('')
    try {
      const payload = await api.creatorDirector(novelId)
      setData(payload)
      setWeightKey((current) => current || weightKeysOf(payload)[0] || '')
    } catch (reason) {
      setData(null)
      setError(reason instanceof Error ? reason.message : String(reason))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void load() }, [novelId])

  const submitWeights = async () => {
    if (!data || !weightKey) return
    const value = Number(weightValue)
    if (!Number.isFinite(value)) { setError('权重必须是数字'); return }
    setSaving(true)
    setError('')
    try {
      const result = await api.updateDirectorWeights(novelId, { [weightKey]: value })
      setData(result.director)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    } finally {
      setSaving(false)
    }
  }

  if (loading && !data) return <section className="world-panel">{header}<p className="world-empty">正在读取导演排序…</p></section>
  if (!data) return <section className="world-panel">{header}<p className="world-empty">导演面板读取失败：{error || '请确认后端已启动'}</p></section>

  return <section className="world-panel">
    {header}
    <div className="world-panel-head">
      <div>
        <span className="story-builder-kicker">导演面板</span>
        <h3>为什么推荐这个事件</h3>
      </div>
      <span className={`badge ${data.meta.persisted ? 'pass' : ''}`}>{data.meta.persisted ? 'StoryState 已存档' : '预览状态 · 未落盘'}</span>
    </div>
    <p className="world-source">视角角色 {data.actor || '—'} · 最近选择 {data.last_choice || '无'} · 当前权重 {Object.keys(data.weights_config).length ? '已由作者调整' : '默认配置'}</p>
    {data.note && <p className="design-warning">{data.note}</p>}

    <div className="world-grid">
      <article className="world-card">
        <h4>chosen · {data.chosen_title || '暂无'}</h4>
        {!data.chosen && <p className="world-empty">当前没有可推荐事件。</p>}
        {data.chosen && <ul className="plot-reasons">
          {data.why_chosen.length === 0 && <li>没有额外解释</li>}
          {data.why_chosen.map((reason) => <li key={reason}>{reason}</li>)}
        </ul>}
      </article>
      <article className="world-card">
        <h4>当前权重</h4>
        <dl>
          {Object.entries(data.weights).map(([key, value]) => <div key={key}>
            <dt>{key}{data.weights_config[key] !== undefined ? ' *' : ''}</dt>
            <dd>{data.weights_config[key] !== undefined ? `${value}（作者设定）` : value}</dd>
          </div>)}
        </dl>
      </article>
    </div>

    <article className="world-card">
      <h4>候选事件排序 · {data.ranked.length}</h4>
      {data.ranked.length === 0 && <p className="world-empty">当前状态没有合法事件可以排序。</p>}
      <div className="world-list">
        {data.ranked.map((row, index) => <div className="world-row" key={row.event_id}>
          <div className="world-row-head">
            <b>{index + 1}. {row.title}</b>
            <span>总分 {row.score.toFixed(3)}{row.is_chosen ? ' · chosen' : ''}</span>
          </div>
          <p>{row.kind || '未分类'} · 优先级 {row.priority}{row.scope ? ` · ${row.scope === 'world' ? '世界事件' : '场景事件'}` : ''}</p>
          <p>逐维得分：{Object.entries(row.dimensions).map(([key, value]) => `${key} ${value}`).join(' · ') || '无'}</p>
          {row.reasons.length > 0 && <p className="plot-goal">加分：{row.reasons.join('；')}</p>}
          {row.deductions.length > 0 && <p className="world-note">扣分：{row.deductions.join('；')}</p>}
          {data.why_not[row.event_id] && <p className="world-note">为什么暂不选：{data.why_not[row.event_id].join('；')}</p>}
        </div>)}
      </div>
    </article>

    <article className="world-card">
      <h4>调整权重（只改配置）</h4>
      <p className="world-empty">权重写入小说配置后由引擎重新排序；前端不参与评分。</p>
      <div className="plot-weight-form">
        <label>维度
          <select aria-label="权重维度" value={weightKey} disabled={saving} onChange={(event) => setWeightKey(event.target.value)}>
            {weightKeysOf(data).map((key) => <option key={key} value={key}>{key}</option>)}
          </select>
        </label>
        <label>数值
          <input aria-label="权重数值" type="number" step="0.1" value={weightValue} disabled={saving}
            onChange={(event) => setWeightValue(event.target.value)} />
        </label>
        <button className="btn primary" disabled={saving || !weightKey} onClick={submitWeights}>{saving ? '正在保存…' : '保存并重新排序'}</button>
      </div>
    </article>

    <article className="world-card">
      <h4>合法事件池 · {data.available_events.length}</h4>
      {data.available_events.length === 0 && <p className="world-empty">导演只排序合法事件；当前没有合法事件。</p>}
      <p className="world-tags">{data.available_events.map((item) => <span key={item.event_id}>{item.event_id}</span>)}</p>
    </article>

    {error && <p className="design-warning">导演面板：{error}</p>}
  </section>
}
