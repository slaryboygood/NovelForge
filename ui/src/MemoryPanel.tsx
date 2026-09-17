import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { api, CreatorKnowledgeRow, CreatorMemoryPayload } from './api'

function KnowledgeList({ rows }: { rows: CreatorKnowledgeRow[] }) {
  if (rows.length === 0) return <p className="world-empty">这里还没有条目。</p>
  return <div className="world-list">{rows.map((row) => <div className="world-row" key={row.id}>
    <div className="world-row-head">
      <b>{row.id}</b>
      <span>{row.certainty}{row.reader_visible ? ' · 读者可见' : ' · 读者未知'}{row.tick ? ` · tick ${row.tick}` : ''}</span>
    </div>
    <p>来源：{row.source || '未记录'}{row.source_event ? ` · ${row.source_event}` : ''}</p>
    <p>持有者：{row.holders.length ? row.holders.join('、') : '未认领（还没有角色知道）'}</p>
  </div>)}</div>
}

/**
 * V2-I-05 记忆面板：三视角知识、承诺 / 债务 / 人情、仇恨来源、未解决冲突与未回收伏笔；
 * 全部来自创作者 API 的查询层结果，前端不做知识下放或回收判断。
 */
export default function MemoryPanel({ novelId, header }: { novelId: string; header?: ReactNode }) {
  const [data, setData] = useState<CreatorMemoryPayload | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError('')
    api.creatorMemory(novelId)
      .then((payload) => { if (!cancelled) setData(payload) })
      .catch((reason) => {
        if (cancelled) return
        setData(null)
        setError(reason instanceof Error ? reason.message : String(reason))
      })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [novelId])

  if (loading && !data) return <section className="world-panel">{header}<p className="world-empty">正在读取知识分层…</p></section>
  if (!data) return <section className="world-panel">{header}<p className="world-empty">记忆面板读取失败：{error || '请确认后端已启动'}</p></section>

  const knowledge = data.knowledge_index
  return <section className="world-panel">
    {header}
    <div className="world-panel-head">
      <div>
        <span className="story-builder-kicker">记忆面板</span>
        <h3>谁知道什么，还欠什么没解决</h3>
      </div>
      <span className={`badge ${data.meta.persisted ? 'pass' : ''}`}>{data.meta.persisted ? 'StoryState 已存档' : '预览状态 · 未落盘'}</span>
    </div>
    <p className="world-source">
      作者 {data.counts.author ?? 0} · 读者可见 {data.counts.reader ?? 0} · 角色知识 {data.counts.character ?? 0} · 未结承诺 {data.counts.outstanding ?? 0} · 未解决冲突 {data.counts.conflicts ?? 0} · 未回收伏笔 {data.counts.open_foreshadows ?? 0}
    </p>

    <div className="world-grid">
      <article className="world-card">
        <h4>author 视角 · {data.author.entries.length}</h4>
        <p className="world-empty">作者知道、读者未必知道；计划类信息不会自动下放给角色。</p>
        <KnowledgeList rows={data.author.entries} />
        {data.author.author_only.length > 0 && <p className="world-note">读者还不知道：{data.author.author_only.join('、')}</p>}
      </article>
      <article className="world-card">
        <h4>reader 视角 · {data.reader.entries.length}</h4>
        <p className="world-empty">读者已经看到过的信息；与角色是否知道严格分开。</p>
        <KnowledgeList rows={data.reader.entries} />
      </article>
    </div>

    <article className="world-card">
      <h4>character 视角 · 谁知道什么</h4>
      {data.characters.length === 0 && <p className="world-empty">当前事实里还没有角色。</p>}
      <div className="world-list">
        {data.characters.map((name) => {
          const rows = data.character_knowledge[name] ?? []
          const readerOnly = data.reader_only[name] ?? []
          return <div className="world-row" key={name}>
            <div className="world-row-head"><b>{name}</b><span>知道 {rows.length} 条 · 读者知道但他不知道 {readerOnly.length} 条</span></div>
            <p>{rows.length ? rows.map((row) => row.id).join('、') : '还没有任何知识'}</p>
            {readerOnly.length > 0 && <p className="world-note">信息差：{readerOnly.join('、')}</p>}
          </div>
        })}
      </div>
    </article>

    <article className="world-card">
      <h4>承诺 / 债务 / 人情 · 未结 {data.obligations.outstanding.length} / 逾期 {data.obligations.overdue.length}</h4>
      {data.obligations.all.length === 0 && <p className="world-empty">还没有承诺、债务或人情记录。</p>}
      <div className="world-list">
        {data.obligations.all.map((item) => <div className="world-row" key={item.id}>
          <div className="world-row-head">
            <b>{item.description || item.id}</b>
            <span>{item.kind} · {item.status}{item.overdue ? ' · 已逾期' : ''}</span>
          </div>
          <p>{item.debtor || '—'} → {item.creditor || '—'}{item.due_tick ? ` · 到期 tick ${item.due_tick}` : ''}{item.settled_tick ? ` · 结清于 tick ${item.settled_tick}` : ''}</p>
        </div>)}
      </div>
    </article>

    <div className="world-grid">
      <article className="world-card">
        <h4>仇恨来源 · {data.hostility.length}</h4>
        {data.hostility.length === 0 && <p className="world-empty">当前没有敌意关系。</p>}
        <div className="world-list">
          {data.hostility.map((row) => <div className="world-row" key={`${row.source_id}-${row.target_id}`}>
            <div className="world-row-head"><b>{row.source_id} → {row.target_id}</b><span>敌意 {row.hostility}</span></div>
            {row.sources.length === 0 && <p className="world-empty">还没有记录到具体原因。</p>}
            {row.sources.map((source) => <p key={source.order}>tick {source.tick} · {source.reason || source.source}（{source.delta}）</p>)}
          </div>)}
        </div>
      </article>

      <article className="world-card">
        <h4>未解决冲突 · {data.conflicts.length}</h4>
        {data.conflicts.length === 0 && <p className="world-empty">当前没有未解决冲突。</p>}
        <div className="world-list">
          {data.conflicts.map((row) => <div className="world-row" key={`${row.kind}-${row.id}`}>
            <div className="world-row-head"><b>{row.title || row.id}</b><span>{row.kind} · {row.status} · 压力 {row.pressure}</span></div>
            {row.participants.length > 0 && <p>相关：{row.participants.join('、')}</p>}
          </div>)}
        </div>
      </article>
    </div>

    <article className="world-card">
      <h4>未回收伏笔 · {data.open_foreshadows.length} / 全部 {data.foreshadows.length}</h4>
      {data.foreshadows.length === 0 && <p className="world-empty">当前小说还没有伏笔定义。</p>}
      <div className="world-list">
        {data.foreshadows.map((item) => <div className="world-row" key={item.id}>
          <div className="world-row-head">
            <b>{item.title}</b>
            <span>{item.status}{item.planted_in ? ` · 埋于 ${item.planted_in}` : ''}{item.payoff_in ? ` · 计划回收 ${item.payoff_in}` : ''}</span>
          </div>
          <p>{item.has_payoff_condition ? (item.payoff_ready ? '回收条件已满足，等待事件兑现' : '回收条件尚未满足') : '还没有回收条件'}</p>
          {item.author_note && <p className="world-note">{item.author_note}</p>}
        </div>)}
      </div>
    </article>

    <article className="world-card">
      <h4>知识总表 · {knowledge.length}</h4>
      {knowledge.length === 0 && <p className="world-empty">还没有任何知识条目。</p>}
      <p className="world-tags">{knowledge.map((row) => <span key={row.id}>{row.id}</span>)}</p>
    </article>

    {error && <p className="design-warning">记忆面板刷新失败：{error}</p>}
  </section>
}
