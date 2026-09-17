import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { api, CreatorProgressionNode, CreatorProgressionPayload } from './api'

const STATUS_LABELS: Record<string, string> = { owned: 'owned · 已拥有', available: 'available · 可解锁', locked: 'locked · 未解锁' }

function specText(spec: Record<string, unknown>): string {
  const op = String(spec.op ?? '')
  const target = String(spec.target ?? spec.key ?? '')
  const value = spec.value === undefined || spec.value === null ? '' : ` ${String(spec.value)}`
  return `${op}${target ? ' · ' + target : ''}${value}`
}

function conditionText(condition: Record<string, unknown> | null): string {
  if (!condition) return ''
  const op = String(condition.op ?? '')
  const parts = [String(condition.key ?? condition.target ?? ''), condition.comparator ? String(condition.comparator) : '',
    condition.value === undefined ? '' : String(condition.value)]
  return `${op} ${parts.filter((item) => item !== '').join(' ')}`
}

function NodeCard({ node }: { node: CreatorProgressionNode }) {
  return <article className={`plot-candidate ${node.status === 'owned' ? 'owned' : node.status === 'available' ? 'available' : 'blocked'}`}>
    <div className="world-row-head">
      <b>{node.name}</b>
      <span className={`plot-state ${node.status === 'owned' ? 'ok' : node.status === 'available' ? 'ok' : 'blocked'}`}>{STATUS_LABELS[node.status] ?? node.status}</span>
    </div>
    {node.summary && <p>{node.summary}</p>}
    {node.missing_requires.length > 0 && <p className="world-note">缺少前置：{node.missing_requires.join('、')}</p>}
    {node.status === 'locked' && node.reason && <p className="world-note">{node.reason}</p>}
    {node.unlock_condition && <p>解锁条件：{conditionText(node.unlock_condition)}</p>}
    {node.costs.length > 0 && <p>成本：{node.costs.map(specText).join('；')}</p>}
    {node.recommendation && <p className="plot-goal">推荐理由：{node.recommendation}</p>}
    {node.story_impact && <p>剧情影响：{node.story_impact}</p>}
    {node.blocked_by && <p className="world-note">与已选节点互斥：{node.blocked_by}</p>}
  </article>
}

/**
 * V2-I-04 成长面板：七类 Progression 的 owned / available / locked 全部由引擎判定，
 * 前端只按分类展示，不做解锁计算。
 */
export default function ProgressionPanel({ novelId, header }: { novelId: string; header?: ReactNode }) {
  const [data, setData] = useState<CreatorProgressionPayload | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError('')
    api.creatorProgression(novelId)
      .then((payload) => { if (!cancelled) setData(payload) })
      .catch((reason) => {
        if (cancelled) return
        setData(null)
        setError(reason instanceof Error ? reason.message : String(reason))
      })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [novelId])

  if (loading && !data) return <section className="world-panel">{header}<p className="world-empty">正在读取成长状态…</p></section>
  if (!data) return <section className="world-panel">{header}<p className="world-empty">成长状态读取失败：{error || '请确认后端已启动'}</p></section>

  return <section className="world-panel">
    {header}
    <div className="world-panel-head">
      <div>
        <span className="story-builder-kicker">成长面板</span>
        <h3>七类成长在同一套 Progression 上</h3>
      </div>
      <span className={`badge ${data.meta.persisted ? 'pass' : ''}`}>{data.meta.persisted ? 'StoryState 已存档' : '预览状态 · 未落盘'}</span>
    </div>
    <p className="world-source">
      已拥有 {data.counts.owned ?? 0} · 可解锁 {data.counts.available ?? 0} · 未解锁 {data.counts.locked ?? 0} · 成长树 {data.trees.length}
    </p>
    {data.note && <p className="design-warning">{data.note}</p>}

    {data.categories.map((category) => <article className="world-card" key={category.category}>
      <h4>{category.label} · owned {category.nodes.filter((node) => node.status === 'owned').length} / available {category.nodes.filter((node) => node.status === 'available').length} / locked {category.nodes.filter((node) => node.status === 'locked').length}</h4>
      {category.nodes.length === 0 && <p className="world-empty">这一类还没有成长节点。</p>}
      <div className="world-list">{category.nodes.map((node) => <NodeCard node={node} key={node.id} />)}</div>
    </article>)}

    <article className="world-card">
      <h4>已拥有节点 · {data.owned.length}</h4>
      {data.owned.length === 0 && <p className="world-empty">还没有任何成长节点被解锁。</p>}
      <p className="world-tags">{data.owned.map((item) => <span key={item}>{item}</span>)}</p>
    </article>

    {error && <p className="design-warning">成长面板刷新失败：{error}</p>}
  </section>
}
