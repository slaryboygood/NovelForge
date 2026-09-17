import { useEffect, useRef, useState } from 'react'
import { api, AdventureView, AdventureBranch } from './api'

export default function AdventurePanel({ id, version, onOutline }: { id: string; version: number; onOutline?: () => void }) {
  const [view, setView] = useState<AdventureView | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [started, setStarted] = useState(false)
  const [branches, setBranches] = useState<AdventureBranch[]>([])
  const [authorPlan, setAuthorPlan] = useState<Record<string, string> | null>(null)
  const inFlight = useRef(false)
  const pendingFork = useRef<{ key: string; request: string } | null>(null)
  useEffect(() => { setView(null); setStarted(false); setError(''); setBranches([]); setAuthorPlan(null); pendingFork.current = null }, [id, version])
  const act = async (choice?: string, branch = view?.state.branch_id || 'main') => {
    if (inFlight.current) return
    inFlight.current = true
    setBusy(true); setError('')
    try {
      setView(await api.adventure(id, version, choice && view ? { revision: view.state.revision, choice_id: choice } : undefined, branch))
      setStarted(true)
      setBranches((await api.adventureBranches(id, version)).branches)
    } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)) }
    finally { setBusy(false); inFlight.current = false }
  }
  const fork = async (at: number) => {
    if (!view || inFlight.current) return
    inFlight.current = true; setBusy(true); setError('')
    const key = `${view.state.branch_id}:${view.state.revision}:${at}`
    if (pendingFork.current?.key !== key) pendingFork.current = { key, request: crypto.randomUUID() }
    try {
      const next = await api.forkAdventure(id, version, view.state.branch_id, at, view.state.revision, pendingFork.current.request)
      setView(next); pendingFork.current = null
      setBranches((await api.adventureBranches(id, version)).branches)
    } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)) }
    finally { inFlight.current = false; setBusy(false) }
  }
  return <section className="adventure-panel">
    <h3>剧情闯关 · 故事路线</h3>
    {!started && <button className="btn primary" disabled={busy} onClick={() => act()}>{busy ? '正在读取…' : '开始 / 继续旅程'}</button>}
    {view && <>
      <label className="adventure-route-select">当前路线 <select value={view.state.branch_id} disabled={busy} onChange={(event) => act(undefined, event.target.value)}>
        {branches.map((branch, index) => <option value={branch.branch_id} key={branch.branch_id}>{branch.branch_id === 'main' ? '原路线' : `分支 ${index} · 从第 ${Number(branch.fork_revision) + 1} 次选择前开始`} · 已走 {branch.revision} 步</option>)}
      </select></label>
      <svg viewBox="0 0 360 48" className="adventure-map" role="img" aria-label={`旅程进度：已完成 ${view.state.revision} 次选择`}>
        <path d="M30 24 H330" stroke="#59616b" strokeWidth="2" />
        {Array.from({ length: view.state.rules_version === 2 ? 8 : 3 }, (_, n) => <g key={n}><circle cx={30 + n * 300 / (view.state.rules_version === 2 ? 7 : 2)} cy="24" r="13" fill={view.state.revision > n ? '#3ddc84' : '#30343b'} stroke="#a8b0bd"/><text x={30 + n * 300 / (view.state.rules_version === 2 ? 7 : 2)} y="29" textAnchor="middle" fill={view.state.revision > n ? '#101410' : '#ffffff'} fontSize="13">{n + 1}</text></g>)}
      </svg>
      <div className="adventure-stats"><span>补给 {view.state.supplies}</span><span>{view.state.ally ? '有同行者' : '独行'}</span><span>{view.state.clue || view.state.facts?.includes('receipt') ? '持有线索' : '尚无线索'}</span></div>
      {view.state.revision > 3 && <div className="adventure-stats"><span>信任变化 {view.state.trust || 0}</span><span>待兑现责任 {view.state.debt || 0}</span><span>{view.state.facts?.includes('diversion_verified') ? '调拨已核实' : view.state.facts?.includes('receipt') ? '已取得回执' : '未取得回执'}</span></div>}
      {view.state.history.length > 0 && !view.completed && <p className="adventure-result">{view.state.history[view.state.history.length - 1]?.result}</p>}
      <h4>{view.title}</h4><p className="adventure-prose">{view.text}</p>
      {view.warnings?.map((warning, index) => <p className="design-warning" key={index}>{warning}</p>)}
      <div className="adventure-choices">{view.choices.map((choice) => <button className="btn" key={choice.id} disabled={busy} onClick={() => act(choice.id)}><b>{choice.label}{choice.suggested ? ' · 符合当前性格' : ''}</b><small>{choice.cost}</small></button>)}</div>
      <details open={view.completed}><summary>旅程记录 · {view.state.history.length} 次选择</summary>{view.state.history.map((entry, i) => <article key={i}><h4>{entry.scene}：{entry.choice}</h4><p>{entry.result}</p><button className="btn" disabled={busy} onClick={() => fork(i)}>从第 {i + 1} 次选择前另开路线</button></article>)}</details>
      {view.state.rules_version === 2 && <details><summary>作者视角 · 后续谜题安排（含剧透）</summary>{authorPlan ? Object.entries(authorPlan).map(([key, value]) => <p key={key}>{value}</p>) : <button className="btn" onClick={async () => {
        try { setAuthorPlan(await api.adventureAuthorPlan(id, version)) } catch (reason) { setError(String(reason)) }
      }}>查看作者安排</button>}</details>}
      {view.completed && <button className="btn" onClick={() => {
        const blob = new Blob([view.state.history.map((e) => `${e.scene}\n${e.choice}\n${e.result}`).join('\n\n')], { type: 'text/plain;charset=utf-8' })
        const url = URL.createObjectURL(blob); const link = document.createElement('a'); link.href = url; link.download = '序章旅程.txt'; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000)
      }}>导出本段故事路线</button>}
      {view.completed && <button className="btn primary" disabled={busy} onClick={async () => {
        if (inFlight.current) return
        inFlight.current = true; setBusy(true); setError('')
        try {
          await api.compileRouteOutline(id, version, view.state.branch_id, view.state.revision)
          onOutline?.()
        } catch (reason) { setError(String(reason)) }
        finally { inFlight.current = false; setBusy(false) }
      }}>用当前路线整合大纲</button>}
    </>}
    {error && <div role="alert" className="story-builder-message error">{error}<button className="btn" disabled={busy} onClick={() => act()}>重新载入旅程</button></div>}
  </section>
}
