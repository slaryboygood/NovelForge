import { useState } from 'react'
import type { ReactNode } from 'react'

/**
 * W6-02：统一候选卡（标题 / 简述 / 适配理由 / 影响范围 / 来源 / 已选状态）。
 *
 * 同一组件复用于 W1-01 创意候选、W1-02 设定候选、十步目录与设计树节点；
 * 影响范围（W6-04）由调用方传入 API 返回的结构，组件不做任何业务推断。
 * 作者可以在卡内直接改写标题与简述（改写结果由调用方交回引擎保存）。
 */
export interface CandidateImpact {
  profile_fields?: string[]
  pack_sections?: string[]
  unlock_action_ids?: string[]
}

export interface CandidateCardProps {
  title: string
  summary?: string
  reason?: string
  source?: string
  selected?: boolean
  multi?: boolean
  disabled?: boolean
  impact?: CandidateImpact | null
  impactNote?: string
  /** 追加在根节点上的类名（保持既有面板的 CSS / 选择器兼容）。 */
  className?: string
  /** 单选语义（如设计树节点）：渲染 radio，无障碍名 = 候选标题。 */
  radio?: { name: string }
  /** 折叠区（如设计树的“开场例子 / 其他方向”）。 */
  extra?: ReactNode
  onToggle?: () => void
  onEdit?: (patch: { label?: string; summary?: string }) => void
  testId?: string
}

export default function CandidateCard({
  title, summary = '', reason = '', source = '', selected = false, multi = false,
  disabled = false, impact = null, impactNote = '', className = '', radio, extra,
  onToggle, onEdit, testId,
}: CandidateCardProps) {
  const [editing, setEditing] = useState(false)
  const [draftTitle, setDraftTitle] = useState(title)
  const [draftSummary, setDraftSummary] = useState(summary)

  const commit = () => {
    onEdit?.({ label: draftTitle.trim(), summary: draftSummary.trim() })
    setEditing(false)
  }

  const impactRows: Array<[string, string]> = []
  if (impact) {
    if (impact.profile_fields?.length) impactRows.push(['进入 NovelProfile', impact.profile_fields.join('、')])
    if (impact.pack_sections?.length) impactRows.push(['进入内容包', impact.pack_sections.join('、')])
    impactRows.push(['解锁候选行动',
      impact.unlock_action_ids?.length ? impact.unlock_action_ids.join('、') : '（保存设定后可见）'])
  }

  const body = <>
    {(editing ? draftSummary : summary) && <p>{editing ? draftSummary : summary}</p>}
    {reason && <p className="candidate-reason">适配理由：{reason}</p>}
    {impactRows.length > 0 && <dl className="candidate-impact">
      {impactRows.map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{value}</dd></div>)}
    </dl>}
    {impactNote && <p className="world-empty">{impactNote}</p>}
    {extra}
    {source && <p className="candidate-source">来源：{source}</p>}
  </>

  return <article
    className={`candidate-card ${className} ${selected ? 'selected' : ''} ${disabled ? 'disabled' : ''}`}
    data-testid={testId}
    aria-selected={selected}>
    {radio
      ? <div className="candidate-card-main">
        <div className="candidate-card-head">
          <label className="candidate-radio">
            <input type="radio" name={radio.name} checked={selected} disabled={disabled}
              onChange={() => onToggle?.()} />
            <b>{editing ? draftTitle : title}</b>
          </label>
          <span className={`badge ${selected ? 'pass' : ''}`}>{selected ? '已选' : '未选'}</span>
        </div>
        {body}
      </div>
      : <button type="button" className="candidate-card-main" disabled={disabled}
        onClick={() => onToggle?.()}>
        <div className="candidate-card-head">
          <b>{editing ? draftTitle : title}</b>
          <span className={`badge ${selected ? 'pass' : ''}`}>
            {selected ? '已选' : (multi ? '可选多个' : '未选')}
          </span>
        </div>
        {body}
      </button>}
    {editing
      ? <div className="candidate-card-edit">
        <label>标题<input aria-label="候选标题" value={draftTitle} maxLength={80}
          onChange={(event) => setDraftTitle(event.target.value)} /></label>
        <label>简述<textarea aria-label="候选简述" rows={2} maxLength={300} value={draftSummary}
          onChange={(event) => setDraftSummary(event.target.value)} /></label>
        <div className="builder-actions">
          <button type="button" className="btn primary" onClick={commit}>保存改写</button>
          <button type="button" className="btn" onClick={() => {
            setDraftTitle(title); setDraftSummary(summary); setEditing(false)
          }}>取消</button>
        </div>
      </div>
      : onEdit && <button type="button" className="candidate-card-edit-toggle"
        onClick={() => setEditing(true)}>改写这条候选</button>}
  </article>
}
