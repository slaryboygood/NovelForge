/*
 * 节点编辑器（drawer）—— V4-06 契约的 UI 侧。
 *
 * 只提交 field-level patch + expected_revision（§29）；
 * AI 改写先 dry-run 预览 → 展示 before/after → 应用 / 放弃（§32–§33）；
 * 接受 / 拒绝是作者决定，与质量 PASS 完全分离（§34）。
 * 冲突：显示「我的版本 / 当前版本 / 差异」，不自动覆盖（§59）。
 */
import { useCallback, useEffect, useState } from 'react'
import Icon from '../v3/design-system/icons/IconRegistry'
import { Button, Card, Disclosure, LoadingState } from '../v3/design-system/primitives'
import {
  studioApi, type DiffDto, type EditorNodeDto, type RevisionHistoryDto,
  type RewriteResultDto,
} from '../api/studio'
import {
  displayValue, fieldLabel, isMultilineField, nodeTitle, nodeTypeLabel,
} from './design/fields'
import { mapError, isConflict } from './design/errors'
import { StatusBadge, reviewStatusKey } from './design/status'
import { DiffView, Drawer, IssueCard } from './components'

export function NodeDrawer({ open, novelId, nodeId, onClose, onChanged, notify }: {
  open: boolean
  novelId: string
  nodeId: string
  onClose: () => void
  onChanged: (message: string) => void
  notify: (tone: 'success' | 'warning' | 'error' | 'info', message: string) => void
}) {
  const [node, setNode] = useState<EditorNodeDto | null>(null)
  const [history, setHistory] = useState<RevisionHistoryDto | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [draft, setDraft] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState('')
  const [diff, setDiff] = useState<DiffDto | null>(null)
  const [conflict, setConflict] = useState<DiffDto | null>(null)
  const [rewriteFields, setRewriteFields] = useState<string[]>([])
  const [instruction, setInstruction] = useState('')
  const [rewritePreview, setRewritePreview] = useState<RewriteResultDto | null>(null)

  const load = useCallback(async () => {
    if (!open || !nodeId) return
    setLoading(true)
    setError('')
    try {
      const [nodePayload, historyPayload] = await Promise.all([
        studioApi.node(novelId, nodeId),
        studioApi.history(novelId, nodeId).catch(() => null),
      ])
      setNode(nodePayload)
      setHistory(historyPayload)
      setDraft(draftFrom(nodePayload))
    } catch (reason) {
      setNode(null)
      setError(mapError(reason).message)
    } finally {
      setLoading(false)
    }
  }, [open, novelId, nodeId])

  // 切换节点 / 重新打开时清空上一次的 diff 与冲突状态（load 本身保持幂等，不吞掉刚生成的 diff）
  useEffect(() => {
    setDiff(null)
    setConflict(null)
    setRewritePreview(null)
    setInstruction('')
  }, [open, nodeId])

  useEffect(() => { void load() }, [load])

  const currentRevision = node?.view.revision ?? 0
  const changedFields = Object.keys(draft).filter((field) => {
    const before = displayValue(payloadOf(node)[field])
    return draft[field] !== before
  })

  async function save() {
    if (!node || changedFields.length === 0) return
    setBusy('save')
    try {
      const changes: Record<string, unknown> = {}
      for (const field of changedFields) changes[field] = coerce(draft[field], node, field)
      const result = await studioApi.patch(novelId, nodeId, {
        changes, expected_revision: currentRevision, reason: '作者手动修改',
      })
      setConflict(null)
      setDiff(result.diff ?? null)
      notify('success', `已保存新版本（r${result.revision}）`)
      onChanged(`已保存新版本（r${result.revision}）`)
      await load()
    } catch (reason) {
      const info = mapError(reason)
      if (isConflict(reason)) {
        notify('warning', info.message)
        await openConflict()
      } else {
        notify('error', info.message)
      }
    } finally {
      setBusy('')
    }
  }

  async function openConflict() {
    if (!currentRevision) return
    try {
      const latest = await studioApi.diff(novelId, nodeId, currentRevision)
      setConflict(latest)
      setDiff(latest)
    } catch {
      setConflict(null)
    }
  }

  async function runRewrite(dryRun: boolean) {
    if (!node || rewriteFields.length === 0 || !instruction.trim()) return
    setBusy(dryRun ? 'preview' : 'apply')
    try {
      const result = await studioApi.rewrite(novelId, nodeId, {
        target_fields: rewriteFields,
        instruction: instruction.trim(),
        expected_revision: currentRevision,
        dry_run: dryRun,
      })
      if (dryRun) {
        setRewritePreview(result)
        setDiff(result.diff ?? null)
        notify('info', '已生成改写预览（尚未写入）')
      } else {
        setRewritePreview(null)
        setInstruction('')
        setDiff(result.diff ?? null)
        notify('success', `已生成待审核的新版本（r${result.revision}）`)
        onChanged('AI 改写已生成待审核版本')
        await load()
      }
    } catch (reason) {
      notify('error', mapError(reason).message)
    } finally {
      setBusy('')
    }
  }

  async function decide(decision: 'accept' | 'reject') {
    setBusy(decision)
    try {
      const result = decision === 'accept'
        ? await studioApi.accept(novelId, nodeId, { revision: currentRevision })
        : await studioApi.reject(novelId, nodeId, { revision: currentRevision })
      notify('success', decision === 'accept'
        ? '已接受这个版本（质量通过与否是另一件事）'
        : '已记录拒绝决定')
      onChanged(decision === 'accept' ? '已接受版本' : '已拒绝版本')
      await load()
      void result
    } catch (reason) {
      notify('error', mapError(reason).message)
    } finally {
      setBusy('')
    }
  }

  async function showDiff(fromRevision: number) {
    setBusy('diff')
    try {
      setDiff(await studioApi.diff(novelId, nodeId, fromRevision))
    } catch (reason) {
      notify('error', mapError(reason).message)
    } finally {
      setBusy('')
    }
  }

  async function restore(fromRevision: number) {
    setBusy('restore')
    try {
      const result = await studioApi.restore(novelId, nodeId, {
        from_revision: fromRevision, reason: `恢复到 r${fromRevision}`,
      })
      notify('success', `已恢复 r${fromRevision} 的内容（新版本 r${result.revision}，历史未删除）`)
      onChanged('已恢复旧版本内容')
      await load()
    } catch (reason) {
      notify('error', mapError(reason).message)
    } finally {
      setBusy('')
    }
  }

  const payload = payloadOf(node)
  const editable = node?.editable_fields ?? []
  const issues = (node?.quality?.issues ?? []) as Parameters<typeof IssueCard>[0]['issue'][]

  return (
    <Drawer open={open} title={node ? nodeTitle(node.node) : '内容'}
      subtitle={node ? `${nodeTypeLabel(node.node.node_type)} · 版本 r${currentRevision}`
        : undefined}
      onClose={onClose} testId="node-drawer"
      footer={node ? (
        <div className="studio-drawer-actions">
          <Button variant="secondary" icon="close" onClick={() => decide('reject')}
            disabled={Boolean(busy)} testId="reject-node">拒绝</Button>
          <Button variant="primary" icon="complete" onClick={() => decide('accept')}
            disabled={Boolean(busy)} testId="accept-node">接受</Button>
        </div>
      ) : null}>
      {loading ? <LoadingState label="正在读取这条内容…" /> : null}
      {error ? <p className="studio-error-inline" role="alert">{error}</p> : null}

      {node ? (
        <div className="studio-drawer-content">
          <div className="studio-drawer-status">
            <StatusBadge status={String(node.node.status)} testId="node-status" />
            <StatusBadge status={String(node.view.quality_status || 'unevaluated')} />
            <StatusBadge status={reviewStatusKey(node.view.review_status || '')} />
          </div>

          {conflict ? (
            <Card tone="quiet" className="studio-conflict" testId="conflict-panel">
              <h3><Icon name="conflict" size={18} /> 内容已被更新</h3>
              <p>后台已经有更新的版本（r{conflict.revision_after}）。
                这是你的修改与当前版本的差异：</p>
              <div className="studio-conflict-actions">
                <Button variant="secondary" size="sm" onClick={() => void load()}
                  testId="conflict-reload">查看最新版本</Button>
                <Button variant="secondary" size="sm"
                  onClick={() => {
                    void navigator.clipboard?.writeText(JSON.stringify(draft))
                    notify('info', '已复制你的修改到剪贴板')
                  }}>复制我的修改</Button>
                <Button variant="ghost" size="sm" onClick={() => setConflict(null)}>
                  重新编辑
                </Button>
              </div>
            </Card>
          ) : null}

          {diff ? (
            <Card tone="quiet" className="studio-diff-card">
              <DiffView diff={diff} />
            </Card>
          ) : null}

          <section className="studio-edit">
            <h3>内容</h3>
            {editable.length === 0 ? (
              <p className="studio-muted">这条内容没有可编辑字段。</p>
            ) : (
              editable.map((field) => (
                <label key={field} className="studio-field">
                  <span>{fieldLabel(node.node.node_type, field)}</span>
                  {isMultilineField(node.node.node_type, field) ? (
                    <textarea rows={3} value={draft[field] ?? ''}
                      onChange={(event) => setDraft({ ...draft,
                        [field]: event.target.value })} />
                  ) : (
                    <input type="text" value={draft[field] ?? ''}
                      onChange={(event) => setDraft({ ...draft,
                        [field]: event.target.value })} />
                  )}
                </label>
              ))
            )}
            <div className="studio-edit-actions">
              <Button variant="primary" icon="complete"
                disabled={changedFields.length === 0 || Boolean(busy)}
                onClick={() => void save()} testId="save-node">
                {busy === 'save' ? '保存中…'
                  : changedFields.length > 0 ? `保存修改（${changedFields.length} 处）`
                    : '保存修改'}
              </Button>
              <span className="studio-muted">保存会创建一个新版本，历史不会删除。</span>
            </div>
          </section>

          <section className="studio-edit">
            <h3>AI 改写</h3>
            <p className="studio-muted">选择要改写的字段，并说明你的要求。</p>
            <div className="studio-chip-row">
              {editable.map((field) => {
                const active = rewriteFields.includes(field)
                return (
                  <button key={field} type="button"
                    className={`studio-chip ${active ? 'is-active' : ''}`}
                    aria-pressed={active}
                    onClick={() => setRewriteFields(active
                      ? rewriteFields.filter((row) => row !== field)
                      : [...rewriteFields, field])}>
                    {fieldLabel(node.node.node_type, field)}
                  </button>
                )
              })}
            </div>
            <label className="studio-field">
              <span>改写要求</span>
              <textarea rows={2} value={instruction}
                placeholder="例如：让冲突更尖锐，但不要改人物的核心目标"
                onChange={(event) => setInstruction(event.target.value)} />
            </label>
            <div className="studio-edit-actions">
              <Button variant="secondary" icon="creation"
                disabled={rewriteFields.length === 0 || !instruction.trim()
                  || Boolean(busy)}
                onClick={() => void runRewrite(true)} testId="rewrite-preview">
                生成改写预览
              </Button>
              {rewritePreview ? (
                <Button variant="primary" icon="complete"
                  disabled={Boolean(busy)} onClick={() => void runRewrite(false)}
                  testId="rewrite-apply">
                  应用这次改写（创建新版本）
                </Button>
              ) : null}
            </div>
          </section>

          {issues.length > 0 ? (
            <section className="studio-edit">
              <h3>这条内容的问题</h3>
              <div className="studio-issue-list">
                {issues.map((issue) => <IssueCard key={issue.issue_id} issue={issue} />)}
              </div>
            </section>
          ) : null}

          <Disclosure summary={`版本历史（${history?.revision_count ?? 0} 个版本）`}
            testId="revision-history">
            {history ? (
              <ul className="studio-history">
                {history.revisions.map((row) => (
                  <li key={row.revision} className="studio-history-row">
                    <div>
                      <b>r{row.revision}</b> <StatusBadge status={String(row.status)} />
                      <p className="studio-meta">
                        {row.author || '系统'} · {row.operation || '生成'} ·{' '}
                        {formatTime(row.created_at)}
                      </p>
                      {row.changed_fields?.length ? (
                        <p className="studio-meta">
                          改动字段：{row.changed_fields
                            .map((field) => fieldLabel(node.node.node_type, field))
                            .join('、')}
                        </p>
                      ) : null}
                    </div>
                    <div className="studio-history-actions">
                      <Button variant="ghost" size="sm"
                        onClick={() => void showDiff(row.revision)}>差异</Button>
                      {row.revision !== currentRevision ? (
                        <Button variant="secondary" size="sm"
                          onClick={() => void restore(row.revision)}>恢复此版本</Button>
                      ) : null}
                    </div>
                  </li>
                ))}
              </ul>
            ) : <p className="studio-muted">没有历史记录。</p>}
          </Disclosure>

          <Disclosure summary="原始字段（诊断）" testId="node-raw">
            <pre className="studio-raw">{JSON.stringify(payload, null, 2)}</pre>
          </Disclosure>
        </div>
      ) : null}
    </Drawer>
  )
}

function payloadOf(node: EditorNodeDto | null): Record<string, unknown> {
  if (!node) return {}
  return { ...(node.node.payload ?? {}), ...(node.node.visible ?? {}) }
}

function draftFrom(node: EditorNodeDto): Record<string, string> {
  const payload = payloadOf(node)
  const draft: Record<string, string> = {}
  for (const field of node.editable_fields) draft[field] = displayValue(payload[field])
  return draft
}

/** 输入框文本 → 字段值（列表字段按「、」拆成数组；不猜测业务的字段保持字符串）。 */
function coerce(text: string, node: EditorNodeDto, field: string): unknown {
  const before = payloadOf(node)[field]
  if (Array.isArray(before)) {
    return text.split(/[、,]/).map((row) => row.trim()).filter(Boolean)
  }
  return text
}

function formatTime(value?: string): string {
  if (!value) return '未知时间'
  const text = String(value)
  const match = text.match(/^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2})/)
  return match ? `${match[1]} ${match[2]}` : text
}

export { nodeTypeLabel }
