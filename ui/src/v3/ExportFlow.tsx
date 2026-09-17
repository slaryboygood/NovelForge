/*
 * V3 导出工作区：把作品真正交到写作环节。
 *
 * NF-001 / NF-002 的修复点：
 *   * 导出 CTA 不再跳到一个不存在的 legacy 页签，而是在这一屏内调用**既有**导出 API，
 *     生成真实的导出产物（文件名 + 内容 + 下载入口）；
 *   * 写作草稿在这里创建与查看，写入的是 writer store 的 canonical 路径——
 *     与 V3 投影读取路径同源，因此「已有写作草稿」这个目标真的能完成。
 *
 * 边界：本组件只做 UI 与 HTTP，不判断业务规则；导出与草稿都由后端产生。
 */
import { useCallback, useEffect, useMemo, useState } from 'react'
import Icon from './design-system/icons/IconRegistry'
import { Badge, Button, Card, SectionHeading } from './design-system/primitives'
import { v3Api, type ExportArtifactDto, type WriterDraftDto } from './api'
import type { CommandCenterViewModel } from './viewmodel'

type ExportFormat = 'markdown' | 'json' | 'docx'

const FORMATS: { format: ExportFormat; label: string; hint: string }[] = [
  { format: 'markdown', label: 'Markdown', hint: '给人读的大纲与事实' },
  { format: 'json', label: 'JSON', hint: '给工具读的结构化数据' },
  { format: 'docx', label: 'Word', hint: '可以直接打开编辑的文档' },
]

const PREVIEW_LIMIT = 4000

function text(reason: unknown): string {
  if (reason instanceof Error && reason.message) return reason.message
  return String(reason ?? '操作失败')
}

function download(filename: string, content: string | Blob) {
  const blob = content instanceof Blob
    ? content
    : new Blob([content], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}

function decodeBase64(payload: string): Blob {
  const binary = atob(payload)
  const bytes = new Uint8Array(binary.length)
  for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index)
  return new Blob([bytes], {
    type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  })
}

export default function ExportFlow({ novelId, model, onChanged, onOpenView }: {
  novelId: string
  model: CommandCenterViewModel
  onChanged: () => Promise<CommandCenterViewModel | null>
  onOpenView: (view: string) => void
}) {
  const exportView = model.exportView
  const [format, setFormat] = useState<ExportFormat>('markdown')
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [artifact, setArtifact] = useState<ExportArtifactDto | null>(null)
  const [drafts, setDrafts] = useState<WriterDraftDto[]>([])
  const [draftsError, setDraftsError] = useState('')
  const [notice, setNotice] = useState('')

  const loadDrafts = useCallback(async () => {
    try {
      const payload = await v3Api.writerDrafts(novelId)
      setDrafts(payload.drafts ?? [])
      setDraftsError('')
    } catch (reason) {
      setDraftsError(text(reason))
    }
  }, [novelId])

  useEffect(() => { void loadDrafts() }, [loadDrafts])

  const preview = useMemo(() => {
    const content = artifact?.artifact.content
    if (!content) return ''
    return content.length > PREVIEW_LIMIT
      ? `${content.slice(0, PREVIEW_LIMIT)}\n…（预览到这里，完整内容请下载）`
      : content
  }, [artifact])

  const generate = useCallback(async () => {
    setBusy('generate'); setError(''); setNotice('')
    try {
      const payload = await v3Api.exportPackage(novelId, format, model.simulation.branchId || 'main')
      setArtifact(payload)
      setNotice(`已经生成导出包：${payload.artifact.filename}`)
    } catch (reason) {
      setError(text(reason))
    } finally {
      setBusy('')
    }
  }, [format, model.simulation.branchId, novelId])

  const createDraft = useCallback(async () => {
    setBusy('draft'); setError(''); setNotice('')
    try {
      const payload = await v3Api.createWriterDraft(novelId, {
        branch_id: model.simulation.branchId || 'main',
      })
      const draftId = String(payload.draft_id ?? '')
      await loadDrafts()
      await onChanged()
      setNotice(draftId
        ? `已经创建写作草稿（${draftId}）。它属于 preview 层，不会改写已经发生的事实。`
        : '已经创建写作草稿。它属于 preview 层，不会改写已经发生的事实。')
    } catch (reason) {
      setError(text(reason))
    } finally {
      setBusy('')
    }
  }, [loadDrafts, model.simulation.branchId, novelId, onChanged])

  const blocker = exportView.blockers[0] ?? ''
  const firstMissing = exportView.missing[0]
  const onlyDraftsMissing = exportView.missing.length === 1
    && firstMissing?.stepId === 'writer_drafts'
  /**
   * 写作草稿属于 preview 层（不写事实），因此它只要求「起点事实已经落盘」，
   * 不被导出 blocker 挡住——否则作者会被一个与自己写作无关的问题卡住。
   */
  const canDraft = Boolean(model.facts.runtimeStarted)

  /**
   * 导出工作区唯一的 Primary CTA：
   *   已经就绪 → 生成导出包；只差写作草稿 → 直接创建草稿；
   *   有阻塞 → 指出阻塞；其它缺失 → 跳到缺的那一步。
   */
  const primary = exportView.ready
    ? { label: '生成导出包', testId: 'v3-export-open',
      run: () => { void generate() }, disabled: Boolean(busy) }
    : blocker
      ? { label: '先处理阻塞：大纲与冲突', testId: 'v3-export-primary',
        run: () => onOpenView(blocker.includes('大纲') ? 'outline' : 'review'),
        disabled: false }
      : onlyDraftsMissing
        ? { label: '创建写作草稿', testId: 'v3-export-primary',
          run: () => { void createDraft() }, disabled: Boolean(busy) }
        : firstMissing
          ? { label: `先补上：${firstMissing.label}`, testId: 'v3-export-primary',
            run: () => onOpenView(firstMissing.view), disabled: false }
          : { label: '生成导出包', testId: 'v3-export-open',
            run: () => { void generate() }, disabled: Boolean(busy) }

  return (
    <>
      <section className="v3-block" data-testid="v3-export-panel">
        <SectionHeading icon="export" title="生成导出包"
          hint="导出的是已经发生的事实、确认后的结构与你的大纲" />
        <div className="v3-flow-actions">
          <Button variant="primary" iconAfter="next_action"
            onClick={primary.run} disabled={primary.disabled}
            testId={primary.testId}>{busy === 'generate' ? '正在生成…' : primary.label}</Button>
          {FORMATS.map((row) => (
            <Button key={row.format} variant={format === row.format ? 'secondary' : 'ghost'}
              onClick={() => setFormat(row.format)}
              testId={`v3-export-format-${row.format}`}
              aria-pressed={format === row.format}>
              {row.label}
            </Button>
          ))}
        </div>
        <p className="v3-hint-line">
          <Icon name="export" size={16} />
          当前格式：{FORMATS.find((row) => row.format === format)?.hint}
        </p>
        {error ? <p className="v3-context-why" data-testid="v3-export-error">
          <Icon name="warning" size={15} />{error}
        </p> : null}
        {notice ? <p className="v3-hint-line" data-testid="v3-export-notice">
          <Icon name="complete" size={16} />{notice}
        </p> : null}
        {artifact ? (
          <div className="v3-export-artifact" data-testid="v3-export-artifact">
            <div className="v3-export-artifact-head">
              <b data-testid="v3-export-artifact-name">{artifact.artifact.filename}</b>
              <Badge tone="success" icon="complete">
                校验 {artifact.validation.status} · {artifact.validation.section_count} 个区块
              </Badge>
            </div>
            <p className="v3-export-artifact-meta">
              export_id：{artifact.artifact.export_id}
              {artifact.artifact.size ? ` · ${Math.round(artifact.artifact.size / 1024)} KB` : ''}
            </p>
            {preview ? (
              <pre className="v3-export-preview"
                data-testid="v3-export-artifact-preview">{preview}</pre>
            ) : null}
            <div className="v3-flow-actions">
              <Button variant="secondary" iconAfter="next_action"
                onClick={() => {
                  if (artifact.artifact.content !== undefined) {
                    download(artifact.artifact.filename, artifact.artifact.content)
                  } else if (artifact.artifact.content_base64) {
                    download(artifact.artifact.filename,
                      decodeBase64(artifact.artifact.content_base64))
                  }
                }}
                testId="v3-export-download">下载这个文件</Button>
            </div>
          </div>
        ) : (
          <Card tone="quiet" className="v3-block">
            <p className="v3-context-why">
              <Icon name="export" size={15} />
              还没有生成导出包：选好格式后点主按钮，这里会出现文件名与内容预览。
            </p>
          </Card>
        )}
      </section>

      <section className="v3-block" data-testid="v3-writer-drafts">
        <SectionHeading icon="chapter" title="写作草稿"
          hint="写作输出属于 preview 层：它是写作提议，不会改写已经发生的事实" />
        <div className="v3-flow-actions">
          <Button variant="secondary" iconAfter="next_action"
            onClick={() => { void createDraft() }} disabled={Boolean(busy) || !canDraft}
            testId="v3-writer-draft-create">
            {busy === 'draft' ? '正在创建…' : '创建写作草稿'}</Button>
        </div>
        {draftsError ? <p className="v3-context-why" data-testid="v3-writer-drafts-error">
          <Icon name="warning" size={15} />{draftsError}
        </p> : null}
        <ul className="v3-outline-children" data-testid="v3-writer-draft-list">
          {drafts.map((row) => (
            <li key={row.draft_id} data-testid={`v3-writer-draft-${row.draft_id}`}>
              <span>
                <b>{row.chapter_id || '整本书的开场草稿'}</b>
                <small>
                  草稿 {row.draft_id}
                  {row.accepted ? ' · 事实校验通过' : ' · 还有需要确认的声明'}
                  {row.synced ? ' · 已经生成事实提议' : ''}
                </small>
              </span>
            </li>
          ))}
          {!drafts.length ? (
            <li data-empty="true">
              <span>
                <b>还没有写作草稿</b>
                <small>{exportView.ready
                  ? '点上面的按钮创建第一份草稿，导出阶段就会完成。'
                  : canDraft
                    ? '起点事实已经落盘：可以创建第一份写作草稿（preview 层，不改写事实）。'
                    : '先让起点事实落盘，才能基于事实创建草稿。'}</small>
              </span>
            </li>
          ) : null}
        </ul>
      </section>
    </>
  )
}
