import { useState } from 'react'
import { api, StoryOutlinePackage } from './api'

const FIELDS = [
  ['title', '标题', false, 120], ['summary', '剧情概要', false, 4000], ['start_state', '起始状态', false, 2000],
  ['end_state', '结束状态', false, 2000], ['ending_hook', '下一场衔接', false, 1000],
  ['pov', '叙事视角', false, 500], ['time', '时间', false, 500], ['location', '地点', false, 500],
  ['participants', '出场人物', true, 2000], ['goals', '目标', true, 4000], ['conflicts', '冲突', true, 8000],
  ['major_turns', '转折', true, 8000], ['information_changes', '信息变化', true, 8000], ['costs', '代价', true, 4000],
] as const

export default function OutlineItemEditor({ outline, item, onSaved }: { outline: StoryOutlinePackage; item: StoryOutlinePackage['items'][number]; onSaved: () => Promise<void> }) {
  const [editing, setEditing] = useState(false)
  const [values, setValues] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  if (!editing) return <button className="btn" disabled={outline.status === 'NEEDS_REVIEW'} onClick={() => {
    setValues(Object.fromEntries(FIELDS.map(([key, , list]) => [key, list ? (item[key] as string[] || []).join('\n') : item[key] as string || ''])))
    setError(''); setEditing(true)
  }}>编辑此条</button>
  return <form className="outline-edit-form" onSubmit={async (event) => {
    event.preventDefault(); if (busy) return
    setBusy(true); setError('')
    try {
      const changes = Object.fromEntries(FIELDS.map(([key, , list]) => [key, list ? values[key].split('\n').map((line) => line.trim()).filter(Boolean) : values[key]]))
      await api.editOutline(outline.package_id, item.item_id, outline.version, changes)
      await onSaved(); setEditing(false)
    } catch (reason) { setError(String(reason)) }
    finally { setBusy(false) }
  }}>
    {FIELDS.map(([key, label, , max]) => <label key={key}>{label}<textarea aria-label={label} rows={key === 'summary' ? 5 : 2} maxLength={max} required={key === 'title' || key === 'summary'} disabled={busy} value={values[key] || ''} onChange={(event) => setValues({ ...values, [key]: event.target.value })} /></label>)}
    {error && <p role="alert" className="design-warning">{error}</p>}
    <button className="btn primary" disabled={busy} type="submit">{busy ? '正在保存…' : '保存为新版本'}</button>
    <button className="btn" disabled={busy} type="button" onClick={() => setEditing(false)}>取消</button>
  </form>
}
