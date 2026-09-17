import { useEffect, useState } from 'react'
import {
  api, OutlineChainPayload, OutlineChapterPlan, OutlineImpactPayload,
  OutlinePackagePayload, OutlineQualityReport, OutlineVersionDiffRow, OutlineVersionRow,
} from './api'

/**
 * W3 大纲锻造：把一条路线的 StoryState 事实转成
 * 全书主线 → 卷纲 → 篇章纲 → 详细章纲（复用既有四级大纲仓库与导出）。
 *
 * 前端只提交结构参数与分支，章纲内容、质量评估、来源校验全部来自引擎。
 */
const KIND_LABELS: Record<string, string> = {
  happened: '已发生', planned: '规划中', suggested: '建议',
}

export default function OutlineForgePanel({ novelId, initialBranchId = '',
  initialPackageId = '', initialVersion = '', onDeepLink }: {
  novelId: string
  initialBranchId?: string
  initialPackageId?: string
  initialVersion?: string
  onDeepLink?: (link: { tab: 'outline'; package_id?: string; version?: string }) => void
}) {
  const [branchId, setBranchId] = useState(initialBranchId || 'main')
  const [volumes, setVolumes] = useState(3)
  const [arcsPerVolume, setArcsPerVolume] = useState(2)
  const [chaptersPerArc, setChaptersPerArc] = useState(5)
  const [chapters, setChapters] = useState<OutlineChapterPlan[]>([])
  const [chain, setChain] = useState<OutlineChainPayload | null>(null)
  const [quality, setQuality] = useState<OutlineQualityReport | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [previewText, setPreviewText] = useState('')
  const [branches, setBranches] = useState<string[]>(['main'])
  const [packageOptions, setPackageOptions] = useState<OutlinePackagePayload[]>([])
  const [activePackage, setActivePackage] = useState('')
  const [versions, setVersions] = useState<OutlineVersionRow[]>([])
  const [versionDiff, setVersionDiff] = useState<OutlineVersionDiffRow[]>([])
  const [impact, setImpact] = useState<OutlineImpactPayload | null>(null)
  const [editField, setEditField] = useState<'summary' | 'ending_hook' | 'title'>('summary')
  const [editValue, setEditValue] = useState('')
  const [activeItem, setActiveItem] = useState('')

  useEffect(() => {
    let cancelled = false
    setError(''); setMessage(''); setChapters([]); setChain(null); setQuality(null)
    api.runtimeBranches(novelId)
      .then((payload) => {
        if (cancelled) return
        const ids = payload.branches.map((row) => row.branch_id)
        setBranches(ids.length ? ids : ['main'])
        // 这本书还没有开始推演：没有路线就没有可锻造的大纲。这是预期空态，
        // 后续接口不会返回数据，因此不再请求，也不显示为错误。
        if (!ids.length) {
          setChain(null)
          setMessage('这本书还没有可锻造的路线：先到「推演」里让故事开始，再回来锻造大纲。')
          return undefined
        }
        const requested = initialBranchId && ids.includes(initialBranchId)
          ? initialBranchId : ''
        const initial = requested || payload.official_branch || ids[0] || 'main'
        setBranchId(initial)
        return api.outlineChain(novelId, initial).then((loaded) => {
          if (cancelled) return
          setChain(loaded)
          setPackageOptions([loaded.book, ...loaded.volumes, ...loaded.arcs,
            ...loaded.chapters].filter(Boolean) as OutlinePackagePayload[])
          const requested = initialPackageId
            ? [loaded.book, ...loaded.volumes, ...loaded.arcs, ...loaded.chapters]
              .find((row) => row && row.package_id === initialPackageId)
            : undefined
          const firstPackage = requested ?? loaded.chapters[0] ?? loaded.book
          if (firstPackage) {
            setActivePackage(firstPackage.package_id)
            setActiveItem(firstPackage.items[0]?.item_id ?? '')
            api.outlineVersions(novelId, firstPackage.package_id).then((rows) => {
              if (!cancelled) setVersions(rows.versions)
            }).catch(() => undefined)
          }
          if (loaded.quality) setQuality(loaded.quality)
          const spec = loaded.book?.design_sections?.structure_spec ?? ''
          const [v, a, c] = spec.split('/').map((item) => Number(item))
          if (loaded.book && v && a && c) {
            setVolumes(v); setArcsPerVolume(a); setChaptersPerArc(c)
            return api.outlinePlan(novelId, { branch_id: initial, volumes: v,
              arcs_per_volume: a, chapters_per_arc: c }).then((preview) => {
              if (cancelled) return
              setChapters(preview.plan.chapters)
              setQuality(preview.quality)
            }).catch(() => undefined)
          }
          return undefined
        })
      })
      .catch((reason) => {
        if (cancelled) return
        const text = reason instanceof Error ? reason.message : String(reason)
        if (!text.includes('大纲')) setError(text)
      })
    return () => { cancelled = true }
  }, [novelId, initialBranchId, initialPackageId])

  // W6-05 深链接：带着 package_id / version 进入时，直接展示该版本的差异对比。
  useEffect(() => {
    const version = Number(initialVersion || 0)
    if (!initialPackageId || version <= 1 || !versions.length) return
    if (activePackage !== initialPackageId) return
    void diffAgainstPrevious(version)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [versions, activePackage, initialPackageId, initialVersion])

  useEffect(() => {
    if (chain?.book && !chain.fresh) {
      setMessage('已锻造的大纲与当前路线不一致（来源已变化），可以重新锻造生成新版本。')
    }
  }, [chain])

  const preview = async () => {
    setBusy(true); setError(''); setMessage('')
    try {
      const result = await api.outlinePlan(novelId, { branch_id: branchId, volumes,
        arcs_per_volume: arcsPerVolume, chapters_per_arc: chaptersPerArc })
      setChapters(result.plan.chapters)
      setQuality(result.quality)
      setMessage(`预览：${result.plan.volumes.length} 卷 / ${result.plan.arcs.length} 篇章 / `
        + `${result.plan.chapters.length} 章；质量问题 ${result.quality.findings.length} 条。`)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    } finally { setBusy(false) }
  }

  const forge = async () => {
    setBusy(true); setError(''); setMessage('')
    try {
      const result = await api.forgeOutline(novelId, { branch_id: branchId, volumes,
        arcs_per_volume: arcsPerVolume, chapters_per_arc: chaptersPerArc })
      setChapters(result.plan.chapters)
      setQuality(result.quality)
      const loaded = await api.outlineChain(novelId, branchId)
      setChain(loaded)
      setMessage(`已锻造 ${result.counts.volumes} 卷 / ${result.counts.arcs} 篇章 / `
        + `${result.counts.chapters} 章（已发生 ${result.counts.happened} 章，规划 `
        + `${result.counts.planned} 章）。`)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    } finally { setBusy(false) }
  }

  const confirmAll = async () => {
    setBusy(true); setError(''); setMessage('')
    try {
      const result = await api.confirmOutlineChain(novelId, branchId)
      setMessage(`已按顺序确认 ${result.count} 个大纲层（确认后历史不可改写，修改只会生成新版本）。`)
      setChain(await api.outlineChain(novelId, branchId))
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    } finally { setBusy(false) }
  }

  const exportMarkdown = async () => {
    setBusy(true); setError(''); setMessage('')
    try {
      const result = await api.outlineExport(novelId, branchId)
      setPreviewText(result.content)
      const blob = new Blob([result.content], { type: 'text/markdown;charset=utf-8' })
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = result.filename
      link.click()
      URL.revokeObjectURL(url)
      setMessage(`已导出 ${result.filename}（${result.content.length} 字）。`)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    } finally { setBusy(false) }
  }

  const loadPackage = async (packageId: string) => {
    setActivePackage(packageId); setVersionDiff([]); setImpact(null); setError('')
    const target = packageOptions.find((row) => row.package_id === packageId)
    setActiveItem(target?.items[0]?.item_id ?? '')
    try {
      const rows = await api.outlineVersions(novelId, packageId)
      setVersions(rows.versions)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    }
  }

  const diffAgainstPrevious = async (version: number) => {
    if (version <= 1) { setError('没有更早的版本可以比较'); return }
    setBusy(true); setError('')
    try {
      const rows = await api.outlineVersionDiff(novelId, activePackage, version - 1, version)
      setVersionDiff(rows.items)
      setMessage(`V${version - 1} → V${version}：${rows.items.length} 个条目有差异。`)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    } finally { setBusy(false) }
  }

  const restore = async (version: number) => {
    setBusy(true); setError('')
    try {
      const result = await api.restoreOutlineVersion(novelId, {
        package_id: activePackage, version })
      setMessage(`已按 V${result.restored_from} 生成新版本 V${result.outline.version}（旧版本保留）。`)
      setVersions((await api.outlineVersions(novelId, activePackage)).versions)
      setChain(await api.outlineChain(novelId, branchId))
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    } finally { setBusy(false) }
  }

  const mergeVersion = async (version: number) => {
    if (version <= 1) { setError('来源版本不合法'); return }
    setBusy(true); setError('')
    try {
      const result = await api.mergeOutlineVersions(novelId, {
        package_id: activePackage, base_version: version - 1, source_version: version,
        item_ids: activeItem ? [activeItem] : [],
      })
      setMessage(`已合并 V${version - 1} 与 V${version} 的选中条目，生成 V${result.outline.version}。`)
      setVersions((await api.outlineVersions(novelId, activePackage)).versions)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    } finally { setBusy(false) }
  }

  const saveItem = async () => {
    const target = packageOptions.find((row) => row.package_id === activePackage)
    if (!target || !activeItem) { setError('先选择要改写的条目'); return }
    setBusy(true); setError('')
    try {
      const current = impact ?? await api.outlineImpact(novelId, activePackage, activeItem,
        branchId)
      const result = await api.reviseOutlineItem(novelId, {
        package_id: activePackage, item_id: activeItem, expected_version: target.version,
        changes: { [editField]: editValue }, branch_id: branchId,
      })
      setImpact(result.impact)
      setVersions((await api.outlineVersions(novelId, activePackage)).versions)
      setChain(await api.outlineChain(novelId, branchId))
      setMessage(`已改写 ${activeItem}（新版本 V${result.outline.version}）；`
        + `下游受影响 ${result.impact.affected_downstream.length} 个包，`
        + `其中已发生事实 ${current.affected_happened.length} 条只提示不改写。`)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    } finally { setBusy(false) }
  }

  const exportAs = async (format: 'json' | 'docx') => {
    setBusy(true); setError('')
    try {
      const result = await api.outlineExportFormat(novelId, format, branchId)
      const blob = format === 'json'
        ? new Blob([result.content ?? ''], { type: 'application/json;charset=utf-8' })
        : new Blob([Uint8Array.from(atob(result.content_base64 ?? ''), (char) => char.charCodeAt(0))],
          { type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' })
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url; link.download = result.filename; link.click()
      URL.revokeObjectURL(url)
      setMessage(`已导出 ${result.filename}`)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    } finally { setBusy(false) }
  }

  return <section className="world-panel outline-forge-panel">
    <div className="world-panel-head">
      <div>
        <span className="story-builder-kicker">大纲锻造 · W3</span>
        <h3>从剧情路线生成全书主线 → 卷纲 → 篇章纲 → 详细章纲</h3>
      </div>
      <span className={`badge ${chain?.fresh ? 'pass' : ''}`}>
        {chain?.book ? (chain.fresh ? '来源一致' : '来源已变化') : '尚未锻造'}
      </span>
    </div>
    <p className="world-source">
      章纲字段来自 StoryState 事实与内容包（行动 / 事件 / 支线 / 伏笔 / 角色目标），
      已发生与规划严格分开；修改只生成新版本，不改写历史。
    </p>
    <div className="creative-inline">
      <label className="creative-field">路线分支
        <select aria-label="大纲分支" value={branchId}
          onChange={(event) => setBranchId(event.target.value)}>
          {branches.map((item) => <option key={item} value={item}>{item}</option>)}
        </select>
      </label>
      <label className="creative-field">卷数
        <input aria-label="卷数" type="number" min={1} max={12} value={volumes}
          onChange={(event) => setVolumes(Number(event.target.value) || 1)} />
      </label>
      <label className="creative-field">每卷篇章
        <input aria-label="每卷篇章" type="number" min={1} max={6} value={arcsPerVolume}
          onChange={(event) => setArcsPerVolume(Number(event.target.value) || 1)} />
      </label>
      <label className="creative-field">每篇章章数
        <input aria-label="每篇章章数" type="number" min={1} max={20} value={chaptersPerArc}
          onChange={(event) => setChaptersPerArc(Number(event.target.value) || 1)} />
      </label>
    </div>
    <div className="builder-actions">
      <button className="btn" disabled={busy} onClick={preview}>预览结构</button>
      <button className="btn primary" disabled={busy} onClick={forge}>锻造四级大纲</button>
      <button className="btn" disabled={busy || !chain?.book} onClick={confirmAll}>确认整条大纲</button>
      <button className="btn" disabled={busy || !chain?.book} onClick={exportMarkdown}>导出 Markdown</button>
      <button className="btn" disabled={busy || !chain?.book} onClick={() => exportAs('json')}>导出 JSON</button>
      <button className="btn" disabled={busy || !chain?.book} onClick={() => exportAs('docx')}>导出 DOCX</button>
    </div>
    {message && <div className="story-builder-message">{message}</div>}
    {error && <div className="story-builder-message error">{error}</div>}

    {quality && <article className="world-card">
      <div className="world-row-head">
        <h4>质量评估 · {quality.ok ? '通过' : '需要处理'}</h4>
        <span>章节 {quality.counts.chapters ?? 0} · 已发生 {quality.counts.happened ?? 0}
          · 规划 {quality.counts.planned ?? 0}</span>
      </div>
      <div className="world-list">
        {quality.findings.map((row) => <div className="world-row" key={`${row.code}-${row.target}`}>
          <b className={row.severity === 'error' ? 'world-note' : ''}>
            {row.severity === 'error' ? '阻塞' : '提示'} · {row.code}
          </b>
          <p>{row.message}{row.target ? `（${row.target}）` : ''}</p>
        </div>)}
        {!quality.findings.length && <div className="world-row"><p>没有问题：主线、支线、伏笔与节奏都有安排。</p></div>}
      </div>
    </article>}

    {chain?.book && <article className="world-card">
      <div className="world-row-head">
        <h4>全书主线</h4>
        <span>{chain.book.items[0]?.title}</span>
      </div>
      <p>{chain.book.items[0]?.summary}</p>
      <p>冲突：{chain.book.items[0]?.conflicts.join('；') || '—'}</p>
      <p>转折：{chain.book.items[0]?.major_turns.join('；') || '—'}</p>
      <p>收束：{chain.book.items[0]?.end_state || '—'}</p>
      <p>卷 {chain.volumes.length} · 篇章 {chain.arcs.length} · 章节 {chain.chapters.length}</p>
    </article>}

    {chain?.book && <article className="world-card">
      <div className="world-row-head">
        <h4>版本与联动 · W4</h4>
        <span>{packageOptions.length} 个大纲包</span>
      </div>
      <label className="creative-field">选择大纲包
        <select aria-label="版本大纲包" value={activePackage}
          onChange={(event) => loadPackage(event.target.value)}>
          {packageOptions.map((row) => <option key={row.package_id} value={row.package_id}>
            {row.level} · {row.items[0]?.title ?? row.package_id}</option>)}
        </select>
      </label>
      <div className="world-list">
        {versions.map((row) => <div className="world-row" key={row.version}>
          <div className="world-row-head">
            <b>V{row.version} · {row.status}</b>
            <span>{row.item_count} 条 · {row.created_at.slice(0, 19)}</span>
          </div>
          <div className="builder-actions">
            <button className="btn" disabled={busy} onClick={() => diffAgainstPrevious(row.version)}>
              与上一版对比
            </button>
            <button className="btn" disabled={busy} onClick={() => restore(row.version)}>
              回退到此版本
            </button>
            <button className="btn" disabled={busy} onClick={() => mergeVersion(row.version)}>
              合并选中条目到此版
            </button>
            {onDeepLink && <button className="btn"
              data-testid="outline-version-deeplink"
              onClick={() => onDeepLink({ tab: 'outline', package_id: activePackage,
                version: String(row.version) })}>
              去版本对比 / 影响分析
            </button>}
          </div>
        </div>)}
      </div>
      <div className="creative-inline">
        <label className="creative-field">要改写的条目
          <select aria-label="改写条目" value={activeItem}
            onChange={(event) => { setActiveItem(event.target.value); setImpact(null) }}>
            {(packageOptions.find((row) => row.package_id === activePackage)?.items ?? [])
              .map((item) => <option key={item.item_id} value={item.item_id}>{item.title}</option>)}
          </select>
        </label>
        <label className="creative-field">字段
          <select aria-label="改写字段" value={editField}
            onChange={(event) => setEditField(event.target.value as 'summary')}>
            <option value="summary">摘要</option>
            <option value="ending_hook">结尾钩子</option>
            <option value="title">标题</option>
          </select>
        </label>
        <label className="creative-field">新内容
          <input aria-label="改写内容" value={editValue}
            onChange={(event) => setEditValue(event.target.value)} />
        </label>
      </div>
      <div className="builder-actions">
        <button className="btn" disabled={busy || !activeItem} onClick={async () => {
          try {
            setImpact(await api.outlineImpact(novelId, activePackage, activeItem, branchId))
          } catch (reason) {
            setError(reason instanceof Error ? reason.message : String(reason))
          }
        }}>查看联动影响</button>
        <button className="btn primary" disabled={busy || !activeItem || !editValue.trim()}
          onClick={saveItem}>改写并查看影响</button>
      </div>
      {versionDiff.length > 0 && <div className="world-list">
        {versionDiff.map((row) => <div className="world-row" key={row.item_id}>
          <div className="world-row-head">
            <b>{row.item_id}</b><span>{row.status} · {row.changed_fields.join('、')}</span>
          </div>
          <p>{row.changed_fields.map((field) =>
            `${field}: ${JSON.stringify(row.before[field])} → ${JSON.stringify(row.after[field])}`)
            .join('；')}</p>
        </div>)}
      </div>}
      {impact && <div className="world-list">
        <div className="world-row">
          <b>下游受影响 {impact.affected_downstream.length} 个包</b>
          {impact.affected_downstream.map((row) => <p key={row.package_id}>
            {row.level} · {row.package_id.slice(-24)} · 状态 {row.status}</p>)}
        </div>
        <div className="world-row">
          <b>已发生事实 {impact.affected_happened.length} 条（只提示，不可改写）</b>
          {impact.affected_happened.slice(0, 5).map((row) => <p key={row.item_id}>{row.title}</p>)}
        </div>
        <div className="world-row">
          <b>规划内容 {impact.affected_planned.length} 条（重新锻造后更新）</b>
          {impact.affected_planned.slice(0, 5).map((row) => <p key={row.item_id}>{row.title}</p>)}
        </div>
      </div>}
    </article>}

    {chain?.volumes.map((volume) => <article className="world-card" key={volume.package_id}>
      <div className="world-row-head">
        <h4>{volume.items[0]?.title}</h4>
        <span>{volume.status}</span>
      </div>
      <p>{volume.items[0]?.summary}</p>
      <p>冲突：{volume.items[0]?.conflicts.join('；') || '—'}</p>
    </article>)}

    {chapters.length > 0 && <article className="world-card">
      <div className="world-row-head">
        <h4>详细章纲 · {chapters.length} 章</h4>
        <span>点开每章查看完整字段</span>
      </div>
      <div className="world-list">
        {chapters.map((row) => <details className="builder-config-details" key={row.id}>
          <summary>{row.title}（{KIND_LABELS[row.kind] ?? row.kind}）</summary>
          <div className="world-row">
            <p>本章目标：{row.goal}</p>
            <p>核心冲突：{row.conflict}</p>
            <p>转折：{row.turn || '—'}</p>
            <p>开场状态：{row.start_state || '—'}</p>
            <p>本章结果：{row.end_state || '—'}</p>
            <p>信息释放：{row.information_changes.join('；') || '—'}</p>
            <p>关系变化：{row.relationship_changes.join('；') || '—'}</p>
            <p>成长变化：{row.progression_changes.join('；') || '—'}</p>
            <p>支线动作：{row.plot_changes.join('；') || '—'}</p>
            <p>伏笔动作：{row.foreshadow_moves.join('；') || '—'}</p>
            <p>代价 / 风险：{row.costs.join('；') || '—'}</p>
            <p>结尾钩子：{row.hook || '—'}</p>
            <p>来源事实：{row.source_ids.join('、') || '（未来章节）'}</p>
            <p>不得违反：{row.must_avoid.join('；') || '—'}</p>
          </div>
        </details>)}
      </div>
    </article>}

    {previewText && <article className="world-card">
      <div className="world-row-head"><h4>导出预览</h4><span>{previewText.length} 字</span></div>
      <pre className="outline-export-preview">{previewText.slice(0, 4000)}</pre>
    </article>}
  </section>
}
