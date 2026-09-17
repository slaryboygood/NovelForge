import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { api, CreatorLinkagePayload } from './api'

/**
 * V2-I-07 大纲联动面板：StoryState → 实际路线 → 全书 / 卷 / 篇章 / 章节。
 * happened / planned / suggested / unresolved 分开显示；重规划只做预览，不改历史。
 */
export default function LinkagePanel({ novelId, header }: { novelId: string; header?: ReactNode }) {
  const [data, setData] = useState<CreatorLinkagePayload | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [stage, setStage] = useState('')
  const [note, setNote] = useState('玩家改选后重新规划未来')
  const [previewing, setPreviewing] = useState(false)

  const load = async () => {
    setLoading(true)
    setError('')
    try {
      const payload = await api.creatorLinkage(novelId)
      setData(payload)
      setStage((current) => current || payload.plans[0]?.id || '')
    } catch (reason) {
      setData(null)
      setError(reason instanceof Error ? reason.message : String(reason))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void load() }, [novelId])

  const preview = async () => {
    setPreviewing(true)
    setError('')
    try {
      setData(await api.creatorLinkage(novelId, true, stage, note))
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    } finally {
      setPreviewing(false)
    }
  }

  if (loading && !data) return <section className="world-panel">{header}<p className="world-empty">正在读取路线与大纲…</p></section>
  if (!data) return <section className="world-panel">{header}<p className="world-empty">大纲联动读取失败：{error || '请确认后端已启动'}</p></section>

  const volumes = data.long_line.volumes
  const arcs = data.long_line.arcs
  return <section className="world-panel">
    {header}
    <div className="world-panel-head">
      <div>
        <span className="story-builder-kicker">大纲联动</span>
        <h3>从已发生的事实长到全书</h3>
      </div>
      <span className={`badge ${data.meta.persisted ? 'pass' : ''}`}>{data.meta.persisted ? 'StoryState 已存档' : '预览状态 · 未落盘'}</span>
    </div>
    <p className="world-source">
      StoryState · tick {data.story_state.tick} · 效果记录 {data.story_state.effect_log} · 支线 {data.story_state.plots} · 进行中事件 {data.story_state.active_events}
    </p>

    <article className="world-card">
      <h4>链路概览</h4>
      <dl>
        <div><dt>StoryState</dt><dd>{data.story_state.effect_log} 条记录{data.story_state.current_location ? ` · 当前地点 ${data.story_state.current_location}` : ''}</dd></div>
        <div><dt>实际路线</dt><dd>happened {data.counts.happened} · planned {data.counts.planned} · suggested {data.counts.suggested}</dd></div>
        <div><dt>全书</dt><dd>卷 {volumes.length} · 篇章 {arcs.length} · 章节 {data.long_line.chapters.length}</dd></div>
        <div><dt>历史不可改写</dt><dd>{data.history_immutable ? '是（重规划只影响未来）' : '否'}</dd></div>
      </dl>
    </article>

    <div className="world-grid">
      <article className="world-card">
        <h4>happened · {data.counts.happened}</h4>
        {data.counts.happened === 0 && <p className="world-empty">还没有已发生的事实。</p>}
        <div className="world-list">
          {data.route.happened.slice(-12).map((record) => <div className="world-row" key={record.id}>
            <div className="world-row-head"><b>{record.result || record.id}</b><span>{record.origin} · tick {record.tick}</span></div>
            <p>来源 {record.source}{record.participants.length ? ` · ${record.participants.join('、')}` : ''}</p>
          </div>)}
        </div>
      </article>
      <article className="world-card">
        <h4>planned / suggested</h4>
        <dl>
          <div><dt>计划阶段</dt><dd>{data.plans.length}</dd></div>
          <div><dt>建议事件</dt><dd>{data.counts.suggested}</dd></div>
          <div><dt>未决项</dt><dd>{data.long_line.unresolved.length}</dd></div>
        </dl>
        {data.plans.length === 0 && <p className="world-empty">作者还没有声明未来阶段；这里不会凭空生成计划。</p>}
        <div className="world-list">
          {data.plans.map((item) => <div className="world-row" key={item.id}>
            <div className="world-row-head"><b>{item.title || item.id}</b><span>{item.status}</span></div>
            {item.goal && <p>{item.goal}</p>}
            {item.note && <p className="world-note">{item.note}</p>}
          </div>)}
        </div>
      </article>
    </div>

    <article className="world-card">
      <h4>卷 / 篇章 / 章节</h4>
      {volumes.length === 0 && <p className="world-empty">还没有已发生章节，无法拆分长线。</p>}
      <div className="world-list">
        {volumes.map((volume) => <div className="world-row" key={volume.id}>
          <div className="world-row-head"><b>{volume.id}</b><span>{volume.arcs.length} 篇章 · {volume.sources.length} 来源</span></div>
          <div className="world-list">
            {volume.arcs.map((arcId) => {
              const arc = arcs.find((item) => item.id === arcId)
              return <div className="world-row" key={arcId}>
                <div className="world-row-head"><b>{arcId}</b><span>{arc?.chapters.length ?? 0} 章</span></div>
                <p>{(arc?.chapters ?? []).map((chapterId) => {
                  const chapter = data.long_line.chapters.find((item) => item.id === chapterId)
                  return chapter ? `${chapter.id}：${chapter.title}` : chapterId
                }).join(' · ')}</p>
              </div>
            })}
          </div>
        </div>)}
      </div>
    </article>

    <article className="world-card">
      <h4>大纲来源校验 · verified {data.trace.verified.length} / unresolved {data.unresolved.length}</h4>
      <p className="world-empty">大纲里的“已发生事实”必须能在 StoryState 的路线里找到来源。</p>
      {data.unresolved.length === 0
        ? <p className="plot-goal">所有条目都有来源。</p>
        : <p className="world-note">无来源（unresolved）：{data.unresolved.join('、')}</p>}
      {(data.existing_outlines.length > 0 || data.outline_preview.length > 0) && <div className="world-list">
        {data.existing_outlines.map((outline) => <div className="world-row" key={outline.package_id}>
          <div className="world-row-head"><b>{outline.level} V{outline.version}</b><span>{outline.status} · {outline.items.length} 条目</span></div>
          {outline.pending_questions.length > 0 && <p className="world-note">{outline.pending_questions.join('；')}</p>}
        </div>)}
        {data.outline_preview.slice(-6).map((item) => <div className="world-row" key={item.item_id}>
          <div className="world-row-head"><b>{item.title}</b><span>由路线生成 · {item.location || '未指明地点'}</span></div>
          <p>{item.summary}</p>
        </div>)}
      </div>}
    </article>

    <article className="world-card">
      <h4>未来重规划预览（不修改已经发生的历史）</h4>
      <p className="world-empty">预览只把结果展示出来，不写回大纲或 StoryState。</p>
      <div className="plot-weight-form">
        <label>改变的阶段
          <select aria-label="改变的阶段" value={stage} disabled={previewing} onChange={(event) => setStage(event.target.value)}>
            <option value="">（不指定）</option>
            {data.plans.map((item) => <option key={item.id} value={item.id}>{item.title || item.id}</option>)}
          </select>
        </label>
        <label>说明
          <input aria-label="重规划说明" value={note} disabled={previewing} onChange={(event) => setNote(event.target.value)} />
        </label>
        <button className="btn primary" disabled={previewing} onClick={preview}>{previewing ? '正在预览…' : '预览重规划'}</button>
      </div>
      {data.replan_preview && <div className="world-list">
        <div className="world-row">
          <div className="world-row-head"><b>计划版本 {data.replan_preview.plan_revision}</b><span>{data.replan_preview.happened_unchanged ? '历史未变' : '历史被改动（不允许）'}</span></div>
          <p>改变的阶段：{data.replan_preview.changed_stage || '未指定'}{data.replan_preview.note ? ` · ${data.replan_preview.note}` : ''}</p>
        </div>
        {data.replan_preview.plan.map((item) => <div className="world-row" key={item.id}>
          <div className="world-row-head"><b>{item.title || item.id}</b><span>{item.status}</span></div>
          {item.goal && <p>{item.goal}</p>}
          {item.note && <p className="world-note">{item.note}</p>}
        </div>)}
      </div>}
    </article>

    {error && <p className="design-warning">大纲联动：{error}</p>}
  </section>
}
