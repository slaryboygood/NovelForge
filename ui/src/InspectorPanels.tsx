import { useState } from 'react'
import { api } from './api'
import type { RepairIssue } from './api'
import type { InspectorRecordPayload } from './api'
import TruthLayerBadge from './components/TruthLayerBadge'
import ProvenanceList from './components/ProvenanceList'
import { PanelState, useApiData } from './hooks/useApiData'

/** M15-01：Canon 检查器（跨层只读检索 + 单条记录 provenance）。 */
export function CanonInspectorPanel({ novelId, initialRef = '', onDeepLink }: {
  novelId: string
  initialRef?: string
  onDeepLink?: (link: { tab: 'inspector' | 'tree'; step?: string }) => void
}) {
  const [query, setQuery] = useState('')
  const [layer, setLayer] = useState('')
  const [kind, setKind] = useState('')
  const [selected, setSelected] = useState(initialRef)
  const overview = useApiData(() => api.inspectorOverview(novelId), [novelId])
  const search = useApiData(
    () => api.inspectorSearch(novelId, { query, layer, record_kind: kind }),
    [novelId, query, layer, kind])
  const record = useApiData(
    () => (selected ? api.inspectorRecord(novelId, selected)
      : Promise.resolve<InspectorRecordPayload>({ novel_id: novelId, ref_id: '',
        found: false, read_only: true })),
    [novelId, selected])

  return <section className="p1-panel" data-testid="inspector-panel">
    <div className="world-panel-head">
      <div>
        <span className="story-builder-kicker">Canon 检查器 · M15-01</span>
        <h3>跨层只读检查：Canon / StoryState / 570 章历史 IR</h3>
      </div>
      <TruthLayerBadge layer="occurred" />
    </div>
    <PanelState loading={overview.loading} error={overview.error}
      empty={false} emptyText="" />
    {overview.data && <p className="world-source" data-testid="inspector-overview">
      Canon 事实 {overview.data.canon.fact_count} · 实体 {overview.data.canon.entity_count} ·
      StoryState 记录 {overview.data.story_state.record_count} · 历史 IR{' '}
      {overview.data.chapter_ir.chapter_count ?? 0} 章（index {overview.data.chapter_ir.index_digest}）
    </p>}
    <div className="creative-inline">
      <label className="creative-field">检索
        <input aria-label="检查器检索" data-testid="inspector-query" value={query}
          onChange={(event) => setQuery(event.target.value)} placeholder="章节 / 事实 / 实体关键字" />
      </label>
      <label className="creative-field">层
        <select aria-label="检查器层" value={layer} onChange={(event) => setLayer(event.target.value)}>
          <option value="">全部</option>
          {(overview.data?.layers ?? ['occurred', 'planned', 'historical_repair', 'ui_derived'])
            .map((item) => <option key={item} value={item}>{item}</option>)}
        </select>
      </label>
      <label className="creative-field">类型
        <select aria-label="检查器类型" value={kind} onChange={(event) => setKind(event.target.value)}>
          <option value="">全部</option>
          {(search.data?.kinds ?? []).map((item) => <option key={item} value={item}>{item}</option>)}
        </select>
      </label>
    </div>
    <PanelState loading={search.loading} error={search.error}
      empty={search.data?.total === 0} emptyText="没有匹配记录：换个关键字或清空筛选。" />
    <div className="p1-card-grid">
      {(search.data?.rows ?? []).slice(0, 12).map((row) => <article className="world-card"
        key={`${row.record_kind}:${row.ref_id}`}
        data-testid={`inspector-row-${row.record_kind}`}>
        <div className="world-row-head">
          <h4>{row.label || row.ref_id}</h4>
          <TruthLayerBadge layer={row.truth_layer} />
        </div>
        <p className="world-source">{row.record_kind} · {row.ref_id}</p>
        <p>{row.summary}</p>
        <div className="builder-actions">
          <button type="button" className="btn"
            onClick={() => setSelected(row.ref_id)}>看出处</button>
        </div>
      </article>)}
    </div>
    {record.data?.found && <article className="world-card" data-testid="inspector-record">
      <div className="world-row-head">
        <h4>记录 {record.data.ref_id}</h4>
        <TruthLayerBadge layer={record.data.truth_layer ?? 'occurred'} />
      </div>
      <ProvenanceList rows={record.data.provenance ?? []}
        testId="inspector-provenance" />
      {record.data.record?.record_kind === 'chapter_ir' && onDeepLink &&
        <button type="button" className="btn"
          onClick={() => onDeepLink({ tab: 'tree', step: record.data?.ref_id })}>
          去大纲结构树看这一章
        </button>}
    </article>}
  </section>
}

/** M15-02：修复中心（诊断 → 预览 → 审批要求 → 执行既有 API → 结果可追踪）。 */
export function RepairCenterPanel({ novelId, onDeepLink }: {
  novelId: string
  onDeepLink?: (link: { tab: 'outline' | 'world' | 'builder'; step?: string }) => void
}) {
  const diagnosis = useApiData(() => api.repairDiagnosis(novelId), [novelId])
  const history = useApiData(() => api.repairHistory(novelId), [novelId])
  const [busy, setBusy] = useState('')
  const [result, setResult] = useState<{ issue: string; text: string } | null>(null)

  const execute = async (issue: RepairIssue) => {
    setBusy(issue.issue_id); setResult(null)
    try {
      if (issue.execution_api === 'settings/check') {
        const report = await api.runSettingsCheck(novelId, { repair: true })
        setResult({ issue: issue.issue_id,
                    text: `已修补 ${report.applied_fixes.length} 项；自检 ${report.ok ? '通过' : '仍有问题'}` })
        await diagnosis.reload()
      } else {
        setResult({ issue: issue.issue_id,
                    text: '该项需要在大纲/世界面板由作者确认（本面板不代写）' })
        onDeepLink?.({ tab: 'outline' })
      }
    } catch (reason) {
      setResult({ issue: issue.issue_id,
                  text: `执行失败：${reason instanceof Error ? reason.message : String(reason)}` })
    } finally { setBusy('') }
  }

  return <section className="p1-panel" data-testid="repair-panel">
    <div className="world-panel-head">
      <div>
        <span className="story-builder-kicker">修复中心 · M15-02</span>
        <h3>诊断 → 预览 → 审批要求 → 执行 → 结果</h3>
      </div>
      <TruthLayerBadge layer="planned" />
    </div>
    <p className="world-source" data-testid="repair-boundary">
      {diagnosis.data?.execution_boundary ?? '只调用既有 API；不直接写 Canon / StoryState'}
    </p>
    <PanelState loading={diagnosis.loading} error={diagnosis.error}
      empty={diagnosis.data?.issue_count === 0} emptyText="当前没有可诊断的问题。" />
    <div className="p1-card-grid">
      {(diagnosis.data?.issues ?? []).map((issue) => <article className="world-card"
        key={issue.issue_id} data-testid={`repair-issue-${issue.source}`}
        data-requires-approval={issue.requires_approval ? 'true' : 'false'}>
        <div className="world-row-head">
          <h4>{issue.message || issue.issue_id}</h4>
          <span>{issue.severity === 'error' ? '阻塞' : '提示'}</span>
        </div>
        <dl>
          <div><dt>改什么</dt><dd>{issue.target || '—'}</dd></div>
          <div><dt>建议动作</dt><dd>{issue.proposed_action}</dd></div>
          <div><dt>影响</dt><dd>{Object.entries(issue.impact).map(([k, v]) =>
            `${k}=${Array.isArray(v) ? v.length : String(v)}`).join(' · ') || '—'}</dd></div>
          <div><dt>审批要求</dt><dd>{issue.requires_approval
            ? `需要作者确认（${issue.approval_note}）` : '系统兜底修复（无需作者确认）'}</dd></div>
          <div><dt>可回溯</dt><dd>settings/check 结果 + 修复历史 effect log</dd></div>
        </dl>
        <p className="world-source">证据（provenance）</p>
        <ProvenanceList rows={issue.evidence.map((ref) => ({ ref, kind: 'evidence' }))}
          testId={`repair-evidence-${issue.source}`} />
        <div className="builder-actions">
          <button type="button" className="btn primary"
            data-testid={`repair-execute-${issue.source}`}
            disabled={Boolean(busy)} onClick={() => execute(issue)}>
            {busy === issue.issue_id ? '正在执行…'
              : issue.execution_api === 'settings/check' ? '执行兜底修复' : '去对应面板处理'}
          </button>
        </div>
      </article>)}
    </div>
    {result && <p className="plot-goal" data-testid="repair-result">
      {result.issue}：{result.text}
    </p>}
    <article className="world-card" data-testid="repair-history">
      <h4>修复 / 事实变更历史（effect log）</h4>
      <PanelState loading={history.loading} error={history.error}
        empty={!history.data?.effect_log.length} emptyText="还没有事实变更记录。" />
      <ul className="p1-list">
        {(history.data?.effect_log ?? []).slice(0, 10).map((row) => <li
          key={`${row.order}-${row.target}`}>
          <b>{row.op} · {row.target}</b>
          <span>{row.source}</span><small>order {row.order}</small>
        </li>)}
      </ul>
    </article>
  </section>
}
