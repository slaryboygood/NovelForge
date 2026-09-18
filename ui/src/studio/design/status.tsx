/*
 * UI_STATUS_MAP —— 状态语义唯一来源（`docs/v4/V4_UI_CONTRACT.md` §4）。
 *
 * 规则：
 *   · 同一状态在任何页面使用同一图标 + 文案 + 色调 + 形状；
 *   · 颜色不是唯一信号（始终带图标与文案）；
 *   · 未登记的状态原样显示（不猜、不翻译成 PASS/FAIL）。
 */
import { Badge } from '../../v3/design-system/primitives'
import Icon from '../../v3/design-system/icons/IconRegistry'

export type StatusTone = 'neutral' | 'primary' | 'progress' | 'success'
  | 'warning' | 'danger' | 'muted'

export interface StatusSpec {
  label: string
  icon: string
  tone: StatusTone
  shape: 'solid' | 'outline' | 'dashed' | 'stripe'
}

export const UI_STATUS_MAP: Record<string, StatusSpec> = {
  /* Blueprint 节点状态 */
  proposed: { label: 'AI 建议（待接受）', icon: 'creation', tone: 'primary', shape: 'dashed' },
  draft: { label: '草稿', icon: 'outline', tone: 'neutral', shape: 'outline' },
  accepted: { label: '已接受', icon: 'complete', tone: 'success', shape: 'solid' },
  superseded: { label: '已被取代', icon: 'back', tone: 'muted', shape: 'stripe' },
  /* 质量状态 */
  unevaluated: { label: '尚未检查', icon: 'current', tone: 'muted', shape: 'outline' },
  passed: { label: '检查通过', icon: 'complete', tone: 'success', shape: 'solid' },
  failed: { label: '未通过', icon: 'warning', tone: 'warning', shape: 'outline' },
  blocked: { label: '被阻止', icon: 'warning', tone: 'danger', shape: 'solid' },
  evaluating: { label: '检查中…', icon: 'progress', tone: 'progress', shape: 'outline' },
  skipped: { label: '已跳过', icon: 'more', tone: 'muted', shape: 'stripe' },
  needs_human_review: { label: '需要作者决定', icon: 'conflict', tone: 'warning',
    shape: 'solid' },
  /* 评审 */
  review_accepted: { label: '已评审接受', icon: 'complete', tone: 'success',
    shape: 'outline' },
  review_rejected: { label: '已评审拒绝', icon: 'close', tone: 'danger', shape: 'outline' },
  pending: { label: '待评审', icon: 'current', tone: 'muted', shape: 'outline' },
  /* setup / payoff */
  open: { label: '未回收', icon: 'foreshadow', tone: 'primary', shape: 'outline' },
  partially_paid: { label: '部分回收', icon: 'foreshadow', tone: 'warning',
    shape: 'outline' },
  paid: { label: '已回收', icon: 'complete', tone: 'success', shape: 'solid' },
  planned: { label: '已计划', icon: 'foreshadow', tone: 'primary', shape: 'outline' },
  abandoned: { label: '已放弃', icon: 'close', tone: 'muted', shape: 'stripe' },
  /* 交付 */
  delivered: { label: '已交付', icon: 'export', tone: 'success', shape: 'solid' },
  dry_run: { label: '预演（未发布）', icon: 'foreshadow', tone: 'primary', shape: 'dashed' },
  partial: { label: '部分交付', icon: 'warning', tone: 'warning', shape: 'outline' },
  /* 修复闭环 */
  repaired: { label: '已修复（待复核）', icon: 'repair', tone: 'progress', shape: 'outline' },
  resolved: { label: '已解决', icon: 'complete', tone: 'success', shape: 'solid' },
  unresolved: { label: '未解决', icon: 'warning', tone: 'warning', shape: 'outline' },
  regressed: { label: '出现回归', icon: 'warning', tone: 'danger', shape: 'solid' },
  needs_author_decision: { label: '需要作者决定', icon: 'conflict', tone: 'warning',
    shape: 'solid' },
  /* 插件 */
  disabled: { label: '已停用', icon: 'locked', tone: 'muted', shape: 'stripe' },
  failed_plugin: { label: '加载失败', icon: 'warning', tone: 'danger', shape: 'solid' },
  incompatible: { label: '与当前版本不兼容', icon: 'warning', tone: 'warning',
    shape: 'outline' },
  active: { label: '运行中', icon: 'complete', tone: 'success', shape: 'solid' },
  loaded: { label: '已加载', icon: 'complete', tone: 'success', shape: 'outline' },
  approved: { label: '已批准', icon: 'complete', tone: 'progress', shape: 'outline' },
  enabled: { label: '已启用', icon: 'current', tone: 'progress', shape: 'outline' },
  compatible: { label: '兼容', icon: 'complete', tone: 'neutral', shape: 'outline' },
  discovered: { label: '已发现（未批准）', icon: 'search', tone: 'muted',
    shape: 'dashed' },
  /* 通用 */
  ask: { label: '需要补充', icon: 'objective', tone: 'primary', shape: 'outline' },
}

const BADGE_TONES: Record<StatusTone, 'neutral' | 'primary' | 'progress' | 'success'
  | 'warning' | 'danger'> = {
  neutral: 'neutral', primary: 'primary', progress: 'progress', success: 'success',
  warning: 'warning', danger: 'danger', muted: 'neutral',
}

/** 未知状态：原样显示字符串（不猜测成 PASS/FAIL，§4）。 */
export function statusSpec(status: string): StatusSpec {
  const key = String(status || '').trim()
  const found = UI_STATUS_MAP[key]
  if (found) return found
  if (!key) return UI_STATUS_MAP.ask
  return { label: key, icon: 'ask', tone: 'neutral', shape: 'outline' }
}

export function statusLabel(status: string): string {
  return statusSpec(status).label
}

/** editor review decision → UI 状态 key。 */
export function reviewStatusKey(decision: string): string {
  const value = String(decision || '').toLowerCase()
  if (value === 'accepted') return 'review_accepted'
  if (value === 'rejected') return 'review_rejected'
  return 'pending'
}

export function pluginStatusKey(row: { status?: string }): string {
  const status = String(row.status || '')
  if (status === 'failed') return 'failed_plugin'
  return status || 'discovered'
}

export function StatusBadge({ status, testId }: { status: string; testId?: string }) {
  const spec = statusSpec(status)
  return (
    <Badge tone={BADGE_TONES[spec.tone]} icon={spec.icon} testId={testId}>
      {spec.label}
    </Badge>
  )
}

/** 形状/边框提示（配合 Badge 使用；颜色不是唯一信号）。 */
export function StatusShape({ status }: { status: string }) {
  const spec = statusSpec(status)
  return <span className={`studio-status-shape shape-${spec.shape}`}
    data-testid={`status-shape-${status}`} aria-hidden="true" />
}

/** 质量 / 节点状态图标（表格或紧凑列表用）。 */
export function StatusIcon({ status, size = 16 }: { status: string; size?: number }) {
  const spec = statusSpec(status)
  return <Icon name={spec.icon} size={size} title={spec.label} />
}
