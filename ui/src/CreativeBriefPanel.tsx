import { useEffect, useState } from 'react'
import { api, CreativeBrief, CreativeSuggestionPayload, SettingImpactPayload } from './api'
import CandidateCard from './components/CandidateCard'

/**
 * W1-01 创意入口面板：一句创意 → 题材 / 基调 / 卖点候选 → 作者确认 → 保存 creative_brief。
 *
 * 只负责“这本小说想写什么”；世界 / 人物 / 势力 / 关系 / 成长 / 主线 / 伏笔的生成属于 W1-02。
 * 候选与理由全部来自 API，前端不自行推断题材，也不虚构模板或内容包。
 */
export default function CreativeBriefPanel({ novelId, compact = false, onChanged }: {
  novelId: string
  compact?: boolean
  onChanged?: () => void
}) {
  const [idea, setIdea] = useState('')
  const [reference, setReference] = useState('')
  const [readerExperience, setReaderExperience] = useState('')
  const [suggestion, setSuggestion] = useState<CreativeSuggestionPayload | null>(null)
  const [draft, setDraft] = useState<CreativeBrief | null>(null)
  const [saved, setSaved] = useState<CreativeBrief | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [impact, setImpact] = useState<SettingImpactPayload | null>(null)

  useEffect(() => {
    let cancelled = false
    setSuggestion(null); setDraft(null); setSaved(null); setMessage(''); setError('')
    api.creativeBrief(novelId)
      .then((state) => {
        if (cancelled) return
        setSaved(state.brief)
        if (state.suggestion) {
          setSuggestion(state.suggestion)
          setDraft(state.suggestion.selection)
          setIdea(state.suggestion.original_idea)
          setReaderExperience(state.suggestion.reader_experience)
          setReference(state.suggestion.references[0] ?? '')
        }
      })
      .catch((reason) => { if (!cancelled) setError(reason instanceof Error ? reason.message : String(reason)) })
    return () => { cancelled = true }
  }, [novelId])

  useEffect(() => {
    let cancelled = false
    api.settingsImpact(novelId)
      .then((payload) => { if (!cancelled) setImpact(payload) })
      .catch(() => { if (!cancelled) setImpact(null) })
    return () => { cancelled = true }
  }, [novelId])

  const request = async (regenerate = false) => {
    if (idea.trim().length < 4) { setError('请至少写一句完整的小说创意'); return }
    setBusy(true); setError(''); setMessage('')
    try {
      const payload = await api.creativeSuggest(novelId, {
        idea: idea.trim(),
        references: reference.trim() ? [reference.trim()] : [],
        reader_experience: readerExperience.trim(),
        selected_genre: draft?.selected_genre ?? '',
        regenerate,
      })
      setSuggestion(payload)
      setDraft(payload.selection)
      setMessage(regenerate ? '已重新生成候选。' : '已根据创意给出候选。')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    } finally { setBusy(false) }
  }

  const choose = (patch: Partial<CreativeBrief>) => {
    setDraft((current) => current ? { ...current, ...patch } : current)
  }

  const save = async () => {
    if (!draft) return
    setBusy(true); setError(''); setMessage('')
    try {
      const result = await api.saveCreativeBrief(novelId, {
        ...draft,
        original_idea: idea.trim(),
        references: reference.trim() ? [reference.trim()] : [],
        reader_experience: readerExperience.trim(),
      })
      setSaved(result.brief)
      setDraft(result.brief)
      setMessage('创意简报已保存（刷新后仍然保留）。')
      onChanged?.()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    } finally { setBusy(false) }
  }

  return <section className="creative-panel">
    <div className="world-panel-head">
      <div>
        <span className="story-builder-kicker">创意入口 · W1-01</span>
        <h3>先说清这本小说想写什么</h3>
      </div>
      <span className={`badge ${saved ? 'pass' : ''}`}>{saved ? '创意简报已保存' : '尚未保存'}</span>
    </div>
    {!compact && <p className="world-source">这一步只确定方向；世界、人物、势力、关系、成长、主线与伏笔在下一步生成。</p>}

    <label className="creative-field">一句话创意
      <textarea aria-label="一句话小说创意" rows={3} maxLength={1000} value={idea}
        onChange={(event) => setIdea(event.target.value)}
        placeholder="例如：一个普通维修工发现城市其实运行在一套隐藏的修仙操作系统上。" />
    </label>
    <div className="creative-inline">
      <label className="creative-field">参考作品（可选）
        <input aria-label="参考作品" value={reference} maxLength={120}
          onChange={(event) => setReference(event.target.value)} />
      </label>
      <label className="creative-field">想要的读者体验（可选）
        <input aria-label="读者体验" value={readerExperience} maxLength={200}
          onChange={(event) => setReaderExperience(event.target.value)} />
      </label>
    </div>
    <div className="builder-actions">
      <button className="btn primary" disabled={busy} onClick={() => request(false)}>{busy ? '正在生成…' : '生成方向候选'}</button>
      <button className="btn" disabled={busy || !suggestion} onClick={() => request(true)}>重新生成</button>
      <button className="btn" disabled={busy || !draft || !idea.trim()} onClick={save}>保存创意简报</button>
    </div>

    {suggestion && <>
      <article className="world-card">
        <h4>题材 / 方向候选 · {suggestion.genre_candidates.length}</h4>
        <div className="world-list candidate-grid" data-testid="creative-genre-candidates">
          {suggestion.genre_candidates.map((item) => <CandidateCard
            key={`${item.template_id}-${item.content_pack_id}`}
            testId="creative-genre-card"
            className="plot-candidate"
            title={item.label || item.genre || item.content_pack_id}
            summary={`模板：${item.template_id || '（暂无模板，先用内容包）'} · 内容包：${item.content_pack_id || '（未指定）'}`}
            reason={item.reason}
            source={`${item.template_id || 'template?'} / ${item.content_pack_id || 'pack?'}`}
            selected={draft?.selected_content_pack_id === item.content_pack_id
              && draft?.selected_template_id === item.template_id}
            impact={impact ? {
              profile_fields: ['selected_genre', 'selected_template_id', 'selected_content_pack_id'],
              pack_sections: ['meta'],
              unlock_action_ids: [],
            } : null}
            onToggle={() => choose({ selected_genre: item.genre, selected_template_id: item.template_id, selected_content_pack_id: item.content_pack_id })} />)}
        </div>
      </article>

      <article className="world-card">
        <h4>基调候选 · {suggestion.tone_candidates.length}</h4>
        <div className="world-list candidate-grid" data-testid="creative-tone-candidates">
          {suggestion.tone_candidates.map((item) => <CandidateCard
            key={item.tone}
            testId="creative-tone-card"
            className="plot-candidate"
            title={item.tone}
            reason={item.reason}
            source="creative/tone"
            selected={draft?.tone === item.tone}
            impact={impact ? { profile_fields: ['tone'], pack_sections: ['actions', 'events'] } : null}
            onToggle={() => choose({ tone: item.tone })} />)}
        </div>
      </article>

      <article className="world-card">
        <h4>核心卖点候选 · {suggestion.selling_point_candidates.length}</h4>
        <p className="world-empty">可多选；最终会写入创意简报。</p>
        <div className="world-list candidate-grid" data-testid="creative-selling-point-candidates">
          {suggestion.selling_point_candidates.map((item) => {
            const picked = draft?.selling_points?.includes(item.text) ?? false
            return <CandidateCard key={item.text} testId="creative-selling-point-card"
              className="plot-candidate"
              multi title={item.text} reason={item.reason} source="creative/selling_point"
              selected={picked}
              impact={impact ? { profile_fields: ['selling_points'], pack_sections: ['plots'] } : null}
              onToggle={() => choose({
                selling_points: picked
                  ? (draft?.selling_points ?? []).filter((text) => text !== item.text)
                  : [...(draft?.selling_points ?? []), item.text],
              })} />
          })}
        </div>
      </article>

      <article className="world-card">
        <h4>当前确认</h4>
        <dl>
          <div><dt>原始创意</dt><dd>{draft?.original_idea || idea}</dd></div>
          <div><dt>题材</dt><dd>{draft?.selected_genre || '未选择'}</dd></div>
          <div><dt>模板</dt><dd>{draft?.selected_template_id || '未选择'}</dd></div>
          <div><dt>内容包</dt><dd>{draft?.selected_content_pack_id || '未选择'}</dd></div>
          <div><dt>基调</dt><dd>{draft?.tone || '未选择'}</dd></div>
          <div><dt>卖点</dt><dd>{draft?.selling_points?.join('、') || '未选择'}</dd></div>
        </dl>
        {suggestion.source === 'rule' && <p className="world-empty">当前使用规则候选（AI 不可用时自动降级）。</p>}
        {suggestion.notes.length > 0 && <p className="world-note">{suggestion.notes.join('；')}</p>}
      </article>
    </>}

    {message && <p className="plot-goal">{message}</p>}
    {error && <div role="alert" className="story-builder-message error">{error}</div>}
  </section>
}
