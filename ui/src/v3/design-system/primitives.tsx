/*
 * NovelForge V3 基础组件（Card / Button / Progress / Badge / EmptyState / ...）。
 *
 * 规则：
 * - 卡片、按钮、进度条、徽标只在这里定义一次，页面不得自行实现；
 * - 层级由 `tone` 表达，不使用颜色以外的唯一状态信号（始终带文字或图形）；
 * - 所有交互元素都有可见焦点与 aria 语义。
 */
import type { ButtonHTMLAttributes, ReactNode } from 'react'
import Icon from './icons/IconRegistry'
import { resolveEmptyArtwork, type EmptyArtworkKind } from './assets/artworkManifest'

/* -------------------------------------------------------------------- Card */
export function Card({ children, className = '', selected = false, tone = 'default',
  testId, as = 'section', onClick }: {
  children: ReactNode
  className?: string
  selected?: boolean
  tone?: 'default' | 'elevated' | 'quiet'
  testId?: string
  as?: 'section' | 'article' | 'div' | 'li'
  onClick?: () => void
}) {
  const Element = as
  const classes = ['v3-card', `v3-card-${tone}`, selected ? 'is-selected' : '',
    onClick ? 'is-clickable' : '', className].filter(Boolean).join(' ')
  if (onClick) {
    return <Element className={classes} data-testid={testId}>
      <button type="button" className="v3-card-hit" onClick={onClick}>{children}</button>
    </Element>
  }
  return <Element className={classes} data-testid={testId}>{children}</Element>
}

/* ------------------------------------------------------------------ Button */
type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger'
  icon?: string
  iconAfter?: string
  size?: 'md' | 'sm'
  testId?: string
}

export function Button({ variant = 'secondary', icon, iconAfter, size = 'md',
  children, className = '', testId, ...rest }: ButtonProps) {
  return (
    <button
      {...rest}
      data-testid={testId}
      className={['v3-btn', `v3-btn-${variant}`, `v3-btn-${size}`, className]
        .filter(Boolean).join(' ')}
    >
      {icon ? <Icon name={icon} size={size === 'sm' ? 16 : 18} /> : null}
      <span className="v3-btn-label">{children}</span>
      {iconAfter ? <Icon name={iconAfter} size={size === 'sm' ? 16 : 18} /> : null}
    </button>
  )
}

export function IconButton({ icon, label, onClick, variant = 'ghost', testId, count = 0 }: {
  icon: string
  label: string
  onClick?: () => void
  variant?: 'ghost' | 'secondary'
  testId?: string
  /** 有数量时显示计数徽标（例如需要留意的问题数）。0 表示不显示。 */
  count?: number
}) {
  return (
    <button type="button" className={`v3-icon-btn v3-icon-btn-${variant}`}
      aria-label={label} title={label} onClick={onClick} data-testid={testId}>
      <Icon name={icon} size={18} />
      {count > 0 ? <span className="v3-icon-btn-count" aria-hidden="true">{count}</span> : null}
    </button>
  )
}

/* ---------------------------------------------------------------- Progress */
export function ProgressBar({ percent, label, tone = 'progress', showValue = true,
  compact = false, testId }: {
  percent: number
  label?: string
  tone?: 'progress' | 'primary' | 'warning' | 'danger'
  showValue?: boolean
  compact?: boolean
  testId?: string
}) {
  const value = Math.max(0, Math.min(100, Math.round(percent)))
  return (
    <div className={`v3-progress ${compact ? 'is-compact' : ''}`} data-testid={testId}>
      {(label || showValue) && <div className="v3-progress-head">
        {label ? <span className="v3-progress-label">{label}</span> : <span />}
        {showValue ? <span className="v3-progress-value">{value}%</span> : null}
      </div>}
      <div className="v3-progress-track" role="progressbar" aria-valuenow={value}
        aria-valuemin={0} aria-valuemax={100} aria-label={label || '进度'}>
        <span className={`v3-progress-fill tone-${tone}`} style={{ width: `${value}%` }} />
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------- Badge */
export function Badge({ children, tone = 'neutral', icon, testId }: {
  children: ReactNode
  tone?: 'neutral' | 'primary' | 'progress' | 'success' | 'warning' | 'danger'
  icon?: string
  testId?: string
}) {
  return (
    <span className={`v3-badge v3-badge-${tone}`} data-testid={testId}>
      {icon ? <Icon name={icon} size={14} /> : null}
      {children}
    </span>
  )
}

/* -------------------------------------------------------- Section heading */
export function SectionHeading({ icon, title, hint, action }: {
  icon?: string
  title: string
  hint?: string
  action?: ReactNode
}) {
  return (
    <div className="v3-section-head">
      <div className="v3-section-title">
        {icon ? <Icon name={icon} size={18} /> : null}
        <h2>{title}</h2>
        {hint ? <p>{hint}</p> : null}
      </div>
      {action}
    </div>
  )
}

/* --------------------------------------------------------------- EmptyState */
export function EmptyState({ icon = 'creation', artwork, title, reason, value, action }: {
  icon?: string
  /** 空态语义：真实插画就位后由 Artwork Manifest 解析，否则退回语义图标。 */
  artwork?: EmptyArtworkKind
  title: string
  reason: string
  value?: string
  action?: ReactNode
}) {
  const artworkUrl = artwork ? resolveEmptyArtwork(artwork) : ''
  return (
    <div className="v3-empty" data-testid="v3-empty-state">
      {artworkUrl ? (
        <span className="v3-empty-art" data-testid="v3-empty-art">
          <img src={artworkUrl} alt="" />
        </span>
      ) : (
        <span className="v3-empty-icon"><Icon name={icon} size={26} /></span>
      )}
      <h3>{title}</h3>
      <p>{reason}</p>
      {value ? <p className="v3-empty-value">{value}</p> : null}
      {action}
    </div>
  )
}

/* ------------------------------------------------------------------ Loading */
export function LoadingState({ label = '正在读取…' }: { label?: string }) {
  return (
    <div className="v3-loading" role="status" data-testid="v3-loading">
      <span className="v3-loading-dot" />
      <span>{label}</span>
    </div>
  )
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="v3-error" role="alert" data-testid="v3-error">
      <Icon name="warning" size={20} />
      <div>
        <b>暂时读不到这一步</b>
        <p>{message}</p>
      </div>
      {onRetry ? <Button variant="secondary" size="sm" onClick={onRetry}>重新读取</Button> : null}
    </div>
  )
}

/* ------------------------------------------------------------------ Checkbox */
export function CheckItem({ label, done, optional = false }: {
  label: string
  done: boolean
  optional?: boolean
}) {
  return (
    <li className={`v3-check ${done ? 'is-done' : ''}`}>
      <span className="v3-check-mark" aria-hidden="true">
        {done ? <Icon name="complete" size={16} /> : <span className="v3-check-empty" />}
      </span>
      <span className="v3-check-label">{label}</span>
      {optional && !done ? <em>可选</em> : null}
      <span className="v3-sr-only">{done ? '已完成' : '未完成'}</span>
    </li>
  )
}

/* -------------------------------------------------------------- Disclosure */
export function Disclosure({ summary, children, testId, open }: {
  summary: string
  children: ReactNode
  testId?: string
  open?: boolean
}) {
  return (
    <details className="v3-disclosure" data-testid={testId}
      {...(open === undefined ? {} : { open })}>
      <summary>{summary}</summary>
      <div className="v3-disclosure-body">{children}</div>
    </details>
  )
}
