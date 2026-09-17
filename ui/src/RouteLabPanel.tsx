import { useEffect, useState } from 'react'
import {
  api, BranchComparisonPayload, BranchListPayload, BranchMergePreviewPayload,
  RuntimeCandidateRow,
} from './api'

/**
 * W2 路线实验室：试演分支 → 结构化对比 → 合并选中的成果 → 设为正式路线。
 *
 * 只调用通用只读 / 操作 API；分支事实、差异与合并效果全部由引擎计算，前端不做规则判断。
 */
export default function RouteLabPanel({ novelId, onDeepLink }: {
  novelId: string
  onDeepLink?: (link: { tab: 'outline' | 'linkage'; branch_id?: string }) => void
}) {
  const [branches, setBranches] = useState<BranchListPayload | null>(null)
  const [activeBranch, setActiveBranch] = useState('main')
  const [candidates, setCandidates] = useState<RuntimeCandidateRow[]>([])
  const [revision, setRevision] = useState(0)
  const [compare, setCompare] = useState<BranchComparisonPayload | null>(null)
  const [preview, setPreview] = useState<BranchMergePreviewPayload | null>(null)
  const [selectedItems, setSelectedItems] = useState<Record<string, boolean>>({})
  const [targetBranch, setTargetBranch] = useState('main')
  const [sourceBranches, setSourceBranches] = useState<string[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  const loadBranches = async () => {
    const payload = await api.runtimeBranches(novelId)
    setBranches(payload)
    if (!payload.branches.some((row) => row.branch_id === activeBranch) && payload.branches.length) {
      setActiveBranch(payload.branches[0].branch_id)
    }
  }

  const loadBranchState = async (branchId: string) => {
    const state = await api.runtimeState(novelId, branchId)
    setCandidates(state.candidates ?? [])
    setRevision(state.revision ?? 0)
  }

  useEffect(() => {
    let cancelled = false
    setError(''); setMessage(''); setCompare(null); setPreview(null)
    api.runtimeBranches(novelId)
      .then((payload) => {
        if (cancelled) return
        setBranches(payload)
        const initial = payload.branches.some((row) => row.branch_id === activeBranch)
          ? activeBranch : (payload.branches[0]?.branch_id ?? 'main')
        setActiveBranch(initial)
        setTargetBranch(payload.official_branch || initial)
        // 这本书还没有开始推演：没有分支就没有可试演的路线状态。
        // 这是预期空态，因此不再请求 runtime/state（否则会得到 422 噪音）。
        if (!payload.branches.length) {
          setCandidates([]); setRevision(0)
          setMessage('这本书还没有开始推演：先到「推演」里让故事开始，再回到路线实验室试演分支。')
          return undefined
        }
        return api.runtimeState(novelId, initial).then((state) => {
          if (cancelled) return
          setCandidates(state.candidates ?? [])
          setRevision(state.revision ?? 0)
        })
      })
      .catch((reason) => {
        if (cancelled) return
        const text = reason instanceof Error ? reason.message : String(reason)
        setError(text.includes('内容包') ? '' : text)
      })
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [novelId])

  const pickBranch = async (branchId: string) => {
    setActiveBranch(branchId); setError(''); setMessage('')
    try { await loadBranchState(branchId) } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    }
  }

  const act = async (actionId: string) => {
    setBusy(true); setError(''); setMessage('')
    try {
      await api.advanceRuntime(novelId, { action_id: actionId, branch_id: activeBranch,
        expected_revision: revision })
      await loadBranchState(activeBranch)
      await loadBranches()
      setMessage(`已在分支 ${activeBranch} 执行 ${actionId}。`)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    } finally { setBusy(false) }
  }

  const fork = async () => {
    setBusy(true); setError(''); setMessage('')
    try {
      const created = await api.forkBranch(novelId, { source_branch: activeBranch,
        label: `试演 ${Date.now() % 10000}` })
      await loadBranches()
      await pickBranch(created.branch_id)
      setMessage(`已从 ${created.source_branch} 复制出试演分支 ${created.branch_id}。`)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    } finally { setBusy(false) }
  }

  const runCompare = async (target: string) => {
    setBusy(true); setError(''); setMessage('')
    try {
      const result = await api.compareBranches(novelId, activeBranch, target)
      setCompare(result)
      setMessage(`对比 ${result.base_branch} → ${result.target_branch}：${result.rows.length} 处差异。`)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    } finally { setBusy(false) }
  }

  const runPreview = async () => {
    setBusy(true); setError(''); setMessage('')
    try {
      const result = await api.previewBranchMerge(novelId, { target_branch: targetBranch,
        source_branches: sourceBranches })
      setPreview(result)
      const initial: Record<string, boolean> = {}
      for (const source of result.sources) {
        for (const item of source.mergeable) initial[`${item.kind}:${item.item}`] = true
      }
      setSelectedItems(initial)
      setMessage('已列出可合并项与冲突项；勾选后再执行合并。')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    } finally { setBusy(false) }
  }

  const runMerge = async () => {
    setBusy(true); setError(''); setMessage('')
    try {
      const keys = Object.keys(selectedItems).filter((key) => selectedItems[key])
      const result = await api.mergeBranches(novelId, { target_branch: targetBranch,
        source_branches: sourceBranches, item_keys: keys })
      setMessage(`已合并 ${result.merged.length} 项到 ${result.target_branch}；`
        + `跳过 ${result.skipped.length} 项；历史${result.history_preserved ? '保持不变' : '被改写（异常）'}。`)
      await loadBranches()
      if (targetBranch === activeBranch) await loadBranchState(activeBranch)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    } finally { setBusy(false) }
  }

  const freeze = async () => {
    setBusy(true); setError(''); setMessage('')
    try {
      const result = await api.freezeBranch(novelId, { branch_id: activeBranch,
        label: `正式路线 ${new Date().toLocaleString('zh-CN')}` })
      await loadBranches()
      setMessage(`已把 ${result.official_branch} 设为正式路线（冻结 revision `
        + `${result.frozen_revision}，快照 ${result.frozen_branch}）。`)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    } finally { setBusy(false) }
  }

  const toggleSource = (branchId: string) => {
    setSourceBranches((current) => current.includes(branchId)
      ? current.filter((item) => item !== branchId) : [...current, branchId])
  }

  return <section className="world-panel route-lab-panel">
    <div className="world-panel-head">
      <div>
        <span className="story-builder-kicker">路线实验室 · W2</span>
        <h3>试演多条剧情路线，再把要保留的成果合并成正式路线</h3>
      </div>
      <span className={`badge ${branches?.official_branch ? 'pass' : ''}`}>
        {branches?.official_branch ? `正式路线：${branches.official_branch.slice(0, 14)}…` : '尚未冻结正式路线'}
      </span>
    </div>
    <p className="world-source">
      每条分支都是独立 StoryState；合并只搬运可执行的成果效果，冲突项不会被自动写入。
    </p>
    {!branches?.started && <p className="world-source">这本小说还没有开始推演：先在上方的设定入口点「开始剧情推演」。</p>}
    {message && <div className="story-builder-message">{message}</div>}
    {error && <div className="story-builder-message error">{error}</div>}

    <article className="world-card">
      <div className="world-row-head"><h4>分支</h4><span>{branches?.branches.length ?? 0} 条</span></div>
      <div className="world-list">
        {(branches?.branches ?? []).map((row) => <div className="world-row" key={row.branch_id}>
          <div className="world-row-head">
            <b>{row.branch_id}{row.official ? ' · 正式路线' : ''}</b>
            <span>revision {row.revision} · tick {row.tick} · 知识 {row.knowledge} · 活跃支线 {row.plots_active}</span>
          </div>
          <p>地点：{row.location} · 未回收伏笔：{row.foreshadows_open}
            {row.source_branch ? ` · 来自 ${row.source_branch}` : ''}</p>
          <div className="builder-actions">
            <button className="btn" disabled={busy} onClick={() => pickBranch(row.branch_id)}>切换试演</button>
            <button className="btn" disabled={busy} onClick={() => runCompare(row.branch_id)}>
              与当前分支对比
            </button>
            <label className="creative-field">作为合并来源
              <input type="checkbox" aria-label={`合并来源 ${row.branch_id}`}
                checked={sourceBranches.includes(row.branch_id)}
                onChange={() => toggleSource(row.branch_id)} />
            </label>
          </div>
        </div>)}
      </div>
      <div className="builder-actions">
        <button className="btn" disabled={busy || !branches?.started} onClick={fork}>从当前分支新建试演分支</button>
        <button className="btn" disabled={busy || !branches?.started} onClick={freeze}>
          把当前分支设为正式路线
        </button>
      </div>
    </article>

    <article className="world-card">
      <div className="world-row-head"><h4>试演 · {activeBranch}</h4><span>revision {revision}</span></div>
      <div className="world-list">
        {candidates.map((row) => <div className="world-row" key={row.action_id}>
          <div className="world-row-head">
            <b>{row.name || row.action_id}</b>
            <span>{row.available ? '可执行' : `不可用：${row.reason || row.code}`}</span>
          </div>
          <button className="btn" disabled={busy || !row.available} onClick={() => act(row.action_id)}>
            在这条分支执行
          </button>
        </div>)}
        {!candidates.length && <div className="world-row"><p>当前没有候选行动。</p></div>}
      </div>
    </article>

    {compare && <article className="world-card">
      <div className="world-row-head">
        <h4>结构化差异 · {compare.base_branch} → {compare.target_branch}</h4>
        <span>{compare.rows.length} 处 · 冲突 {compare.conflicts.length}</span>
      </div>
      <div className="world-list">
        {compare.rows.map((row) => <div className="world-row" key={`${row.kind}:${row.item_id}`}>
          <div className="world-row-head">
            <b>{row.label || row.item_id}</b>
            <span>{row.kind} · {row.conflict ? '冲突' : row.mergeable ? '可合并' : '仅记录'}</span>
          </div>
          <p>{String(row.base)} → {String(row.target)}　{row.note}</p>
        </div>)}
        {!compare.rows.length && <div className="world-row"><p>两条分支没有差异。</p></div>}
        {onDeepLink && <div className="world-row" data-testid="route-compare-deeplink">
          <b>带着这条分支继续（W6-05）</b>
          <p>差异结果可以直接带进大纲影响分析，不需要手动切页签再重选对象。</p>
          <div className="builder-actions">
            <button type="button" className="btn primary"
              onClick={() => onDeepLink({ tab: 'outline', branch_id: compare.target_branch })}>
              去大纲影响分析（{compare.target_branch}）
            </button>
          </div>
        </div>}
      </div>
    </article>}

    <article className="world-card">
      <div className="world-row-head"><h4>合并与冻结</h4><span>目标 {targetBranch}</span></div>
      <label className="creative-field">目标分支
        <select aria-label="合并目标分支" value={targetBranch}
          onChange={(event) => setTargetBranch(event.target.value)}>
          {(branches?.branches ?? []).map((row) => <option key={row.branch_id}
            value={row.branch_id}>{row.branch_id}</option>)}
        </select>
      </label>
      <div className="builder-actions">
        <button className="btn" disabled={busy || !sourceBranches.length} onClick={runPreview}>预览合并</button>
        <button className="btn primary" disabled={busy || !preview} onClick={runMerge}>执行合并</button>
      </div>
      {preview && <div className="world-list">
        {preview.sources.map((source) => <div className="world-row" key={source.source_branch}>
          <div className="world-row-head">
            <b>{source.source_branch}</b>
            <span>可合并 {source.mergeable.length} · 冲突 {source.conflicts.length}</span>
          </div>
          {source.mergeable.map((item) => <label className="creative-field" key={`${item.kind}:${item.item}`}>
            <span>{item.kind} · {item.label || item.item}</span>
            <input type="checkbox" aria-label={`合并项 ${item.kind}:${item.item}`}
              checked={Boolean(selectedItems[`${item.kind}:${item.item}`])}
              onChange={() => setSelectedItems((current) => ({
                ...current, [`${item.kind}:${item.item}`]: !current[`${item.kind}:${item.item}`],
              }))} />
          </label>)}
          {source.conflicts.map((item) => <p key={`c-${item.kind}:${item.item}`}>
            冲突 · {item.kind} · {item.label || item.item}：{item.note}
          </p>)}
        </div>)}
      </div>}
    </article>
  </section>
}
