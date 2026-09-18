/*
 * Story Studio 共享组件（卡片 / 抽屉 / Diff / issue / 冲突 / 通知）。
 *
 * 复用 V3 Design System（tokens + Icon + primitives），不新建第二套主题（§70）。
 * 这里只做展示与交互编排，**不做业务判断**（§2）。
 */
import { useEffect, useRef, useState, type ReactNode } from 'react'
import Icon from '../v3/design-system/icons/IconRegistry'
import {
  Button, Card, Disclosure, EmptyState, ErrorState, LoadingState, SectionHeading,
} from '../v3/design-system/primitives'
import {
  displayValue, fieldLabel, nodeTitle, nodeTypeIcon, nodeTypeLabel, storyFunctionLabel,
} from './design/fields'
import { StatusBadge, StatusIcon, reviewStatusKey } from './design/status'
import type { DiffDto, QualityIssueRow, StudioNode } from '../api/studio'

/* ------------------------------------------------------------------- 容器 */

export function StudioSection({ icon, title, hint, action, children, testId }: {
  icon?: string
  title: string
  hint?: string
  action?: ReactNode
  children: ReactNode
  testId?: string
}) {
  return (
    <section className="studio-section" data-testid={testId}>
      <SectionHeading icon={icon} title={title} hint={hint} action={action} />
      {children}
    </section>
  )
}

export function StudioPanel({ state, onRetry, empty, emptyTitle, emptyReason,
  emptyIcon = 'creation', emptyAction, children }: {
  state: { loading: boolean; error: string }
  onRetry?: () => void
  empty?: boolean
  emptyTitle?: string
  emptyReason?: string
  emptyIcon?: string
  emptyAction?: ReactNode
  children: ReactNode
}) {
  if (state.loading) return <LoadingState label="正在读取…" />
  if (state.error) return <ErrorState message={state.error} onRetry={onRetry} />
  if (empty) {
    return <EmptyState icon={emptyIcon} title={emptyTitle ?? '这里还是空的'}
      reason={emptyReason ?? '还没有内容'} action={emptyAction} />
  }
  return <>{children}</>
}

/* ------------------------------------------------------------------- 卡片 */

export function NodeCard({ node, onOpen, selected = false, badgeStatus, extra }: {
  node: StudioNode
  onOpen?: () => void
  selected?: boolean
  badgeStatus?: string
  extra?: ReactNode
}) {
  const icon = nodeTypeIcon(node.node_type)
  const fields = collectCardFields(node)
  const functions = (node.visible?.story_function ?? node.payload?.story_function
    ?? []) as unknown[]
  const review = String(node.review_status || '')
  return (
    <Card as="article" tone="elevated" selected={selected} onClick={onOpen}
      testId={`node-card-${node.node_id}`} className="studio-node-card">
      <header className="studio-card-head">
        <span className="studio-card-icon"><Icon name={icon} size={22} /></span>
        <div className="studio-card-title">
          <h3>{nodeTitle(node)}</h3>
          <p>
            <span className="studio-card-type">{nodeTypeLabel(node.node_type)}</span>
            <span className="studio-meta">· 版本 r{node.revision}</span>
          </p>
        </div>
        <StatusBadge status={badgeStatus || String(node.status)} />
      </header>

      {node.node_type === 'scene' && functions.length > 0 ? (
        <p className="studio-scene-function" data-testid="scene-function">
          <Icon name="objective" size={15} />
          这场戏的作用：{functions.map((row) => storyFunctionLabel(String(row)))
            .join('、')}
        </p>
      ) : null}

      <dl className="studio-card-fields">
        {fields.map(([key, value]) => (
          <div key={key} className="studio-card-field">
            <dt>{fieldLabel(node.node_type, key)}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>

      {review ? (
        <p className="studio-card-foot">
          <StatusBadge status={reviewStatusKey(review)} />
        </p>
      ) : null}
      {extra}
    </Card>
  )
}

function collectCardFields(node: StudioNode): [string, string][] {
  const data = { ...(node.payload ?? {}), ...(node.visible ?? {}) }
  const preferred = ['title', 'name', 'goal', 'conflict', 'turn', 'outcome', 'hook',
    'scene_purpose', 'next_hook', 'premise', 'central_conflict', 'status', 'relation',
    'source_node', 'target_node', 'content', 'result']
  const rows: [string, string][] = []
  for (const key of preferred) {
    const value = displayValue(data[key])
    if (value && rows.length < 4 && !['title', 'name'].includes(key)) {
      rows.push([key, value])
    }
  }
  return rows
}

/* ------------------------------------------------------------------ 抽屉 */

export function Drawer({ open, title, subtitle, onClose, footer, children, testId }: {
  open: boolean
  title: string
  subtitle?: string
  onClose: () => void
  footer?: ReactNode
  children: ReactNode
  testId?: string
}) {
  const ref = useRef<HTMLDivElement | null>(null)
  const opener = useRef<Element | null>(null)

  useEffect(() => {
    if (!open) return undefined
    opener.current = document.activeElement
    ref.current?.focus()
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('keydown', onKey)
      ;(opener.current as HTMLElement | null)?.focus?.()
    }
  }, [open, onClose])

  if (!open) return null
  return (
    <div className="studio-drawer-scrim" onClick={onClose} data-testid={testId}>
      <aside className="studio-drawer" role="dialog" aria-modal="true"
        aria-label={title} tabIndex={-1} ref={ref}
        onClick={(event) => event.stopPropagation()}>
        <header className="studio-drawer-head">
          <div>
            <h2>{title}</h2>
            {subtitle ? <p>{subtitle}</p> : null}
          </div>
          <button type="button" className="studio-icon-button" aria-label="关闭面板"
            onClick={onClose} data-testid="drawer-close">
            <Icon name="close" size={18} />
          </button>
        </header>
        <div className="studio-drawer-body">{children}</div>
        {footer ? <footer className="studio-drawer-foot">{footer}</footer> : null}
      </aside>
    </div>
  )
}

export function ConfirmDialog({ open, title, body, confirmLabel, onConfirm, onCancel }: {
  open: boolean
  title: string
  body: string
  confirmLabel: string
  onConfirm: () => void
  onCancel: () => void
}) {
  useEffect(() => {
    if (!open) return undefined
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onCancel()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onCancel])
  if (!open) return null
  return (
    <div className="studio-drawer-scrim" onClick={onCancel} data-testid="confirm-dialog">
      <div className="studio-dialog" role="dialog" aria-modal="true" aria-label={title}
        onClick={(event) => event.stopPropagation()}>
        <h2>{title}</h2>
        <p>{body}</p>
        <div className="studio-dialog-actions">
          <Button variant="secondary" onClick={onCancel}>取消</Button>
          <Button variant="primary" onClick={onConfirm} testId="confirm-accept">
            {confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  )
}

/* -------------------------------------------------------------------- Diff */

export function DiffView({ diff, testId = 'diff-view' }: { diff: DiffDto | null
  testId?: string }) {
  if (!diff) return <p className="studio-muted">没有可显示的差异。</p>
  const changes = diff.field_changes ?? []
  if (changes.length === 0) {
    return <p className="studio-muted" data-testid={`${testId}-empty`}>
      这两次版本的内容没有差别（可能只是状态变化）。
    </p>
  }
  return (
    <div className="studio-diff" data-testid={testId}>
      <p className="studio-muted">
        版本 r{diff.revision_before} → r{diff.revision_after}：共 {changes.length} 处改动
      </p>
      {changes.map((row) => (
        <div key={row.field} className="studio-diff-row" data-testid={`diff-${row.field}`}>
          <h4>{fieldLabel('', row.field) === row.field ? row.field
            : fieldLabel('', row.field)}</h4>
          <div className="studio-diff-pair">
            <div className="studio-diff-side before">
              <span>修改前</span>
              <p>{displayValue(row.before) || '（空）'}</p>
            </div>
            <div className="studio-diff-side after">
              <span>修改后</span>
              <p>{displayValue(row.after) || '（空）'}</p>
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}

/* ----------------------------------------------------------------- 质量 */

export function IssueCard({ issue, onOpen, testId }: {
  issue: QualityIssueRow
  onOpen?: () => void
  testId?: string
}) {
  const nodeIds = issue.scope?.node_ids ?? []
  return (
    <Card as="article" tone="elevated" onClick={onOpen}
      testId={testId ?? `issue-${issue.issue_id}`} className="studio-issue-card">
      <header className="studio-issue-head">
        <span className="studio-issue-severity">
          <Icon name={issue.severity === 'blocker' ? 'warning' : 'conflict'} size={18} />
          {SEVERITY_LABELS[issue.severity] ?? issue.severity}
        </span>
        <StatusBadge status={issue.status} />
      </header>
      <h3>{issueHumanLabel(issue.code)}</h3>
      <p className="studio-issue-reason">{issue.reason}</p>
      <p className="studio-issue-meta">
        <span className="studio-chip">{issue.gate}</span>
        {nodeIds.length > 0 ? (
          <span className="studio-meta">影响 {nodeIds.length} 个节点</span>
        ) : null}
        <span className="studio-code" title="诊断用">诊断码 {issue.code}</span>
      </p>
    </Card>
  )
}

export const SEVERITY_LABELS: Record<string, string> = {
  info: '提示',
  minor: '次要',
  major: '重要',
  blocker: '必须处理',
}

/** issue code → 作者语言（找不到时回退为 code 本身，不编造语义）。 */
export const ISSUE_LABELS: Record<string, string> = {
  CANON_CONTRADICTION: '与既有设定冲突',
  CAUSAL_GAP: '因果断裂',
  CHARACTER_MOTIVATION_GAP: '人物动机断裂',
  CHARACTER_ARC_INCONSISTENT: '人物弧不一致',
  CONTINUITY_CONFLICT: '前后不一致',
  BLUEPRINT_VAGUE_CONTENT: '内容过于笼统',
  BLUEPRINT_FIELD_LABEL_TEXT: '内容里混入了字段名',
  BLUEPRINT_PLACEHOLDER_TEXT: '内容里还有占位文字',
  BLUEPRINT_TITLE_TOO_SIMILAR: '标题太相似',
  MISSING_REQUIRED_NODE: '缺少必需的结构节点',
  ORPHAN_NODE: '有节点没有归属',
  REFERENCE_BROKEN: '引用指向了不存在的内容',
  SETUP_PAYOFF_DISTRIBUTION_SKEW: '伏笔与回收分布失衡',
  PACING_STAGNATION: '节奏停滞',
  CRISIS_UNRESOLVED: '危机没有解决',
  DELIVERY_MISSING_REQUIRED_NODE: '交付前发现结构不完整',
  DELIVERY_UNPAID_REQUIRED_SETUP: '有必回收的伏笔未回收',
  DELIVERY_QUALITY_STALE: '质量结论过期',
}

export function issueHumanLabel(code: string): string {
  return ISSUE_LABELS[code] ?? code
}

/* --------------------------------------------------------------- 通知 */

export type ToastTone = 'success' | 'warning' | 'error' | 'info'

export interface ToastRow {
  id: string
  tone: ToastTone
  message: string
}

export function ToastStack({ rows, onDismiss }: {
  rows: ToastRow[]
  onDismiss: (id: string) => void
}) {
  if (rows.length === 0) return null
  return (
    <div className="studio-toasts" role="status" aria-live="polite"
      data-testid="studio-toasts">
      {rows.map((row) => (
        <div key={row.id} className={`studio-toast tone-${row.tone}`}
          data-testid={`toast-${row.tone}`}>
          <Icon name={row.tone === 'error' ? 'warning'
            : row.tone === 'warning' ? 'warning'
              : row.tone === 'success' ? 'complete' : 'bell'} size={16} />
          <span>{row.message}</span>
          <button type="button" aria-label="关闭提示" onClick={() => onDismiss(row.id)}>
            <Icon name="close" size={14} />
          </button>
        </div>
      ))}
    </div>
  )
}

export function useToasts() {
  const [rows, setRows] = useState<ToastRow[]>([])
  const push = (tone: ToastTone, message: string) => {
    const id = `${Date.now()}-${Math.random().toString(16).slice(2, 8)}`
    setRows((current) => [...current, { id, tone, message }].slice(-4))
  }
  const dismiss = (id: string) => setRows((current) => current.filter((row) => row.id !== id))
  return { rows, push, dismiss }
}

/* ------------------------------------------------------------- 长操作面板 */

export function OperationPanel({ open, label, detail, onClose }: {
  open: boolean
  label: string
  detail?: string
  onClose: () => void
}) {
  if (!open) return null
  return (
    <div className="studio-operation" role="status" data-testid="studio-operation">
      <span className="studio-loading-dot" />
      <div>
        <b>{label}</b>
        <p>{detail ?? '正在处理…可以关闭这个面板，但请求会继续执行。'}</p>
      </div>
      <Button variant="ghost" size="sm" onClick={onClose}>关闭面板</Button>
    </div>
  )
}

export function StatusLegend({ statuses }: { statuses: string[] }) {
  return (
    <ul className="studio-legend" data-testid="status-legend">
      {statuses.map((status) => (
        <li key={status}><StatusIcon status={status} /><span>
          <StatusBadge status={status} />
        </span></li>
      ))}
    </ul>
  )
}

export { Disclosure }
