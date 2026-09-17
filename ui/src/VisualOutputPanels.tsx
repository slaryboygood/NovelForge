import { useEffect, useMemo, useState } from 'react'
import { api } from './api'
import TruthLayerBadge from './components/TruthLayerBadge'
import { PanelState, useApiData } from './hooks/useApiData'

/** W6-10：两条分支差异并列高亮（信任 / 资源 / 知识 / 支线 / 伏笔）。 */
export function RouteComparePanel({ novelId, initialBranchId = '' }: {
  novelId: string; initialBranchId?: string
}) {
  const { data: branches, loading, error } = useApiData(
    () => api.runtimeBranches(novelId), [novelId])
  const ids = useMemo(() => (branches?.branches ?? []).map((row) => row.branch_id),
    [branches])
  const [base, setBase] = useState(initialBranchId || 'main')
  const [target, setTarget] = useState('')
  const [compare, setCompare] = useState<Awaited<
    ReturnType<typeof api.compareBranches>> | null>(null)
  const [busy, setBusy] = useState(false)
  const [compareError, setCompareError] = useState('')

  useEffect(() => {
    if (ids.length && !ids.includes(base)) setBase(ids[0])
    if (ids.length >= 2 && !ids.includes(target)) {
      setTarget(ids.find((id) => id !== (ids.includes(base) ? base : ids[0])) ?? '')
    }
  }, [ids, base, target])

  const run = async () => {
    if (!target) return
    setBusy(true); setCompareError('')
    try {
      setCompare(await api.compareBranches(novelId, base, target))
    } catch (reason) {
      setCompare(null)
      setCompareError(reason instanceof Error ? reason.message : String(reason))
    } finally { setBusy(false) }
  }

  return <section className="p1-panel" data-testid="route-compare-panel">
    <div className="world-panel-head">
      <div>
        <span className="story-builder-kicker">路线对比可视化 · W6-10</span>
        <h3>两条分支的差异并列显示</h3>
      </div>
      <TruthLayerBadge layer="comparison" />
    </div>
    <PanelState loading={loading} error={error} empty={ids.length === 0}
      emptyText="还没有分支：先开始推演或新建试演分支。" />
    <div className="creative-inline">
      <label className="creative-field">基准分支
        <select aria-label="基准分支" value={base} onChange={(event) => setBase(event.target.value)}>
          {ids.map((id) => <option key={id} value={id}>{id}</option>)}
        </select>
      </label>
      <label className="creative-field">对比分支
        <select aria-label="对比分支" value={target} onChange={(event) => setTarget(event.target.value)}>
          {ids.filter((id) => id !== base).map((id) => <option key={id} value={id}>{id}</option>)}
        </select>
      </label>
      <button type="button" className="btn primary" disabled={busy || !target} onClick={run}>
        {busy ? '正在对比…' : '对比差异'}
      </button>
    </div>
    {compareError && <div role="alert" className="story-builder-message error">{compareError}</div>}
    {compare && <div className="p1-compare" data-testid="route-compare-rows">
      <div className="p1-compare-head">
        <b>{compare.base_branch}</b><b>{compare.target_branch}</b>
      </div>
      {compare.rows.map((row) => <div className="p1-compare-row" key={`${row.kind}-${row.item_id}`}
        data-testid={`compare-row-${row.kind}`}
        data-changed={row.base === row.target ? 'false' : 'true'}
        data-conflict={row.conflict ? 'true' : 'false'}>
        <div className="p1-compare-cell base">
          <small>{row.kind}</small><span>{formatValue(row.base)}</span>
        </div>
        <div className="p1-compare-cell target">
          <small>{row.kind}</small><span>{formatValue(row.target)}</span>
        </div>
        <p>{row.label}{row.note ? ` · ${row.note}` : ''}</p>
      </div>)}
      {compare.conflicts.length > 0 && <p className="world-note">冲突：{compare.conflicts.join('、')}</p>}
    </div>}
  </section>
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

/** W6-11：BOOK → VOLUME → ARC → CHAPTER 折叠树（节奏 / 钩子标记）。 */
export function OutlineTreePanel({ novelId, initialBranchId = '' }: {
  novelId: string; initialBranchId?: string
}) {
  const { data, loading, error } = useApiData(
    () => api.outlineChain(novelId, initialBranchId || 'main'),
    [novelId, initialBranchId])
  const volumes = data?.volumes ?? []
  const arcs = data?.arcs ?? []
  const chapters = data?.chapters ?? []
  const pacing = (data?.quality?.pacing ?? []).slice(0, 2)
  return <section className="p1-panel" data-testid="outline-tree-panel">
    <div className="world-panel-head">
      <div>
        <span className="story-builder-kicker">大纲结构树 · W6-11</span>
        <h3>全书 → 卷 → 篇章 → 章节</h3>
      </div>
      <TruthLayerBadge layer="planned" />
    </div>
    <PanelState loading={loading} error={error} empty={!data?.book}
      emptyText="还没有大纲：先在大纲锻造里生成四级大纲。" />
    {data?.book && <details className="p1-tree" open data-testid="outline-tree-book">
      <summary><b>BOOK · {data.book.items[0]?.title ?? data.book.package_id}</b></summary>
      {volumes.map((volume) => <details className="p1-tree" key={volume.package_id}
        data-testid={`outline-tree-volume-${volume.package_id}`}>
        <summary><b>VOLUME · {volume.items[0]?.title ?? volume.package_id}</b></summary>
        {arcs.filter((arc) => arc.parent_package_id === volume.package_id)
          .map((arc) => <details className="p1-tree" key={arc.package_id}
            data-testid={`outline-tree-arc-${arc.package_id}`}>
            <summary><b>ARC · {arc.items[0]?.title ?? arc.package_id}</b></summary>
            {chapters.filter((chapter) => chapter.parent_package_id === arc.package_id)
              .map((chapter) => {
                const item = chapter.items[0]
                return <div className="p1-tree-leaf" key={chapter.package_id}
                  data-testid={`outline-tree-chapter-${chapter.package_id}`}>
                  <b>CHAPTER · {item?.title ?? chapter.package_id}</b>
                  <div className="p1-markers">
                    {pacing.map((tag) => <span key={tag}
                      className="p1-marker">节奏 {tag}</span>)}
                    {item?.ending_hook && <span className="p1-marker hook">
                      钩子：{item.ending_hook}</span>}
                    {(item?.major_turns ?? []).slice(0, 1).map((turn) =>
                      <span key={turn} className="p1-marker">转折：{turn}</span>)}
                  </div>
                </div>
              })}
          </details>)}
      </details>)}
    </details>}
  </section>
}

/** W6-12：风格与参考位（moodboard）；纯设计态，只存在浏览器本地，不写 StoryState。 */
export function MoodboardPanel({ novelId }: { novelId: string }) {
  const storageKey = `novelforge.moodboard.${novelId}`
  const [items, setItems] = useState<Array<{ id: string; text: string; image: string }>>([])
  const [text, setText] = useState('')
  const [image, setImage] = useState('')

  useEffect(() => {
    try {
      const raw = localStorage.getItem(storageKey)
      setItems(raw ? JSON.parse(raw) : [])
    } catch { setItems([]) }
  }, [storageKey])

  const persist = (next: Array<{ id: string; text: string; image: string }>) => {
    setItems(next)
    try { localStorage.setItem(storageKey, JSON.stringify(next)) } catch { /* 忽略 */ }
  }

  const add = () => {
    if (!text.trim() && !image.trim()) return
    persist([...items, { id: `mood_${items.length + 1}_${Date.now()}`, text: text.trim(), image: image.trim() }])
    setText(''); setImage('')
  }

  return <section className="p1-panel" data-testid="moodboard-panel">
    <div className="world-panel-head">
      <div>
        <span className="story-builder-kicker">风格与参考位 · W6-12</span>
        <h3>参考图 / 文字 mood（仅本地设计态）</h3>
      </div>
      <TruthLayerBadge layer="ui_derived" />
    </div>
    <p className="world-source">
      这些参考位只存在浏览器本地（localStorage），不进入 StoryState / Canon，也不会影响引擎判定。
    </p>
    <div className="creative-inline">
      <label className="creative-field">文字 mood
        <input aria-label="文字 mood" value={text} maxLength={200} data-testid="mood-text"
          onChange={(event) => setText(event.target.value)} placeholder="例如：冷、干燥、铁锈味" />
      </label>
      <label className="creative-field">本地图片引用（可选）
        <input aria-label="本地图片引用" value={image} maxLength={300} data-testid="mood-image"
          onChange={(event) => setImage(event.target.value)} placeholder="例如：assets/ref/wall.png" />
      </label>
      <button type="button" className="btn primary" onClick={add} data-testid="mood-add">加入参考位</button>
    </div>
    <PanelState loading={false} error="" empty={!items.length}
      emptyText="还没有参考位：写下 mood 或本地图片引用即可（只在本浏览器保存）。" />
    <div className="p1-card-grid">
      {items.map((item) => <article className="world-card" key={item.id}
        data-testid="mood-card">
        {item.image && <img className="p1-mood-image" src={item.image} alt={item.text || '参考图'} />}
        {item.text && <p>{item.text}</p>}
        <button type="button" className="btn"
          onClick={() => persist(items.filter((row) => row.id !== item.id))}>移除</button>
      </article>)}
    </div>
  </section>
}
