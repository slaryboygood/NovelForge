/*
 * Delivery（§45–§48）。
 *
 * 选择（accepted / current）→ preflight → 交付 → manifest → 下载。
 * 格式列表来自 backend registry（含插件 exporter，§55）；blocked 时不提供正式下载。
 */
import { useEffect, useState } from 'react'
import {
  deliveryArtifactUrl, type DeliveryFormatsDto, type DeliveryPreflightDto,
  type DeliverySnapshotRow,
} from '../../api/studio'
import { Button, Card, Disclosure, SectionHeading } from '../../v3/design-system/primitives'
import Icon from '../../v3/design-system/icons/IconRegistry'
import { StatusBadge } from '../design/status'
import { mapError } from '../design/errors'

export function Delivery({ novelId, formats, snapshots, onDeliver, onRefresh, busy }: {
  novelId: string
  formats: DeliveryFormatsDto | null
  snapshots: DeliverySnapshotRow[]
  onDeliver: (body: {
    selection_mode: string
    formats: string[]
    require_accepted: boolean
    require_quality_pass: boolean
  }) => Promise<DeliveryPreflightDto>
  onRefresh: () => void
  busy: string
}) {
  const [selectionMode, setSelectionMode] = useState('accepted')
  const [chosen, setChosen] = useState<string[]>([])
  const [requireAccepted, setRequireAccepted] = useState(true)
  const [requireQuality, setRequireQuality] = useState(true)
  const [result, setResult] = useState<DeliveryPreflightDto | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!formats) return
    setChosen((current) => (current.length > 0 ? current
      : formats.default_formats.filter((fmt) => formats.format_ids.includes(fmt))))
  }, [formats])

  const blocked = result ? result.status !== 'delivered' : false
  const available = formats?.formats ?? []

  return (
    <section className="studio-workspace" data-testid="workspace-delivery">
      <SectionHeading icon="export" title="交付"
        hint="把已接受、检查通过的版本导出为正式文件"
        action={<Button variant="ghost" icon="back" onClick={onRefresh}>刷新</Button>} />

      <div className="studio-grid studio-grid-2">
        <Card tone="elevated">
          <header className="studio-tile-head"><Icon name="objective" size={20} />
            <h2>1. 选择交付内容</h2></header>
          <div className="studio-radio-row" role="radiogroup" aria-label="交付依据">
            <label className="studio-radio">
              <input type="radio" name="selection-mode" value="accepted"
                checked={selectionMode === 'accepted'}
                onChange={() => setSelectionMode('accepted')} />
              <span>已接受版本（推荐）</span>
            </label>
            <label className="studio-radio">
              <input type="radio" name="selection-mode" value="current"
                checked={selectionMode === 'current'}
                onChange={() => setSelectionMode('current')} />
              <span>当前工作版本（可能包含未接受内容）</span>
            </label>
          </div>
          <label className="studio-toggle">
            <input type="checkbox" checked={requireAccepted}
              onChange={(event) => setRequireAccepted(event.target.checked)} />
            <span>要求所有节点都已接受</span>
          </label>
          <label className="studio-toggle">
            <input type="checkbox" checked={requireQuality}
              onChange={(event) => setRequireQuality(event.target.checked)} />
            <span>要求质量检查针对当前版本通过</span>
          </label>
        </Card>

        <Card tone="elevated">
          <header className="studio-tile-head"><Icon name="export" size={20} />
            <h2>2. 选择格式</h2></header>
          {available.length === 0 ? (
            <p className="studio-muted">读取不到可用格式。</p>
          ) : (
            <ul className="studio-format-list">
              {available.map((row) => {
                const active = chosen.includes(row.format)
                return (
                  <li key={row.format}>
                    <button type="button"
                      className={`studio-chip ${active ? 'is-active' : ''}`}
                      aria-pressed={active}
                      onClick={() => setChosen(active
                        ? chosen.filter((fmt) => fmt !== row.format)
                        : [...chosen, row.format])}
                      data-testid={`format-${row.format}`}>
                      <b>{row.format.toUpperCase()}</b>
                      <span>{row.text === false ? '二进制' : '文本'}</span>
                      <span className="studio-meta">
                        {row.owner_type === 'plugin' ? `插件：${row.owner_id}` : '内建'}
                      </span>
                    </button>
                  </li>
                )
              })}
            </ul>
          )}
          <p className="studio-meta">
            列表来自后端 exporter registry：插件提供的格式会自动出现在这里。
          </p>
        </Card>
      </div>

      <Card tone="elevated" className="studio-delivery-run">
        <header className="studio-tile-head"><Icon name="complete" size={20} />
          <h2>3. 交付</h2></header>
        <div className="studio-edit-actions">
          <Button variant="primary" icon="export" disabled={chosen.length === 0
            || Boolean(busy)}
            onClick={async () => {
              setError('')
              try {
                setResult(await onDeliver({
                  selection_mode: selectionMode,
                  formats: chosen,
                  require_accepted: requireAccepted,
                  require_quality_pass: requireQuality,
                }))
              } catch (reason) {
                setError(mapError(reason).message)
              }
            }}
            testId="deliver-submit">
            {busy === 'deliver' ? '交付中…' : '开始交付'}
          </Button>
          <span className="studio-muted">
            交付不调用模型、不修改内容；被阻止时不会发布任何文件。
          </span>
        </div>
        {error ? <p className="studio-error-inline" role="alert">{error}</p> : null}
      </Card>

      {result ? (
        <Card tone={blocked ? 'quiet' : 'elevated'} className="studio-delivery-result"
          testId="delivery-result">
          <header className="studio-tile-head">
            <Icon name={blocked ? 'warning' : 'complete'} size={20} />
            <h2>{blocked ? '交付被阻止' : '交付完成'}</h2>
            <StatusBadge status={result.status} testId="delivery-status" />
          </header>

          {blocked ? (
            <div>
              <p>{result.validation?.blocking_reason
                || result.post_validation?.blocking_reason
                || '存在阻止交付的问题。'}</p>
              <ul className="studio-blockers">
                {(result.validation?.issues ?? []).map((issue) => (
                  <li key={issue.code}>
                    <Icon name="warning" size={15} />
                    <span>{issue.message}</span>
                    <span className="studio-code">{issue.code}</span>
                  </li>
                ))}
              </ul>
              <p className="studio-muted">
                {mapError({ detail: { code: (result.validation?.issues ?? [])[0]?.code } })
                  .message}
              </p>
            </div>
          ) : (
            <div>
              <p className="studio-meta">交付编号：{result.manifest?.snapshot_id
                || result.snapshot_id}</p>
              <ul className="studio-artifact-list">
                {(result.artifacts ?? []).map((artifact) => (
                  <li key={artifact.path} data-testid={`artifact-${artifact.format}`}>
                    <div>
                      <b>{artifact.filename}</b>
                      <p className="studio-meta">
                        {artifact.format.toUpperCase()} · {formatBytes(artifact.size)}
                      </p>
                    </div>
                    <a className="studio-download"
                      href={deliveryArtifactUrl(novelId,
                        result.manifest?.snapshot_id || result.snapshot_id || '',
                        artifact.path)}
                      download={artifact.filename}
                      data-testid={`download-${artifact.format}`}>
                      <Icon name="export" size={16} /> 下载
                    </a>
                  </li>
                ))}
              </ul>
              <Disclosure summary="高级详情（校验和与版本）">
                <ul className="studio-kv">
                  {(result.artifacts ?? []).map((artifact) => (
                    <li key={`sum-${artifact.path}`}>
                      <span>{artifact.filename}</span>
                      <b className="studio-code">{artifact.checksum.slice(0, 16)}…</b>
                    </li>
                  ))}
                  <li><span>导出器</span><b>
                    {(result.artifacts ?? []).map((row) => row.exporter_id).join('、')}
                  </b></li>
                </ul>
              </Disclosure>
            </div>
          )}
        </Card>
      ) : null}

      <section className="studio-workspace">
        <h2 className="studio-h2">交付历史（{snapshots.length}）</h2>
        {snapshots.length === 0 ? (
          <p className="studio-muted">还没有交付记录。</p>
        ) : (
          <ul className="studio-snapshot-list">
            {snapshots.map((row) => (
              <li key={row.snapshot_id} className="studio-snapshot-row">
                <span className="studio-code">{row.snapshot_id}</span>
                <span>{row.formats?.join(' / ') || ''}</span>
                <span className="studio-meta">{formatTime(row.created_at)}</span>
                <StatusBadge status="delivered" />
              </li>
            ))}
          </ul>
        )}
      </section>
    </section>
  )
}

function formatBytes(size: number): string {
  if (!size) return '0 B'
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / 1024 / 1024).toFixed(2)} MB`
}

function formatTime(value?: string): string {
  if (!value) return ''
  const text = String(value)
  const match = text.match(/^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2})/)
  return match ? `${match[1]} ${match[2]}` : text
}
