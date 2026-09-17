import { useState } from 'react'
import { api, DesignNode, StoryBuilderSessionPayload } from './api'
import CandidateCard from './components/CandidateCard'

function NodeEditor({ node, disabled, choose }: { node: DesignNode; disabled: boolean; choose: (id?: string, text?: string) => void }) {
  const [custom, setCustom] = useState(node.selection?.custom_text || '')
  const [showAll, setShowAll] = useState(false)
  const chosen = node.options.find((item) => item.id === node.selection?.option_id)
  const sorted = [...node.options].sort((a, b) => Number(b.available) - Number(a.available) || Number(Boolean(b.recommendation)) - Number(Boolean(a.recommendation)))
  const visible = showAll ? sorted : sorted.filter((item, index) => index < 4 || item.id === chosen?.id)
  return <details className={`design-node ${node.needs_review ? 'needs-review' : ''}`} open={node.needs_review || (!node.selection && node.unlocked)}>
    <summary><b>{node.title}</b><span>{node.needs_review ? '待复核' : chosen?.name || node.selection?.custom_text || (node.unlocked ? '可选择' : '未解锁')}</span></summary>
    <p>{node.prompt}</p>
    {!node.unlocked && <p className="design-warning">{node.reason}</p>}
    {node.needs_review && <p className="design-warning">前置设定已变化。原选择仍保留，请重新选择或清除。</p>}
    <div className="design-options">{visible.map((option) => <CandidateCard
      key={option.id} className="design-option" testId="design-tree-option"
      title={option.name}
      summary={option.summary}
      reason={option.recommendation || (option.available ? '' : String(option.reason ?? ''))}
      source={`设计树 · ${node.title}`}
      selected={node.selection?.option_id === option.id}
      disabled={disabled || !option.available}
      radio={{ name: node.id }}
      impact={Object.keys(option.effects).length > 0 ? {
        profile_fields: Object.keys(option.effects),
        pack_sections: [],
      } : null}
      extra={option.examples.length > 0
        ? <details><summary>开场例子</summary>{option.examples.map((text, i) => <p key={i}>{text}</p>)}</details>
        : null}
      onToggle={() => choose(option.id)} />)}</div>
    {sorted.length > 4 && <button className="btn" onClick={() => setShowAll(!showAll)}>{showAll ? '收起其他方向' : `查看全部 ${sorted.length} 个方向`}</button>}
    <div className="design-custom"><label>自己的设定<input value={custom} maxLength={500} disabled={disabled || !node.unlocked} onChange={(event) => setCustom(event.target.value)} /></label><button className="btn" disabled={disabled || !node.unlocked || !custom.trim()} onClick={() => choose(undefined, custom)}>采用</button>{node.selection && <button className="btn" disabled={disabled} onClick={() => choose()}>清除选择</button>}</div>
  </details>
}

export default function DesignTreePanel({ payload, all, busy, onChange, onBusy, onFailure }: {
  payload: StoryBuilderSessionPayload; all: boolean; busy: boolean;
  onChange: (next: StoryBuilderSessionPayload) => void; onBusy: (value: boolean) => void; onFailure: (error: unknown) => Promise<void>;
}) {
  const [section, setSection] = useState('background')
  const groups = [{ id: 'reader_experience', title: '定位与主题' }, { id: 'worldview', title: '世界规则' }, { id: 'background', title: '生活背景' }, { id: 'protagonist', title: '主角' }, { id: 'core_characters', title: '同伴与对手' }, { id: 'factions_locations', title: '势力与场所' }, { id: 'major_events', title: '开篇、结局与长期规划' }, { id: 'progression', title: '能力与资源' }, { id: 'style', title: '叙事方式' }]
  const selectedSection = all ? section : payload.session.current_step
  const nodes = (payload.design_tree || []).filter((node) => node.step === selectedSection)
  if (!nodes.length && !all) return null
  const choose = async (field: string, option?: string, text = '') => {
    if (busy) return
    onBusy(true)
    try { onChange(await api.saveDesign(payload.session.session_id, field, payload.session.selection_version, option, text)) }
    catch (error) { await onFailure(error) }
    finally { onBusy(false) }
  }
  return <section className="design-tree"><h3>故事设计树</h3>
    {all && <div className="design-tabs" role="tablist" aria-label="设计分区">{groups.map((group) => {
      const members = payload.design_tree.filter((item) => item.step === group.id)
      const review = members.filter((item) => item.needs_review).length
      return <button className={`btn ${section === group.id ? 'primary' : ''}`} role="tab" aria-selected={section === group.id} key={group.id} onClick={() => setSection(group.id)}>{group.title} {review ? `待复核 ${review}` : `${members.filter((item) => item.selection).length}/${members.length}`}</button>
    })}</div>}
    {nodes.map((node) => <NodeEditor key={`${node.id}-${payload.session.selection_version}`} node={node} disabled={busy} choose={(option, text) => choose(node.id, option, text)} />)}
  </section>
}
